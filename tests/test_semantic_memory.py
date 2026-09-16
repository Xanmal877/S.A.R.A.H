import os
import pathlib
import sqlite3
import tempfile
import unittest

from modules.memory.episodic_memory import (
    _clear_episodic_store_cache,
    get_episodic_store,
)
from modules.memory.semantic_memory import (
    _clear_semantic_store_cache,
    get_semantic_store,
    semantic_fact_summary,
)
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
)


class SemanticMemoryStorageTests(unittest.TestCase):
    """Storage path honoring SARAH_STATE_DIR, persistence/reload, and the
    explicit append-only fact schema."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def _path(self, char):
        return os.path.join(self._tmpdir.name, "state", char, "semantic_memory.sqlite")

    def test_store_uses_character_scoped_sqlite_path(self):
        from modules.memory.semantic_memory import SemanticMemoryStore
        store = SemanticMemoryStore(character_id="sarah")
        self.assertEqual(store.storage_path, self._path("sarah"))
        store.add_fact("home", "has a garden", source_note="manual")
        self.assertTrue(os.path.exists(store.storage_path))

    def test_schema_has_expected_explicit_columns(self):
        from modules.memory.semantic_memory import SemanticMemoryStore
        store = SemanticMemoryStore(character_id="sarah")
        store.add_fact("home", "has a garden", person_id="p1", source_episode_id=3,
                       source_note="note", confidence=0.8, salience=0.6,
                       metadata={"k": "v"})
        conn = sqlite3.connect(store.storage_path)
        cur = conn.execute("PRAGMA table_info(facts)")
        cols = {row[1] for row in cur.fetchall()}
        conn.close()
        for col in ("fact_id", "character_id", "person_id", "topic", "value",
                    "source_episode_id", "source_note", "confidence", "salience",
                    "status", "created_at", "superseded_at", "metadata_json"):
            self.assertIn(col, cols)

    def test_facts_persist_after_reload(self):
        store = get_semantic_store("sarah")
        store.add_fact("pet", "likes cats", person_id="p1", source_episode_id=1)
        from modules.memory.semantic_memory import SemanticMemoryStore
        reloaded = SemanticMemoryStore(character_id="sarah")
        self.assertEqual(reloaded.count(), 1)
        self.assertEqual(reloaded.retrieve(person_id="p1")[0]["topic"], "pet")


class SemanticRevisionTests(unittest.TestCase):
    """Append-only revision model: same scope+topic supersedes, never deletes."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        self.store = get_semantic_store("sarah")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_new_fact_supersedes_prior_active_in_same_scope_topic(self):
        old = self.store.add_fact("home", "lives downtown", source_note="old")
        new = self.store.add_fact("home", "moved to the suburbs", source_note="new")
        # The new revision is active.
        active = self.store.retrieve(topic="home", active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["fact_id"], new)
        self.assertEqual(active[0]["value"], "moved to the suburbs")
        # The old revision is superseded (not deleted): full history survives.
        prev = self.store.get_fact(old)
        self.assertEqual(prev["status"], "superseded")
        self.assertIsNotNone(prev["superseded_at"])
        self.assertEqual(prev["value"], "lives downtown")
        # Total row count keeps both revisions.
        self.assertEqual(self.store.count(), 2)

    def test_retrieve_defaults_to_active_only(self):
        self.store.add_fact("food", "likes tea")
        self.store.add_fact("food", "prefers coffee")
        rows = self.store.retrieve(topic="food")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "prefers coffee")

    def test_scope_keeps_general_and_person_facts_distinct(self):
        self.store.add_fact("pet", "has a dog", person_id=None)
        self.store.add_fact("pet", "has a cat", person_id="alice")
        # Different scope (NULL vs alice) must NOT supersede each other.
        general_active = [f for f in self.store.retrieve(topic="pet", active_only=True)
                          if f["person_id"] is None]
        self.assertEqual(len(general_active), 1)
        self.assertEqual(general_active[0]["value"], "has a dog")
        # alice's scope sees her own fact plus the general one (never a
        # different person's) - both are intended, distinct revisions.
        alice = [f for f in self.store.retrieve(topic="pet", person_id="alice", active_only=True)
                 if f["person_id"] == "alice"]
        self.assertEqual(len(alice), 1)
        self.assertEqual(alice[0]["value"], "has a cat")
        # Distinct scopes are never superseded by each other: both active rows
        # exist and the count keeps both.
        self.assertEqual(self.store.count(), 2)

    def test_same_person_subsequent_revisions_supersede_within_scope(self):
        # Two general facts same topic -> second supersedes first.
        self.store.add_fact("pet", "has a dog", person_id=None)
        self.store.add_fact("pet", "switched to a cat", person_id=None)
        general = [f for f in self.store.retrieve(topic="pet", active_only=True)
                   if f["person_id"] is None]
        self.assertEqual(len(general), 1)
        self.assertEqual(general[0]["value"], "switched to a cat")

    def test_same_person_supersedes(self):
        self.store.add_fact("taste", "likes jazz", person_id="alice")
        self.store.add_fact("taste", "now prefers blues", person_id="alice")
        alice = self.store.retrieve(topic="taste", person_id="alice", active_only=True)
        self.assertEqual(len(alice), 1)
        self.assertEqual(alice[0]["value"], "now prefers blues")

    def test_differs_across_person_ids(self):
        self.store.add_fact("taste", "likes jazz", person_id="alice")
        self.store.add_fact("taste", "likes rock", person_id="bob")
        self.assertEqual(self.store.count(), 2)
        alice = {f["value"] for f in self.store.retrieve(topic="taste", person_id="alice")}
        bob = {f["value"] for f in self.store.retrieve(topic="taste", person_id="bob")}
        self.assertIn("likes jazz", alice)
        self.assertIn("likes rock", bob)


