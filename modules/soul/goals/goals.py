"""
Versioned, per-character persistent goal lifecycle.

A character (Sarah, Tama, Saki, ...) maintains an explicit, persistent set of
goals with a full lifecycle - proposed / active / blocked / awaiting_approval /
completed / abandoned - rather than the flat "active/done" list in
identity_state. Each goal lives under
~/.sarah/state/{character_id}/goals.json (honoring SARAH_STATE_DIR via
modules.memory.json_file_store.state_dir), is versioned so a later phase can
migrate without misreading old files, and keeps an append-only audit `history`
for every status/content/priority change instead of silently overwriting.

Goal layout (this is a sibling to identity_state / person_profiles):

  {
    "version": 1,
    "goals": {
      "<goal_id>": {
        "goal_id": "goal-...",            # stable id (tools reference goals by this)
        "title": str,
        "rationale": str,                 # why this goal exists
        "source": str,                   # provenance (who/what raised it; free text)
        "priority": int 1..5,            # bounded
        "status": one of proposed|active|blocked|awaiting_approval|completed|abandoned
        "created_at": str, "updated_at": str,
        "next_action": str,               # the concrete next step
        "blockers": [str],                # reasons it is currently blocked
        "completion_outcome": str,        # set when completed
        "person_id": str|None,            # optional; None = character-general
        "linked_episode_ids": [int],      # optional links into episodic memory
        "linked_fact_ids": [int],         # optional links into semantic memory
        "history": [{ at, action, field?, old?, new?, source? }]   # append-only audit
      }
    }
  }

Unknown versions fail closed (loaded as empty) rather than guessing at a shape
the code doesn't understand - same rule as person_profiles.

Model-visible rendering never leaks raw person/linked ids (see render_goals),
but goals are addressed by their stable `goal_id` handle so the tools stay
usable across turns.

The store is character-scoped: a goal a character writes is isolated from every
other character's goals. Person isolation for *callers* (active_person_id) is
enforced at the tool layer (modules/memory/goal_tools.py), not here, mirroring
how person profiles keep the write-authorization decision at the tool boundary.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from modules.memory.json_file_store import state_dir
from modules.soul.identity_state.identity_state import active_character_id

logger = logging.getLogger("GoalStore")

# Schema version for a goals file. Bump + add a migration (don't silently
# rewrite) if the on-disk shape ever changes.
GOALS_VERSION = 1

# Goal lifecycle states.
GOAL_STATUSES = (
    "proposed", "active", "blocked", "awaiting_approval", "completed", "abandoned",
)
# Statuses that count as "still in play" for the [ACTIVE GOALS] context section
# and list_active_goals() - i.e. everything except the terminal states.
NON_TERMINAL_STATUSES = ("proposed", "active", "blocked", "awaiting_approval")

# Priority is bounded to an int 1..5 (5 = highest). The bounds are enforced on
# write so stored priority always stays within range regardless of caller input.
PRIORITY_MIN = 1
PRIORITY_MAX = 5
PRIORITY_DEFAULT = 3

# Bound for context / model-visible goal recall.
ACTIVE_GOALS_LIMIT = 6


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _clamp_priority(value, default: int = PRIORITY_DEFAULT) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(PRIORITY_MIN, min(PRIORITY_MAX, v))


def _new_goal_id() -> str:
    """A short, stable, opaque id for a goal. Collision-resistant enough for a
    per-character store (8 hex chars); the store is per-character so ids never
    need to be globally unique across characters."""
    return f"goal-{uuid.uuid4().hex[:8]}"


class GoalStore:
    """Persistent, versioned goal store for a single character.

    Layout:
      { "version": 1,
        "goals": { "<goal_id>": { ...goal... } } }
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "goals.json"
        )
        self.storage_path = os.path.expanduser(self.storage_path)
        self._goals: dict = {}
        self._version = GOALS_VERSION
        self._load()

    # ── persistence ───────────────────────────────────────────────────
    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load goals from %s: %s", self.storage_path, e)
            return
        version = saved.get("version")
        if version != GOALS_VERSION:
            # Unknown/newer schema: fail closed rather than guess. A later
            # version's shape we haven't written yet might not round-trip
            # through this old store.
            logger.warning(
                "Goals at %s have unsupported version %r (expected %d); "
                "loading as empty. A migration would be needed - not guessed.",
                self.storage_path, version, GOALS_VERSION,
            )
            return
        self._goals = saved.get("goals", {}) or {}
        self._version = version

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Could not save goals to %s: %s", self.storage_path, e)

    # ── lifecycle ────────────────────────────────────────────────────
    def create_goal(self, title: str, *, rationale: str = "", source: str = "internal",
                    priority: int = PRIORITY_DEFAULT, next_action: str = "",
                    person_id: str = None, blocker: str = None,
                    linked_episode_ids=None, linked_fact_ids=None,
                    status: str = "proposed") -> Optional[str]:
        """Create a new goal and return its stable goal_id (or None on invalid
        input/storage failure). Status defaults to 'proposed'. Blocks are
        recorded via the first blocker entry when supplied."""
        title = (title or "").strip()
        if not title:
            logger.warning("Goal title must be non-empty; refusing to create.")
            return None
        status = status if status in GOAL_STATUSES else "proposed"
        gid = _new_goal_id()
        created = _now_iso()
        entry = {
            "goal_id": gid,
            "title": title,
            "rationale": rationale or "",
            "source": source or "internal",
            "priority": _clamp_priority(priority),
            "status": status,
            "created_at": created,
            "updated_at": created,
            "next_action": next_action or "",
            "blockers": [blocker] if blocker else [],
            "completion_outcome": "",
            "person_id": person_id or None,
            "linked_episode_ids": [int(i) for i in (linked_episode_ids or []) if i is not None],
            "linked_fact_ids": [int(i) for i in (linked_fact_ids or []) if i is not None],
            "history": [{
                "at": created,
                "action": "create",
                "new": {
                    "title": title,
                    "status": status,
                    "priority": _clamp_priority(priority),
                    "source": source or "internal",
                },
                "source": source or "internal",
            }],
        }
        self._goals[gid] = entry
        self._save()
        return gid

    def get_goal(self, goal_id: str) -> Optional[dict]:
        goal = self._goals.get(goal_id)
        return dict(goal) if goal is not None else None

    def update_goal(self, goal_id: str, *, title: str = None, rationale: str = None,
                    source: str = None, priority: int = None, next_action: str = None,
                    person_id: str = None, linked_episode_ids=None,
                    linked_fact_ids=None, audit_actor: str = None) -> Optional[dict]:
        """In-place content update of a live goal. Every changed field is
        appended to the goal's audit history (old -> new) rather than silently
        overwriting. Returns the updated goal (or None if the goal is missing/
        terminal/invalid)."""
        g = self._goals.get(goal_id)
        if g is None or g["status"] in ("completed", "abandoned"):
            return None
        now = _now_iso()
        changes = []
        if title is not None and title.strip() and title.strip() != g["title"]:
            changes.append(("title", g["title"], title.strip()))
            g["title"] = title.strip()
        if rationale is not None and rationale != g["rationale"]:
            changes.append(("rationale", g["rationale"], rationale))
            g["rationale"] = rationale
        if source is not None and source != g["source"]:
            changes.append(("source", g["source"], source))
            g["source"] = source
        if priority is not None:
            newp = _clamp_priority(priority)
            if newp != g["priority"]:
                changes.append(("priority", g["priority"], newp))
                g["priority"] = newp
        if next_action is not None and next_action != g["next_action"]:
            changes.append(("next_action", g["next_action"], next_action))
            g["next_action"] = next_action
        if person_id is not None and person_id != g.get("person_id"):
            changes.append(("person_id", g.get("person_id"), person_id or None))
            g["person_id"] = person_id or None
        if linked_episode_ids is not None:
            newids = [int(i) for i in linked_episode_ids if i is not None]
            if newids != g.get("linked_episode_ids", []):
                changes.append(("linked_episode_ids", g.get("linked_episode_ids", []), newids))
                g["linked_episode_ids"] = newids
        if linked_fact_ids is not None:
            newids = [int(i) for i in linked_fact_ids if i is not None]
            if newids != g.get("linked_fact_ids", []):
                changes.append(("linked_fact_ids", g.get("linked_fact_ids", []), newids))
                g["linked_fact_ids"] = newids
        if not changes:
            return dict(g)
        g["updated_at"] = now
        seen = set()
        unique_changes = []
        for field, old, new in changes:
            if field in seen:
                continue
            seen.add(field)
            unique_changes.append({"field": field, "old": old, "new": new})
        g["history"].append({
            "at": now,
            "action": "content",
            "changes": unique_changes,
            "source": audit_actor or g["source"],
        })
        self._save()
        return dict(g)

    # ── status transitions (each appends an audit entry) ─────────────
    def _transition(self, goal_id: str, new_status: str, *, note: str = "",
                    outcome: str = "", audit_actor: str = None,
                    allowed_from: tuple) -> Optional[dict]:
        g = self._goals.get(goal_id)
        if g is None:
            return None
        if g["status"] in ("completed", "abandoned"):
            return None
        if g["status"] not in allowed_from:
            return None
        old = g["status"]
        now = _now_iso()
        g["status"] = new_status
        g["updated_at"] = now
        if note:
            g["blockers"] = (g["blockers"] or []) + [note]
        if new_status == "completed" and outcome:
            g["completion_outcome"] = outcome
        elif new_status == "completed" and not outcome:
            g["completion_outcome"] = g["completion_outcome"] or note or "completed"
        g["history"].append({
            "at": now,
            "action": "status",
            "field": "status",
            "old": old,
            "new": new_status,
            "note": note or None,
            "source": audit_actor or g["source"],
        })
        self._save()
        return dict(g)

    def activate_goal(self, goal_id: str, audit_actor: str = None) -> Optional[dict]:
        """Move a proposed/blocked/awaiting_approval goal to active."""
        return self._transition(goal_id, "active", audit_actor=audit_actor,
                                allowed_from=("proposed", "blocked", "awaiting_approval"))

    def mark_blocked(self, goal_id: str, reason: str, audit_actor: str = None) -> Optional[dict]:
        """Block a live goal, recording the blocker reason (audited)."""
        if not (reason or "").strip():
            reason = "blocked"
        return self._transition(goal_id, "blocked", note=reason.strip(),
                                audit_actor=audit_actor,
                                allowed_from=("proposed", "active", "awaiting_approval"))

    def request_approval(self, goal_id: str, audit_actor: str = None) -> Optional[dict]:
        """Move a proposed/active/blocked goal to awaiting_approval."""
        return self._transition(goal_id, "awaiting_approval", audit_actor=audit_actor,
                                allowed_from=("proposed", "active", "blocked"))

    def complete_goal(self, goal_id: str, outcome: str = "", audit_actor: str = None) -> Optional[dict]:
        """Mark a live goal completed, recording its outcome."""
        return self._transition(goal_id, "completed", outcome=outcome,
                                audit_actor=audit_actor,
                                allowed_from=("proposed", "active", "blocked",
                                              "awaiting_approval"))

    def abandon_goal(self, goal_id: str, reason: str = "", audit_actor: str = None) -> Optional[dict]:
        """Mark a live goal abandoned (note is audited as a blocker reason)."""
        return self._transition(goal_id, "abandoned", note=reason or "abandoned",
                                audit_actor=audit_actor,
                                allowed_from=("proposed", "active", "blocked",
                                              "awaiting_approval"))

    # ── read / query ─────────────────────────────────────────────────
    def _ordered(self):
        # Ordered by priority desc, then oldest-first for ties (creation order).
        return sorted(
            self._goals.values(),
            key=lambda g: (-g.get("priority", PRIORITY_DEFAULT), g.get("created_at", "")),
        )

    def list_goals(self, *, status: str = None, person_id: str = None,
                   limit: int = None) -> list:
        """Return goal dicts for this character. `status` filters by exact
        status; `person_id` filters to that person's goals ONLY (None person
        goals are character-general and included unless person_id is given
        AND the caller boundary says otherwise - see note below)."""
        if limit is not None:
            limit = max(1, min(int(limit), 100))
        result = []
        for g in self._ordered():
            if status and g["status"] != status:
                continue
            if person_id and g.get("person_id") != person_id:
                continue
            result.append(dict(g))
            if limit is not None and len(result) >= limit:
                break
        return result

    def list_active(self, *, person_id: str = None, limit: int = ACTIVE_GOALS_LIMIT) -> list:
        """Goals still in play (proposed/active/blocked/awaiting_approval),
        excluding terminal (completed/abandoned) ones. When `person_id` is
        given, results are restricted to that person's goals; when None, all
        live goals are returned (caller scoping is applied at the tool layer)."""
        result = []
        for g in self._ordered():
            if g["status"] in ("completed", "abandoned"):
                continue
            if person_id and g.get("person_id") != person_id:
                continue
            result.append(dict(g))
            if limit is not None and len(result) >= limit:
                break
        return result

    def count(self, status: str = None) -> int:
        if status:
            return sum(1 for g in self._goals.values() if g.get("status") == status)
        return len(self._goals)

    # ── serialization ────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"version": self._version, "goals": self._goals}


