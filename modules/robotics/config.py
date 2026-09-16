"""Robotics runtime configuration.

Reads the optional ``robotics`` section from ``~/.sarah/hive_config.json``.
Robotics is disabled by default; a node only gets a runtime when it
explicitly opts in by setting ``robotics.enabled`` to true. This keeps the
existing behavior of every other node unchanged.
"""

from __future__ import annotations

DEFAULT_ROBOTICS_CONFIG = {
    "enabled": False,
    "mode": "sim",          # "sim" (SimRobotBody) or "hardware" (acked controller)
    "port": "/dev/ttyACM0",
    "baudrate": 115200,
}


def load_robotics_config() -> dict:
    """Return the robotics config section, merged over safe defaults.

    Missing keys fall back to the defaults above; a missing or malformed
    ``robotics`` section simply yields the defaults (robotics stays off).
    """
    cfg = dict(DEFAULT_ROBOTICS_CONFIG)
    try:
        from modules.hive.config import load_config

        section = load_config().get("robotics") or {}
        cfg.update(section)
    except Exception as exc:  # noqa: BLE001 - config must never break startup
        import logging

        logging.getLogger("robotics.config").debug(
            "Using default robotics config: %s", exc
        )
    return cfg
