"""Simulated robot body implementing a deterministic sense/tick loop.

``SimRobotBody`` owns a ``BodyState`` (physical telemetry) and reads a
``BodyIntent`` (planner intent) each tick. This mirrors the intent/telеmetry
split used elsewhere in S.A.R.A.H., but keeps the simulation self-contained:
no external soul/body wiring is required. The caller is responsible for
feeding a ``BodyIntent``; a fresh body starts with a default idle intent and
a fully-charged battery.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .navigation import FakeWorld
from .state import DIRS, ActionResult, BodyIntent, BodyState, turn_heading

logger = logging.getLogger("SimRobotBody")

# Body constants (same semantics as Anna's robot body).
MOVE_DRAIN = 0.35
TURN_DRAIN = 0.15
PASSIVE_DRAIN = 0.08
CHARGE_RATE = 2.5

_DETAIL_IDSLE = "No action requested; body sitting idle."
_DETAIL_MOVE_BLOCKED = "Move blocked; position unchanged."
_DETAIL_MOVE_OK = "Forward step taken."
_DETAIL_DOCK_OK = "Docked at charging station."
_DETAIL_DOCK_NOT_CHARGER = "Dock refused: not on a charging pad."
_DETAIL_CHARGE_NOT_CHARGER = "Charge refused: not on a charging pad."
_DETAIL_CHARGE_OK = "Charging."
_DETAIL_UNDOCK_OK = "Undocked."


class SimRobotBody:
    """Deterministic simulated body on a ``FakeWorld``.

    ``tick()`` executes the intent's ``desired_action`` (with collision
    refusal, battery drain, charging, and docking), applies passive drain, and
    records an ``ActionResult`` in telemetry. ``sense()`` refreshes raw sensor
    readings into ``self.state`` without changing state that affects physics.
    """

    def _succeed(self, action: str, detail: str) -> None:
        self.state.last_move_succeeded = True
        self._record(action, True, detail)

    def _fail(self, action: str, detail: str) -> None:
        self.state.last_move_succeeded = False
        self._record(action, False, detail)

    def _record(self, action: str, succeeded: bool, detail: str) -> None:
        result = ActionResult(
            tick=self._tick_count,
            action=action,
            succeeded=succeeded,
            detail=detail,
            position=self.state.position,
            heading=self.state.heading,
            battery=self.state.battery,
        )
        self.telemetry.push(result)
        self._emit(f"[tick {self._tick_count}] {action}: {detail}")
        logger.debug(
            "action result: action=%r succeeded=%s detail=%r at=%s battery=%.1f",
            action,
            succeeded,
            detail,
            self.state.position,
            self.state.battery,
        )

    def __init__(
        self,
        world: FakeWorld,
        intent: BodyIntent | None = None,
        event_log: Callable[[str], None] | None = None,
    ) -> None:
        """Create a body attached to ``world``.

        ``intent`` defaults to a fresh idle intent; ``event_log`` is an
        optional callable receiving human-readable messages about each action
        (used purely for observability, not for control flow).
        """
        self.world = world
        self.state = BodyState()
        self.intent = intent or BodyIntent()
        self.telemetry = Telemetry()
        self._tick_count = 0
        self._event_log = event_log or (lambda _msg: None)

    def __repr__(self) -> str:
        return (
            f"SimRobotBody(pos={self.state.position}, "
            f"heading={self.state.heading!r}, battery={self.state.battery:.1f})"
        )

    @property
    def current_position(self) -> tuple[int, int]:
        return self.state.position

    @property
    def current_heading(self) -> str:
        return self.state.heading

    # ---- sense ------------------------------------------------------

    def sense(self) -> None:
        """Refresh raw sensor readings into ``self.state``.

        Does not consume battery or move the body. A ``None`` ultrasonic
        reading means "no obstacle within range this frame".
        """
        state = self.state
        state.ultrasonic_cm = self.world.ultrasonic_cm(state.position, state.heading)
        state.sensor_rays = [self.world.sensor_ray(state.position, state.heading)]
        # Charging only persists while actually on a pad.
        if state.position not in self.world.chargers:
            state.is_charging = False

    # ---- tick -------------------------------------------------------

    def tick(
        self,
        delta: float = 1.0,
        world: FakeWorld | None = None,
        intent: BodyIntent | None = None,
    ) -> None:
        """Execute one simulation step.

        Optionally accepts an override ``world`` and / or ``intent`` for a
        single tick; when omitted the body's stored world / intent are used.
        This is convenient for tests that vary the world per tick.
        """
        if world is not None:
            self.world = world
        if intent is not None:
            self.intent = intent

        self._tick_count += 1
        action = self.intent.desired_action

        if action == "move_forward":
            self._move_forward()
        elif action == "turn_left":
            self._turn(-1)
        elif action == "turn_right":
            self._turn(1)
        elif action == "dock":
            self._dock()
        elif action == "undock":
            self._undock()
        elif action == "charge":
            self._charge(delta)
        else:
            self._idle(action)

        self._passive_drain(delta)

    def _move_forward(self) -> None:
        new_position = self._forward_position()
        if self.world.is_blocked(new_position):
            self._fail("move_forward", _DETAIL_MOVE_BLOCKED)
            self._emit("Move blocked.")
            return
        self.state.position = new_position
        self._succeed("move_forward", _DETAIL_MOVE_OK)
        self._drain(MOVE_DRAIN)

    def _turn(self, steps: int) -> None:
        action = "turn_right" if steps > 0 else "turn_left"
        self.state.heading = turn_heading(self.state.heading, steps)
        self._succeed(action, f"Turned {abs(steps)} quarter-turn(s).")
        self._drain(TURN_DRAIN)

    def _dock(self) -> None:
        if self.state.position not in self.world.chargers:
            self._fail("dock", _DETAIL_DOCK_NOT_CHARGER)
            return
        self.state.docked = True
        self.state.is_charging = True
        self._succeed("dock", _DETAIL_DOCK_OK)
        self._emit("Docked at charging station.")

    def _undock(self) -> None:
        self.state.docked = False
        self.state.is_charging = False
        self._succeed("undock", _DETAIL_UNDOCK_OK)
        self._emit("Undocked.")

    def _charge(self, delta: float) -> None:
        if self.state.position not in self.world.chargers:
            self.state.is_charging = False
            self._fail("charge", _DETAIL_CHARGE_NOT_CHARGER)
            return
        self.state.is_charging = True
        self.state.battery = min(100.0, self.state.battery + CHARGE_RATE * delta)
        self._succeed("charge", _DETAIL_CHARGE_OK)

    def _idle(self, action: str) -> None:
        # Report the actual requested action verb, even when idle.
        verb = action if action else "idle"
        self.state.left_motor = 0.0
        self.state.right_motor = 0.0
        self._succeed(verb, _DETAIL_IDSLE)

    # ---- internals --------------------------------------------------

    def _forward_position(self) -> tuple[int, int]:
        x, y = self.state.position
        dx, dy = self._heading_delta(self.state.heading)
        return x + dx, y + dy

    def _heading_delta(self, heading: str) -> tuple[int, int]:
        return DIRS[heading]

    def _drain(self, amount: float) -> None:
        self.state.battery = max(0.0, self.state.battery - amount)

    def _passive_drain(self, delta: float) -> None:
        if not self.state.is_charging:
            self._drain(PASSIVE_DRAIN * delta)

    def _emit(self, message: str) -> None:
        self._event_log(message)


class Telemetry:
    """Append-only log of ``ActionResult`` records (action telemetry)."""

    def __init__(self, max_len: int = 500) -> None:
        self.records: list[ActionResult] = []
        self._max_len = max_len

    def push(self, result: ActionResult) -> None:
        self.records.append(result)
        if len(self.records) > self._max_len:
            self.records = self.records[-self._max_len :]

    @property
    def last(self) -> ActionResult | None:
        return self.records[-1] if self.records else None

    @property
    def count(self) -> int:
        return len(self.records)

    def succeeded_recently(self, action: str, limit: int = 10) -> bool:
        """Whether the most recent ``limit`` records include a success for ``action``."""
        for record in self.records[-limit:]:
            if record.action == action and record.succeeded:
                return True
        return False
