"""
Tool-level wrappers for the explicit goal lifecycle.

These are the *trusted-local* registry tools (registered in init_tools.py and
therefore available to the desktop daemon / CLI / voice). They deliberately are
NOT added to Discord's allowlist (discord/main.py DISCORD_ALLOWED_TOOLS): goal
writing from an externally-reachable, untrusted-input surface needs an
authorization design first - same reasoning as person profiles / episodic
memory.

Semantics are safe and explicit:
  * create_goal returns a stable goal_id handle the tools use thereafter.
  * list_active_goals is read-only and bounded.
  * mark blocked / request approval / complete / abandon are explicit
    transitions, each audited in the store.
  * update_goal edits live-goal content, appending an audit entry per change.

Caller identity binding: when the application has bound active_person_id (e.g.
Discord -> "discord:{author.id}", CLI/voice -> "local:operator"), the goal tools
refuse any attempt by the model to assign or reassign a goal to a different
person - a caller-bound request may only create person-scoped goals for the
active caller, and may never move an existing goal onto another person. With no
caller binding (a trusted autonomous system), the model may optionally supply a
person_id for a new goal.
"""

from modules.soul.goals import _active_store
from modules.soul.goals.goals import (
    ACTIVE_GOALS_LIMIT,
    render_goals,
)
from modules.soul.identity_state.identity_state import active_person_id


def _resolve_person(person_id: str = None):
    """Apply the caller-identity boundary: when active_person_id is bound by the
    trusted application, the model cannot assign a goal to a different person.

    Returns (person_id, error_or_None).
    """
    active_person = active_person_id.get()
    if active_person is not None and person_id not in (None, active_person):
        return None, "Refused: the current caller identity cannot be overridden."
    return (active_person if active_person is not None else person_id), None


def _check_goal_access(store, goal_id: str):
    """Return a goal only when the bound caller is allowed to operate on it.

    Listing is already person-scoped, but a model could still present a guessed
    or previously observed goal id directly to a transition tool. Recheck at
    every direct-id boundary so a caller cannot change someone else's goal.
    """
    goal = store.get_goal(goal_id)
    if goal is None:
        return None, f"No goal with id '{goal_id}'."
    active_person = active_person_id.get()
    if active_person is not None and goal.get("person_id") != active_person:
        return None, "Refused: the current caller cannot access another person's goal."
    return goal, None


def create_goal(title: str, rationale: str = "", source: str = "internal",
                priority: int = 3, next_action: str = "", person_id: str = None):
    """Create a new persistent goal for this character in 'proposed' status.
    Returns a stable goal_id handle for later use. When a caller identity is
    bound, the goal is scoped to that caller and cannot be assigned elsewhere.

    Args: title (str, required), rationale (str, optional), source (str,
    optional provenance), priority (int 1-5, optional), next_action (str,
    optional), person_id (str, optional; overridden/scoped by the caller)."""
    person, err = _resolve_person(person_id)
    if err:
        return err
    gid = _active_store().create_goal(
        title, rationale=rationale, source=source, priority=priority,
        next_action=next_action, person_id=person,
    )
    if gid is None:
        return "Failed to create goal (title empty or storage error)."
    return f"Created goal id={gid} (status: proposed, priority {priority})."


def list_active_goals(limit: int = ACTIVE_GOALS_LIMIT, person_id: str = None):
    """List this character's live (non-terminal) goals, highest priority first.
    Read-only and bounded. With a bound caller, only that caller's goals are
    listed. Args: limit (int, optional), person_id (str, optional)."""
    person, err = _resolve_person(person_id)
    if err:
        return err
    store = _active_store()
    if person is not None:
        goals = store.list_active(person_id=person, limit=limit)
    else:
        goals = store.list_active(limit=limit)
    rendered = render_goals(store.character_id, goals)
    return rendered if rendered else "No active goals."


def update_goal(goal_id: str, title: str = None, rationale: str = None,
                priority: int = None, next_action: str = None,
                person_id: str = None):
    """Update content of a live goal. Never touches a completed/abandoned goal.
    Every changed field is audited (old -> new). A caller-bound request cannot
    move a goal onto another person.

    Args: goal_id (str, stable), title (str, optional), rationale (str,
    optional), priority (int 1-5, optional), next_action (str, optional),
    person_id (str, optional)."""
    store = _active_store()
    goal, err = _check_goal_access(store, goal_id)
    if err:
        return err
    if goal["status"] in ("completed", "abandoned"):
        return f"Goal '{goal_id}' is terminal ({goal['status']}) and cannot be updated."
    if person_id is not None:
        _, err = _resolve_person(person_id)
        if err:
            return err
    updated = store.update_goal(
        goal_id, title=title, rationale=rationale, priority=priority,
        next_action=next_action, person_id=person_id,
    )
    if updated is None:
        return f"Goal '{goal_id}' could not be updated."
    return f"Updated goal '{goal_id}'."


def mark_goal_active(goal_id: str):
    """Move a proposed/blocked/awaiting_approval goal to active.
    Args: goal_id (str, stable)."""
    store = _active_store()
    _, err = _check_goal_access(store, goal_id)
    if err:
        return err
    updated = store.activate_goal(goal_id)
    return _transition_result(store, goal_id, updated, "activated")


def mark_goal_blocked(goal_id: str, reason: str = "blocked"):
    """Block a live goal with a recorded reason (audited). Args: goal_id (str),
    reason (str, optional)."""
    store = _active_store()
    _, err = _check_goal_access(store, goal_id)
    if err:
        return err
    updated = store.mark_blocked(goal_id, reason)
    return _transition_result(store, goal_id, updated, "marked blocked")


def request_goal_approval(goal_id: str):
    """Move a proposed/active/blocked goal to awaiting_approval.
    Args: goal_id (str, stable)."""
    store = _active_store()
    _, err = _check_goal_access(store, goal_id)
    if err:
        return err
    updated = store.request_approval(goal_id)
    return _transition_result(store, goal_id, updated, "set to awaiting_approval")


def complete_goal(goal_id: str, outcome: str = ""):
    """Mark a live goal completed, recording its outcome (audited).
    Args: goal_id (str, stable), outcome (str, optional)."""
    store = _active_store()
    _, err = _check_goal_access(store, goal_id)
    if err:
        return err
    updated = store.complete_goal(goal_id, outcome)
    return _transition_result(store, goal_id, updated, "completed")


def abandon_goal(goal_id: str, reason: str = ""):
    """Abandon a live goal, recording why (audited). Args: goal_id (str,
    stable), reason (str, optional)."""
    store = _active_store()
    _, err = _check_goal_access(store, goal_id)
    if err:
        return err
    updated = store.abandon_goal(goal_id, reason)
    return _transition_result(store, goal_id, updated, "abandoned")


def _transition_result(store, goal_id: str, updated, verb: str) -> str:
    if updated is None:
        goal = store.get_goal(goal_id)
        if goal is None:
            return f"No goal with id '{goal_id}'."
        if goal["status"] in ("completed", "abandoned"):
            return f"Goal '{goal_id}' is terminal ({goal['status']}); cannot be {verb}."
        return f"Goal '{goal_id}' could not be {verb} from status '{goal['status']}'."
    return f"Goal '{goal_id}' {verb}."
