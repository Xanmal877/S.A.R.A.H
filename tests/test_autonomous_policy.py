import json
import unittest

from modules.tools.tool_orchestrator import ToolOrchestrator
from modules.tools.tool_registry import registry


class _StubLLM:
    """Fake LLM that returns canned decisions in sequence, so the test can
    assert how the orchestrator enforces policy without talking to Ollama."""

    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def generate_decision(self, prompt):
        return self._decisions.pop(0)


def _mk_decisions(*payloads):
    return [_encode_json(p) for p in payloads]


def _encode_json(payload):
    return json.dumps(payload)


def _register_sentinel(name, calls):
    """Register a tool that records invocation, so we can prove whether the
    orchestrator actually executed it."""
    def sentinel(*_args, **_kwargs):
        calls.append(name)
        return f"executed {name}"
    registry.register(name, sentinel, "test sentinel")
    return sentinel


class AutonomousToolBlockingTests(unittest.TestCase):
    """Phase 1: code-enforced autonomous policy. Autonomous (observe_and_suggest)
    requests may only use a minimal read-only/observe allowlist; any other
    requested tool returns a clear approval-required message WITHOUT executing.
    Interactive / Discord existing allowlists remain unchanged."""

    def setUp(self):
        self.calls = []

    def _run(self, orchestrator, request="observe", context=""):
        import asyncio
        return asyncio.run(orchestrator.process_request(request, system_context=context))

    def test_observe_only_never_executes_write_tool(self):
        # Registering the tools this "actor" would reach lets us prove the
        # orchestrator did NOT execute them - a stronger check than message text.
        _register_sentinel("run_command", self.calls)
        _register_sentinel("install_package", self.calls)
        _register_sentinel("browser_navigate", self.calls)
        llm = _StubLLM(_mk_decisions(
            {"tool": "run_command", "args": {"command": "rm -rf /"}},
            {"tool": "install_package", "args": {"name": "evil"}},
            {"tool": "browser_navigate", "args": {"url": "x"}},
            {"final_answer": "I asked but was not allowed to act."},
        ))
        orch = ToolOrchestrator(llm, character_id="sarah", observe_only=True)
        result = self._run(orch)
        # None of the banned tools may ever run.
        self.assertEqual(self.calls, [])
        # The loop did complete (reached the final answer), returning normally.
        self.assertEqual(result, "I asked but was not allowed to act.")

    def test_observe_only_allowlist_is_minimal_read_only(self):
        # Effective allowlist under observe_only must be drawn from the
        # observe set and be readonly - crucially it must NOT include the
        # write/act tools.
        llm = _StubLLM([_encode_json({"final_answer": "ok"})])
        orch = ToolOrchestrator(llm, character_id="sarah", observe_only=True)
        allowed = orch._effective_allowlist
        self.assertIsNotNone(allowed)
        for banned in ("run_command", "install_package", "start_container",
                       "git_commit", "media_next", "browser_navigate", "speak",
                       "check_new_downloads", "diff_directory"):
            self.assertNotIn(banned, allowed)
        # Sanity: it does expose some read-only observers.
        self.assertTrue(allowed)

    def test_observe_only_intersects_with_existing_allowlist(self):
        # Even if a caller passes allowlist_tools, observe_only further scopes
        # it down to the read-only/observe subset.
        llm = _StubLLM([_encode_json({"final_answer": "ok"})])
        orch = ToolOrchestrator(
            llm, character_id="sarah",
            allowed_tools={"run_command", "get_system_info", "retrieve_memory"},
            observe_only=True,
        )
        allowed = orch._effective_allowlist
        self.assertNotIn("run_command", allowed)
        self.assertIn("get_system_info", allowed)
        self.assertIn("retrieve_memory", allowed)

    def test_non_observe_allowlist_uses_standard_block_message(self):
        # Without observe_only, an existing allowed_tools deny keeps the
        # original generic message and does not run the tool.
        _register_sentinel("run_command", self.calls)
        llm = _StubLLM(_mk_decisions(
            {"tool": "run_command", "args": {"command": "ls"}},
            {"final_answer": "ok"},
        ))
        orch = ToolOrchestrator(
            llm, character_id="sarah",
            allowed_tools={"form_opinion"},
        )
        self._run(orch)
        self.assertEqual(self.calls, [])

    def test_no_allowlist_and_no_observe_only_is_unrestricted(self):
        # The normal interactive/desktop path: neither restriction set, so the
        # effective allowlist is None (full registry) and an ordinary (non
        # approval-required) tool runs without a proposal id.
        _register_sentinel("send_notification", self.calls)
        llm = _StubLLM(_mk_decisions(
            {"tool": "send_notification", "args": {"title": "hi"}},
            {"final_answer": "ok"},
        ))
        orch = ToolOrchestrator(llm, character_id="sarah")
        self.assertIsNone(orch._effective_allowlist)
        result = self._run(orch)
        self.assertEqual(result, "ok")
        self.assertIn("send_notification", self.calls)


if __name__ == "__main__":
    unittest.main()
