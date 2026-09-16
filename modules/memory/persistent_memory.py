import os

from modules.memory.json_file_store import JsonFileStore, state_dir


class PersistentMemory(JsonFileStore):
    """
    Handles long-term storage of non-secret information,
    preferences, and system configuration decisions.
    """

    def __init__(self, storage_path=None, character_id: str = "sarah"):
        # Default to a per-character file (~/.sarah/state/{character_id}/
        # memory.json) so Sarah and Tama keep isolated long-term memories.
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "memory.json"
        )
        self.storage_path = os.path.expanduser(self.storage_path)
        self.character_id = character_id
        self._ensure_dir(self.storage_path)
        self.data = self._load(self.storage_path, {})

    def save(self):
        self._save(self.storage_path, self.data)

    def store(self, key, value):
        self.data[key] = value
        self.save()

    def retrieve(self, key, default=None):
        return self.data.get(key, default)

    def update_context(self, updates: dict):
        self.data.update(updates)
        self.save()

