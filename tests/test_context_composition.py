import tempfile
import unittest

from modules.context import assemble_autonomous_context, assemble_character_context
from modules.soul.identity_state.identity_state import (
    _clear_identity_state_cache,
    active_character_id,
)
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
        # Drop identity-state instances pinned before the redirect - without
        # this, the identity tools below would write into the live ~/.sarah
        # file instead of this temp dir (the historical pollution bug).
        _clear_identity_state_cache()
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


class RecentExperiencesRecallTests(unittest.TestCase):
    """Bounded recent-experience recall surfaced only in the autonomous context
    ([RECENT EXPERIENCES]) from the system-written reflection journal.

    Covers: character isolation, hard bound (max 5), empty omission,
    autonomous-only inclusion (absent from conversational context), and no raw
    proposal args / ids leaking into the rendered snippet."""

    @classmethod
    def setUpClass(cls):
        # Direct imports that don't need the agent machinery.
        from modules.soul.reflection_log.reflection_log import (
            ENTRY_AUTONOMOUS,
            ENTRY_OUTCOME,
            RECENT_EXPERIENCE_LIMIT,
            _clear_reflection_log_store_cache,
            get_reflection_log_store,
        )
        cls.ENTRY_AUTONOMOUS = ENTRY_AUTONOMOUS
        cls.ENTRY_OUTCOME = ENTRY_OUTCOME
        cls.LIMIT = RECENT_EXPERIENCE_LIMIT
        cls._get = staticmethod(get_reflection_log_store)
        cls._clear = staticmethod(_clear_reflection_log_store_cache)

    def setUp(self):
        import os
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmp.name
        self._clear()
        active_character_id.set("sarah")

    def tearDown(self):
        import os
        self._clear()
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmp.cleanup()

    def _append(self, kind: str, content: str, character="sarah", **kw):
        return self._get(character).append(kind=kind, content=content, **kw)

    def _ctx(self, agent=None):
        if agent is not None:
            return assemble_autonomous_context(agent)
        # Conversational path (Discord bot / CLI) - must NOT include the section.
        return assemble_character_context(agent=None)

    def test_recent_experiences_are_bounded_to_five(self):
        for i in range(20):
            self._append(self.ENTRY_AUTONOMOUS, f"reflection-{i}")
        agent = _FakeAgent()
        ctx = self._ctx(agent)
        self.assertIn("[RECENT EXPERIENCES]", ctx)
        # The five newest entries appear; older ones beyond the bound never do.
        for e in ("reflection-15", "reflection-16", "reflection-17",
                  "reflection-18", "reflection-19"):
            self.assertIn(e, ctx)
        self.assertNotIn("reflection-14", ctx)
        self.assertNotIn("reflection-0", ctx)

    def test_empty_journal_omits_section(self):
        ctx = self._ctx(_FakeAgent())
        self.assertNotIn("[RECENT EXPERIENCES]", ctx)

    def test_characters_are_isolated(self):
        self._append(self.ENTRY_AUTONOMOUS, "sarah private reflection")
        self._append(self.ENTRY_AUTONOMOUS, "tama private reflection", character="tama")
        # Sarah's context shows only her own journal.
        ctx = self._ctx(_FakeAgent())
        self.assertIn("sarah private reflection", ctx)
        self.assertNotIn("tama private reflection", ctx)

    def test_only_autonomous_context_includes_section(self):
        self._append(self.ENTRY_AUTONOMOUS, "only-here reflection")
        # Autonomous loop context includes the section.
        auto_ctx = assemble_autonomous_context(_FakeAgent())
        self.assertIn("[RECENT EXPERIENCES]", auto_ctx)
        self.assertIn("only-here reflection", auto_ctx)
        # Conversational (Discord/CLI) context must NOT include it.
        conv_ctx = assemble_character_context(agent=None)
        self.assertNotIn("[RECENT EXPERIENCES]", conv_ctx)
        self.assertNotIn("only-here reflection", conv_ctx)

    def test_no_raw_proposal_args_or_ids_leak(self):
        # An outcome entry carries bounded reason content plus a proposal id.
        self._append(
            self.ENTRY_OUTCOME,
            "Proposed action 'run_command' failed (proposal status: failed).",
            proposal_id="proposal-abc123", goal_id="goal-xyz", outcome="failure",
        )
        ctx = self._ctx(_FakeAgent())
        self.assertIn("[RECENT EXPERIENCES]", ctx)
        # The bounded reason is present and labelled as an action outcome.
        self.assertIn("Action outcome", ctx)
        self.assertIn("failed", ctx)
        # Raw ids / args never leak into the rendered snippet.
        self.assertNotIn("proposal-abc123", ctx)
        self.assertNotIn("goal-xyz", ctx)
        self.assertNotIn("echo ok", ctx)

    def test_reflection_echoed_internal_handles_are_masked(self):
        self._append(
            self.ENTRY_AUTONOMOUS,
            "Continue goal-deadbeef after proposal-cafebabe succeeds.",
        )
        ctx = self._ctx(_FakeAgent())
        self.assertNotIn("goal-deadbeef", ctx)
        self.assertNotIn("proposal-cafebabe", ctx)
        self.assertIn("[internal reference]", ctx)


def assemble_assertable(agent):
    """Small wrapper so tests read clearly: with an agent use the autonomous
    path; without one set the contextvar and use the plain path."""
    if agent is not None:
        return assemble_autonomous_context(agent)
    return assemble_character_context(agent=None)


if __name__ == "__main__":
    unittest.main()
