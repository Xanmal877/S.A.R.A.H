import tempfile
import unittest

from modules.context import assemble_autonomous_context, assemble_character_context
from modules.soul.identity_state.identity_state import active_character_id
from modules.soul.mental_state.mental_state import MentalState
from modules.soul.soul import Soul


class _FakeAgent:
    """A lightweight stand-in for BaseCharacter so context assembly can run
    without loading the full agent/soul machinery (no LLM, no screen, etc.)."""
    def __init__(self, character_id="sarah", current_task=""):
        self.character_id = character_id
        self.characterName = character_id.capitalize()
        self.currentTask = current_task
        self.soul = Soul(character_id=character_id)
        # A real SetupPersonality sets nonzero MBTI; make get_summary() include
        # a personality line.
        self.soul.mental_state.mbti.energy = 85
        self.soul.mental_state.mbti.mind = 80
        self.soul.mental_state.mbti.nature = 75
        self.soul.mental_state.mbti.tactics = 85


class ContextCompositionTests(unittest.TestCase):
    """Phase 1: one reusable context path that includes identity, mental/drive
    state, current goal/task, and available perception - used by the autonomous
    loop and Discord/CLI. Replaces the legacy RPG health/mana/stamina readout
    with meaningful digital state."""

    def _fresh(self):
        self._tmp = tempfile.TemporaryDirectory()
        import os
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmp.name
        active_character_id.set("sarah")

    def setUp(self):
        self._fresh()

    def tearDown(self):
        import os
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmp.cleanup()

    def test_context_includes_identity(self):
        from modules.memory.identity_tools import add_interest, form_opinion
        active_character_id.set("sarah")
        add_interest("astronomy")
        form_opinion("python", "the right tool", "clear and readable")
        agent = _FakeAgent()
        ctx = assemble_assertable(agent)
        self.assertIn("Interests: astronomy", ctx)
        self.assertIn("python", ctx)

    def test_context_includes_current_goal_and_task(self):
        active_character_id.set("sarah")
        agent = _FakeAgent(current_task="debugging the daemon")
        from modules.memory.identity_tools import add_goal, complete_goal
        add_goal("Ship phase 1")
        add_goal("Old goal")
        complete_goal("Old goal")
        ctx = assemble_assertable(agent)
        self.assertIn("debugging the daemon", ctx)
        self.assertIn("Ship phase 1", ctx)
        # Completed goals should not appear as active goals.
        self.assertNotIn("Old goal", ctx)

    def test_context_includes_mental_state_not_rpg_stats(self):
        agent = _FakeAgent()
        ctx = assemble_assertable(agent)
        self.assertIn("[MENTAL STATE]", ctx)
        # Meaningful digital state lines (drives/needs) must be present.
        self.assertIn("Focus:", ctx)
        self.assertIn("Sanity:", ctx)
        # The legacy RPG readout must not leak into the new context.
        self.assertNotIn("Health:", ctx)
        self.assertIn("Personality:", ctx)  # MBTI baseline present too

    def test_context_includes_available_perception(self):
        agent = _FakeAgent()
        ctx = assemble_character_context(
            agent,
            screen_text="a terminal with logs",
            hive_summary="1 node online",
            body_state="Battery: 80.0%",
        )
        self.assertIn("[SCREEN]", ctx)
        self.assertIn("a terminal with logs", ctx)
        self.assertIn("[HIVE]", ctx)
        self.assertIn("[BODY]", ctx)
        self.assertIn("Battery:", ctx)

    def test_context_resolves_character_when_agent_absent(self):
        # A caller with no live agent (e.g. the Discord bot) still fetches the
        # right character's identity via active_character_id set just before
        # assembly.
        from modules.memory.identity_tools import add_interest
        active_character_id.set("tama")
        add_interest("cats")
        ctx = assemble_character_context(agent=None)
        self.assertIn("cats", ctx)
        # Sarah, read without an agent, must not see Tama's identity.
        active_character_id.set("sarah")
        sarah_ctx = assemble_character_context(agent=None)
        self.assertNotIn("cats", sarah_ctx)


def assemble_assertable(agent):
    """Small wrapper so tests read clearly: with an agent use the autonomous
    path; without one set the contextvar and use the plain path."""
    if agent is not None:
        return assemble_autonomous_context(agent)
    return assemble_character_context(agent=None)


if __name__ == "__main__":
    unittest.main()
