import subprocess
import shutil
import logging

logger = logging.getLogger("Windows")


def list_windows():
    """Lists open windows (id, desktop, PID, host, title). Best-effort: KDE Wayland only
    exposes windows still running under XWayland this way; native-Wayland-only clients
    won't appear."""
    if not shutil.which("wmctrl"):
        return "Error: wmctrl not available (install wmctrl)."
    try:
        result = subprocess.run(["wmctrl", "-l", "-x", "-p"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return f"Error listing windows: {result.stderr.strip()}"
        return result.stdout.strip() or "No windows found."
    except Exception as e:
        logger.error(f"wmctrl call failed: {e}")
        return f"Error listing windows: {e}"
