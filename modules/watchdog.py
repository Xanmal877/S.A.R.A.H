"""
Liveness watchdog + heartbeat for a character's autonomous loop.

``Restart=always`` in sarah.service cannot save a process that is wedged but
still alive: a deadlock stops the loop silently while systemd still sees a
healthy PID and never restarts it. That is the exact failure mode the liveness
watchdogs in Hermes Agent were written for (a gateway parked for ~30h in
``futex_wait_queue`` - every thread blocked, zero logs, live PID, supervisor
satisfied). S.A.R.A.H. runs the same way - unattended, always on, restarted
only by systemd - so it needs the same backstop.

``Watchdog`` is a daemon thread armed at loop entry. The loop calls
:meth:`Watchdog.kick` on every tick; if no kick arrives for ``timeout_s`` the
watchdog assumes the loop is parked and:

1. dumps every thread's stack with ``faulthandler`` to the dump file, so the
   *next* occurrence is diagnosable instead of silent;
2. appends a one-line JSON incident record;
3. exits with ``SERVICE_EXIT_CODE`` so systemd respawns a clean process.

It also writes a small ``heartbeat.json`` (every ``heartbeat_interval_s``, not
every tick) so an external monitor can read liveness and reflection health off
disk without touching the daemon.

Design notes (deliberate, matching the rest of this project):

- **Best-effort, never fatal.** Every filesystem operation is guarded: a
  broken watchdog must never affect the loop it observes. The fire path does
  no imports and never touches logging - the wedged loop may hold the import
  lock and the logging handlers' locks.
- **Slow is not dead.** The default timeout is deliberately generous (~15 min)
  because the loop legitimately blocks for seconds to minutes at a time
  (``spectacle`` capture, a local vision describe, a reasoning call).
  A watchdog that fires during normal heavy work is worse than none.
- **Env-only configuration.** ``SARAH_WATCHDOG=0`` disables it,
  ``SARAH_WATCHDOG_TIMEOUT_S`` overrides the deadline. It is armed before the
  heavy subsystem imports, so reading the JSON config here would put a file
  that may be mid-edit into the startup path.
- **Stdlib only** (``faulthandler``, ``threading``, ``json``, ``os``, ``time``),
  like the rest of ``modules/``.
"""

from __future__ import annotations

import faulthandler
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("Watchdog")

# systemd's Restart=always respawns on any non-zero exit. 75 (EX_TEMPFAIL)
# marks "restarted on purpose by the watchdog" distinctly from a real crash in
# the unit's history.
SERVICE_EXIT_CODE = 75

DEFAULT_TIMEOUT_S = 900.0
MIN_TIMEOUT_S = 60.0
DEFAULT_HEARTBEAT_INTERVAL_S = 15.0

# The waiter re-reads its deadline at most this often, so a kick takes effect
# promptly without busy-waiting.
DEFAULT_POLL_SLICE_S = 5.0

# Bounded join when disarming at shutdown.
_DISARM_JOIN_S = 2.0

ENV_WATCHDOG = "SARAH_WATCHDOG"
ENV_WATCHDOG_TIMEOUT_S = "SARAH_WATCHDOG_TIMEOUT_S"

_FALSEY = frozenset({"0", "false", "no", "off"})

DEFAULT_DUMP_PATH = "~/.sarah/watchdog.dump"
DEFAULT_INCIDENT_PATH = "~/.sarah/watchdog.log"
DEFAULT_HEARTBEAT_PATH = "~/.sarah/heartbeat.json"


def watchdog_disabled() -> bool:
    """True when ``SARAH_WATCHDOG`` opts out explicitly."""
    return os.environ.get(ENV_WATCHDOG, "").strip().lower() in _FALSEY


