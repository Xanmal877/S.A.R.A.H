"""
Deterministic action-outcome-to-experience interpreter.

This module is invoked ONLY from the ToolOrchestrator, immediately after
store.record_outcome() records the executor result of a consumed action
proposal. It turns that single deterministic success/failure boolean into:

  - a bounded outcome interpretation (experience) written to the per-character
    reflection journal (modules/soul/reflection_log);
  - safe, fixed-clamped goal transitions: a failed proposal marks its linked
    goal blocked; a successful proposal reactivates a linked goal that is
    blocked. It NEVER auto-completes or auto-abandons a goal (those are
    explicit, audited operator/agent decisions);
  - a fixed-clamped mood nudge on the character's mental state, driven ONLY by
    the executor success boolean (success -> a small morale up; failure -> a
    small morale down). NO LLM text, no tool args, no content of the outcome is
    ever used to shape mood - only the boolean.

Agent-less design: the interpreter is a pure function of the recorded proposal
(plus an optional mental_state handler). If no mental_state is passed (e.g. a
tool-call loop running without a full BaseCharacter/Soul, or under test), the
mood nudge is skipped but all goal/journal/episode bookkeeping still happens.
Failure of the interpreter itself must NEVER alter the underlying tool result or
the already-recorded proposal outcome, so every call is wrapped in a best-effort
guard by its sole caller (ToolOrchestrator._execute_gated).

"Fixed clamped constants" means the mood offsets are module-level literals -
they do not depend on the outcome text, the tool, the goal, or anything other
than success == True/False - and the resulting value is clamped to the module's
0..1 range by MentalState/NeedsModule.tick semantics.
"""

import logging

from modules.soul.reflection_log.reflection_log import (
    ENTRY_OUTCOME,
    SOURCE_OUTCOME_INTERPRETER,
    get_reflection_log_store,
)

logger = logging.getLogger("OutcomeInterpreter")

# Fixed mood offsets applied based only on the executor success boolean. Chosen
# small so a single action can't swing mood wildly; clamped by the mental state
# module's 0..1 range on the way in.
SUCCESS_MOOD_OFFSET = 0.02
FAILURE_MOOD_OFFSET = -0.03

# Upper bound for the bounded outcome reason stored in goal blockers / journal.
OUTCOME_REASON_LIMIT = 400

# The only mood field the interpreter is allowed to touch. Kept to one so the
# surface area for "content-driven mood" stays tiny and auditable.
_MOOD_FIELD = "morale"


