import asyncio
import logging
import time

from .config import load_secret
from .peer_registry import peer_registry
from .protocol import decode_message, encode_message
from .tls import client_context

logger = logging.getLogger("HiveCore")


class HiveCore:
    """
    Active hive polling, only run on nodes configured with role="core"
    (see modules/hive/config.py). Periodically queries every currently
    discovered peer (modules/hive/peer_registry.py) for its system info and
    screen description, and exposes the aggregate as a [HIVE] world-state
    section (see get_hive_summary / modules/observationModule.py).
    """

    def __init__(self, poll_interval: float = 20.0):
        self.poll_interval = poll_interval
        self.secret = load_secret()
        self.peer_info = {}  # name -> {"host":..., "system_info":..., "screen_description":..., "last_polled":...}
        self._task = None

    async def start(self):
        if not self.secret:
            logger.warning("No hive secret provisioned - HiveCore polling disabled.")
            return
        self._task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self):
        while True:
            await self._poll_all_peers()
            await asyncio.sleep(self.poll_interval)

    async def _poll_all_peers(self):
        for name, peer in peer_registry.all().items():
            try:
                sysinfo = await self._query(peer["host"], peer["port"], "get_system_info")
                screen = await self._query(peer["host"], peer["port"], "get_screen_description")
                self.peer_info[name] = {
                    "host": peer["host"],
                    "system_info": sysinfo,
                    "screen_description": screen.get("description", ""),
                    "last_polled": time.time(),
                }
            except Exception as e:
                logger.warning(f"Failed to poll hive peer '{name}': {e}")

    async def _query(self, host: str, port: int, msg_type: str, data: dict = None) -> dict:
        ssl_ctx = client_context()
        if not ssl_ctx:
            raise RuntimeError("No hive TLS cert provisioned - cannot query peers.")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx), timeout=5
        )
        try:
            writer.write(encode_message(self.secret, msg_type, data))
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
            envelope = decode_message(self.secret, raw)
            return envelope.get("data", {})
        finally:
            writer.close()

    def get_hive_summary(self, max_chars: int = 800) -> str:
        if not self.peer_info:
            return "No hive peers currently known."
        lines = []
        for name, info in self.peer_info.items():
            age = time.time() - info["last_polled"]
            lines.append(
                f"- {name} ({info['host']}, last polled {age:.0f}s ago): "
                f"{info['screen_description'][:200]}"
            )
        return "\n".join(lines)[:max_chars]
