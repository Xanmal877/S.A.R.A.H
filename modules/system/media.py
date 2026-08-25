import subprocess
import shutil
import logging

logger = logging.getLogger("Media")


def _playerctl(*args):
    if not shutil.which("playerctl"):
        return None, "Error: playerctl not available (install playerctl)."
    try:
        result = subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None, f"Error: {result.stderr.strip() or 'no active media player found'}"
        return result.stdout.strip(), None
    except Exception as e:
        logger.error(f"playerctl call failed: {e}")
        return None, f"Error: {e}"


def media_play_pause():
    _, err = _playerctl("play-pause")
    return err or "Toggled play/pause."


def media_next():
    _, err = _playerctl("next")
    return err or "Skipped to next track."


def media_previous():
    _, err = _playerctl("previous")
    return err or "Skipped to previous track."


def media_status():
    out, err = _playerctl(
        "metadata", "--format", "{{playerName}}: {{artist}} - {{title}} ({{status}})"
    )
    return err or out or "No media playing."
