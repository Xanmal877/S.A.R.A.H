"""
Arduino robotics hardware adapter for S.A.R.A.H.

Provides a hardware abstraction layer for Arduino-based robot control,
featuring acknowledgement-gated state updates, obstacle detection, safe stop,
and line-based command/response protocol.

This module uses synchronous blocking APIs. Integration code should wrap these
with asyncio.to_thread() for non-blocking I/O.

Adapted from Anna/anna/body/arduino_body.py with S.A.R.A.H-specific patterns.
"""

from __future__ import annotations

import logging
import types
from typing import Self

from .state import ActionResult, BodyIntent, BodyState, turn_heading
from .transport import Transport, TransportError

logger = logging.getLogger("robotics.hardware")


class HardwareError(Exception):
    """Base exception for hardware layer failures."""


class RoboticsHardware:
    """Arduino robotics hardware interface with safe, acknowledged state updates.
    
    Synchronous low-level API. For async usage, wrap with asyncio.to_thread().
    """

    def __init__(self, transport: Transport) -> None:
        """Initialize hardware adapter.
        
        Args:
            transport: Transport instance (SerialTransport or MockTransport).
            
        Raises:
            HardwareError: If transport is invalid.
        """
        if not transport:
            raise HardwareError("Transport instance required")
        
        self.transport = transport
        self.last_command_succeeded = False
        self.obstacle_threshold_cm = 12.0
        self.current_distance_cm: float | None = None
        
        logger.info("Initialized robotics hardware")

    def _send_command(self, command: str) -> str:
        """Send a command via transport with error handling.
        
        Args:
            command: Command string.
            
        Returns:
            Response string (stripped).
            
        Raises:
            HardwareError: On communication failure.
        """
        try:
            response = self.transport.send(command)
            logger.debug(f"[Hardware] {command} -> {response}")
            return response
        except TransportError as e:
            raise HardwareError(f"Communication failed: {e}") from e

    def _expect_response(self, command: str, expected: str) -> bool:
        """Send command and verify expected response (acknowledgement gate).
        
        Updates last_command_succeeded based on response match.
        
        Args:
            command: Command string.
            expected: Expected response string.
            
        Returns:
            True if response matches expected (acknowledged), False otherwise.
        """
        try:
            response = self._send_command(command)
            succeeded = response == expected
            self.last_command_succeeded = succeeded
            
            if not succeeded:
                logger.warning(
                    f"Command '{command}' failed: expected '{expected}', got '{response}'"
                )
            
            return succeeded
        except HardwareError as e:
            self.last_command_succeeded = False
            logger.error(f"Command '{command}' error: {e}")
            return False

    # Core control commands

    def ping(self) -> bool:
        """Ping hardware to verify connection.
        
        Returns:
            True if hardware responds with PONG.
        """
        return self._expect_response("PING", "PONG")

    def get_version(self) -> str | None:
        """Request hardware version string.
        
        Returns:
            Version string, or None on failure.
        """
        try:
            response = self._send_command("GET_VERSION")
            if response:
                return response
        except HardwareError:
            pass
        return None

    def stop(self) -> bool:
        """Stop all motors immediately (safe stop).
        
        Returns:
            True if hardware acknowledged stop.
        """
        return self._expect_response("STOP", "OK")

    # Motor and servo control

    def move_forward(self) -> bool:
        """Execute forward movement.
        
        Returns:
            True if hardware acknowledged command.
        """
        return self._expect_response("MOVE_FORWARD", "OK")

    def turn_left(self) -> bool:
        """Execute left turn.
        
        Returns:
            True if hardware acknowledged command.
        """
        return self._expect_response("TURN_LEFT", "OK")

    def turn_right(self) -> bool:
        """Execute right turn.
        
        Returns:
            True if hardware acknowledged command.
        """
        return self._expect_response("TURN_RIGHT", "OK")

    def set_servo(self, servo_index: int, angle: int) -> bool:
        """Set servo position.
        
        Args:
            servo_index: Servo ID (typically 0 for steering).
            angle: Angle in degrees (typically 0-180).
            
        Returns:
            True if hardware acknowledged command.
        """
        command = f"SET_SERVO|{servo_index}|{angle}"
        return self._expect_response(command, "OK")

    def display_message(self, line1: str, line2: str = "") -> bool:
        """Display text on hardware LCD (if available).
        
        Args:
            line1: First line text (max ~16 chars, pipes/bars replaced).
            line2: Second line text (max ~16 chars, pipes/bars replaced).
            
        Returns:
            True if hardware acknowledged command.
        """
        # Sanitize display text: max 16 chars, replace pipes with slashes
        line1 = line1.replace("|", "/")[:16]
        line2 = line2.replace("|", "/")[:16]
        command = f"DISPLAY|{line1}|{line2}"
        return self._expect_response(command, "OK")

    # Sensing

    def read_distance(self) -> float | None:
        """Read ultrasonic distance sensor.
        
        Parses response format: "DISTANCE|<float>"
        Updates internal state for obstacle detection.
        
        Returns:
            Distance in cm, or None on failure/invalid reading.
        """
        self.current_distance_cm = None
        try:
            response = self._send_command("GET_DISTANCE")
            
            if not response.startswith("DISTANCE|"):
                logger.warning(f"Invalid distance response format: {response}")
                return None
            
            # Parse: "DISTANCE|45.5"
            try:
                distance_str = response.split("|", 1)[1]
                distance = float(distance_str)
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse distance: {response} ({e})")
                return None
            
            # Reject negative distances
            if distance < 0:
                logger.warning(f"Negative distance reading rejected: {distance}")
                return None
            
            self.current_distance_cm = distance
            return distance
            
        except HardwareError as e:
            logger.error(f"Failed to read distance: {e}")
            return None

    # Obstacle detection and safety

    def obstacle_too_close(self) -> bool:
        """Check if obstacle is too close based on last sensor reading.
        
        Uses current_distance_cm (set by read_distance) and obstacle_threshold_cm.
        
        Returns:
            True if obstacle detected within threshold, False otherwise.
        """
        if self.current_distance_cm is None:
            return False
        return self.current_distance_cm < self.obstacle_threshold_cm

    def set_obstacle_threshold(self, cm: float) -> None:
        """Configure obstacle detection threshold.
        
        Args:
            cm: Distance threshold in centimeters.
        """
        if cm <= 0:
            logger.warning(
                f"Invalid obstacle threshold: {cm}, "
                f"keeping {self.obstacle_threshold_cm}"
            )
            return
        self.obstacle_threshold_cm = cm
        logger.info(f"Set obstacle threshold to {cm}cm")

    # Lifecycle

    def close(self) -> None:
        """Close hardware connection and cleanup.
        
        Attempts safe stop before closing.
        """
        try:
            # Attempt safe stop
            self.stop()
        except HardwareError as e:
            logger.warning(f"Error during safe stop on close: {e}")
        
        try:
            # Close transport
            self.transport.close()
            logger.info("Closed robotics hardware")
        except OSError as e:
            logger.error(f"Error closing transport: {e}")

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool:
        """Context manager exit."""
        self.close()
        return False


