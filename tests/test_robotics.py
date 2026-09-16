import asyncio
import unittest

from modules.robotics import (
    BodyIntent,
    FakeWorld,
    MockTransport,
    RoboticsHardware,
    RoboticsRuntime,
    SimRobotBody,
)


class RoboticsTests(unittest.TestCase):
    def test_simulation_refuses_blocked_move_without_changing_position(self):
        world = FakeWorld(width=3, height=3, obstacles={(2, 1)}, chargers={(0, 0)})
        body = SimRobotBody(world)
        body.state.position = (1, 1)
        body.state.heading = "east"

        body.tick(intent=BodyIntent(desired_action="move_forward"))

        self.assertEqual(body.state.position, (1, 1))
        self.assertFalse(body.state.last_move_succeeded)
        self.assertFalse(body.telemetry.last.succeeded)

    def test_simulation_charges_only_on_charger(self):
        world = FakeWorld(width=4, height=4, obstacles=set(), chargers={(0, 0)})
        body = SimRobotBody(world)
        body.state.position = (1, 1)
        body.state.battery = 50

        body.tick(intent=BodyIntent(desired_action="charge"))
        self.assertFalse(body.state.is_charging)
        self.assertFalse(body.telemetry.last.succeeded)

        body.state.position = (0, 0)
        body.tick(intent=BodyIntent(desired_action="dock"))
        body.tick(intent=BodyIntent(desired_action="charge"))
        self.assertTrue(body.state.is_charging)
        self.assertGreater(body.state.battery, 50)

    def test_hardware_updates_state_only_after_acknowledgement(self):
        transport = MockTransport({"GET_DISTANCE": "DISTANCE|50", "MOVE_FORWARD": "ERROR"})
        from modules.robotics.hardware import BodyStateAdapter

        adapter = BodyStateAdapter(RoboticsHardware(transport))
        adapter.set_intent("move_forward")
        result = adapter.execute_action()

        self.assertFalse(result.succeeded)
        self.assertEqual(adapter.body_state.position, (3, 3))
        self.assertFalse(adapter.body_state.last_move_succeeded)

    def test_runtime_is_disabled_by_default(self):
        runtime = RoboticsRuntime("test", {"enabled": False})

        asyncio.run(runtime.start())
        asyncio.run(runtime.tick())

        self.assertIsNone(runtime.state)

    def test_runtime_simulation_runs_intent_cycle(self):
        runtime = RoboticsRuntime("test", {"enabled": True, "mode": "sim"})
        runtime.intent.desired_action = "move_forward"

        asyncio.run(runtime.start())
        asyncio.run(runtime.tick())

        self.assertIsNotNone(runtime.state)
        self.assertEqual(runtime.state.position, (4, 3))
        asyncio.run(runtime.close())

    def test_runtime_close_unregisters_itself(self):
        from modules.robotics import get_runtime, register_runtime

        runtime = RoboticsRuntime("test", {"enabled": True, "mode": "sim"})
        register_runtime("test", runtime)
        asyncio.run(runtime.close())

        self.assertIsNone(get_runtime("test"))
