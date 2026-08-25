import subprocess
import shutil
import logging

logger = logging.getLogger("Clipboard")


def _copy_cmd():
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--input"]
    return None


def _paste_cmd():
    if shutil.which("wl-paste"):
        return ["wl-paste", "--no-newline"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--output"]
    return None


def get_clipboard():
    cmd = _paste_cmd()
    if not cmd:
        return "Error: no clipboard tool available (install wl-clipboard or xsel)."
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return f"Error reading clipboard: {result.stderr.strip()}"
        return result.stdout
    except Exception as e:
        logger.error(f"Clipboard read failed: {e}")
        return f"Error reading clipboard: {e}"


def set_clipboard(text: str):
    cmd = _copy_cmd()
    if not cmd:
        return "Error: no clipboard tool available (install wl-clipboard or xsel)."
    try:
        # wl-copy forks a background process to hold the clipboard; that child
        # inherits piped stdout/stderr, so capture_output=True would hang until
        # the daemon exits. Route its output to DEVNULL instead.
        stdout_target = subprocess.DEVNULL if cmd[0] == "wl-copy" else subprocess.PIPE
        result = subprocess.run(
            cmd, input=text, stdout=stdout_target, stderr=stdout_target, text=True, timeout=5
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip() if result.stderr else ""
            return f"Error setting clipboard: {stderr or f'exit code {result.returncode}'}"
        return "Clipboard updated."
    except Exception as e:
        logger.error(f"Clipboard write failed: {e}")
        return f"Error setting clipboard: {e}"
