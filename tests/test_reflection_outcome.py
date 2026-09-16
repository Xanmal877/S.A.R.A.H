"""
Tests for the deterministic action-outcome-to-experience loop + bounded
reflection journal.

Phase: after an action proposal outcome is recorded, a system-only
outcome_interpreter turns the executor success boolean into a journal entry,
safe goal transitions, and a fixed-clamped mood nudge. Autonomous reflection
output is persisted (non-duplicate) to the same bounded per-character journal.

Covers: journal store isolation/cap/version; success/failure goal state and
mood clamping; agentless operation; terminal-goal no-op; interpreter failure
that must not alter the underlying tool result; reflection (autonomous) write;
and no tool/Discord exposure.
"""

import asyncio
import json
import os
import tempfile
import unittest

from modules.soul.action_proposals import (
    _active_store as _proposal_active_store,
    _clear_action_proposal_store_cache,
    get_action_proposal_store,
)
from modules.soul.experience.outcome_interpreter import interpret_outcome
from modules.soul.goals import _clear_goal_store_cache, get_goal_store
from modules.soul.identity_state.identity_state import active_character_id
from modules.soul.mental_state.mental_state import MentalState
from modules.soul.reflection_log import (
    REFLECTION_LOG_CAP,
    REFLECTION_LOG_VERSION,
    _clear_reflection_log_store_cache,
    get_reflection_log_store,
)
from modules.soul.reflection_log.reflection_log import (
    ENTRY_AUTONOMOUS,
    ENTRY_OUTCOME,
)