def resolve_watchdog_timeout() -> float:
    """Deadline in seconds: env override, floor-clamped, default on garbage."""
    raw = os.environ.get(ENV_WATCHDOG_TIMEOUT_S, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Ignoring non-numeric %s=%r; using default %.0fs",
            ENV_WATCHDOG_TIMEOUT_S, raw, DEFAULT_TIMEOUT_S,
        )
        return DEFAULT_TIMEOUT_S
    if value <= 0:
        return DEFAULT_TIMEOUT_S
    return max(value, MIN_TIMEOUT_S)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Watchdog:
    """Daemon-thread liveness guard for one autonomous loop.

    Usage (see ``agents/baseAgent.Run``)::

        watchdog = Watchdog().arm()
        while True:
            ...          # do a tick
            watchdog.kick()   # proof of life, every tick

    ``kick`` resets the deadline; nothing else does. Arm once at loop entry and
    ``disarm`` in the loop's ``finally`` so a normal shutdown is not mistaken
    for a stall.

    ``timeout_s=None`` (the default) resolves through :func:`resolve_watchdog_timeout`,
    so ``SARAH_WATCHDOG_TIMEOUT_S`` actually reaches the loop's watchdog.
    """

    def __init__(
        self,
        timeout_s: Optional[float] = None,
        dump_path: str = DEFAULT_DUMP_PATH,
        incident_path: str = DEFAULT_INCIDENT_PATH,
        heartbeat_path: Optional[str] = DEFAULT_HEARTBEAT_PATH,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        exit_code: int = SERVICE_EXIT_CODE,
        exit_fn: Callable[[int], None] = os._exit,
        clock_fn: Callable[[], float] = time.monotonic,
        poll_slice_s: float = DEFAULT_POLL_SLICE_S,
        name: str = "sarah-watchdog",
    ):
        if timeout_s is None:
            timeout_s = resolve_watchdog_timeout()
        self.timeout_s = max(float(timeout_s), MIN_TIMEOUT_S)
        self.dump_path = os.path.expanduser(dump_path)
        self.incident_path = os.path.expanduser(incident_path)
        self.heartbeat_path = os.path.expanduser(heartbeat_path) if heartbeat_path else None
        self.heartbeat_interval_s = max(float(heartbeat_interval_s), 0.0)
        self.exit_code = int(exit_code)
        self.exit_fn = exit_fn
        self.clock_fn = clock_fn
        self.poll_slice_s = max(float(poll_slice_s), 0.001)
        self.name = name

        now = self.clock_fn()
        self._deadline = now + self.timeout_s
        self._last_kick = now
        self._last_heartbeat = -float("inf")
        self._lock = threading.Lock()
        self._armed = False
        self._fired = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ===== Lifecycle

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def fired(self) -> bool:
        """True once the watchdog has begun firing (exit is imminent)."""
        return self._fired

    def arm(self) -> "Watchdog":
        """Start the waiter thread. Idempotent; safe to call before the loop."""
        if self._armed:
            return self
        now = self.clock_fn()
        with self._lock:
            self._armed = True
            self._last_kick = now
            self._deadline = now + self.timeout_s
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()
        logger.info(
            "Watchdog armed (timeout %.0fs, dump %s, heartbeat %s)",
            self.timeout_s, self.dump_path, self.heartbeat_path or "off",
        )
        return self

    def disarm(self) -> None:
        """Stop the waiter without treating shutdown as a stall."""
        with self._lock:
            was_armed = self._armed
            self._armed = False
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=_DISARM_JOIN_S)
        if was_armed:
            logger.info("Watchdog disarmed")

    # ===== Liveness

    def kick(self, value: Optional[Dict[str, Any]] = None) -> None:
        """Report progress: reset the deadline and (interval-gated) heartbeat.

        Called every tick by the loop, so the heartbeat write is rate-limited
        rather than doing a filesystem write per second for days on end.
        """
        now = self.clock_fn()
        with self._lock:
            self._last_kick = now
            self._deadline = now + self.timeout_s

        if self.heartbeat_path is None:
            return
        if (now - self._last_heartbeat) < self.heartbeat_interval_s:
            return
        self._last_heartbeat = now
        payload = {"pid": os.getpid(), "ts": _utc_now_iso()}
        if value:
            payload.update(value)
        self._write_heartbeat(payload)

    def seconds_until_fire(self) -> float:
        """Seconds left before the watchdog fires (negative once overdue)."""
        with self._lock:
            return self._deadline - self.clock_fn()

    # ===== Waiter thread

    def _run(self) -> None:
        while not self._stop.wait(self.poll_slice_s):
            with self._lock:
                if not self._armed:
                    return
                overdue = self.clock_fn() >= self._deadline
            if overdue:
                self._fire()
                return

    def _fire(self) -> None:
        """Forensics, then hard-exit so systemd respawns us.

        Deliberately import-free and logging-free: the wedged main thread may
        hold the import lock and the logging locks, and this runs on the
        watchdog thread.
        """
        with self._lock:
            self._fired = True
            stall_s = self.clock_fn() - self._last_kick
        self._write_dump(stall_s)
        self._write_incident(stall_s)
        try:
            self.exit_fn(self.exit_code)
        except Exception:
            os._exit(self.exit_code)

    # ===== Files (all best-effort)

    def _write_dump(self, stall_s: float) -> None:
        """Append a stack dump for every thread. Failure is not fatal."""
        try:
            os.makedirs(os.path.dirname(self.dump_path) or ".", exist_ok=True)
            with open(self.dump_path, "a", encoding="utf-8") as fh:
                fh.write(
                    f"\n===== watchdog fire {_utc_now_iso()} "
                    f"(pid {os.getpid()}, no progress for {stall_s:.0f}s, "
                    f"timeout {self.timeout_s:.0f}s) =====\n"
                )
                fh.flush()
                faulthandler.dump_traceback(file=fh, all_threads=True)
        except Exception:
            pass

    def _write_incident(self, stall_s: float) -> None:
        """Append one JSON incident record. Failure is not fatal."""
        record = {
            "ts": _utc_now_iso(),
            "pid": os.getpid(),
            "reason": "no_progress",
            "stall_s": round(stall_s, 1),
            "timeout_s": self.timeout_s,
            "exit_code": self.exit_code,
            "dump": self.dump_path,
        }
        try:
            os.makedirs(os.path.dirname(self.incident_path) or ".", exist_ok=True)
            with open(self.incident_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass

    def _write_heartbeat(self, payload: Dict[str, Any]) -> None:
        """Atomically replace the heartbeat file. Failure is not fatal."""
        path = self.heartbeat_path
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, default=str)
            os.replace(tmp, path)
        except Exception:
            pass