class SemanticIsolationTests(unittest.TestCase):
    """Retrieval/consolidation never crosses character or person boundaries."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        # Person id is "alice", but the value text deliberately does not embed
        # that word, so raw-id-hiding tests can assert the id never surfaces.
        get_semantic_store("sarah").add_fact(
            "secret", "sarah private fact", person_id="alice")
        get_semantic_store("sarah").add_fact(
            "general", "sarah general fact", person_id=None)
        get_semantic_store("tama").add_fact(
            "secret", "tama private fact", person_id="bob")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_character_scope_isolates_characters(self):
        sarah = {f["value"] for f in get_semantic_store("sarah").retrieve(query="private")}
        tama = {f["value"] for f in get_semantic_store("tama").retrieve(query="private")}
        self.assertIn("sarah private fact", sarah)
        self.assertNotIn("tama private fact", sarah)
        self.assertIn("tama private fact", tama)
        self.assertNotIn("sarah private fact", tama)

    def test_person_scope_never_crosses_person_boundary(self):
        store = get_semantic_store("sarah")
        alice = {f["value"] for f in store.retrieve(person_id="alice")}
        self.assertIn("sarah private fact", alice)
        self.assertIn("sarah general fact", alice)  # general NULL-person fact
        # A different (unknown) person must not see alice's private fact.
        bob = {f["value"] for f in store.retrieve(person_id="bob")}
        self.assertNotIn("sarah private fact", bob)
        self.assertIn("sarah general fact", bob)

    def test_summary_omits_raw_stable_person_ids(self):
        summary = semantic_fact_summary("sarah", person_id="alice")
        self.assertIn("sarah private fact", summary)
        self.assertNotIn("alice", summary)


class SemanticSourceValidationTests(unittest.TestCase):
    """consolidate_episode verifies the source episode belongs to the character."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        # Sarah owns a small set of episodes (ids 1..N).
        self.sarah_ep = get_episodic_store("sarah").record(
            "conversation", "alice said she loves gardens", source="cli",
            person_id="alice")
        # Give sarah an extra episode so its owned ids span 1..2.
        get_episodic_store("sarah").record("task", "extra task", source="cli")
        # Tama's episode ids are independent and start at 1 again; to get an id
        # sarah does NOT own, record 3 tama episodes so tama's 3rd id (=3) is
        # outside sarah's {1,2} set while still belonging to a real episode.
        get_episodic_store("tama").record("conversation", "bob a", source="cli", person_id="bob")
        get_episodic_store("tama").record("conversation", "bob b", source="cli", person_id="bob")
        self.tama_ep = get_episodic_store("tama").record(
            "conversation", "bob c private", source="cli", person_id="bob")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_consolidate_only_reads_own_character_episode(self):
        from modules.memory.semantic_tools import consolidate_episode
        # The tama-owned episode is invisible to sarah's store - consolidation
        # must not read it as if it were sarah's, and must write nothing.
        before = get_semantic_store("sarah").count()
        result = consolidate_episode(self.tama_ep, "topic", "value")
        self.assertNotIn("Consolidated fact", result)
        self.assertEqual(get_semantic_store("sarah").count(), before)
        # Sarah's own episode -> accepted, provenance recorded.
        result = consolidate_episode(self.sarah_ep, "hobby", "alice loves gardens")
        self.assertIn("Consolidated fact #", result)
        facts = get_semantic_store("sarah").retrieve(person_id="alice", topic="hobby")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["source_episode_id"], self.sarah_ep)

    def test_missing_episode_is_rejected(self):
        from modules.memory.semantic_tools import consolidate_episode
        result = consolidate_episode(999999, "topic", "value")
        self.assertIn("No episode #999999", result)
        self.assertEqual(get_semantic_store("sarah").count(), 0)

    def test_missing_episode_is_rejected(self):
        from modules.memory.semantic_tools import consolidate_episode
        result = consolidate_episode(999999, "topic", "value")
        self.assertIn("No episode #999999", result)
        self.assertEqual(get_semantic_store("sarah").count(), 0)

    def test_consolidated_fact_inherits_episode_person_scope(self):
        from modules.memory.semantic_tools import consolidate_episode
        consolidate_episode(self.sarah_ep, "hobby", "alice loves gardens")
        # The fact is scoped to the source episode's person (alice).
        alice = {f["value"] for f in get_semantic_store("sarah").retrieve(person_id="alice", topic="hobby")}
        self.assertIn("alice loves gardens", alice)
        bob = get_semantic_store("sarah").retrieve(person_id="bob", topic="hobby")
        self.assertEqual(bob, [])


