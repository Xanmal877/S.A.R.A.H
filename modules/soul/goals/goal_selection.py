"""
Deterministic drive-aware selection among a character's explicit persistent goals.

This is NOT an LLM planner and it never talks to a model. It is a small, purely
local, fully deterministic scoring + ranking function that picks the single goal
an autonomous observe-and-suggest turn should focus on.

  candidates = explicit non-terminal goals with status in {active, proposed}.
               blocked / awaiting_approval / completed / abandoned are all
               excluded from *actionable* selection (blocked & awaiting_approval
               are non-terminal but not actionable; completed/abandoned are
               terminal and dropped by list_active too).
  rank       = status        (active before proposed)
             > priority      (desc)
             > drive-fit     (desc)
             > recency       (most recently touched first)
             > goal_id       (final deterministic total-order tie-break)

The drive-fit score is TRANSPARENT: it is computed ONLY from the character's
available behavioral drives (modules.soul.mental_state.DrivesModule) and the
goal's own text (title + rationale + next_action), matched against a small set
of simple normalized keyword categories:

   explore/research     -> the explore drive
   social/communicate   -> the social drive
   rest/recover         -> the rest drive
   focus/work           -> the focus drive

fit = sum over categories of (category_matches / total_matches) * drive[category]

i.e. the proportion of the goal's keyword signal that falls into each drive
category, weighted by how strong that drive currently is. If the goal carries no
keyword signal at all, its fit is 0. There is no randomization anywhere:
selection is a pure function of (goals, drives), so identical inputs always
select the identical goal.

Selection NEVER creates, transitions, or mutates a goal. A drive cannot create
a goal here - this only *reads* the existing explicit store (get_goal_store),
scoped to the given character and optional person_id, mirroring how the tools
keep person isolation at the boundary.
"""

from datetime import datetime

from modules.soul.goals import get_goal_store
from modules.soul.goals.goals import PRIORITY_DEFAULT

# The only statuses a goal may have to be *actionable* (i.e. something we would
# steer an autonomous turn toward). The goal store allows a full lifecycle
# (proposed/active/blocked/awaiting_approval/completed/abandoned); here we only
# ever consider the two that represent unattended work the agent can drive.
ACTIONABLE_STATUSES = ("active", "proposed")
NON_ACTIONABLE_NON_TERMINAL = ("blocked", "awaiting_approval")

# Status ordering for ranking: smaller sorts first, so active always beats
# proposed.
STATUS_RANK = {"active": 0, "proposed": 1}

# Keyword categories -> drive name. Matching is simple lowercase substring
# matching over "title rationale next_action"; deliberately not stemming or
# fuzzy so the behavior is predictable and easy to reason about.
DRIVE_CATEGORIES = {
    "explore": {
        "drive": "explore",
        "keywords": (
            "explor", "research", "investigat", "discover", "learn", "study",
            "find", "search", "scout", "examine", "curios", "look into",
            "look at", "read about", "figure out", "probe",
        ),
    },
    "social": {
        "drive": "social",
        "keywords": (
            "social", "communicat", "talk", "message", "contact", "friend",
            "reach out", "share", "chat", "collaborat", "coordinat", "ask",
            "respond", "meet", "greet",
        ),
    },
    "rest": {
        "drive": "rest",
        "keywords": (
            "rest", "recover", "sleep", "recharge", "relax", "recuperate",
            "unwind", "calm", "decompres", "restore energy",
        ),
    },
    "focus": {
        "drive": "focus",
        "keywords": (
            "focus", "work", "write", "fix", "build", "code", "finish",
            "complete", "ship", "draft", "implement", "review", "plan",
            "refactor", "improve", "task", "deliver", "commit", "release",
        ),
    },
}


def _drive_value(drives, name: str) -> float:
    """Read one drive value (0..1) from a DrivesModule, a dict, or None,
    failing safe to 0.0 so a missing/unusual drive never breaks ranking."""
    if drives is None:
        return 0.0
    try:
        v = drives.get(name) if isinstance(drives, dict) else getattr(drives, name)
    except Exception:  # noqa: BLE001 - missing drive must not break selection
        return 0.0
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def _time_ordinal(iso_str) -> float:
    """ISO timestamp -> epoch seconds, for a lexicographically-safe descending
    sort of recency. Fails safe to 0.0 (i.e. treated as oldest) on unparsable
    input."""
    if not iso_str:
        return 0.0
    try:
        return datetime.fromisoformat(iso_str).timestamp()
    except ValueError:
        return 0.0


