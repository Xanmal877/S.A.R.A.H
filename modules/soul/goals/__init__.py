"""
Per-character registry for GoalStore.

Tool calls don't get a handle to the live agent/Soul object (see
modules/tools/executor.py), so - exactly like identity_state / person_profiles -
the goal tools resolve "whose goals" via the active_character_id contextvar.
We import that contextvar from identity_state (NOT redeclare it) so identity,
person-profile, and goal tools all read the same per-task value: the
ToolOrchestrator sets that exact contextvar before running a character's
tool-call loop. Redeclaring it here would silently diverge and break isolation
between Sarah and Tama.

This package deliberately re-exports the store registry from .goals so there is
exactly ONE goal-store cache shared by the tool layer, context assembly, and
tests - a second registry here would let tools and context read divergent store
instances (especially under redirectable SARAH_STATE_DIR).
"""

from modules.soul.identity_state.identity_state import active_character_id  # noqa: F401

from .goals import (  # noqa: F401
    GoalStore,
    _active_store,
    _clear_goal_store_cache,
    get_goal_store,
)
