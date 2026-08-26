import os
import json
import hashlib
import logging

logger = logging.getLogger("FileWatcher")

SNAPSHOT_DIR = os.path.expanduser("~/.sarah/watch")
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")


def _snapshot_path(path: str) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    key = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()
    return os.path.join(SNAPSHOT_DIR, f"{key}.json")


def _scan(path: str) -> dict:
    state = {}
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                st = os.stat(full)
                state[full] = {"size": st.st_size, "mtime": st.st_mtime}
            except OSError:
                continue
    return state


def _load_snapshot(path: str) -> dict:
    snap_path = _snapshot_path(path)
    if os.path.exists(snap_path):
        try:
            with open(snap_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_snapshot(path: str, state: dict):
    with open(_snapshot_path(path), "w") as f:
        json.dump(state, f)


def diff_directory(path: str = DOWNLOADS_DIR):
    """Compares a directory against its last recorded snapshot, reports new/removed/changed
    files, then updates the snapshot to the current state. Call again later to see what's
    changed since. Args: path (str, optional, defaults to ~/Downloads)."""
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return f"Error: '{path}' is not a directory."

    old = _load_snapshot(path)
    new = _scan(path)
    _save_snapshot(path, new)

    if not old:
        return f"First check of '{path}' - recorded {len(new)} file(s) as the baseline."

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        f for f in set(new) & set(old)
        if new[f]["size"] != old[f]["size"] or new[f]["mtime"] != old[f]["mtime"]
    )

    if not added and not removed and not changed:
        return f"No changes in '{path}' since the last check."

    parts = []
    if added:
        parts.append("New: " + ", ".join(os.path.relpath(f, path) for f in added))
    if removed:
        parts.append("Removed: " + ", ".join(os.path.relpath(f, path) for f in removed))
    if changed:
        parts.append("Changed: " + ", ".join(os.path.relpath(f, path) for f in changed))
    return " | ".join(parts)


def check_new_downloads():
    """Convenience wrapper: checks ~/Downloads specifically for changes since the last check."""
    return diff_directory(DOWNLOADS_DIR)
