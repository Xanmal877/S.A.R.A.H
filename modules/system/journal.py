import subprocess
import logging

logger = logging.getLogger("Journal")


def get_recent_logs(lines: int = 50, unit: str = None, priority: str = None):
    """Reads recent entries from the systemd journal. Args: lines (int), unit (str, optional systemd unit name), priority (str, optional e.g. 'err')."""
    cmd = ["journalctl", "-n", str(int(lines)), "--no-pager"]
    if unit:
        cmd += ["-u", str(unit)]
    if priority:
        cmd += ["-p", str(priority)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error reading journal: {result.stderr.strip()}"
        return result.stdout.strip() or "No log entries found."
    except Exception as e:
        logger.error(f"journalctl call failed: {e}")
        return f"Error reading journal: {e}"