# ── per-character registry + contextvar resolution (same as identity/person) ──
_goal_stores: dict[str, "GoalStore"] = {}


def get_goal_store(character_id: str = "sarah") -> "GoalStore":
    """Look up (or lazily create) the goal store for a character."""
    if character_id not in _goal_stores:
        _goal_stores[character_id] = GoalStore(character_id=character_id)
    return _goal_stores[character_id]


def _active_store() -> "GoalStore":
    """Resolve the store for whichever character's tool-call loop is running."""
    return get_goal_store(active_character_id.get())


def _clear_goal_store_cache():
    """Drop cached store instances (tests only). Each store pins a storage_path
    at construction; redirecting SARAH_STATE_DIR to a fresh temp dir requires
    invalidating the cache so a later case doesn't reuse a stale path."""
    _goal_stores.clear()


# ── model-visible rendering ─────────────────────────────────────────────
def _person_label(character_id: str, person_id: str) -> str:
    """Human/presentation label for a person, omitting the raw stable id (same
    rule as episodic/semantic/person renders). Uses the display name when a
    profile exists; otherwise emits nothing rather than leaking the raw id."""
    try:
        from modules.soul.person_profiles import get_person_profile_store
    except Exception:  # noqa: BLE001 - profiler store is optional for rendering
        return ""
    profile = get_person_profile_store(character_id).get_profile(person_id)
    if profile is None:
        return ""
    return profile.get("display_name") or ""


