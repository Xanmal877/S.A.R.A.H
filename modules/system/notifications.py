import logging
import shutil
import subprocess

logger = logging.getLogger("Notifications")

_VALID_URGENCY = ("low", "normal", "critical")


def send_notification(title: str, message: str = "", urgency: str = "normal"):
    if not shutil.which("notify-send"):
        return "Error: notify-send not available."
    if urgency not in _VALID_URGENCY:
        urgency = "normal"
    try:
        result = subprocess.run(
            ["notify-send", "-u", urgency, "-a", "S.A.R.A.H.", title, message],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return f"Error sending notification: {result.stderr.strip()}"
        return "Notification sent."
    except Exception as e:
        logger.error(f"Notification failed: {e}")
        return f"Error sending notification: {e}"
