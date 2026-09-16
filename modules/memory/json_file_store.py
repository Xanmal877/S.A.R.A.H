import json
import os


def state_dir(character_id: str) -> str:
    """Base directory for a character's persistent state.

    Defaults to ~/.sarah/state/{character_id} (matching identity_state and
    mental_state persistence). SARAH_STATE_DIR overrides the root so tests and
    alternate deployments can point state elsewhere without touching the real
    ~/.sarah tree.
    """
    base = os.environ.get("SARAH_STATE_DIR", os.path.expanduser("~/.sarah"))
    return os.path.join(base, "state", character_id)


class JsonFileStore:
    """
    Shared load/save boilerplate for the small JSON-file-backed stores in
    this package (ChangeHistory, PersistentMemory) - previously copy-pasted
    identically in both. Subclasses set self._path and self._default (a
    list or dict, whichever shape their data is) before calling _load().
    """

    def _ensure_dir(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _load(self, path: str, default):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save(self, path: str, data) -> None:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