class _EnvMixin:
    """Redirect SARAH_STATE_DIR to a fresh temp dir and drop the store caches so
    each test gets isolated, real on-disk stores (mirrors the other suites)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmp.name
        _clear_reflection_log_store_cache()
        _clear_goal_store_cache()
        _clear_action_proposal_store_cache()
        active_character_id.set("sarah")
        self.addCleanup(self._teardown)

    def _teardown(self):
        _clear_reflection_log_store_cache()
        _clear_goal_store_cache()
        _clear_action_proposal_store_cache()
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmp.cleanup()

    def _journal_path(self, char="sarah"):
        return os.path.join(self._tmp.name, "state", char, "reflection_log.json")

    def _journal(self, char="sarah"):
        return get_reflection_log_store(char)

    def _store(self, char="sarah"):
        return get_action_proposal_store(char)

    def _goal(self, char="sarah", **kw):
        gid = get_goal_store(char).create_goal(
            kw.pop("title", "Test goal"), **kw,
        )
        return gid


class ReflectionLogStoreTests(_EnvMixin, unittest.TestCase):
    """Versioned store, per-character isolation, hard cap, unknown-version
    fail-closed."""

    def test_store_path_honors_sarah_state_dir_and_character_scoping(self):
        self._journal("sarah").append(kind=ENTRY_AUTONOMOUS, content="hello")
        self._journal("tama").append(kind=ENTRY_AUTONOMOUS, content="tama says")
        # Distinct per-character files.
        self.assertTrue(os.path.exists(self._journal_path("sarah")))
        self.assertTrue(os.path.exists(self._journal_path("tama")))
        # Isolation: tama's journal has its own single entry.
        self.assertEqual(self._journal("tama").count(), 1)
        sarah_entries = self._journal("sarah").list()
        self.assertTrue(any(e["content"] == "hello" for e in sarah_entries))
        self.assertFalse(any(e["content"] == "tama says" for e in sarah_entries))

    def test_versioned_layout_and_persistence(self):
        store = self._journal("sarah")
        store.append(kind=ENTRY_OUTCOME, content="outcome", outcome="success")
        # Fresh store (cache cleared) reloads the same file with the schema.
        from modules.soul.reflection_log.reflection_log import ReflectionLogStore
        reloaded = ReflectionLogStore(character_id="sarah")
        self.assertEqual(reloaded._version, REFLECTION_LOG_VERSION)
        data = json.load(open(self._journal_path("sarah")))
        self.assertEqual(data["version"], REFLECTION_LOG_VERSION)
        self.assertIsInstance(data["entries"], list)
        self.assertEqual(reloaded.count(), 1)

    def test_unknown_version_fails_closed_to_empty(self):
        path = self._journal_path("sarah")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"version": 999, "entries": [{"id": "x", "kind": ENTRY_AUTONOMOUS}]}, f)
        store = self._journal("sarah")
        self.assertEqual(store.count(), 0)  # failed closed, not guessed

    def test_cap_keeps_newest_and_drops_oldest(self):
        store = self._journal("sarah")
        for i in range(REFLECTION_LOG_CAP + 50):
            store.append(kind=ENTRY_AUTONOMOUS, content=f"entry-{i}")
        self.assertLessEqual(store.count(), REFLECTION_LOG_CAP)
        newest = store.list()
        # Newest are retained, oldest dropped.
        self.assertEqual(newest[0]["content"], f"entry-{REFLECTION_LOG_CAP + 49}")
        self.assertTrue(any(e["content"] == f"entry-{REFLECTION_LOG_CAP - 1}" for e in newest))
        self.assertFalse(any(e["content"] == "entry-0" for e in newest))

    def test_append_rejects_unknown_kind(self):
        store = self._journal("sarah")
        rc = store.append(kind="nonsense", content="x")
        self.assertEqual(rc, -1)
        self.assertEqual(store.count(), 0)

    def test_entry_has_full_field_set(self):
        store = self._journal("sarah")
        store.append(kind=ENTRY_OUTCOME, content="reason", goal_id="goal-1",
                     proposal_id="proposal-1", outcome="success",
                     source="outcome_interpreter")
        e = store.list()[0]
        self.assertTrue(e["id"].startswith("reflection-"))
        self.assertEqual(e["kind"], ENTRY_OUTCOME)
        self.assertEqual(e["content"], "reason")
        self.assertEqual(e["goal_id"], "goal-1")
        self.assertEqual(e["proposal_id"], "proposal-1")
        self.assertEqual(e["outcome"], "success")
        self.assertEqual(e["source"], "outcome_interpreter")


class _ProposalFactory(_EnvMixin):
    """Shared helper to produce a recorded proposal dict for interpretation."""

    def _recorded_proposal(self, tool="run_command", args=None, *, success, goal_id=None,
                           character="sarah"):
        store = get_action_proposal_store(character)
        args = args or '{"command":"echo ok"}'
        pid = store.propose(tool, args, goal_id=goal_id, ttl_seconds=86400)
        store.approve(pid)
        store.validate_and_consume(pid, tool, args)
        return store.record_outcome(pid, "result-ok" if success else "Error: boom",
                                    success=success)


class OutcomeInterpreterTests(_ProposalFactory, unittest.TestCase):
    """Success/failure clamping, goal transitions, agentless operation,
    terminal-goal no-op."""

    def test_success_reactivates_blocked_goal(self):
        gid = self._goal(title="Finish server room cleanup")
        get_goal_store("sarah").mark_blocked(gid, "was stuck")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "blocked")

        prop = self._recorded_proposal(goal_id=gid, success=True)
        ms = MentalState()
        ms.needs.morale = 0.5
        summary = interpret_outcome(prop, mental_state=ms, character_id="sarah")

        goal = get_goal_store("sarah").get_goal(gid)
        self.assertEqual(goal["status"], "active")  # reactivated, not completed
        self.assertEqual(summary["goal"]["transitioned"], "active")

    def test_failure_marks_goal_blocked(self):
        gid = self._goal(title="Patch the webserver")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "proposed")

        prop = self._recorded_proposal(goal_id=gid, success=False)
        ms = MentalState()
        ms.needs.morale = 0.5
        summary = interpret_outcome(prop, mental_state=ms, character_id="sarah")

        goal = get_goal_store("sarah").get_goal(gid)
        self.assertEqual(goal["status"], "blocked")
        self.assertTrue(any("failed" in b for b in goal["blockers"]))
        self.assertEqual(summary["goal"]["transitioned"], "blocked")

    def test_success_on_blocked_never_completes_goal(self):
        gid = self._goal(title="Keep drives alive")
        get_goal_store("sarah").mark_blocked(gid, "blocker")
        prop = self._recorded_proposal(goal_id=gid, success=True)
        interpret_outcome(prop, character_id="sarah")
        self.assertNotEqual(get_goal_store("sarah").get_goal(gid)["status"], "completed")
        self.assertNotEqual(get_goal_store("sarah").get_goal(gid)["status"], "abandoned")

    def test_terminal_goal_is_no_op(self):
        gid = self._goal(title="Done forever")
        get_goal_store("sarah").complete_goal(gid, outcome="finished")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "completed")
        # Failure outcome on a completed goal must NOT un-complete / un-abandon it.
        prop = self._recorded_proposal(goal_id=gid, success=False)
        summary = interpret_outcome(prop, character_id="sarah")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "completed")
        self.assertEqual(summary["goal"]["transitioned"], None)

    def test_no_goal_id_does_no_goal_work(self):
        prop = self._recorded_proposal(success=True)  # no goal link
        summary = interpret_outcome(prop, character_id="sarah")
        self.assertEqual(summary["goal"]["goal_id"], None)
        self.assertEqual(summary["goal"]["transitioned"], None)

    def test_fixed_mood_clamp_success_up(self):
        prop = self._recorded_proposal(success=True)
        ms = MentalState()
        ms.needs.morale = 0.5
        interpret_outcome(prop, mental_state=ms, character_id="sarah")
        self.assertAlmostEqual(ms.needs.morale, 0.52, places=4)

    def test_fixed_mood_clamp_failure_down(self):
        prop = self._recorded_proposal(success=False)
        ms = MentalState()
        ms.needs.morale = 0.5
        interpret_outcome(prop, mental_state=ms, character_id="sarah")
        self.assertAlmostEqual(ms.needs.morale, 0.47, places=4)

    def test_mood_clamped_to_unit_range(self):
        prop = self._recorded_proposal(success=True)
        ms = MentalState()
        ms.needs.morale = 0.99
        interpret_outcome(prop, mental_state=ms, character_id="sarah")
        self.assertLessEqual(ms.needs.morale, 1.0)
        prop2 = self._recorded_proposal(success=False)
        ms2 = MentalState()
        ms2.needs.morale = 0.01
        interpret_outcome(prop2, mental_state=ms2, character_id="sarah")
        self.assertGreaterEqual(ms2.needs.morale, 0.0)

    def test_agentless_still_does_bookkeeping_but_skips_mood(self):
        # No mental_state passed -> mood nudge skipped.
        gid = self._goal(title="agentless goal")
        prop = self._recorded_proposal(goal_id=gid, success=False)
        before = MentalState().needs.morale  # default 0.5, untouched
        summary = interpret_outcome(prop, mental_state=None, character_id="sarah")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "blocked")
        self.assertTrue(summary["journaled"])
        ms = MentalState()
        self.assertEqual(ms.needs.morale, before)  # unchanged in a fresh instance

    def test_episode_enriched_deterministically_no_raw_args(self):
        from modules.memory.episodic_memory import _clear_episodic_store_cache, get_episodic_store
        _clear_episodic_store_cache()
        gid = self._goal(title="Enriched episode")
        prop = self._recorded_proposal(goal_id=gid, args='{"command":"super-secret payload"}',
                                       success=True)
        interpret_outcome(prop, character_id="sarah")
        episodes = get_episodic_store("sarah").retrieve(kinds=["action"])
        self.assertTrue(len(episodes) >= 1)
        content = episodes[0]["content"]
        # Deterministic enrichment, linked to goal + tool; raw args never stored.
        self.assertIn("run_command", content)
        self.assertIn(gid, content)
        self.assertNotIn("super-secret", content)
        self.assertNotIn("payload", content)

    def test_journal_outcome_entry_written_and_no_raw_args(self):
        gid = self._goal(title="journal goal")
        prop = self._recorded_proposal(goal_id=gid, args='{"command":"secret -p 123"}',
                                       success=False)
        interpret_outcome(prop, character_id="sarah")
        entries = self._journal("sarah").list()
        outcome_entries = [e for e in entries if e["kind"] == ENTRY_OUTCOME]
        self.assertEqual(len(outcome_entries), 1)
        self.assertEqual(outcome_entries[0]["goal_id"], gid)
        self.assertEqual(outcome_entries[0]["outcome"], "failure")
        # Raw action args must never leak into the journal.
        self.assertNotIn("secret", outcome_entries[0]["content"])
        self.assertNotIn("-p 123", outcome_entries[0]["content"])
        # The bounded reason references tool + status only.
        self.assertIn("run_command", outcome_entries[0]["content"])

    def test_interpreter_failure_does_not_alter_tool_result(self):
        # Even if journaling itself fails (e.g. unwritable store), the proposal
        # outcome and any mood handling must not raise up, and the interpreter
        # returns a best-effort summary rather than breaking the orchestrator.
        import modules.soul.experience.outcome_interpreter as oi
        original = oi.get_reflection_log_store
        def _boom(*a, **k):
            raise RuntimeError("storage down")
        oi.get_reflection_log_store = _boom
        self.addCleanup(lambda: setattr(oi, "get_reflection_log_store", original))
        gid = self._goal(title="resilient")
        prop = self._recorded_proposal(goal_id=gid, success=True)
        # Must not raise even though journaling failed.
        summary = interpret_outcome(prop, character_id="sarah")
        self.assertFalse(summary["journaled"])
        # The interpreter's failure handling is pure - the recorded proposal
        # remains exactly as the store recorded it.
        self.assertEqual(prop["status"], "executed")


class _StubLLM:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def generate_decision(self, prompt):
        return self._decisions.pop(0)


def _enc(d):
    return json.dumps(d)


class OrchestratorIntegrationTests(_EnvMixin, unittest.TestCase):
    """Verify the interpreter is invoked from the orchestrator after
    record_outcome, success/failure both flow through, and terminal no-op."""

    def setUp(self):
        super().setUp()
        self.calls = []

    def _register_sentinel(self, name, calls, default_result=None):
        from modules.tools.tool_registry import registry

        def sentinel(*args, **kwargs):
            calls.append((name, kwargs))
            return default_result if default_result is not None else f"executed {name}"
        registry.register(name, sentinel, "test sentinel")
        return sentinel

    def _run(self, orch, request="do thing"):
        return asyncio.run(orch.process_request(request))

    def test_successful_approved_action_reactivates_blocked_goal(self):
        from modules.tools.tool_orchestrator import ToolOrchestrator
        self._register_sentinel("run_command", self.calls, "SENTINEL_OK")
        gid = self._goal(title="Integration goal")
        get_goal_store("sarah").mark_blocked(gid, "was blocked")
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "blocked")

        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"echo hi"}', goal_id=gid, ttl_seconds=86400)
        store.approve(pid)
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "echo hi", "proposal_id": pid,
        }}), _enc({"final_answer": "done"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(result, "done")
        # Blocked goal reactivated (not completed) via the interpreter.
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "active")
        # Journal got an outcome entry for this proposal.
        entries = self._journal("sarah").list()
        self.assertTrue(any(e["kind"] == ENTRY_OUTCOME for e in entries))

    def test_failed_approved_action_blocks_linked_goal(self):
        import modules.tools.tool_orchestrator as orch_mod
        from modules.tools.tool_orchestrator import ToolOrchestrator
        self._register_sentinel("run_command", self.calls)
        gid = self._goal(title="Integration goal 2")
        # Goal currently in 'proposed' (live, not terminal).
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "proposed")

        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"boom"}', goal_id=gid, ttl_seconds=86400)
        store.approve(pid)

        original_exec = orch_mod.executor.execute
        async def failing_execute(tool_name, **kwargs):
            raise RuntimeError("kaboom")
        orch_mod.executor.execute = failing_execute
        self.addCleanup(self._restore_executor, orch_mod, original_exec)

        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "boom", "proposal_id": pid,
        }}), _enc({"final_answer": "it errored"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(result, "it errored")
        # Linked goal marked blocked by the interpreter.
        self.assertEqual(get_goal_store("sarah").get_goal(gid)["status"], "blocked")

    def _restore_executor(self, orch_mod, original):
        orch_mod.executor.execute = original


class NoToolNoDiscordExposureTests(_EnvMixin, unittest.TestCase):
    """The reflection journal is system-written only: no registry tool and no
    Discord allowlist entry must ever reference it.

    These are source-inspection based rather than importing init_tools /
    discord.main, because both are heavy to import in a unit test (init_tools
    drags in psutil/psutil-backed system modules; discord.main runs an
    interactive .env bootstrap). The registration and allowlist are plain
    literal definitions, so a text-level check is both cheaper and sufficient
    to prove no exposure was added."""

    def _repo(self, *parts):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(repo, *parts)

    def _read(self, rel):
        with open(self._repo(*rel.split("/"))) as f:
            return f.read()

    def test_registration_file_never_registers_journal_or_interpreter_tools(self):
        src = self._read("modules/tools/init_tools.py")
        for needle in ("reflection_log", "outcome_interpreter", "interpret_outcome",
                       "write_reflection", "get_reflection"):
            self.assertNotIn(needle, src)

    def test_no_outcome_interpreter_tool_in_registry_source(self):
        src = self._read("modules/tools/init_tools.py")
        self.assertNotIn("interpret_outcome", src)
        self.assertNotIn("registry.register(\"interpret", src)

    def test_not_in_discord_allowlist(self):
        src = self._read("discord/main.py")
        # DISCORD_ALLOWED_TOOLS must not include journal/interpreter tooling.
        self.assertNotIn("reflection_log", src)
        self.assertNotIn("outcome_interpreter", src)

    def test_journal_store_not_imported_by_registry_or_discord(self):
        reg = self._read("modules/tools/init_tools.py")
        discord_src = self._read("discord/main.py")
        for mod in ("reflection_log", "experience.outcome_interpreter"):
            self.assertNotIn(f"import {mod}", reg)
            self.assertNotIn(f"from {mod}", reg)
            self.assertNotIn(f"import {mod}", discord_src)
            self.assertNotIn(f"from {mod}", discord_src)


if __name__ == "__main__":
    unittest.main()
