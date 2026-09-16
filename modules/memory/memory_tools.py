import json

from modules.memory.change_history import ChangeHistory
from modules.memory.persistent_memory import PersistentMemory
from modules.soul.identity_state.identity_state import active_character_id

# Per-character memory / change-history, resolved via active_character_id
# (the same contextvar the identity tools and ToolOrchestrator use) so the
# memory tools always read/write the character whose loop is running rather
# than always Sarah's. Lazy instantiation keeps the default "sarah" memory
# compatible and lets tests construct fresh stores per character.
_memories = {}
_histories = {}


def _memory():
    character_id = active_character_id.get()
    if character_id not in _memories:
        _memories[character_id] = PersistentMemory(character_id=character_id)
    return _memories[character_id]


def _history():
    character_id = active_character_id.get()
    if character_id not in _histories:
        _histories[character_id] = ChangeHistory(character_id=character_id)
    return _histories[character_id]


def store_memory(key: str, value: str):
    """Stores a piece of information in long-term memory."""
    _memory().store(key, value)
    return f"Successfully remembered {key}."

def retrieve_memory(key: str):
    """Retrieves a piece of information from long-term memory."""
    val = _memory().retrieve(key)
    return val if val else "No memory found for that key."

def record_change(request: str, action: str, result: str, files_changed: list = None, backup_path: str = None):
    """Records a system change in the history log."""
    _history().record(request, action, result, files_changed, backup_path)
    return "Change recorded in history."

def get_recent_changes():
    """Retrieves the last few changes made to the system."""
    changes = _history().get_recent()
    return json.dumps(changes, indent=2)
