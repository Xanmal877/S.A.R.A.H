import subprocess
import logging

logger = logging.getLogger("SystemShell")

class SystemShell:
    """
    Provides low-level shell access to the Linux system.
    """
    def run_command(self, command: str, use_sudo: bool = False):
        """
        Executes a shell command and returns the output.
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
            return f"Error executing command: {str(e)}"

shell = SystemShell()
