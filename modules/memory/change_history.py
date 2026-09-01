import os
from datetime import datetime

from modules.memory.json_file_store import JsonFileStore


class ChangeHistory(JsonFileStore):
    """
    Records every modification Sarah makes to the system.
    """
    def __init__(self, history_path="~/.sarah/history.json"):
        self.history_path = os.path.expanduser(history_path)
        self._ensure_dir(self.history_path)
        self.logs = self._load(self.history_path, [])

    def save(self):
        self._save(self.history_path, self.logs)

    def record(self, request, action, result, files_changed=None, backup_path=None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "request": request,
            "action": action,
            "result": result,
            "files_changed": files_changed or [],
            "backup_path": backup_path
        }
        self.logs.append(entry)
        self.save()

    def get_recent(self, limit=10):
        return self.logs[-limit:]

history = ChangeHistory()
