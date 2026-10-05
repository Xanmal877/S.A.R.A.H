#!/usr/bin/env python3
"""One-time, idempotent cleanup of the legacy identity-state goal wall.

Background (measured 2026-10-05 on the live tree): the legacy
``identity_state.json`` goal list had accumulated 276 rows with only 6 distinct
titles - 68x "Ship phase 1", 46x each of three test-pollution strings, and 114
rows already marked done - because ``IdentityState.add_goal`` appended blindly
on every call. The explicit, versioned goal store (``goals.json``) is the real
goal authority and had never been written in production, so context assembly
fell back to that wall. Sarah's own reflection journal flagged it: "an
unreadable wall of dozens of duplicated 'Ship phase 1' rows buried under legacy
entries."

What this script does - mechanically, with a backup, inventing no semantics:

  1. Backs the identity file up to ``identity_state.json.pre-goal-migration-<ts>``.
  2. Collapses the legacy goal list to ONE canonical active row (dedup by title,
     one canonical title kept) and archives every other row to
     ``goals_legacy_archive.json`` (full history preserved, reversible).
  3. Creates that canonical goal in the explicit goal store so ``goals.json``
     finally exists and ``active_goals_summary()`` returns something real.
  4. Dedupes ``relationship_notes`` in place, archiving the churn.

Safety:
  * Never destructive: the original file is copied before any write, and
    ``--dry-run`` reports what would change without touching anything.
  * Idempotent: running it twice is a no-op. The canonical goal is only created
    when the explicit store has no live goal with that title, and the legacy
    list is only rewritten when it actually contains duplicates/extras.
  * Honors ``SARAH_STATE_DIR`` exactly like every other character store.

Usage:
    python3 scripts/migrate_legacy_goals.py                 # sarah, apply
    python3 scripts/migrate_legacy_goals.py --dry-run       # report only
    python3 scripts/migrate_legacy_goals.py --character tama
"""
import argparse
import json
import logging
import os
import shutil
import sys
from collections import Counter
from datetime import datetime

# Allow running straight from a checkout (`python3 scripts/migrate_...py`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.memory.json_file_store import state_dir  # noqa: E402
from modules.soul.goals import get_goal_store  # noqa: E402
from modules.soul.identity_state.identity_state import IdentityState  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("migrate_legacy_goals")

# The single goal that survives as the canonical explicit goal. Pinned to the
# success criterion Sarah herself articulated in her journal, so the loop can
# actually read its own done/not-done state.
CANONICAL_TITLE = "Ship phase 1"
CANONICAL_RATIONALE = "Canonical goal after the legacy goal-wall cleanup."
CANONICAL_NEXT_ACTION = "Verify a usable API credential is present, then run the smoke test."
CANONICAL_CRITERION = "key present AND smoke test passes"


def _backup(path: str, stamp: str) -> str:
    backup = f"{path}.pre-goal-migration-{stamp}"
    shutil.copy2(path, backup)
    return backup


def _legacy_goal_title(row) -> str:
    if isinstance(row, dict):
        return row.get("goal") or row.get("title") or ""
    return str(row)


