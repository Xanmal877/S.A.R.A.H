import logging
import subprocess

logger = logging.getLogger("GitTools")


def _run_git(repo_path: str, args: list, timeout: int = 30):
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Error (code {result.returncode}): {output}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: git command timed out."
    except Exception as e:
        logger.error(f"git call failed: {e}")
        return f"Error: {e}"


def git_status(repo_path: str):
    return _run_git(repo_path, ["status", "--short", "--branch"])


def git_log(repo_path: str, count: int = 10):
    return _run_git(repo_path, ["log", f"-{int(count)}", "--oneline"])


def git_diff(repo_path: str, staged: bool = False):
    args = ["diff", "--stat"]
    if staged:
        args.insert(1, "--staged")
    return _run_git(repo_path, args)


def git_pull(repo_path: str):
    return _run_git(repo_path, ["pull"], timeout=60)


def git_commit(repo_path: str, message: str, add_all: bool = False):
    """Commits staged (or all, if add_all) changes locally. Does NOT push - pushing is a
    shared/visible action and stays a manual step. Args: repo_path (str), message (str),
    add_all (bool, optional)."""
    if add_all:
        add_result = _run_git(repo_path, ["add", "-A"])
        if add_result.startswith("Error"):
            return add_result
    return _run_git(repo_path, ["commit", "-m", message])
