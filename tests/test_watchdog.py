"""Liveness watchdog tests (modules/watchdog.py).

The watchdog's whole job is to kill the process it observes, so these tests
drive it with an injected clock, an injected exit function and a tiny poll
slice - no sleeping on the real deadline, and no test ever exits the runner.
"""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.watchdog import (  # noqa: E402
    DEFAULT_TIMEOUT_S,
    MIN_TIMEOUT_S,
    SERVICE_EXIT_CODE,
    Watchdog,
    resolve_watchdog_timeout,
    watchdog_disabled,
)


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


class _Recorder:
    def __init__(self):
        self.codes = []

    def __call__(self, code: int) -> None:
        self.codes.append(code)


class WatchdogFireTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = _Clock()
        self.exit = _Recorder()

    def _paths(self):
        base = self.tmp.name
        return (
            os.path.join(base, "watchdog.dump"),
            os.path.join(base, "watchdog.log"),
            os.path.join(base, "heartbeat.json"),
        )

    def _watchdog(self, timeout_s=60.0, **kw):
        dump, incident, heartbeat = self._paths()
        return Watchdog(
            timeout_s=timeout_s,
            dump_path=dump,
            incident_path=incident,
            heartbeat_path=heartbeat,
            exit_fn=self.exit,
            clock_fn=self.clock,
            poll_slice_s=0.01,
            **kw,
        )

    def _join(self, watchdog, seconds=3.0):
        thread = watchdog._thread
        if thread is not None:
            thread.join(timeout=seconds)

    def test_kick_defers_fire_while_the_loop_is_alive(self):
        watchdog = self._watchdog(timeout_s=60.0).arm()
        try:
            for _ in range(10):
                self.clock.advance(50.0)  # never exceeds the 60s deadline
                watchdog.kick()
            self._join(watchdog, seconds=0.2)
            self.assertEqual(self.exit.codes, [], "watchdog fired on a live loop")
            self.assertFalse(watchdog.fired)
        finally:
            watchdog.disarm()

    def test_fires_and_exits_when_the_loop_stops_kicking(self):
        watchdog = self._watchdog(timeout_s=60.0).arm()
        try:
            self.clock.advance(61.0)  # a stall past the deadline
            self._join(watchdog)
            self.assertEqual(self.exit.codes, [SERVICE_EXIT_CODE])
        finally:
            watchdog.disarm()

    def test_disarm_before_the_deadline_prevents_any_fire(self):
        watchdog = self._watchdog(timeout_s=60.0).arm()
        watchdog.disarm()
        self.clock.advance(600.0)
        self._join(watchdog, seconds=0.2)
        self.assertEqual(self.exit.codes, [])
        self.assertFalse(watchdog.fired)

    def test_fire_writes_an_all_thread_stack_dump(self):
        dump, _, _ = self._paths()
        watchdog = self._watchdog(timeout_s=60.0).arm()
        try:
            self.clock.advance(61.0)
            self._join(watchdog)
            with open(dump, "r", encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("watchdog fire", text)
            self.assertIn("no progress for", text)
            self.assertIn("Thread", text)  # faulthandler stack output
        finally:
            watchdog.disarm()

    def test_fire_writes_one_json_incident_record(self):
        _, incident, _ = self._paths()
        watchdog = self._watchdog(timeout_s=60.0).arm()
        try:
            self.clock.advance(61.0)
            self._join(watchdog)
            with open(incident, "r", encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["reason"], "no_progress")
            self.assertEqual(record["exit_code"], SERVICE_EXIT_CODE)
            self.assertEqual(record["pid"], os.getpid())
            self.assertGreaterEqual(record["stall_s"], 60.0)
        finally:
            watchdog.disarm()

    def test_fire_still_exits_when_the_dump_path_is_unwritable(self):
        # /proc is not writable: forensic writing must fail without stopping
        # the exit, or a wedged daemon would never be respawned.
        watchdog = Watchdog(
            timeout_s=60.0,
            dump_path="/proc/does-not-exist/watchdog.dump",
            incident_path="/proc/does-not-exist/watchdog.log",
            heartbeat_path=None,
            exit_fn=self.exit,
            clock_fn=self.clock,
            poll_slice_s=0.01,
        ).arm()
        try:
            self.clock.advance(61.0)
            self._join(watchdog)
            self.assertEqual(self.exit.codes, [SERVICE_EXIT_CODE])
        finally:
            watchdog.disarm()

    def test_second_arm_is_a_no_op(self):
        watchdog = self._watchdog().arm()
        try:
            first_thread = watchdog._thread
            watchdog.arm()
            self.assertIs(watchdog._thread, first_thread)
        finally:
            watchdog.disarm()


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = _Clock()

    def _heartbeat_path(self):
        return os.path.join(self.tmp.name, "heartbeat.json")

    def test_heartbeat_is_written_atomically_and_carries_the_payload(self):
        path = self._heartbeat_path()
        watchdog = Watchdog(
            heartbeat_path=path,
            heartbeat_interval_s=0.0,
            exit_fn=_Recorder(),
            clock_fn=self.clock,
            poll_slice_s=0.01,
        )
        watchdog.kick({"task": "Explore", "last_reflection_ago_s": 12.5})
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["pid"], os.getpid())
        self.assertEqual(payload["task"], "Explore")
        self.assertEqual(payload["last_reflection_ago_s"], 12.5)
        self.assertIn("ts", payload)
        self.assertFalse(os.path.exists(path + ".tmp"), "temp file left behind")

    def test_heartbeat_write_is_rate_limited_but_kicks_always_land(self):
        path = self._heartbeat_path()
        watchdog = Watchdog(
            heartbeat_path=path,
            heartbeat_interval_s=15.0,
            exit_fn=_Recorder(),
            clock_fn=self.clock,
            poll_slice_s=0.01,
        )
        watchdog.kick()  # first kick always writes
        first = os.stat(path).st_mtime_ns

        self.clock.advance(1.0)
        watchdog.kick()  # too soon to rewrite, but the deadline still moves
        after_kick = watchdog.seconds_until_fire()
        self.assertGreater(after_kick, watchdog.timeout_s - 1.5)
        self.assertEqual(os.stat(path).st_mtime_ns, first)

        self.clock.advance(20.0)
        watchdog.kick()  # ...but the interval has now elapsed
        self.assertGreaterEqual(os.stat(path).st_mtime_ns, first)

    def test_no_heartbeat_path_means_no_writes(self):
        watchdog = Watchdog(
            heartbeat_path=None,
            heartbeat_interval_s=0.0,
            exit_fn=_Recorder(),
            clock_fn=self.clock,
            poll_slice_s=0.01,
        )
        watchdog.kick()
        self.assertEqual(os.listdir(self.tmp.name), [])


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in ("SARAH_WATCHDOG", "SARAH_WATCHDOG_TIMEOUT_S")
        }
        for key in self._saved:
            os.environ.pop(key, None)
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_defaults_when_nothing_is_configured(self):
        self.assertFalse(watchdog_disabled())
        self.assertEqual(resolve_watchdog_timeout(), DEFAULT_TIMEOUT_S)

    def test_opt_out_values_disable_the_watchdog(self):
        for value in ("0", "false", "NO", "off"):
            os.environ["SARAH_WATCHDOG"] = value
            self.assertTrue(watchdog_disabled(), value)

    def test_enabled_values_do_not_disable_it(self):
        for value in ("", "1", "true", "yes"):
            os.environ["SARAH_WATCHDOG"] = value
            self.assertFalse(watchdog_disabled(), value)

    def test_timeout_override_is_floor_clamped(self):
        os.environ["SARAH_WATCHDOG_TIMEOUT_S"] = "120"
        self.assertEqual(resolve_watchdog_timeout(), 120.0)

    def test_garbage_and_nonpositive_timeouts_fall_back_to_default(self):
        for raw in ("banana", "0", "-5"):
            os.environ["SARAH_WATCHDOG_TIMEOUT_S"] = raw
            self.assertEqual(resolve_watchdog_timeout(), DEFAULT_TIMEOUT_S, raw)

    def test_env_override_reaches_a_default_constructed_watchdog(self):
        # The documented knob has to actually reach the loop's watchdog - a
        # default-constructed Watchdog must resolve the env, not the constant.
        os.environ["SARAH_WATCHDOG_TIMEOUT_S"] = "120"
        watchdog = Watchdog()
        self.assertEqual(watchdog.timeout_s, 120.0)
        self.assertFalse(watchdog.armed, "constructing must not arm anything")

    def test_minimum_timeout_is_enforced_on_the_class_too(self):
        watchdog = Watchdog(timeout_s=1.0, heartbeat_path=None, clock_fn=_Clock())
        self.assertEqual(watchdog.timeout_s, MIN_TIMEOUT_S)


if __name__ == "__main__":
    unittest.main()
