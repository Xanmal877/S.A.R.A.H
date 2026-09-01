import json

from modules.memory.change_history import history
from modules.memory.persistent_memory import memory


def store_memory(key: str, value: str):
    """Stores a piece of information in long-term memory."""
    memory.store(key, value)
    return f"Successfully remembered {key}."

def retrieve_memory(key: str):
    """Retrieves a piece of information from long-term memory."""
    val = memory.retrieve(key)
    return val if val else "No memory found for that key."

def record_change(request: str, action: str, result: str, files_changed: list = None, backup_path: str = None):
    """Records a system change in the history log."""
    history.record(request, action, result, files_changed, backup_path)
    return "Change recorded in history."

def get_recent_changes():
    """Retrieves the last few changes made to the system."""
    changes = history.get_recent()
    return json.dumps(changes, indent=2)
