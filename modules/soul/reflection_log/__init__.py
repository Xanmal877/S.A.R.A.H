"""
Per-character registry for ReflectionLogStore.

The reflection journal is SYSTEM-WRITTEN ONLY. It is NOT a tool, NOT registered
in modules/tools/init_tools.py, and NOT exposed to Discord - there is no model
tool that can read or write it. The autonomous loop and the outcome interpreter
(themselves reachable only from the ToolOrchestrator) append entries; resolution
of "whose journal" goes through the active_character_id contextvar, exactly like
goals / action_proposals, so Sarah and Tama keep fully isolated journals.

This package deliberately re-exports the store registry from .reflection_log so
there is exactly ONE reflection-log cache shared by mainAgent, the outcome
interpreter, and tests - a second registry here would let callers read divergent
store instances (especially under redirectable SARAH_STATE_DIR).
"""

from modules.soul.identity_state.identity_state import active_character_id  # noqa: F401

from .reflection_log import (  # noqa: F401
    ENTRY_AUTONOMOUS,
    ENTRY_OUTCOME,
    RECENT_EXPERIENCE_LIMIT,
    REFLECTION_LOG_CAP,
    REFLECTION_LOG_VERSION,
    SOURCE_AUTONOMOUS_LOOP,
    SOURCE_OUTCOME_INTERPRETER,
    ReflectionLogStore,
    _active_store,
    _clear_reflection_log_store_cache,
    get_reflection_log_store,
    recent_experiences_summary,
)