def _clamp(value, lo=0.0, hi=1.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def _bounded_reason(success: bool, tool: str, status: str) -> str:
    """A deterministic, bounded outcome reason built ONLY from the executor
    success flag + tool/status. Never embeds raw args or outcome content.

    Example: "Tool 'run_command' failed (status: failed)." or
              "Tool 'run_command' succeeded (status: executed)."
    """
    verb = "failed" if not success else "succeeded"
    text = f"Proposed action '{tool}' {verb} (proposal status: {status})."
    if not success:
        text += " Linked goal marked blocked."
    elif status == "executed":
        text += " Linked blocked goal reactivated."
    return text[:OUTCOME_REASON_LIMIT]


def _apply_mood_nudge(success: bool, mental_state) -> None:
    """Apply the fixed, clamped mood nudge. No-op when mental_state is None or
    lacks a NeedsModule with the morale field. Only ever reads/writes the fixed
    constant offsets, never the outcome content."""
    if mental_state is None:
        return
    try:
        needs = mental_state.needs
    except Exception:  # noqa: BLE001 - missing handler must not raise
        return
    if not hasattr(needs, _MOOD_FIELD):
        return
    try:
        current = float(getattr(needs, _MOOD_FIELD))
    except (TypeError, ValueError):
        current = 0.5
    offset = SUCCESS_MOOD_OFFSET if success else FAILURE_MOOD_OFFSET
    setattr(needs, _MOOD_FIELD, _clamp(current + offset))


def _handle_goal(success: bool, proposal: dict, character_id: str) -> dict:
    """Apply the ONLY safe, deterministic goal transitions this phase permits:

      - failure  + linked goal live  -> mark the goal blocked (bounded reason)
      - success  + linked goal blocked -> reactivate the goal

    Never completes or abandons a goal. Returns a summary of what (if anything)
    changed, so callers/tests can assert the transition.
    """
    result = {"goal_id": None, "transitioned": None, "transitioned_from": None}
    goal_id = proposal.get("goal_id")
    if not goal_id:
        return result
    result["goal_id"] = goal_id

    try:
        from modules.soul.goals import get_goal_store
        goal_store = get_goal_store(character_id)
    except Exception as e:  # noqa: BLE001 - goal bookkeeping is best-effort
        logger.warning("Could not resolve goal store for outcome on %s: %s", goal_id, e)
        return result

    reason = _bounded_reason(success, proposal.get("tool", ""), proposal.get("status", ""))
    try:
        goal = goal_store.get_goal(goal_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read goal %s during outcome: %s", goal_id, e)
        return result
    if goal is None:
        return result
    # Terminal goals are left strictly alone - the interpreter never completes
    # or abandons, and never resurrects a terminal goal.
    if goal["status"] in ("completed", "abandoned"):
        return result

    try:
        if not success:
            if goal["status"] in ("active", "proposed", "awaiting_approval"):
                updated = goal_store.mark_blocked(goal_id, reason,
                                                  audit_actor=SOURCE_OUTCOME_INTERPRETER)
                if updated is not None:
                    result["transitioned"] = "blocked"
                    result["transitioned_from"] = goal["status"]
        else:
            if goal["status"] == "blocked":
                updated = goal_store.activate_goal(goal_id,
                                                   audit_actor=SOURCE_OUTCOME_INTERPRETER)
                if updated is not None:
                    result["transitioned"] = "active"
                    result["transitioned_from"] = "blocked"
    except Exception as e:  # noqa: BLE001 - never let goal handling break the call
        logger.warning("Goal transition for outcome on %s failed: %s", goal_id, e)
    return result


def interpret_outcome(proposal: dict, mental_state=None, *, character_id: str = None) -> dict:
    """Interpret one recorded action outcome and persist its experience.

    `proposal` is the (post-record_outcome) proposal dict returned by the
    store. `mental_state` is optional; when None (agent-less operation) the mood
    nudge is skipped but goal/journal bookkeeping still runs. Returns a summary
    dict describing what was interpreted/written.

    Safe to call even on malformed input (never raises to the caller).

    Bookkeeping performed here (deterministic, no raw args, no LLM text):
      - journal: append an `outcome` entry with the bounded reason, linked
        goal/proposal ids and the success/failure marker;
      - goals:   the safe transitions described in _handle_goal;
      - mood:    the fixed clamped nudge (unless agent-less).
    """
    summary = {
        "journaled": False,
        "goal": {"goal_id": None, "transitioned": None, "transitioned_from": None},
    }
    if not isinstance(proposal, dict):
        return summary

    success = (proposal.get("status") == "executed")
    tool = proposal.get("tool", "")
    outcome = "success" if success else "failure"
    reason = _bounded_reason(success, tool, proposal.get("status", ""))
    goal_id = proposal.get("goal_id")

    # 1. Journal the outcome (agent-less safe: reflection store is file-backed).
    try:
        cid = character_id or "sarah"
        store = get_reflection_log_store(cid)
        store.append(
            kind=ENTRY_OUTCOME,
            content=reason,
            goal_id=goal_id,
            proposal_id=proposal.get("id"),
            outcome=outcome,
            source=SOURCE_OUTCOME_INTERPRETER,
        )
        summary["journaled"] = True
    except Exception as e:  # noqa: BLE001 - journaling is best-effort
        logger.warning("Could not journal outcome: %s", e)

    # 2. Safe goal transitions.
    summary["goal"] = _handle_goal(success, proposal, character_id or "sarah")

    # 3. Fixed clamped mood nudge (skipped when agent-less).
    _apply_mood_nudge(success, mental_state)

    return summary
