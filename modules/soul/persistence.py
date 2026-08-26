import json
import os
import logging

logger = logging.getLogger("SoulPersistence")

def _state_path(character_id: str) -> str:
    return os.path.expanduser(f"~/.sarah/state/{character_id}/mental_state.json")


def load_mental_state(character_id: str = "sarah") -> dict:
    """Loads the last saved needs/drives/enneagram state for the given
    character, if any. Returns {} on first run (MentalState.startup()
    already treats {} as 'use defaults')."""
    path = _state_path(character_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load saved mental state from {path}: {e}")
        return {}


def save_mental_state(mental_state, character_id: str = "sarah") -> None:
    """Persists MentalState.to_dict() so mood/needs survive process restarts
    instead of resetting to defaults every time the daemon restarts."""
    path = _state_path(character_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(mental_state.to_dict(), f, indent=2)
    except OSError as e:
        logger.warning(f"Could not save mental state to {path}: {e}")