def cleanup(character_id: str, dry_run: bool) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    identity_path = os.path.join(state_dir(character_id), "identity_state.json")
    goals_path = os.path.join(state_dir(character_id), "goals.json")
    archive_path = os.path.join(state_dir(character_id), "goals_legacy_archive.json")

    print(f"character      : {character_id}")
    print(f"identity file  : {identity_path}")
    print(f"explicit goals : {goals_path}")

    if not os.path.exists(identity_path):
        print("No identity_state.json - nothing to clean.")
        return 0

    identity = IdentityState(character_id=character_id)
    goal_store = get_goal_store(character_id)

    goals = list(identity.goals or [])
    notes = list(identity.relationship_notes or [])

    titles = Counter(_legacy_goal_title(g) for g in goals)
    note_texts = Counter(
        n.get("note") if isinstance(n, dict) else str(n) for n in notes
    )
    print(f"\nlegacy goals   : {len(goals)} rows, {len(titles)} distinct titles")
    for t, n in titles.most_common(8):
        print(f"    {n:4d}x {t!r}")
    print(f"notes          : {len(notes)} rows, {len(note_texts)} distinct")

    # ---- plan the legacy goal collapse -------------------------------------
    # Index of the single legacy row that survives (the first one whose title
    # matches the canonical title). If none matches, the canonical row is
    # rebuilt from the first active legacy row with the title pinned - nothing
    # is invented, and when there are no goals at all nothing is kept.
    kept_idx = None
    for i, g in enumerate(goals):
        if _legacy_goal_title(g) == CANONICAL_TITLE:
            kept_idx = i
            break
    if kept_idx is None:
        for i, g in enumerate(goals):
            if isinstance(g, dict) and g.get("status") == "active":
                kept_idx = i
                break
    if kept_idx is not None and _legacy_goal_title(goals[kept_idx]) != CANONICAL_TITLE:
        goals[kept_idx] = dict(goals[kept_idx], goal=CANONICAL_TITLE)
    kept = [goals[kept_idx]] if kept_idx is not None else []
    archived = [g for i, g in enumerate(goals) if i != kept_idx]

    # ---- plan the note dedupe ---------------------------------------------
    seen_notes = set()
    kept_notes = []
    archived_notes = []
    for n in notes:
        text = n.get("note") if isinstance(n, dict) else str(n)
        if text in seen_notes:
            archived_notes.append(n)
            continue
        seen_notes.add(text)
        kept_notes.append(n)

    # ---- plan the explicit-goal creation ----------------------------------
    existing = None
    try:
        for g in goal_store.list_active():
            if g.get("title") == CANONICAL_TITLE:
                existing = g
                break
    except Exception as e:  # noqa: BLE001 - report, never guess
        logger.warning("Could not read explicit goal store: %s", e)

    print("\nplan:")
    print(f"  legacy goals   : {len(goals)} -> {len(kept)} kept, "
          f"{len(archived)} archived")
    print(f"  notes          : {len(notes)} -> {len(kept_notes)} kept, "
          f"{len(archived_notes)} archived")
    if existing is not None:
        print(f"  explicit goal  : already present ({existing['goal_id']}) - skip")
    else:
        print(f"  explicit goal  : create {CANONICAL_TITLE!r} "
              f"(criterion: {CANONICAL_CRITERION})")
    if not archived and not archived_notes and existing is not None:
        print("\nNothing to do (already clean).")
        return 0

    if dry_run:
        print("\n--dry-run: no files written.")
        return 0

    # ---- apply ------------------------------------------------------------
    backup = _backup(identity_path, stamp)
    print(f"\nbacked up identity file -> {backup}")

    if archived or archived_notes:
        archive_payload = {
            "archived_at": datetime.now().isoformat(),
            "character_id": character_id,
            "reason": "legacy identity-state goal wall + note churn cleanup",
            "goals": archived,
            "relationship_notes": archived_notes,
        }
        if os.path.exists(archive_path):
            try:
                with open(archive_path, "r") as f:
                    prior = json.load(f)
            except (OSError, json.JSONDecodeError):
                prior = {}
            merged = prior.get("goals", []) + archive_payload["goals"]
            merged_notes = prior.get("relationship_notes", []) + archive_payload["relationship_notes"]
            archive_payload["goals"] = merged
            archive_payload["relationship_notes"] = merged_notes
        with open(archive_path, "w") as f:
            json.dump(archive_payload, f, indent=2)
        print(f"archived -> {archive_path} "
              f"({len(archive_payload['goals'])} goals, "
              f"{len(archive_payload['relationship_notes'])} notes)")

        identity.goals = kept
        identity.relationship_notes = kept_notes
        identity._save()
        print(f"rewrote identity file: {len(kept)} goal row(s), "
              f"{len(kept_notes)} note(s)")

    if existing is None:
        gid = goal_store.create_goal(
            CANONICAL_TITLE,
            rationale=CANONICAL_RATIONALE,
            source="migration",
            priority=4,
            next_action=CANONICAL_NEXT_ACTION,
            status="active",
        )
        if gid:
            print(f"created explicit goal {gid}: {CANONICAL_TITLE!r}")
        else:
            print("WARNING: could not create the explicit goal.", file=sys.stderr)
            return 2

    print("\nDone. Verify with:")
    print(f"  python3 -c \"import sys; sys.path.insert(0,'.'); "
          f"from modules.soul.goals.goals import active_goals_summary; "
          f"print(active_goals_summary('{character_id}'))\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", default="sarah")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return cleanup(args.character, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
