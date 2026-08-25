import subprocess
import shutil
import logging

logger = logging.getLogger("Media")


def _playerctl(*args, player: str = None):
    if not shutil.which("playerctl"):
        return None, "Error: playerctl not available (install playerctl)."
    cmd = ["playerctl"]
    if player:
        cmd += ["-p", player]
    cmd += list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None, f"Error: {result.stderr.strip() or 'no active media player found'}"
        return result.stdout.strip(), None
    except Exception as e:
        logger.error(f"playerctl call failed: {e}")
        return None, f"Error: {e}"


def list_media_players():
    """Lists the MPRIS player names playerctl currently sees (e.g. browser, phone via KDE Connect)."""
    out, err = _playerctl("-l")
    return err or out or "No media players found."


def media_play_pause(player: str = None):
    """Args: player (str, optional) - an exact name from list_media_players(), e.g. 'kdeconnect.mpris_...'."""
    _, err = _playerctl("play-pause", player=player)
    return err or "Toggled play/pause."


def media_next(player: str = None):
    _, err = _playerctl("next", player=player)
    return err or "Skipped to next track."


def media_previous(player: str = None):
    _, err = _playerctl("previous", player=player)
    return err or "Skipped to previous track."


def media_status(player: str = None):
    out, err = _playerctl(
        "metadata", "--format", "{{playerName}}: {{artist}} - {{title}} ({{status}})", player=player
    )
    return err or out or "No media playing."
