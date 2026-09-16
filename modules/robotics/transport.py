"""
Dependency-light serial transport layer for Arduino robotics communication.

Supports both real serial connections and mocking for testing.
Delays pyserial import to module runtime, not import time.

This is a low-level, synchronous API. Integration code using these classes
should execute them via asyncio.to_thread() if needed for non-blocking I/O.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger("robotics.transport")


class TransportError(Exception):
    """Base exception for transport layer failures."""


class Transport(ABC):
    """Abstract transport interface for robotics hardware communication."""

    @abstractmethod
    def send(self, command: str) -> str:
        """Send a command and receive a line-based response.
        
        BLOCKING: This is synchronous I/O. For async use, wrap with
        asyncio.to_thread().
        
        Args:
            command: Command string (newline will be added).
            
        Returns:
            Response string (stripped).
            
        Raises:
            TransportError: On communication failure.
        """

    @abstractmethod
    def close(self) -> None:
        """Close the transport connection."""


class SerialTransport(Transport):
    """Real serial connection to Arduino or compatible device.
    
    Delays pyserial import to first instantiation, avoiding hard dependency at module load.
    """

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baudrate: int = 115200,
        timeout: float = 1.0,
        boot_delay: float = 2.0,
    ) -> None:
        """Initialize serial transport.
        
        Args:
            port: Serial port (e.g., "/dev/ttyACM0", "COM3").
            baudrate: Baud rate (default 115200).
            timeout: Read timeout in seconds (default 1.0).
            boot_delay: Delay after opening port to flush boot messages (default 2.0).
            
        Raises:
            TransportError: If port cannot be opened.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: object = None
        
        try:
            import serial
        except ImportError as e:
            raise TransportError(
                "pyserial not installed. Install with: pip install pyserial"
            ) from e
        
        try:
            self.serial = serial.Serial(port, baudrate, timeout=timeout)
            logger.info(f"Opened serial port {port} at {baudrate} baud")
            
            # Wait for Arduino boot and flush any boot messages
            time.sleep(boot_delay)
            self._flush_boot()
            
        except Exception as e:
            raise TransportError(f"Failed to open port {port}: {e}") from e

    def _flush_boot(self) -> None:
        """Drain any boot/startup messages from the serial buffer."""
        if not self.serial:
            return
            
        try:
            while self.serial.in_waiting:
                line = self.serial.readline().decode(errors="ignore").strip()
                if line:
                    logger.debug(f"[Serial Boot] {line}")
        except (OSError, AttributeError) as e:
            logger.warning(f"Error flushing boot messages: {e}")

    def send(self, command: str) -> str:
        """Send a line-based command and receive a response.
        
        BLOCKING: This is a synchronous operation. For async use, wrap with
        asyncio.to_thread().
        
        Args:
            command: Command string.
            
        Returns:
            Response string (stripped).
            
        Raises:
            TransportError: On communication failure.
        """
        if not self.serial or not self.serial.is_open:
            raise TransportError("Serial port is not open")
        
        try:
            # Send command with newline
            self.serial.write((command.strip() + "\n").encode())
            self.serial.flush()
            
            # Read response line
            response = self.serial.readline().decode(errors="ignore").strip()
            return response
            
        except Exception as e:
            raise TransportError(f"Serial communication error: {e}") from e

    def close(self) -> None:
        """Close the serial port."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info(f"Closed serial port {self.port}")


class MockTransport(Transport):
    """Mock transport for testing without hardware.
    
    Simulates responses based on command patterns. Useful for development,
    testing, and CI environments.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        echo_commands: bool = False,
    ) -> None:
        """Initialize mock transport.
        
        Args:
            responses: Dictionary mapping commands to responses.
                      If None, uses default mock responses.
                      Use '*' as a catch-all key for unmatched commands.
            echo_commands: If True, unknown commands return the command itself.
        """
        self.echo_commands = echo_commands
        self.command_log: list[str] = []
        self.is_open = True
        
        # Default mock responses
        self.responses: dict[str, str] = {
            "PING": "PONG",
            "GET_VERSION": "1.0.0",
            "STOP": "OK",
            "MOVE_FORWARD": "OK",
            "TURN_LEFT": "OK",
            "TURN_RIGHT": "OK",
            "GET_DISTANCE": "DISTANCE|45.5",
            "*": "OK",  # Catch-all for unmatched commands
        }
        
        # Override with user-provided responses
        if responses:
            self.responses.update(responses)
        
        logger.info("Initialized mock transport")

    def send(self, command: str) -> str:
        """Send a mock command and return a simulated response.
        
        Args:
            command: Command string.
            
        Returns:
            Simulated response.
            
        Raises:
            TransportError: If mock is closed.
        """
        if not self.is_open:
            raise TransportError("Mock transport is closed")
        
        command_stripped = command.strip()
        self.command_log.append(command_stripped)
        
        # Try exact match first
        if command_stripped in self.responses:
            response = self.responses[command_stripped]
        # Try prefix match (e.g., "SET_SERVO|0|90" matches "SET_SERVO")
        else:
            # Find first matching prefix (skip catch-all)
            matching_keys = [
                k for k in self.responses
                if k != "*" and command_stripped.startswith(k)
            ]
            if matching_keys:
                response = self.responses[matching_keys[0]]
            else:
                # Fall back to catch-all or echo
                response = (
                    self.responses.get("*", command_stripped)
                    if self.echo_commands
                    else self.responses.get("*", "OK")
                )
        
        logger.debug(f"[Mock] {command_stripped} -> {response}")
        return response

    def close(self) -> None:
        """Close the mock transport."""
        self.is_open = False
        logger.info(f"Closed mock transport after {len(self.command_log)} commands")

    def get_command_log(self) -> list[str]:
        """Return list of commands sent to mock transport."""
        return self.command_log.copy()
