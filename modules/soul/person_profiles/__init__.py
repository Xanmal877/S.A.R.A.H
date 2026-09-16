"""
Per-character registry for PersonProfileStore.

Tool calls don't get a handle to the live agent/Soul object (see
modules/tools/executor.py), so - exactly like identity_state - the person
profile tools resolve "whose person profiles" via the active_character_id
contextvar. We import that contextvar from identity_state (NOT redeclare it)
so both identity and person-profile tools read the same per-task value: the
ToolOrchestrator sets that exact contextvar before running a character's
tool-call loop. Redeclaring it here would silently diverge and break
isolation between Sarah and Tama.
"""

from .person_profile import PersonProfileStore
from modules.soul.identity_state.identity_state import active_character_id  # noqa: F401

# One store per character, lazily created and cached for the process lifetime
# (writes call _save() immediately, so a crash doesn't rely on flushing).
_person_profile_stores: dict[str, "PersonProfileStore"] = {}


def get_person_profile_store(character_id: str = "sarah") -> "PersonProfileStore":
    if character_id not in _person_profile_stores:
        _person_profile_stores[character_id] = PersonProfileStore(character_id=character_id)
    return _person_profile_stores[character_id]


def _active_store() -> "PersonProfileStore":
    """Resolve the store for whichever character the current tool-call loop
    belongs to (see active_character_id above)."""
    return get_person_profile_store(active_character_id.get())


def _clear_person_profile_store_cache():
    """Drop the cached store instances (tests only). Stored profile objects
    hold a fixed storage_path from construction, so a test that redirects
    SARAH_STATE_DIR to a fresh temp dir must invalidate the cache or a later
    case would reuse a store pointed at the previous temp dir."""
    _person_profile_stores.clear()
