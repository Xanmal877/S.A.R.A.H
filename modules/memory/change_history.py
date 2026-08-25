import json
import os
import shutil
from datetime import datetime

class ChangeHistory:
    """
    Records every modification Sarah makes to the system.
    """
    def __init__(self, history_path="~/.sarah/history.json"):
        self.history_path = os.path.expanduser(history_path)
        self._ensure_dir()
        self.logs = self._load()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)

    def _load(self):
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save(self):
        with open(self.history_path, "w") as f:
            json.dump(self.logs, f, indent=4)

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
