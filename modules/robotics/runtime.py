"""Character-scoped robotics runtime wrapper and registry.

This is the integration seam between S.A.R.A.H. and ``modules/robotics``,
modelled on ``modules/avatar/avatar_bridge.py``: one runtime per
``character_id``, looked up through a module-level registry so tools and the
observation module can resolve "whose body am I talking to" the same way
avatar tools resolve the avatar bridge.

A ``RoboticsRuntime`` owns a ``BodyIntent`` (what a planner wants the body to
do) and either a ``SimRobotBody`` (deterministic simulation) or an
acknowledgement-gated hardware ``RoboticsController``. It exposes the current
``BodyState`` and ``tick``/``close`` lifecycle.

Robotics is **disabled by default**: a runtime only builds a body when the
node's config opts in (``~/.sarah/hive_config.json`` -> ``robotics.enabled``).
When disabled, ``start``/``tick``/``close`` are no-ops and ``state`` is
``None``, so existing behavior is unchanged on every other node.

Hardware calls are blocking (serial I/O), so the async ``start``/``tick``/
``close`` methods thread-wrap the hardware path via ``asyncio.to_thread`` to
avoid stalling the asyncio event loop. The simulation path is pure CPU and
runs inline.
"""

from __future__ import annotations

import asyncio
import logging

from .config import load_robotics_config
from .navigation import FakeWorld
from .sim_body import SimRobotBody
from .state import BodyIntent, BodyState

logger = logging.getLogger("robotics.runtime")

# One runtime per character, keyed by character_id (mirrors AvatarBridge's
# _bridges registry). A character with no runtime is normal, not an error.
_runtimes: dict[str, RoboticsRuntime] = {}


def register_runtime(character_id: str, runtime: RoboticsRuntime) -> None:
    _runtimes[character_id] = runtime


def get_runtime(character_id: str) -> RoboticsRuntime | None:
    """Return the running RoboticsRuntime for this character, or None.

    Callers must treat "no runtime yet" as normal - the same way avatar tools
    treat "no bridge yet" as normal. A runtime may also exist but be disabled
    (``runtime.enabled is False``), in which case it has no body.
    """
    return _runtimes.get(character_id)


def unregister_runtime(character_id: str, runtime: RoboticsRuntime) -> None:
    """Remove ``runtime`` if it is still the registered instance."""
    if _runtimes.get(character_id) is runtime:
        _runtimes.pop(character_id, None)


class RoboticsRuntime:
    """Owns a body (sim or hardware) plus the intent a planner writes to it.

    Disabled by default. When ``enabled`` is false, ``start``/``tick``/
    ``close`` are no-ops and ``state`` is ``None``.
    """

    def __init__(self, character_id: str, config: dict | None = None) -> None:
        self.character_id = character_id
        self.config = config or load_robotics_config()
        self.intent = BodyIntent()
        self._body: SimRobotBody | None = None
        self._controller = None  # RoboticsController, imported lazily
        self._closed = False

    # ---- configuration ----------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled"))

    @property
    def mode(self) -> str:
        return self.config.get("mode", "sim")

    # ---- state ------------------------------------------------------

    @property
    def state(self) -> BodyState | None:
        """Current body telemetry, or ``None`` when no body is running."""
        if self._body is not None:
            return self._body.state
        if self._controller is not None:
            return self._controller_state()
        return None

    def _controller_state(self) -> BodyState:
        return self._controller.body_state

    # ---- lifecycle --------------------------------------------------

    async def start(self) -> None:
        """Build the body for this runtime, if enabled and not already closed."""
        if not self.enabled or self._closed:
            return
        if self.mode == "hardware":
            await asyncio.to_thread(self._start_hardware)
        else:
            self._start_sim()
        logger.info(
            "Robotics runtime started for '%s' (mode=%s)",
            self.character_id,
            self.mode,
        )

    def _start_sim(self) -> None:
        self._body = SimRobotBody(FakeWorld(), intent=self.intent)

    def _start_hardware(self) -> None:
        from .hardware import RoboticsController, RoboticsHardware
        from .transport import SerialTransport

        transport = SerialTransport(
            port=self.config.get("port", "/dev/ttyACM0"),
            baudrate=self.config.get("baudrate", 115200),
        )
        hardware = RoboticsHardware(transport)
        self._controller = RoboticsController(hardware)

    async def tick(self, delta: float = 1.0) -> None:
        """Execute one body step from the current intent."""
        if not self.enabled or self._closed:
            return
        if self._controller is not None:
            await asyncio.to_thread(self._tick_hardware, delta)
        elif self._body is not None:
            self._body.tick(delta)

    def _tick_hardware(self, delta: float) -> None:
        self._controller.body_intent = self.intent
        self._controller.execute_action(delta)

    async def close(self) -> None:
        """Safe-stop and release the body. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._controller is not None:
            await asyncio.to_thread(self._controller.close)
            self._controller = None
        self._body = None
        unregister_runtime(self.character_id, self)
        logger.info("Robotics runtime closed for '%s'", self.character_id)
