import json
import os
from datetime import datetime

class PersistentMemory:
    """
    Handles long-term storage of non-secret information, 
    preferences, and system configuration decisions.
    """
    def __init__(self, storage_path="~/.sarah/memory.json"):
        self.storage_path = os.path.expanduser(storage_path)
        self._ensure_dir()
        self.data = self._load()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        with open(self.storage_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def store(self, key, value):
        self.data[key] = value
        self.save()

    def retrieve(self, key, default=None):
        return self.data.get(key, default)

    def update_context(self, updates: dict):
        self.data.update(updates)
        self.save()

memory = PersistentMemory()
