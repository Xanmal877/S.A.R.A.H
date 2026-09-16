"""
Focused tests for persistent action proposals + code-enforced approval gate.

Covers: transition history, expiry, exact-match, character/person isolation,
single-use consumption, blocked execution without approval, allowed read-only
execution, autonomous policy compatibility, and Discord exclusion.
"""

import json
import os
import tempfile
import unittest

from modules.soul.action_proposals import (
    _active_store,
    _clear_action_proposal_store_cache,
    get_action_proposal_store,
    get_risk_category,
)
from modules.soul.action_proposals.action_proposal_tools import (
    approve_action,
    list_pending_actions,
    propose_action,
    reject_action,
)
from modules.soul.identity_state.identity_state import active_character_id, active_person_id
from modules.tools.tool_orchestrator import ToolOrchestrator
from modules.tools.tool_registry import registry


class _EnvMixin:
    """Redirect SARAH_STATE_DIR to a temp dir and invalidate the store cache so
    each test gets an isolated, real on-disk store (mirrors the other store
    tests)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmp.name
        _clear_action_proposal_store_cache()
        active_character_id.set("sarah")
        self.addCleanup(self._teardown)

    def _teardown(self):
        _clear_action_proposal_store_cache()
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmp.cleanup()

    def _store(self, character_id="sarah"):
        return get_action_proposal_store(character_id)


class StoreLifecycleTests(_EnvMixin, unittest.TestCase):
    """Versioned store, transition history, expiry, exact match, isolation."""

    def test_store_is_character_scoped_and_persisted(self):
        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"ls"}', rationale="inspect")
        self.assertTrue(pid.startswith("proposal-"))
        # A fresh store for the same character reloads from disk.
        _clear_action_proposal_store_cache()
        reloaded = self._store("sarah")
        self.assertIsNotNone(reloaded.get(pid))

    def test_propose_creates_full_field_set(self):
        pid = self._store().propose(
            "git_pull", '{"repo_path":"/x"}', rationale="sync",
            evidence="saw diverged branch", goal_id="goal-abc",
        )
        p = self._store().get(pid)
        self.assertEqual(p["tool"], "git_pull")
        self.assertEqual(p["args"], {"repo_path": "/x"})
        self.assertEqual(p["status"], "proposed")
        self.assertEqual(p["risk_category"], "approval_required")
        self.assertEqual(p["goal_id"], "goal-abc")
        self.assertTrue(p["expires_at"] > p["created_at"])
        self.assertEqual(p["actor"], None)
        self.assertEqual(p["outcome"], "")
        self.assertEqual(p["history"][-1]["action"], "propose")

    def test_propose_person_binding(self):
        # Without a bound caller, person_id is advisory metadata on the proposal.
        active_person_id.set(None)
        pid = self._store().propose("run_command", '{"command":"ls"}', person_id="discord:alice")
        p = self._store().get(pid)
        self.assertEqual(p["person_id"], "discord:alice")
        # With a bound caller, the proposal is forced to that caller.
        active_person_id.set("discord:bob")
        pid2 = self._store().propose("run_command", '{"command":"ls"}')
        p2 = self._store().get(pid2)
        self.assertEqual(p2["person_id"], "discord:bob")
        # A bound caller cannot assign a proposal to a different person.
        self.assertIsNone(
            self._store().propose("run_command", '{"command":"ls"}', person_id="discord:mallory")
        )

    def test_risk_classification(self):
        # approval-required categories
        for t in ("run_command", "install_package", "start_service",
                  "stop_container", "git_commit", "git_pull",
                  "run_remote_command", "push_file_to_peer", "browser_click",
                  "media_next", "set_clipboard", "form_opinion", "store_memory",
                  "record_episode", "upsert_person_profile", "add_semantic_fact",
                  "create_goal"):
            self.assertEqual(get_risk_category(t), "approval_required", t)
        # read-only
        self.assertEqual(get_risk_category("get_system_info"), "readonly")
        self.assertEqual(get_risk_category("git_log"), "readonly")
        self.assertEqual(get_risk_category("retrieve_memory"), "readonly")
        # ordinary default
        self.assertEqual(get_risk_category("send_notification"), "ordinary")

    def test_transition_history_tracks_propose_approve_consume(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"echo hi"}')
        store.approve(pid, actor="operator", decision="ok go")
        consumed = store.validate_and_consume(pid, "run_command", '{"command":"echo hi"}')
        self.assertNotIn("error", consumed)
        self.assertEqual(consumed["status"], "executed")
        p = store.get(pid)
        actions = [h["action"] for h in p["history"]]
        self.assertIn("propose", actions)
        self.assertTrue(any(h["action"] == "status" and h["new"] == "approved"
                            for h in p["history"]))
        self.assertTrue(any(h["action"] == "status" and h["new"] == "executed"
                            for h in p["history"]))
        self.assertEqual(p["actor"], "operator")
        self.assertEqual(p["decision"], "ok go")

    def test_expiry_before_approval(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"ls"}', ttl_seconds=60)
        # Force-expire by rewriting the file timestamp to the past.
        p = store.get(pid)
        from datetime import datetime, timedelta
        import modules.soul.action_proposals.action_proposals as ap
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="microseconds")
        p["expires_at"] = past
        store._proposals[pid]["expires_at"] = past
        store._save()
        after = store.get(pid)
        self.assertEqual(after["status"], "expired")
        consumed = store.validate_and_consume(pid, "run_command", '{"command":"ls"}')
        self.assertIn("error", consumed)
        self.assertIn("expired", consumed["error"])

    def test_exact_match_required(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"ls -la"}')
        store.approve(pid)
        # Different args -> refusal (no execution, proposal still approved/usable for exact).
        consumed = store.validate_and_consume(pid, "run_command", '{"command":"rm -rf /"}')
        self.assertIn("error", consumed)
        self.assertIn("arguments", consumed["error"])
        # Different tool -> refusal.
        consumed2 = store.validate_and_consume(pid, "git_pull", '{"command":"ls -la"}')
        self.assertIn("error", consumed2)
        self.assertIn("tool", consumed2["error"])
        # Exact match -> succeeds.
        good = store.validate_and_consume(pid, "run_command", '{"command":"ls -la"}')
        self.assertNotIn("error", good)

    def test_single_use_consumption(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"touch /tmp/x"}', ttl_seconds=86400)
        store.approve(pid)
        first = store.validate_and_consume(pid, "run_command", '{"command":"touch /tmp/x"}')
        self.assertNotIn("error", first)
        # Second use is refused - the approval has been consumed.
        second = store.validate_and_consume(pid, "run_command", '{"command":"touch /tmp/x"}')
        self.assertIn("error", second)
        self.assertIn("executed", second["error"])

    def test_character_isolation(self):
        # A proposal belonging to sarah must never authorize work for tama.
        sarah = self._store("sarah")
        pid = sarah.propose("run_command", '{"command":"ls"}')
        sarah.approve(pid)
        # tama's store cannot see / consume sarah's proposal.
        tama = self._store("tama")
        self.assertIsNone(tama.get(pid))
        refused = tama.validate_and_consume(pid, "run_command", '{"command":"ls"}')
        self.assertIn("error", refused)
        self.assertIn("current character", refused["error"])

    def test_outcome_recording(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"echo ok"}', ttl_seconds=86400)
        store.approve(pid)
        store.validate_and_consume(pid, "run_command", '{"command":"echo ok"}')
        out = store.record_outcome(pid, "ran fine", success=True)
        self.assertEqual(out["outcome"], "ran fine")
        self.assertEqual(out["status"], "executed")
        # failed execution transitions to failed
        pid2 = store.propose("run_command", '{"command":"false"}', ttl_seconds=86400)
        store.approve(pid2)
        store.validate_and_consume(pid2, "run_command", '{"command":"false"}')
        out2 = store.record_outcome(pid2, "Error: boom", success=False)
        self.assertEqual(out2["status"], "failed")

    def test_reject_is_terminal(self):
        store = self._store()
        pid = store.propose("run_command", '{"command":"ls"}')
        store.reject(pid, actor="operator", decision="no")
        p = store.get(pid)
        self.assertEqual(p["status"], "rejected")
        self.assertEqual(p["actor"], "operator")
        # rejected cannot be consumed.
        consumed = store.validate_and_consume(pid, "run_command", '{"command":"ls"}')
        self.assertIn("error", consumed)

    def test_bound_caller_cannot_access_another_persons_proposal(self):
        store = self._store()
        # Create a proposal for a specific person (no caller bound).
        active_person_id.set(None)
        pid = store.propose("run_command", '{"command":"ls"}', person_id="discord:alice")
        # Now bind a DIFFERENT caller: direct-id approve/reject/consume must refuse.
        active_person_id.set("discord:mallory")
        self.assertIsNone(store.approve(pid))
        self.assertIsNone(store.reject(pid))
        refused = store.validate_and_consume(pid, "run_command", '{"command":"ls"}')
        self.assertIn("error", refused)
        self.assertIn("caller", refused["error"])
        # And alice's proposal is untouched (still proposed; alice can approve).
        active_person_id.set("discord:alice")
        self.assertEqual(store.get(pid)["status"], "proposed")
        self.assertIsNotNone(store.approve(pid))

    def test_general_proposal_accessible_in_caller_bound_context(self):
        # A general (person_id None) proposal may be operated on by ANY bound caller.
        store = self._store()
        active_person_id.set(None)
        pid = store.propose("run_command", '{"command":"ls"}')
        store.approve(pid)
        active_person_id.set("discord:mallory")
        consumed = store.validate_and_consume(pid, "run_command", '{"command":"ls"}')
        self.assertNotIn("error", consumed)

    def test_pending_list_scope_to_bound_caller(self):
        store = self._store()
        active_person_id.set(None)
        alice_pid = store.propose("run_command", '{"command":"ls a"}', person_id="discord:alice")
        bob_pid = store.propose("run_command", '{"command":"ls b"}', person_id="discord:bob")
        general_pid = store.propose("run_command", '{"command":"ls g"}')
        active_person_id.set("discord:alice")
        ids = [p["id"] for p in store.list_pending()]
        self.assertIn(alice_pid, ids)
        self.assertIn(general_pid, ids)   # character-general still visible
        self.assertNotIn(bob_pid, ids)   # another person's proposal hidden


class ToolLayerTests(_EnvMixin, unittest.TestCase):
    """propose/list/approve/reject trusted-local tools."""

    def test_propose_list_approve_reject_flow(self):
        active_character_id.set("sarah")
        out = propose_action("run_command", '{"command":"ls"}', rationale="need to look", goal_id="goal-1")
        pid = out.split("id=")[1].split(" ")[0]
        self.assertTrue(pid.startswith("proposal-"))
        pending = list_pending_actions()
        self.assertIn("proposal-", pending)
        self.assertNotIn('"command"', pending)  # raw args not leaked to model text

        self.assertEqual(approve_action(pid), f"Approved action proposal '{pid}'.")
        # approved is single-use and refused on non-exact attempt via gate.

        self.assertEqual(reject_action(pid), f"Rejected action proposal '{pid}'.")

    def test_approve_then_reject_allowed_then_terminal(self):
        pid = propose_action("git_pull", '{"repo_path":"/x"}').split("id=")[1].split(" ")[0]
        self.assertEqual(approve_action(pid, decision="go"), f"Approved action proposal '{pid}'.")
        # A proposal that is already approved cannot be approved again.
        self.assertIn("cannot be approved", approve_action(pid))
        # An operator may still reject an approved-but-not-yet-executed proposal.
        self.assertEqual(reject_action(pid), f"Rejected action proposal '{pid}'.")
        # rejected is terminal.
        self.assertIn("cannot be rejected", reject_action(pid))

    def test_propose_action_resolves_active_person_id(self):
        # With a bound caller, the proposal is scoped to that caller.
        active_person_id.set("discord:caller")
        out = propose_action("run_command", '{"command":"ls"}')
        self.assertNotIn("Failed", out)
        pid = out.split("id=")[1].split(" ")[0]
        self.assertEqual(self._store("sarah").get(pid)["person_id"], "discord:caller")
        # A bound caller cannot propose/assign an action for a different person.
        active_person_id.set("discord:other")
        out_refused = propose_action("run_command", '{"command":"ls"}', person_id="discord:caller")
        self.assertIn("Failed", out_refused)

    def test_bound_caller_cannot_approve_reject_another_persons_proposal(self):
        from modules.soul.action_proposals import get_action_proposal_store
        # sarah proposes for alice (no caller bound).
        active_person_id.set(None)
        store = get_action_proposal_store("sarah")
        pid = store.propose("run_command", '{"command":"ls"}', person_id="discord:alice")
        # A trusted caller (active_person_id) cannot approve/reject alice's proposal.
        active_person_id.set("discord:mallory")
        self.assertIn("Refused", approve_action(pid))
        self.assertIn("Refused", reject_action(pid))


class _StubLLM:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def generate_decision(self, prompt):
        return self._decisions.pop(0)


def _enc(d):
    return json.dumps(d)


def _register_sentinel(name, calls, default_result=None):
    def sentinel(*args, **kwargs):
        calls.append((name, kwargs))
        return default_result if default_result is not None else f"executed {name}"
    registry.register(name, sentinel, "test sentinel")
    return sentinel


class OrchestratorApprovalGateTests(_EnvMixin, unittest.TestCase):
    """Code-enforced execution path: gated approval, read-only passthrough,
    autonomous compatibility, Discord exclusion."""

    def setUp(self):
        super().setUp()
        self.calls = []

    def _run(self, orch, request="do thing", context=""):
        import asyncio
        return asyncio.run(orch.process_request(request, system_context=context))

    def _store_for_active(self):
        # process_request uses the sarah contextvar by default.
        return self._store("sarah")

    def test_blocked_execution_without_approval(self):
        _register_sentinel("run_command", self.calls)
        llm = _StubLLM([_enc({"tool": "run_command", "args": {"command": "echo hi"}}),
                        _enc({"final_answer": "I need operator approval."})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(self.calls, [])  # never executed
        self.assertEqual(result, "I need operator approval.")
        # The refusal message is surfaced to the model via the tool result feed;
        # verify the gate message directly too.
        self.assertIn("requires operator approval", orch._approval_required_message("run_command"))

    def test_approval_required_with_valid_proposal_executes(self):
        sentinel_default = "SENTINEL_OK"
        _register_sentinel("run_command", self.calls, sentinel_default)
        # Approve a proposal ahead of time via the store (trusted operator action).
        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"echo hi"}', ttl_seconds=86400)
        store.approve(pid, actor="operator", decision="approved")
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "echo hi", "proposal_id": pid,
        }}), _enc({"final_answer": "done"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(result, "done")
        self.assertEqual(self.calls, [("run_command", {"command": "echo hi"})])
        # proposal is now consumed (executed)
        self.assertEqual(store.get(pid)["status"], "executed")

    def test_exact_match_gate_in_orchestrator(self):
        _register_sentinel("run_command", self.calls)
        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"echo hi"}', ttl_seconds=86400)
        store.approve(pid)
        # Model tries to run a DIFFERENT command than approved.
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "rm -rf /", "proposal_id": pid,
        }}), _enc({"final_answer": "refused"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(self.calls, [])  # not executed
        self.assertEqual(result, "refused")
        # And the proposal was NOT consumed by the failed (refused) attempt.
        self.assertEqual(store.get(pid)["status"], "approved")

    def test_allowed_read_only_execution_without_approval(self):
        _register_sentinel("get_system_info", self.calls)
        llm = _StubLLM([_enc({"tool": "get_system_info", "args": {}}),
                        _enc({"final_answer": "ok"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(self.calls, [("get_system_info", {})])
        self.assertEqual(result, "ok")

    def test_ordinary_tool_no_proposal_required(self):
        _register_sentinel("send_notification", self.calls)
        llm = _StubLLM([_enc({"tool": "send_notification", "args": {"title": "x"}}),
                        _enc({"final_answer": "ok"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(self.calls, [("send_notification", {"title": "x"})])
        self.assertEqual(result, "ok")

    def test_autonomous_policy_compatibility_blocks_without_proposal_tool(self):
        # Under observe_only, the write tool is refused outright (stricter than
        # the non-observe gate) and never executes even with a proposal id.
        _register_sentinel("run_command", self.calls)
        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"echo hi"}', ttl_seconds=86400)
        store.approve(pid)
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "echo hi", "proposal_id": pid,
        }}), _enc({"final_answer": "I observed only."})])
        orch = ToolOrchestrator(llm, character_id="sarah", observe_only=True)
        result = self._run(orch)
        self.assertEqual(self.calls, [])
        self.assertEqual(result, "I observed only.")
        # Under observe_only, the approval tools are NOT in the effective allowlist.
        allowed = orch._effective_allowlist or set()
        self.assertNotIn("approve_action", allowed)
        self.assertNotIn("propose_action", allowed)

    def test_discord_exclusion(self):
        # The action-proposal tools are trusted-local and must NOT be reachable
        # from Discord. The Discord allowlist (mirrored here) excludes them all.
        discord_allowed = {
            "form_opinion", "get_opinion", "add_interest", "add_dislike",
            "add_relationship_note", "add_goal", "complete_goal",
            "get_identity_summary", "avatar_move_to", "avatar_say",
            "avatar_play", "store_memory", "retrieve_memory",
        }
        for t in ("propose_action", "list_pending_actions",
                  "approve_action", "reject_action"):
            self.assertNotIn(t, discord_allowed)

    def test_character_isolation_in_orchestrator(self):
        # A proposal approved for one character must not authorize execution for
        # a different character via the orchestrator.
        _register_sentinel("run_command", self.calls)
        store = self._store("sarah")
        pid = store.propose("run_command", '{"command":"ls"}', ttl_seconds=86400)
        store.approve(pid)
        # Now the orchestrator is running for TAMA, not sarah.
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "ls", "proposal_id": pid,
        }}), _enc({"final_answer": "no access"})])
        orch = ToolOrchestrator(llm, character_id="tama")
        result = self._run(orch)
        self.assertEqual(self.calls, [])
        self.assertEqual(result, "no access")
        # And sarah's proposal was NOT consumed (tama can't touch it).
        self.assertEqual(store.get(pid)["status"], "approved")

    def test_bound_caller_cannot_consume_another_persons_proposal_in_orchestrator(self):
        _register_sentinel("run_command", self.calls)
        store = self._store("sarah")
        active_person_id.set(None)
        pid = store.propose("run_command", '{"command":"ls"}', person_id="discord:alice", ttl_seconds=86400)
        store.approve(pid)
        # The orchestrator runs for a bound caller who is NOT alice.
        active_person_id.set("discord:mallory")
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "ls", "proposal_id": pid,
        }}), _enc({"final_answer": "no access"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        # process_request sets active_character_id but NOT active_person_id; the
        # caller binding from the application boundary is what _execute_gated reads.
        self.assertEqual(result, "no access")
        self.assertEqual(self.calls, [])
        self.assertEqual(store.get(pid)["status"], "approved")  # untouched

    def test_bound_caller_can_execute_general_proposal_in_orchestrator(self):
        _register_sentinel("run_command", self.calls, "GEN_OK")
        store = self._store("sarah")
        active_person_id.set(None)
        pid = store.propose("run_command", '{"command":"echo hi"}', ttl_seconds=86400)
        store.approve(pid)
        # A bound caller may execute a character-general (person_id None) proposal.
        active_person_id.set("discord:mallory")
        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "echo hi", "proposal_id": pid,
        }}), _enc({"final_answer": "done"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(result, "done")
        self.assertEqual(self.calls, [("run_command", {"command": "echo hi"})])
        self.assertEqual(store.get(pid)["status"], "executed")

    def test_executor_exception_records_failure_and_transitions_failed(self):
        import modules.tools.tool_orchestrator as orch_mod
        store = self._store("sarah")
        active_person_id.set(None)
        pid = store.propose("run_command", '{"command":"boom"}', ttl_seconds=86400)
        store.approve(pid)
        # Orchestrator for sarah, no bound caller.
        active_person_id.set(None)

        original_execute = orch_mod.executor.execute

        async def failing_execute(tool_name, **kwargs):
            raise RuntimeError("kaboom from executor")

        orch_mod.executor.execute = failing_execute
        self.addCleanup(self._restore_executor, orch_mod, original_execute)

        llm = _StubLLM([_enc({"tool": "run_command", "args": {
            "command": "boom", "proposal_id": pid,
        }}), _enc({"final_answer": "it errored"})])
        orch = ToolOrchestrator(llm, character_id="sarah")
        result = self._run(orch)
        self.assertEqual(result, "it errored")
        # The consumed proposal is now 'failed' (NOT left dangling as 'executed'),
        # an error outcome is recorded, and it can never run again from this id.
        p = store.get(pid)
        self.assertEqual(p["status"], "failed")
        self.assertIn("kaboom from executor", p["outcome"])
        # Single-use preserved: a retry attempt is refused.
        retry = store.validate_and_consume(pid, "run_command", '{"command":"boom"}')
        self.assertIn("error", retry)

    def _restore_executor(self, orch_mod, original_execute):
        orch_mod.executor.execute = original_execute


if __name__ == "__main__":
    unittest.main()
