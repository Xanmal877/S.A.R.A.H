import json
import os
import logging

logger = logging.getLogger("SoulPersistence")

STATE_PATH = os.path.expanduser("~/.sarah/state/mental_state.json")


def load_mental_state() -> dict:
    """Loads the last saved needs/drives/enneagram state, if any. Returns {}
    on first run (MentalState.startup() already treats {} as 'use defaults')."""
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load saved mental state from {STATE_PATH}: {e}")
        return {}


def save_mental_state(mental_state) -> None:
    """Persists MentalState.to_dict() so mood/needs survive process restarts
    instead of resetting to defaults every time the daemon restarts."""
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(mental_state.to_dict(), f, indent=2)
    except OSError as e:
        logger.warning(f"Could not save mental state to {STATE_PATH}: {e}")
