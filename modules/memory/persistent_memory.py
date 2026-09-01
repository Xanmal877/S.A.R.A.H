import os

from modules.memory.json_file_store import JsonFileStore


class PersistentMemory(JsonFileStore):
    """
    Handles long-term storage of non-secret information,
    preferences, and system configuration decisions.
    """
    def __init__(self, storage_path="~/.sarah/memory.json"):
        self.storage_path = os.path.expanduser(storage_path)
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

memory = PersistentMemory()
