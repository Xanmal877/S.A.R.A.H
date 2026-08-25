import asyncio
import logging

from .config import load_secret
from .protocol import encode_message, decode_message, ProtocolError
from modules.system.system_info import get_system_info

logger = logging.getLogger("HiveServer")

# Explicit whitelist. This is the safety boundary that keeps the flat,
# ungated modules.tools.tool_registry (which includes arbitrary
# `run_command`) off the network entirely - only these three read-only
# operations are reachable by a hive peer, and they're implemented by
# calling the underlying modules directly, never via executor.execute().
SUPPORTED_TYPES = {"ping", "get_system_info", "get_screen_description"}


class HiveServer:
    """
    Authenticated (HMAC/PSK, see protocol.py), read-only TCP responder.
    Every hive node runs one (see agents/baseAgent.py). Refuses to start at
    all if no shared secret is provisioned (~/.sarah/hive_secret) - fail
    closed rather than ever listen unauthenticated.
    """

    def __init__(self, node_name: str, port: int, screen_watcher=None):
        self.node_name = node_name
        self.port = port
        self.screen_watcher = screen_watcher
        self.secret = load_secret()
        self._server = None

    async def start(self):
        if not self.secret:
            logger.warning(
                "No hive secret provisioned (~/.sarah/hive_secret) - "
                "HiveServer NOT starting. Run init_secret() to provision one."
            )
            return
        self._server = await asyncio.start_server(self._handle_client, "0.0.0.0", self.port)
        logger.info(f"Hive server listening on 0.0.0.0:{self.port}")

    async def _handle_client(self, reader, writer):
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
            envelope = decode_message(self.secret, raw)
            response_data = await self._dispatch(envelope["type"], envelope.get("data", {}))
            writer.write(encode_message(self.secret, "response", response_data))
            await writer.drain()
        except (ProtocolError, asyncio.TimeoutError) as e:
            logger.warning(f"Rejected hive request: {e}")
        except Exception as e:
            logger.exception(f"Error handling hive request: {e}")
        finally:
            writer.close()

    async def _dispatch(self, msg_type: str, data: dict) -> dict:
        if msg_type not in SUPPORTED_TYPES:
            return {"error": f"Unsupported message type: {msg_type}"}

        if msg_type == "ping":
            return {"status": "ok", "node_name": self.node_name}

        if msg_type == "get_system_info":
            return await asyncio.to_thread(get_system_info)

        if msg_type == "get_screen_description":
            if self.screen_watcher:
                return {"description": self.screen_watcher.get_summary()}
            return {"description": "Screen watching not enabled on this node."}
