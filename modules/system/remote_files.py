import asyncio
import os
import logging

from modules.hive.peer_registry import peer_registry

logger = logging.getLogger("RemoteFiles")


async def _rsync(args: list, timeout: int = 120):
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync", "-az", "-e", "ssh -o BatchMode=yes -o ConnectTimeout=8", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout.decode(errors="ignore") + stderr.decode(errors="ignore")).strip()
        if proc.returncode != 0:
            return f"Error (code {proc.returncode}): {output}"
        return output or "Transfer complete."
    except asyncio.TimeoutError:
        return "Error: rsync timed out."
    except Exception as e:
        logger.error(f"rsync failed: {e}")
        return f"Error: {e}"


async def push_file_to_peer(host: str, local_path: str, remote_path: str):
    """Copies a local file/directory to a hive peer over rsync+SSH. `host` must currently be
    a discovered hive peer - same trust boundary as run_remote_command. Args: host (str),
    local_path (str), remote_path (str)."""
    known_hosts = peer_registry.known_hosts()
    if host not in known_hosts:
        return f"Refused: '{host}' is not a currently known hive peer ({sorted(known_hosts)})."
    local_path = os.path.expanduser(local_path)
    if not os.path.exists(local_path):
        return f"Error: local path '{local_path}' does not exist."
    return await _rsync([local_path, f"{host}:{remote_path}"])


async def pull_file_from_peer(host: str, remote_path: str, local_path: str):
    """Copies a file/directory from a hive peer to this machine over rsync+SSH. `host` must
    currently be a discovered hive peer. Args: host (str), remote_path (str), local_path (str)."""
    known_hosts = peer_registry.known_hosts()
    if host not in known_hosts:
        return f"Refused: '{host}' is not a currently known hive peer ({sorted(known_hosts)})."
    local_path = os.path.expanduser(local_path)
    return await _rsync([f"{host}:{remote_path}", local_path])
