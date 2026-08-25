import asyncio
import logging

from modules.hive.peer_registry import peer_registry

logger = logging.getLogger("RemoteShell")


async def run_remote_command(host: str, command: str, use_sudo: bool = False) -> str:
    """
    Runs `command` on a remote machine over SSH, autonomously (no
    confirmation gate - matches Sarah's "investigate and act" identity for
    hive peers, per the operator's explicit choice).

    The only enforced restriction: `host` must currently be a discovered
    hive peer (modules/hive/peer_registry.py) - Sarah cannot SSH into an
    arbitrary or hallucinated hostname, only a machine that has actually
    announced itself on the hive network. The real authentication boundary
    is SSH's own key-based auth: this only works on hosts where the
    operator has already deliberately installed Sarah's SSH key. BatchMode
    is forced on, so a host without that trust fails fast instead of
    hanging on a password prompt.
    """
    known_hosts = peer_registry.known_hosts()
    if host not in known_hosts:
        return f"Refused: '{host}' is not a currently known hive peer ({sorted(known_hosts)})."

    remote_cmd = f"sudo {command}" if use_sudo else command
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, remote_cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = (stdout.decode(errors="ignore") + stderr.decode(errors="ignore")).strip()
        return output or f"(no output, exit code {proc.returncode})"
    except asyncio.TimeoutError:
        return f"Error: SSH command to {host} timed out."
    except Exception as e:
        return f"Error: {str(e)}"
