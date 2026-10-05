import ast
import os
import pathlib
import tempfile
import unittest

from modules.context import assemble_character_context
from modules.soul.goals import _clear_goal_store_cache
from modules.soul.identity_state.identity_state import _clear_identity_state_cache
from modules.soul.goals.goals import (
    GOALS_VERSION,
    GoalStore,
    render_goals,
)
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
)


def _path(tmpdir, char, name="goals.json"):
    return os.path.join(tmpdir, "state", char, name)


class GoalStoreTests(unittest.TestCase):
    """Phase: versioned, per-character persistent goal lifecycle with a full
    status state machine, bounded priority, and append-only audit history."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_goal_store_cache()
        _clear_identity_state_cache()
        self._clear_person_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    @staticmethod
    def _clear_person_cache():
        try:
            from modules.soul.person_profiles import _clear_person_profile_store_cache
            _clear_person_profile_store_cache()
        except Exception:
            pass

    def test_store_is_versioned_and_character_scoped(self):
        store = GoalStore(character_id="sarah")
        self.assertEqual(store.storage_path, _path(self._tmpdir.name, "sarah"))
        gid = store.create_goal("test goal")
        self.assertTrue(gid.startswith("goal-"))
        self.assertTrue(os.path.exists(store.storage_path))
        import json
        with open(store.storage_path) as f:
            raw = json.load(f)
        self.assertEqual(raw["version"], GOALS_VERSION)
        self.assertIn(gid, raw["goals"])

    def test_goals_are_isolated_character_to_character(self):
        sarah = GoalStore(character_id="sarah")
        tama = GoalStore(character_id="tama")
        gid = sarah.create_goal("sarah's private goal")
        # Tama must not see Sarah's goal.
        self.assertIsNone(tama.get_goal(gid))
        self.assertEqual(tama.count(), 0)
        self.assertEqual(sarah.count(), 1)
        # Tama can have her own goal with the same title, isolated.
        tama_gid = tama.create_goal("sarah's private goal")
        self.assertIsNotNone(tama_gid)
        self.assertEqual(tama.count(), 1)
        # Files are per-character and distinct.
        sarah_file = _path(self._tmpdir.name, "sarah")
        tama_file = _path(self._tmpdir.name, "tama")
        self.assertTrue(os.path.exists(sarah_file))
        self.assertTrue(os.path.exists(tama_file))
        self.assertNotEqual(os.path.realpath(sarah_file), os.path.realpath(tama_file))

    def test_persistence_reload_from_disk(self):
        store = GoalStore(character_id="sarah")
        gid = store.create_goal(
            "finish writeup", rationale="deadline", source="operator",
            priority=5, next_action="draft", person_id="local:operator",
        )
        store.update_goal(gid, next_action="review")
        # A fresh instance (fresh process / reload) must see the saved goal.
        reloaded = GoalStore(character_id="sarah")
        g = reloaded.get_goal(gid)
        self.assertIsNotNone(g)
        self.assertEqual(g["title"], "finish writeup")
        self.assertEqual(g["priority"], 5)
        self.assertEqual(g["next_action"], "review")
        self.assertEqual(g["person_id"], "local:operator")
        self.assertEqual(len(g["history"]), 2)  # create + content update
        # Status transition survives reload too.
        reloaded.activate_goal(gid)
        g2 = GoalStore(character_id="sarah").get_goal(gid)
        self.assertEqual(g2["status"], "active")

    def test_status_lifecycle_and_history(self):
        store = GoalStore(character_id="sarah")
        gid = store.create_goal("release")
        self.assertEqual(store.get_goal(gid)["status"], "proposed")
        store.activate_goal(gid)
        self.assertEqual(store.get_goal(gid)["status"], "active")
        store.mark_blocked(gid, "waiting on keys")
        self.assertEqual(store.get_goal(gid)["status"], "blocked")
        self.assertIn("waiting on keys", store.get_goal(gid)["blockers"])
        store.request_approval(gid)
        self.assertEqual(store.get_goal(gid)["status"], "awaiting_approval")
        store.complete_goal(gid, "shipped to prod")
        self.assertEqual(store.get_goal(gid)["status"], "completed")
        self.assertEqual(store.get_goal(gid)["completion_outcome"], "shipped to prod")
        # Only non-terminal goals count as "active"/live.
        self.assertEqual(store.list_active(), [])
        # Every transition appended an audit entry (create + 4 transitions).
        self.assertEqual(len(store.get_goal(gid)["history"]), 5)

    def test_audit_history_preserves_old_values_not_silent_overwrite(self):
        store = GoalStore(character_id="sarah")
        gid = store.create_goal("old title", priority=2)
        store.update_goal(gid, title="new title", priority=5)
        store.update_goal(gid, title="new title")  # no-op must not append
        store.complete_goal(gid, "done")
        hist = store.get_goal(gid)["history"]
        # Content update recorded both field changes old->new.
        content_entry = [h for h in hist if h["action"] == "content"][0]
        changes = {c["field"]: c for c in content_entry["changes"]}
        self.assertEqual(changes["title"]["old"], "old title")
        self.assertEqual(changes["title"]["new"], "new title")
        self.assertEqual(changes["priority"]["old"], 2)
        self.assertEqual(changes["priority"]["new"], 5)
        # No-op update appended nothing (still just create + content + complete).
        self.assertEqual(len(hist), 3)
        # Status transition preserved prior status in audit.
        status_entry = [h for h in hist if h["action"] == "status"][0]
        self.assertEqual(status_entry["new"], "completed")

    def test_priority_is_bounded(self):
        store = GoalStore(character_id="sarah")
        # Out-of-range & non-numeric priority clamp to 1..5.
        gid = store.create_goal("bounded", priority=99)
        self.assertEqual(store.get_goal(gid)["priority"], 5)
        gid2 = store.create_goal("low", priority=-5)
        self.assertEqual(store.get_goal(gid2)["priority"], 1)
        gid3 = store.create_goal("bad", priority="not-a-number")
        self.assertEqual(store.get_goal(gid3)["priority"], 3)

    def test_terminal_goals_are_immutable(self):
        store = GoalStore(character_id="sarah")
        gid = store.create_goal("done deal")
        store.complete_goal(gid, "done")
        self.assertIsNone(store.activate_goal(gid))
        self.assertIsNone(store.update_goal(gid, title="tamper"))
        self.assertIsNone(store.abandon_goal(gid))
        # Title unchanged & status still terminal.
        g = store.get_goal(gid)
        self.assertEqual(g["title"], "done deal")
        self.assertEqual(g["status"], "completed")

    def test_linked_ids_and_render_hides_raw_ids(self):
        store = GoalStore(character_id="sarah")
        gid = store.create_goal("audited goal", person_id="discord:42",
                                linked_episode_ids=[1, 2], linked_fact_ids=[9])
        rendered = render_goals("sarah", store.list_active())
        # Raw person id must never appear in model text.
        self.assertNotIn("discord:42", rendered)
        # Linked episode/fact ids are summarized by count, never shown raw.
        self.assertNotIn("[1, 2]", rendered)
        self.assertNotIn("[9]", rendered)
        # The stable goal_id IS shown as a reference handle (like episode '#N').
        self.assertIn(gid, rendered)
        # Title is shown and links summarized by count.
        self.assertIn("audited goal", rendered)
        self.assertIn("2 episode(s)", rendered)
        self.assertIn("1 fact(s)", rendered)


class GoalToolTests(unittest.TestCase):
    """Tool-level coverage: caller-identity binding, character isolation, and
    the legacy flat goal tools preserved unchanged."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_goal_store_cache()
        _clear_identity_state_cache()
        self._clear_person_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    @staticmethod
    def _clear_person_cache():
        try:
            from modules.soul.person_profiles import _clear_person_profile_store_cache
            _clear_person_profile_store_cache()
        except Exception:
            pass

    def test_create_with_no_caller_can_specify_person(self):
        from modules.memory.goal_tools import create_goal, list_active_goals
        result = create_goal("operator goal", person_id="local:operator")
        self.assertIn("Created goal", result)
        listing = list_active_goals()
        self.assertIn("operator goal", listing)

    def test_caller_override_blocking(self):
        from modules.memory.goal_tools import (
            abandon_goal,
            complete_goal,
            create_goal,
            mark_goal_active,
            mark_goal_blocked,
            request_goal_approval,
            update_goal,
        )
        # Trusted boundary binds this caller.
        active_person_id.set("discord:12345")
        # Cannot create a goal for a different person.
        self.assertIn("Refused", create_goal("x", person_id="discord:99999"))
        # Can create for self (bound caller).
        r = create_goal("my task", person_id="discord:12345")
        self.assertIn("Created goal", r)
        self.assertNotIn("Refused", r)
        # Extract the id.
        gid = r.split("goal id=")[1].split(" ")[0]
        # Transition tools work on a goal.
        self.assertNotIn("Refused", mark_goal_active(gid))
        self.assertNotIn("Refused", mark_goal_blocked(gid, "need info"))
        # Cannot reassign an existing goal to another person via update.
        self.assertIn("Refused", update_goal(gid, person_id="discord:99999"))
        # The caller can still transition their own goal.
        self.assertNotIn("Refused", request_goal_approval(gid))
        self.assertNotIn("Refused", complete_goal(gid, "finished"))
        self.assertNotIn("Refused", abandon_goal(gid))

    def test_bound_caller_cannot_operate_on_another_persons_goal_by_id(self):
        from modules.memory.goal_tools import (
            complete_goal,
            create_goal,
            update_goal,
        )

        other = create_goal("private task", person_id="discord:other")
        other_id = other.split("goal id=")[1].split(" ")[0]
        active_person_id.set("discord:caller")
        self.assertIn("Refused", update_goal(other_id, title="tampered"))
        self.assertIn("Refused", complete_goal(other_id, "tampered"))

    def test_listing_is_scoped_to_bound_caller(self):
        from modules.memory.goal_tools import create_goal, list_active_goals
        # Without a caller, create a goal for a specific person.
        active_person_id.set(None)
        create_goal("alice goal", person_id="discord:333")
        create_goal("bob goal", person_id="discord:444")
        # Now bind a caller; they see only their own goals.
        active_person_id.set("discord:333")
        listing = list_active_goals()
        self.assertIn("alice goal", listing)
        self.assertNotIn("bob goal", listing)

    def test_explicit_and_legacy_tools_coexist(self):
        from modules.memory.goal_tools import create_goal, list_active_goals
        from modules.memory.identity_tools import add_goal, complete_goal as legacy_complete
        # Legacy writes to identity_state goals (unchanged).
        add_goal("legacy flat goal")
        legacy_complete("legacy flat goal")
        # Explicit store is separate.
        from modules.soul.goals import get_goal_store
        store = get_goal_store("sarah")
        self.assertEqual(store.list_active(), [])
        create_goal("explicit goal")
        self.assertIn("explicit goal", list_active_goals())
        # No collision between explicit complete_goal and legacy complete_goal.
        self.assertEqual(store.count(), 1)

    def test_tools_not_exported_to_discord(self):
        # Goal-writing tools must NOT be in Discord's allowlist. Read the
        # allowlist from source to avoid importing discord.main (side effects).
        repo = pathlib.Path(__file__).resolve().parents[1]
        src = (repo / "discord" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        allowlist = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DISCORD_ALLOWED_TOOLS":
                        allowlist = {elt.value for elt in node.value.elts
                                     if isinstance(elt, ast.Constant)}
        self.assertIsNotNone(allowlist)
        for tool in (
            "create_goal", "list_active_goals", "update_goal",
            "mark_goal_active", "mark_goal_blocked", "request_goal_approval",
            "complete_goal_explicit", "abandon_goal",
        ):
            self.assertNotIn(tool, allowlist)
        # Legacy flat goal tools remain allowed on Discord (unchanged boundary).
        self.assertIn("add_goal", allowlist)
        self.assertIn("complete_goal", allowlist)


class GoalContextTests(unittest.TestCase):
    """The [ACTIVE GOALS] section prefers the explicit store and only falls
    back to legacy identity goals when the store has nothing live."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_goal_store_cache()
        _clear_identity_state_cache()
        self._clear_person_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    @staticmethod
    def _clear_person_cache():
        try:
            from modules.soul.person_profiles import _clear_person_profile_store_cache
            _clear_person_profile_store_cache()
        except Exception:
            pass

    def test_context_shows_explicit_goals(self):
        from modules.memory.goal_tools import create_goal
        gid_line = create_goal("refactor daemon", priority=5)
        gid = gid_line.split("goal id=")[1].split(" ")[0]
        ctx = assemble_character_context(agent=None)
        self.assertIn("[ACTIVE GOALS]", ctx)
        self.assertIn("refactor daemon", ctx)
        # The stable goal id is present so the loop can act on it.
        self.assertIn(gid, ctx)

    def test_context_prefers_explicit_over_legacy(self):
        # Seed legacy identity goals AND an explicit store goal. The [ACTIVE
        # GOALS] section must prefer the explicit one and omit legacy (treating
        # it as fallback only). Note: the [AGENT] identity summary legitimately
        # still lists legacy identity goals, so assertions target the section.
        from modules.memory.goal_tools import create_goal
        from modules.memory.identity_tools import add_goal
        add_goal("legacy goal text")
        create_goal("explicit goal text")
        ctx = assemble_character_context(agent=None)
        section = _active_goals_section(ctx)
        self.assertNotIn("legacy goal text", section)
        self.assertIn("explicit goal text", section)

    def test_context_falls_back_to_legacy_when_store_empty(self):
        from modules.memory.identity_tools import add_goal
        add_goal("legacy fallback goal")
        ctx = assemble_character_context(agent=None)
        section = _active_goals_section(ctx)
        self.assertIn("legacy fallback goal", section)

    def test_goal_section_hides_raw_person_id_but_shows_goal_id(self):
        from modules.memory.goal_tools import create_goal
        line = create_goal("caller task", person_id="discord:777")
        gid = line.split("goal id=")[1].split(" ")[0]
        active_person_id.set("discord:777")
        ctx = assemble_character_context(agent=None)
        section = _active_goals_section(ctx)
        self.assertIn("caller task", section)
        # Raw person id must not leak, goal id must be present (handle).
        self.assertNotIn("discord:777", section)
        self.assertIn(gid, section)


def _active_goals_section(ctx: str) -> str:
    """Extract just the [ACTIVE GOALS] block (falling back to '' if absent) so
    assertions on the section don't trip over the [AGENT] identity summary,
    which legitimately includes legacy identity goals."""
    marker = "[ACTIVE GOALS]"
    start = ctx.find(marker)
    if start == -1:
        return ""
    body = ctx[start + len(marker):]
    # Slice up to the next section marker line.
    for sect in ("[MENTAL STATE]", "[ACTIVE PERSON]", "[RELEVANT MEMORIES]",
                 "[RELEVANT FACTS]", "[PERCEPTION]"):
        idx = body.find(sect)
        if idx != -1:
            body = body[:idx]
            break
    return body


if __name__ == "__main__":
    unittest.main()