class BodyStateAdapter:
    """High-level robot control with state-based intent/telemetry.
    
    This adapter bridges BodyState/BodyIntent/ActionResult contracts with the
    low-level hardware layer. It enforces acknowledgement-gating, obstacle
    avoidance, and action telemetry.
    
    Synchronous low-level API; wrap with asyncio.to_thread() for async usage.
    """

    def __init__(self, hardware: RoboticsHardware) -> None:
        """Initialize state adapter.
        
        Args:
            hardware: RoboticsHardware instance.
        """
        self.hardware = hardware
        self.body_state = BodyState()
        self.body_intent = BodyIntent()
        self.tick_count = 0
        self.action_history: list[ActionResult] = []
        
        logger.info("Initialized BodyStateAdapter")

    def sense(self) -> None:
        """Poll sensors and update body_state telemetry.
        
        Called regularly to refresh sensor data and update BodyState with
        current sensor readings. Distance is stored in body_state.ultrasonic_cm.
        """
        distance = self.hardware.read_distance()
        if distance is not None:
            self.body_state.ultrasonic_cm = int(distance)
            logger.debug(f"Sensed distance: {distance:.1f}cm")
        else:
            self.body_state.ultrasonic_cm = None

    def set_intent(self, desired_action: str, target_pos: tuple[int, int] | None = None,
                   reason: str = "") -> None:
        """Set the desired action for the next tick.
        
        Args:
            desired_action: Action name (from state.ACTIONS).
            target_pos: Optional target position for navigation.
            reason: Brief reason for the action (logged).
        """
        self.body_intent.desired_action = desired_action
        self.body_intent.target_position = target_pos
        self.body_intent.reason = reason

    def execute_action(self, delta: float = 1.0) -> ActionResult:
        """Execute the intended action and return telemetry.
        
        Acknowledgement-gated: body_state only updates on successful hardware
        response. Obstacle detection gates movement. Returns detailed ActionResult
        for event history and logging.
        
        Returns:
            ActionResult with tick, action, success flag, and telemetry snapshot.
        """
        self.tick_count += 1
        action = self.body_intent.desired_action
        succeeded = False
        detail = ""
        
        # Sense first to get fresh obstacle data
        self.sense()
        
        if action == "move_forward":
            # Check obstacle before moving
            if self.hardware.obstacle_too_close():
                detail = (
                    f"Obstacle detected at {self.hardware.current_distance_cm}cm "
                    f"(threshold: {self.hardware.obstacle_threshold_cm}cm)"
                )
                logger.warning(f"Movement refused: {detail}")
            elif self.hardware.move_forward():
                # Hardware acknowledged; update position on axis of heading
                dx, dy = self._get_heading_delta()
                new_pos = (
                    self.body_state.position[0] + dx,
                    self.body_state.position[1] + dy,
                )
                self.body_state.position = new_pos
                self.body_state.last_move_succeeded = True
                self.body_state.battery = max(0.0, self.body_state.battery - 0.35)
                succeeded = True
                detail = f"Moved to {new_pos}"
                logger.info(detail)
            else:
                detail = "Hardware move_forward failed"
                logger.error(detail)
                self.body_state.last_move_succeeded = False
        
        elif action == "turn_left":
            if self.hardware.turn_left():
                # Hardware acknowledged; update heading
                self.body_state.heading = turn_heading(self.body_state.heading, -1)
                succeeded = True
                detail = f"Turned left, heading now {self.body_state.heading}"
                logger.info(detail)
            else:
                detail = "Hardware turn_left failed"
                logger.error(detail)
        
        elif action == "turn_right":
            if self.hardware.turn_right():
                # Hardware acknowledged; update heading
                self.body_state.heading = turn_heading(self.body_state.heading, 1)
                succeeded = True
                detail = f"Turned right, heading now {self.body_state.heading}"
                logger.info(detail)
            else:
                detail = "Hardware turn_right failed"
                logger.error(detail)
        
        elif action == "idle":
            succeeded = True
            detail = "Idling"
        
        else:
            detail = f"Unknown action: {action}"
            logger.warning(detail)

        if action in ("turn_left", "turn_right") and succeeded:
            self.body_state.battery = max(0.0, self.body_state.battery - 0.15)
        if action not in ("charge",) and not self.body_state.is_charging:
            self.body_state.battery = max(0.0, self.body_state.battery - 0.08 * delta)
        self.body_state.last_move_succeeded = succeeded
        
        # Create telemetry snapshot
        result = ActionResult(
            tick=self.tick_count,
            action=action,
            succeeded=succeeded,
            detail=detail,
            position=self.body_state.position,
            heading=self.body_state.heading,
            battery=self.body_state.battery,
        )
        
        self.action_history.append(result)
        return result

    def safe_stop(self) -> bool:
        """Execute safe stop.
        
        Returns:
            True if hardware acknowledged stop.
        """
        if self.hardware.stop():
            logger.info("Safe stop executed")
            return True
        else:
            logger.error("Safe stop failed")
            return False

    def get_body_state(self) -> BodyState:
        """Return current body state snapshot."""
        return self.body_state

    def _get_heading_delta(self) -> tuple[int, int]:
        """Get (dx, dy) movement delta for current heading."""
        from .state import DIRS
        return DIRS.get(self.body_state.heading, (0, 0))

    def close(self) -> None:
        """Shutdown: safe stop and close hardware."""
        self.hardware.close()

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool:
        """Context manager exit."""
        self.close()
        return False


# Backward compatibility alias
RoboticsController = BodyStateAdapter
