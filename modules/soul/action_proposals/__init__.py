"""
Per-character registry for ActionProposalStore.

Tool calls don't get a handle to the live agent/Soul object (see
modules/tools/executor.py), so - exactly like identity_state / goals / person
profiles - the action-proposal tools resolve "whose proposals" via the
active_character_id contextvar. We import that contextvar from identity_state
(NOT redeclare it) so identity, person-profile, goal, and action-proposal tools
all read the same per-task value: the ToolOrchestrator sets that exact contextvar
before running a character's tool-call loop. Redeclaring it here would silently
diverge and break character isolation.

This package deliberately re-exports the store registry from
.action_proposals so there is exactly ONE action-proposal cache shared by the
tool layer, the ToolOrchestrator approval gate, and tests - a second registry
here would let tools and the orchestrator read divergent store instances
(especially under redirectable SARAH_STATE_DIR).
"""

from modules.soul.identity_state.identity_state import active_character_id  # noqa: F401

from .action_proposals import (  # noqa: F401
    ActionProposalStore,
    _active_store,
    _clear_action_proposal_store_cache,
    get_action_proposal_store,
    get_risk_category,
    render_proposals,
)
