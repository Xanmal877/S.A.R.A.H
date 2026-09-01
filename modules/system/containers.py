import logging
import shutil
import subprocess

logger = logging.getLogger("Containers")


def _binary():
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return None


def _run(args: list, timeout: int = 30):
    binary = _binary()
    if not binary:
        return "Error: neither docker nor podman is available."
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Error (code {result.returncode}): {output}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: {binary} command timed out."
    except Exception as e:
        logger.error(f"container call failed: {e}")
        return f"Error: {e}"


def list_containers(all: bool = True):
    args = ["ps"]
    if all:
        args.append("-a")
    return _run(args)


def list_images():
    return _run(["images"])


def container_logs(name: str, lines: int = 50):
    return _run(["logs", "--tail", str(int(lines)), name])


def start_container(name: str):
    return _run(["start", name])


def stop_container(name: str):
    return _run(["stop", name])


def restart_container(name: str):
    return _run(["restart", name])
