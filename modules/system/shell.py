import logging
import subprocess

logger = logging.getLogger("SystemShell")

class SystemShell:
    """
    Provides low-level shell access to the Linux system.
    """
    def run_command(self, command: str, use_sudo: bool = False):
        """
        Executes a shell command string and returns the output.

        This intentionally runs through a shell (pipes, globs, redirects
        are the whole point of a general "run arbitrary shell command"
        tool). Callers that build a command from separate identifiers
        (a package name, a service name, ...) should use run_argv instead
        so those values can't inject extra shell syntax.
        """
        if use_sudo:
            command = f"sudo {command}"

        logger.info(f"Running command: {command}")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"Error (code {result.returncode}): {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out."
        except Exception as e:
            return f"Error executing command: {e!s}"

    def run_argv(self, args: list, use_sudo: bool = False):
        """
        Executes a command from a list of argv tokens with no shell
        involved, so no individual token (e.g. a package or service name)
        can inject additional shell commands via `;`, `&&`, backticks, etc.
        """
        if use_sudo:
            args = ["sudo", *args]

        logger.info(f"Running command: {args}")
        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"Error (code {result.returncode}): {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out."
        except Exception as e:
            return f"Error executing command: {e!s}"

shell = SystemShell()
