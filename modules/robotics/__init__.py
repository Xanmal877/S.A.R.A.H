"""
Robotics module for S.A.R.A.H.

Two layers:

1. **Simulation & State** (deterministic, stdlib-only, suitable for planning/testing):
   - ``state``: BodyState/BodyIntent/ActionResult contracts
   - ``navigation``: FakeWorld (bounds/obstacles/chargers), NavigationHelper
   - ``sim_body``: Simulated body implementation

2. **Hardware & Transport** (real Arduino control or mockable for testing):
   - ``transport``: SerialTransport (real) and MockTransport (testing)
   - ``hardware``: RoboticsHardware (low-level commands), RoboticsController (high-level)

Hardware features:
- Line-based command/response protocol (compatible with Arduino serial)
- Acknowledgement-gated state updates
- Obstacle detection and refusal
- Safe stop on close
- Context manager support
- Lazy pyserial import (dependency-light)
- Full mock support for testing

Example:
    from modules.robotics.transport import SerialTransport, MockTransport
    from modules.robotics.hardware import RoboticsHardware, RoboticsController

    # Real hardware
    transport = SerialTransport(port="/dev/ttyACM0")
    hardware = RoboticsHardware(transport)
    controller = RoboticsController(hardware)
    controller.sense()
    controller.move_forward()
    controller.close()

    # Or mock for testing
    transport = MockTransport()
    with RoboticsHardware(transport) as hardware:
        hardware.ping()
"""

# Simulation & state layer (stdlib-only)
from .hardware import HardwareError, RoboticsController, RoboticsHardware
from .navigation import FakeWorld, NavigationHelper
from .runtime import RoboticsRuntime, get_runtime, register_runtime, unregister_runtime
from .sim_body import SimRobotBody, Telemetry
from .state import (
    ACTIONS,
    DIRS,
    HEADINGS,
    ActionResult,
    BodyIntent,
    BodyState,
    turn_heading,
)

# Hardware & transport layer (with optional pyserial)
from .transport import MockTransport, SerialTransport, Transport, TransportError

__all__ = [
    "ACTIONS",
    "DIRS",
    "HEADINGS",
    "ActionResult",
    "BodyIntent",
    "BodyState",
    "FakeWorld",
    "HardwareError",
    "MockTransport",
    "NavigationHelper",
    "RoboticsController",
    "RoboticsHardware",
    "RoboticsRuntime",
    "SerialTransport",
    "SimRobotBody",
    "Telemetry",
    "Transport",
    "TransportError",
    "get_runtime",
    "register_runtime",
    "turn_heading",
    "unregister_runtime",
]