def drive_fit_for_goal(goal: dict, drives) -> dict:
    """Transparent drive-fit score for one goal given the current drives.

    Returns a dict with the overall `fit` (0..1), the raw `total_keyword_hits`,
    and a per-category breakdown so the reason for a score can be inspected:
    each category lists its drive, that drive's current value, the number of
    keyword hits, and the resulting contribution.
    """
    text = " ".join(
        str(x) for x in (
            goal.get("title"), goal.get("rationale"), goal.get("next_action"),
        ) if x
    ).lower()

    category_hits = {}
    for cat, spec in DRIVE_CATEGORIES.items():
        hits = 0
        for kw in spec["keywords"]:
            if kw in text:
                hits += 1
        category_hits[cat] = hits

    total = sum(category_hits.values())
    fit = 0.0
    categories = {}
    for cat, hits in category_hits.items():
        drive_name = DRIVE_CATEGORIES[cat]["drive"]
        drive_val = _drive_value(drives, drive_name)
        contribution = (hits / total) * drive_val if total > 0 else 0.0
        fit += contribution
        categories[cat] = {
            "drive": drive_name,
            "drive_value": round(drive_val, 4),
            "keyword_hits": hits,
            "contribution": round(contribution, 4),
        }
    return {
        "fit": round(fit, 4),
        "total_keyword_hits": total,
        "categories": categories,
    }


def _rank_key(item: dict) -> tuple:
    """Stable, fully deterministic ordering key for an actionable candidate.

    order: status (active first) -> priority desc -> drive-fit desc ->
    recency desc (updated_at, then created_at) -> goal_id asc.
    All components are primitives so the tuple ordering is total and reproducible.
    """
    return (
        STATUS_RANK.get(item["status"], 99),
        -item["priority"],
        -item["drive_fit"],
        -_time_ordinal(item["_updated_at"]),
        -_time_ordinal(item["_created_at"]),
        item["goal_id"],
    )


def _no_goal_reason(candidates: list) -> str:
    """A short, honest explanation when nothing is selected (maintains the
    no-goal / generic observe behavior)."""
    if not candidates:
        return (
            "No non-terminal explicit goals to select from; staying on the "
            "generic observe-and-suggest loop."
        )
    statuses = [g.get("status") for g in candidates]
    return (
        "No actionable explicit goal. Only non-terminal goals with status "
        f"active/proposed are selectable; this character's live goals are: "
        f"{', '.join(statuses)}."
    )


def select_goal(character_id: str = "sarah", *, drives=None, person_id=None) -> dict:
    """Deterministically select the single goal an autonomous turn should focus
    on, for a given character (optionally scoped to one person).

    Never mutates the store and never creates a goal - a drive only influences
    the ranking below, it cannot spawn a new goal.

    Returns a structured decision dict:
      {
        "selected": <scored goal> or None,
        "reason":   str,
        "candidate_count": int,
        "candidates": [ scored goals, best first ],
      }
    where each scored goal carries goal_id/title/status/priority, the
    drive_fit + its transparent breakdown, and the raw goal text fields.
    """
    store = get_goal_store(character_id)
    # list_active() already drops terminal (completed/abandoned). From the
    # remaining non-terminal set we further exclude blocked/awaiting_approval
    # because they are not actionable.
    non_terminal = store.list_active(person_id=person_id)
    actionable = [g for g in non_terminal if g.get("status") in ACTIONABLE_STATUSES]

    if not actionable:
        return {
            "selected": None,
            "reason": _no_goal_reason(non_terminal),
            "candidate_count": 0,
            "candidates": [],
        }

    scored = []
    for g in actionable:
        gid = g.get("goal_id", "")
        fit = drive_fit_for_goal(g, drives)
        scored.append({
            "goal_id": gid,
            "title": g.get("title", ""),
            "rationale": g.get("rationale", ""),
            "next_action": g.get("next_action", ""),
            "status": g.get("status", "proposed"),
            "priority": g.get("priority", PRIORITY_DEFAULT),
            "drive_fit": fit["fit"],
            "drive_fit_breakdown": fit,
            "_updated_at": g.get("updated_at", g.get("created_at", "")),
            "_created_at": g.get("created_at", ""),
        })

    scored.sort(key=_rank_key)
    top = scored[0]
    decision = {
        "selected": top,
        "reason": _explain(top),
        "candidate_count": len(actionable),
        "candidates": scored,
    }
    return decision


def _explain(item: dict) -> str:
    """A readable but precise reason for a selection, grounded in the same
    numbers used to rank."""
    b = item["drive_fit_breakdown"]
    drive_matches = ", ".join(
        f"{cat}(drive={c['drive']} = {c['drive_value']:.2f} -> {c['contribution']:.3f})"
        for cat, c in b["categories"].items()
        if c["keyword_hits"] > 0
    ) or "no drive keyword match (fit 0)"
    return (
        f"selected '{item['title']}' ({item['goal_id']}, {item['status']}, "
        f"priority {item['priority']}, drive-fit {item['drive_fit']:.3f}); "
        f"matched drives: {drive_matches}."
    )
