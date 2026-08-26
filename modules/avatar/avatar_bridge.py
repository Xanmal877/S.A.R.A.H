import asyncio
import json
import logging

logger = logging.getLogger("AvatarBridge")

DEFAULT_PORT = 8791

# One avatar per character actually has a body to bridge to right now, but
# keyed by character_id from the start so a second (Sarah, once she has one)
# doesn't collide on the same port.
AVATAR_PORTS = {
    "tama": 8791,
    "sarah": 8792,
}

_bridges: dict = {}


def register_bridge(character_id: str, bridge: "AvatarBridge") -> None:
    _bridges[character_id] = bridge


def get_bridge(character_id: str):
    """Returns the running AvatarBridge for this character, or None if none
    has been started - callers (avatar_tools.py) must treat "no bridge yet"
    as normal, not an error, same as AvatarBridge itself treats "no avatar
    connected" as normal."""
    return _bridges.get(character_id)


class AvatarBridge:
    """
    Localhost-only IPC to one character's Godot avatar process (see
    ../../avatar/). Newline-delimited JSON over asyncio TCP, same framing
    convention as modules/hive/protocol.py - no new dependency (websockets
    isn't in piplist.txt) for what's a same-machine loopback channel, so no
    HMAC signing either (that defends hive's actual network boundary; this
    one never leaves 127.0.0.1).

    Python is the brain, Godot is a dumb rendering client (see avatar/scripts
    /body/avatar_body.gd's header) - this class only ever sends "cmd"
    messages out and receives "event" messages back. It does not decide
    anything itself.

    The avatar process connects to us, not the other way around, since the
    Python daemon is the long-lived side (systemd service) and the avatar
    is whatever gets started/restarted independently. If no avatar is
    connected, send_* calls are silently no-ops - callers (tools) should
    treat "no avatar" as normal, not an error.
    """

    def __init__(self, character_id: str = "sarah", port: int = DEFAULT_PORT, on_event=None):
        self.character_id = character_id
        self.port = port
        self.on_event = on_event  # callable(event_name: str, args: dict)
        self._server = None
        self._writer: asyncio.StreamWriter = None

    async def start(self):
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", self.port)
        logger.info(f"AvatarBridge listening on 127.0.0.1:{self.port} for '{self.character_id}'")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        # One avatar process at a time. A reconnect (e.g. avatar restarted)
        # simply replaces the old writer - the old connection, if still
        # somehow alive, just stops receiving further commands.
        logger.info(f"Avatar client connected for '{self.character_id}'")
        self._writer = writer
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                self._handle_line(line)
        except (ConnectionResetError, asyncio.IncompleteReadError) as e:
            logger.warning(f"Avatar connection dropped: {e}")
        finally:
            if self._writer is writer:
                self._writer = None
            writer.close()
            logger.info(f"Avatar client disconnected for '{self.character_id}'")

    def _handle_line(self, line: bytes):
        try:
            msg = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Malformed message from avatar: {e}")
            return

        if msg.get("type") != "event":
            return
        name = msg.get("name")
        args = msg.get("args", {})
        logger.info(f"Avatar event: {name} {args}")
        if self.on_event:
            self.on_event(name, args)

    async def _send(self, name: str, args: dict = None):
        if not self._writer:
            logger.debug(f"No avatar connected, dropping command '{name}'")
            return
        payload = json.dumps({"type": "cmd", "name": name, "args": args or {}}) + "\n"
        try:
            self._writer.write(payload.encode("utf-8"))
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            logger.warning(f"Failed to send '{name}' to avatar: {e}")
            self._writer = None

    async def move_to(self, x: float, y: float, running: bool = False):
        await self._send("move_to", {"x": x, "y": y, "running": running})

    async def play(self, animation: str):
        await self._send("play", {"animation": animation})

    async def say(self, text: str):
        await self._send("say", {"text": text})
