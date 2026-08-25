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
        result = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return f"Error setting clipboard: {result.stderr.strip()}"
        return "Clipboard updated."
    except Exception as e:
        logger.error(f"Clipboard write failed: {e}")
        return f"Error setting clipboard: {e}"