def _render_goal(character_id: str, goal: dict) -> str:
    """A single model-visible goal line.

    The stable goal_id is shown as the tool-reference handle (so the loop can
    mark/complet/abandon it in follow-up calls, exactly like episode '#N' in the
    episodic renderer). Raw *person* ids and raw *linked episode/fact* ids are
    never shown: the person is labeled by display name only (or not at all),
    and links are summarized by count.
    """
    gid = goal.get("goal_id")
    status = goal.get("status")
    title = goal.get("title")
    head = f"{gid} [{status}] {title}" if gid else f"[{status}] {title}"
    parts = [head, f"priority {goal.get('priority', PRIORITY_DEFAULT)}"]
    if goal.get("rationale"):
        parts.append(f"- {goal['rationale']}")
    pid = goal.get("person_id")
    if pid:
        label = _person_label(character_id, pid)
        if label:
            parts.append(f"about {label}")
    if goal.get("next_action"):
        parts.append(f"next: {goal['next_action']}")
    if goal.get("blockers"):
        parts.append(f"blocked by: {'; '.join(goal['blockers'])}")
    if goal.get("completion_outcome"):
        parts.append(f"outcome: {goal['completion_outcome']}")
    line = " · ".join(parts)
    links = []
    if goal.get("linked_episode_ids"):
        links.append(f"{len(goal['linked_episode_ids'])} episode(s)")
    if goal.get("linked_fact_ids"):
        links.append(f"{len(goal['linked_fact_ids'])} fact(s)")
    if links:
        line += f" [linked: {', '.join(links)}]"
    return "- " + line


def render_goals(character_id: str, goals: list) -> str:
    """Concise, bounded, model-visible rendering of goals without raw person or
    linked-entity ids."""
    if not goals:
        return ""
    return "\n".join(_render_goal(character_id, g) for g in goals)


def active_goals_summary(character_id: str, *, person_id: str = None,
                         limit: int = ACTIVE_GOALS_LIMIT) -> str:
    """A bounded summary of the store's live (non-terminal) goals for the given
    character/person scope, for the [ACTIVE GOALS] context section."""
    return render_goals(
        character_id,
        get_goal_store(character_id).list_active(person_id=person_id, limit=limit),
    )
