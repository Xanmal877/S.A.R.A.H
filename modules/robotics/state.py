"""Robotics state contract: body telemetry, intent, and action-result telemetry.

These are plain dataclasses with safe defaults. The contract mirrors a clear
separation of duties (mirroring how S.A.R.A.H. splits soul intent from body
telemetry, but kept self-contained here so the simulation has no hidden
dependencies):

- ``BodyState``  - factual physical telemetry. The body writes these; a
  navigation/planner layer reads them.
- ``BodyIntent`` - desired behavior. A planner writes these; the body reads
  them each ``tick``.
- ``ActionResult`` - outcome of a single body action, used for telemetry /
  event history rather than for control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Clockwise ordering; used so turning can be expressed as ``index + delta``.
HEADINGS: list[str] = ["north", "east", "south", "west"]

# Delta for each heading: (dx, dy).
DIRS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}

# Recognised actions a planner may write into BodyIntent.desired_action.
# Anything else is treated as "idle" by the body.
ACTIONS: tuple[str, ...] = (
    "idle",
    "move_forward",
    "turn_left",
    "turn_right",
    "dock",
    "undock",
    "charge",
)


def turn_heading(heading: str, steps: int) -> str:
    """Return the heading after turning ``steps`` quarter-turns (+/- clockwise).

    ``steps`` is mod 4, so turning right four times returns the original
    heading. Raises if ``heading`` is not a known heading.
    """
    index = HEADINGS.index(heading)  # raises ValueError on unknown heading
    return HEADINGS[(index + steps) % len(HEADINGS)]


@dataclass
class BodyState:
    """Factual physical telemetry about the simulated body."""

    position: tuple[int, int] = (3, 3)
    heading: str = "east"
    battery: float = 100.0
    is_charging: bool = False
    docked: bool = False
    left_motor: float = 0.0
    right_motor: float = 0.0
    last_move_succeeded: bool = True

    # Populated by ``sense()``; ``None`` means "no reading this frame".
    ultrasonic_cm: int | None = None
    # Line segments cast by the sensor layer this frame.
    sensor_rays: list[tuple[tuple[int, int], tuple[int, int]]] = field(
        default_factory=list
    )


@dataclass
class BodyIntent:
    """Desired behavior written by a planner, read by the body."""

    desired_action: str = "idle"
    target_position: tuple[int, int] | None = None
    reason: str = "Waiting for first tick."


@dataclass
class ActionResult:
    """Outcome of one action the body executed on a tick."""

    tick: int
    action: str
    succeeded: bool
    detail: str = ""
    position: tuple[int, int] = (0, 0)
    battery: float = 0.0
    heading: str = "east"
