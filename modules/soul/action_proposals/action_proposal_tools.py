"""
Tool-level wrappers for persistent action proposals.

These are the *trusted-local* registry tools (registered in init_tools.py and
therefore available to the desktop daemon / CLI / voice). They deliberately are
NOT added to Discord's allowlist (discord/main.py DISCORD_ALLOWED_TOOLS): an
externally-reachable, untrusted-input surface must never be able to propose or
approve system-mutating actions on this machine - same reasoning as goal /
episodic / person-profile authorization boundaries.

Provided tools (all operate on the active character's store):
  * propose_action  - create a proposal (e.g. from a suggestion) for operator
                      approval. Returns a stable proposal id.
  * list_pending_actions - read-only list of proposals awaiting a decision.
  * approve_action  - operator grants approval on a proposed action.
  * reject_action   - operator refuses a proposed action.

Approval is a deliberate, audited operator decision with an audit history; an
approved proposal is single-use (consumed on execution) and character-scoped, so
it can never authorize a different character or a second run of the same
operation.
"""

from modules.soul.action_proposals import _active_store, render_proposals
from modules.soul.action_proposals.action_proposals import (
    PROPOSAL_LIST_LIMIT,
    get_risk_category,
)
from modules.soul.identity_state.identity_state import active_person_id


def _person_access_error(store, proposal_id: str):
    """Return a refusal reason when the bound caller may not operate on a
    proposal by direct id (same access rule as the store). A bound caller may
    access proposals whose person_id is None (character-general) or matches
    them; never another person's. None when allowed."""
    active_person = active_person_id.get()
    if active_person is None:
        return None
    entry = store.get(proposal_id)
    if entry is not None and entry.get("person_id") not in (None, active_person):
        return "Refused: the current caller cannot access another person's action proposal."
    return None


def propose_action(tool: str, args: str = "{}", rationale: str = "",
                   evidence: str = "", goal_id: str = None, person_id: str = None,
                   risk_category: str = None, ttl_seconds: int = 86400):
    """Propose a non-observe action for operator approval; returns a stable
    proposal id. The action will NOT run until approved and submitted for
    execution with the exact same tool+args.

    Args: tool (str, exact tool name), args (str, optional JSON of the exact
    arguments to run), rationale (str, optional why), evidence (str, optional
    what was inspected), goal_id (str, optional goal this serves), person_id
    (str, optional; overridden/scoped to the bound caller), risk_category
    (str, optional; defaults to the classified category for the tool), ttl_seconds
    (int, optional proposal lifetime before expiration)."""
    store = _active_store()
    pid = store.propose(
        tool, args or "{}", rationale=rationale, evidence=evidence,
        risk_category=risk_category, goal_id=goal_id, person_id=person_id,
        ttl_seconds=ttl_seconds,
    )
    if pid is None:
        return "Failed to create action proposal (empty tool or storage error)."
    risk = get_risk_category(tool)
    return (f"Proposed action id={pid} tool='{tool}' (risk: {risk}) awaiting "
            f"operator approval. Submit this id with exact matching args to execute.")


def list_pending_actions(limit: int = PROPOSAL_LIST_LIMIT):
    """List this character's proposals still awaiting an operator decision
    (read-only, bounded, no raw args in output). Args: limit (int, optional)."""
    store = _active_store()
    pending = store.list_pending(limit=limit)
    rendered = render_proposals(pending)
    return rendered if rendered else "No action proposals awaiting approval."


def approve_action(proposal_id: str, decision: str = ""):
    """Approve a proposed action so it may be executed once with exact matching
    args. Args: proposal_id (str), decision (str, optional operator note)."""
    store = _active_store()
    access = _person_access_error(store, proposal_id)
    if access is not None:
        return access
    updated = store.approve(proposal_id, actor="operator", decision=decision)
    if updated is None:
        entry = store.get(proposal_id)
        if entry is None:
            return f"No action proposal with id '{proposal_id}'."
        if entry["status"] != "proposed":
            return (f"Action proposal '{proposal_id}' is '{entry['status']}' "
                    "and cannot be approved.")
        return f"Action proposal '{proposal_id}' could not be approved."
    return f"Approved action proposal '{proposal_id}'."


def reject_action(proposal_id: str, decision: str = ""):
    """Reject a proposed/approved action (terminal; cannot be executed).
    Args: proposal_id (str), decision (str, optional operator note)."""
    store = _active_store()
    access = _person_access_error(store, proposal_id)
    if access is not None:
        return access
    updated = store.reject(proposal_id, actor="operator", decision=decision)
    if updated is None:
        entry = store.get(proposal_id)
        if entry is None:
            return f"No action proposal with id '{proposal_id}'."
        if entry["status"] in ("executed", "failed", "rejected"):
            return (f"Action proposal '{proposal_id}' is '{entry['status']}' "
                    "and cannot be rejected.")
        return f"Action proposal '{proposal_id}' could not be rejected."
    return f"Rejected action proposal '{proposal_id}'."