class SemanticCallerOverrideTests(unittest.TestCase):
    """A bound caller cannot read/link another person's episode or write another
    person's fact."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        self.alice_ep = get_episodic_store("sarah").record(
            "conversation", "alice private", source="cli", person_id="alice")
        self.operator_ep = get_episodic_store("sarah").record(
            "conversation", "operator general chat", source="cli", person_id=None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_bound_caller_cannot_consolidate_another_episode(self):
        from modules.memory.semantic_tools import consolidate_episode
        active_person_id.set("local:operator")
        result = consolidate_episode(self.alice_ep, "topic", "value")
        self.assertIn("Refused", result)
        self.assertIn("another person's episode", result)
        self.assertEqual(get_semantic_store("sarah").count(), 0)

    def test_bound_caller_can_consolidate_own_or_general_episode(self):
        from modules.memory.semantic_tools import consolidate_episode
        active_person_id.set("local:operator")
        # Own (general/NULL) episode consolidates fine and scopes to caller.
        result = consolidate_episode(self.operator_ep, "routine", "operator likes early starts")
        self.assertIn("Consolidated fact #", result)
        facts = get_semantic_store("sarah").retrieve(person_id="local:operator", topic="routine")
        self.assertEqual(facts[0]["value"], "operator likes early starts")
        self.assertEqual(facts[0]["source_episode_id"], self.operator_ep)

    def test_bound_caller_cannot_write_another_persons_fact(self):
        from modules.memory.semantic_tools import add_semantic_fact
        active_person_id.set("local:operator")
        result = add_semantic_fact("topic", "value", person_id="alice")
        self.assertIn("Refused", result)
        self.assertIn("identity cannot be overridden", result)
        self.assertEqual(get_semantic_store("sarah").count(), 0)

    def test_bound_caller_cannot_read_another_persons_facts(self):
        from modules.memory.semantic_tools import retrieve_facts
        get_semantic_store("sarah").add_fact("secret", "alice's private fact", person_id="alice")
        active_person_id.set("local:operator")
        result = retrieve_facts(person_id="alice")
        self.assertIn("Refused", result)
        self.assertIn("identity cannot be overridden", result)


class SemanticContextTests(unittest.TestCase):
    """Context inclusion of the [RELEVANT FACTS] section, bounded and raw-id free."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_semantic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_context_includes_relevant_facts_for_caller_and_goal(self):
        from modules.context import assemble_character_context
        from modules.memory.semantic_tools import add_semantic_fact
        active_person_id.set("local:operator")
        add_semantic_fact("project", "garden redesign is the priority", salience=0.9)
        add_semantic_fact("errand", "unrelated", salience=0.3)
        ctx = assemble_character_context(agent=None, goal="garden redesign")
        self.assertIn("[RELEVANT FACTS]", ctx)
        self.assertIn("garden redesign is the priority", ctx)

    def test_context_section_omitted_when_no_facts(self):
        from modules.context import assemble_character_context
        ctx = assemble_character_context(agent=None, goal="anything")
        self.assertNotIn("[RELEVANT FACTS]", ctx)


class SemanticDiscordExclusionTests(unittest.TestCase):
    """Semantic write/read tools are NOT in the Discord allowlist."""

    def test_discord_allowlist_excludes_semantic_tools(self):
        import ast
        repo = pathlib.Path(__file__).resolve().parents[1]
        src = (repo / "discord" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        allowlist = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DISCORD_ALLOWED_TOOLS":
                        allowlist = {
                            elt.value for elt in node.value.elts
                            if isinstance(elt, ast.Constant)
                        }
        self.assertIsNotNone(allowlist)
        for tool in ("consolidate_episode", "add_semantic_fact",
                     "retrieve_facts", "get_semantic_fact_summary"):
            self.assertNotIn(tool, allowlist)


if __name__ == "__main__":
    unittest.main()
