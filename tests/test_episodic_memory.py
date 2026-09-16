import os
import sqlite3
import tempfile
import unittest

from modules.context import assemble_character_context
from modules.memory.episodic_memory import (
    _clear_episodic_store_cache,
    episodic_memory_summary,
    get_episodic_store,
)
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
)


class EpisodicMemoryStorageTests(unittest.TestCase):
    """Phase: durable per-character episodic memory backed by stdlib SQLite.

    Covers: storage path honoring SARAH_STATE_DIR, persistence/reload, and the
    explicit append-only event schema (no auto-capture)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
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
        return os.path.join(self._tmpdir.name, "state", char, "episodes.sqlite")

    def test_store_uses_character_scoped_sqlite_path(self):
        from modules.memory.episodic_memory import EpisodicMemoryStore
        store = EpisodicMemoryStore(character_id="sarah")
        self.assertEqual(store.storage_path, self._path("sarah"))
        store.record("observation", "saw the garden", source="manual")
        self.assertTrue(os.path.exists(store.storage_path))

    def test_schema_has_expected_explicit_columns(self):
        from modules.memory.episodic_memory import EpisodicMemoryStore
        store = EpisodicMemoryStore(character_id="sarah")
        store.record("task", "fix", source="manual", confidence=0.8, salience=0.6,
                     goal_id="g1", person_id="p1", metadata={"k": "v"})
        conn = sqlite3.connect(store.storage_path)
        cur = conn.execute("PRAGMA table_info(episodes)")
        cols = {row[1] for row in cur.fetchall()}
        conn.close()
        for col in ("id", "recorded_at", "character_id", "person_id", "kind",
                    "content", "source", "confidence", "salience", "goal_id",
                    "metadata_json"):
            self.assertIn(col, cols)

    def test_episodes_persist_after_reload(self):
        store = get_episodic_store("sarah")
        store.record("conversation", "told a story", source="cli", person_id="p1")
        # Fresh store instance reading the same file.
        from modules.memory.episodic_memory import EpisodicMemoryStore
        reloaded = EpisodicMemoryStore(character_id="sarah")
        self.assertEqual(reloaded.count(), 1)

    def test_episode_write_is_append_only_and_returns_id(self):
        store = get_episodic_store("sarah")
        row_a = store.record("kind_a", "first", source="r1")
        row_b = store.record("kind_b", "second", source="r2")
        self.assertIsNotNone(row_a)
        self.assertGreater(row_b, row_a)
        self.assertEqual(store.count(), 2)


class EpisodicIsolationTests(unittest.TestCase):
    """Retrieval/composition never crosses character or person boundaries."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        # Seed per-character + per-person data once per test class run.
        get_episodic_store("sarah").record(
            "conversation", "sarah private talk", source="cli", person_id="alice")
        get_episodic_store("sarah").record(
            "conversation", "sarah general note", source="cli")
        get_episodic_store("tama").record(
            "conversation", "tama talk", source="cli", person_id="bob")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_character_scope_isolates_characters(self):
        sarah = get_episodic_store("sarah").retrieve(kinds=["conversation"], rank="recency")
        tama = get_episodic_store("tama").retrieve(kinds=["conversation"], rank="recency")
        sarah_texts = {e["content"] for e in sarah}
        tama_texts = {e["content"] for e in tama}
        self.assertIn("sarah private talk", sarah_texts)
        self.assertNotIn("tama talk", sarah_texts)
        self.assertIn("tama talk", tama_texts)
        self.assertNotIn("sarah private talk", tama_texts)

    def test_person_scope_never_crosses_person_boundary(self):
        store = get_episodic_store("sarah")
        # Person-scoped retrieval for alice: her own + general, never a
        # different person's.
        alice = {e["content"] for e in store.retrieve(person_id="alice", rank="recency")}
        self.assertIn("sarah private talk", alice)
        self.assertIn("sarah general note", alice)
        # A different (unknown) person must not see alice's private episode.
        bob = {e["content"] for e in store.retrieve(person_id="bob")}
        self.assertNotIn("sarah private talk", bob)
        self.assertIn("sarah general note", bob)

    def test_summary_omits_raw_stable_person_ids(self):
        summary = episodic_memory_summary("sarah", person_id="alice")
        self.assertIn("sarah private talk", summary)
        self.assertNotIn("alice", summary)


class EpisodicRetrievalBehaviorTests(unittest.TestCase):
    """Ranking, kind/filter, query text, and bounded limit."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)
        store = get_episodic_store("sarah")
        store.record("task", "fix the daemon crash", source="cli", salience=0.9,
                     confidence=0.95)
        store.record("observation", "garden grew roses", source="manual", salience=0.3)
        store.record("conversation", "talked about tea", source="cli", salience=0.7)
        store.record("conversation", "debugged the daemon with alice", source="cli",
                     salience=0.5, person_id="alice")
        self.store = store

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_salience_ranking_orders_highest_first(self):
        ranks = [e["content"] for e in self.store.retrieve(rank="salience")]
        self.assertEqual(ranks[0], "fix the daemon crash")
        self.assertEqual(ranks[1], "talked about tea")  # salience 0.7
        self.assertEqual(ranks[2], "debugged the daemon with alice")  # 0.5

    def test_recency_ranking_orders_by_recorded_at(self):
        ranks = [e["content"] for e in self.store.retrieve(rank="recency")]
        self.assertEqual(ranks[-1], "fix the daemon crash")  # recorded first

    def test_kind_filter_restricts_results(self):
        only_conv = self.store.retrieve(kinds=["conversation"], rank="recency")
        self.assertTrue(all(e["kind"] == "conversation" for e in only_conv))
        self.assertEqual(len(only_conv), 2)

    def test_query_text_filters_content(self):
        matches = self.store.retrieve(query="daemon", rank="recency")
        texts = {e["content"] for e in matches}
        self.assertIn("fix the daemon crash", texts)
        self.assertNotIn("garden grew roses", texts)

    def test_bounded_limit(self):
        limited = self.store.retrieve(limit=2, rank="salience")
        self.assertEqual(len(limited), 2)
        # Limit is clamped non-negatively.
        self.assertTrue(1 <= len(self.store.retrieve(limit=0)) <= 4)

    def test_sql_parameterization_blocks_injection(self):
        # A malicious query string must be treated as data, not executable SQL.
        needle = "'; DROP TABLE episodes;--"
        # Add a normal row so we can assert it survives.
        get_episodic_store("sarah").record("task", "safe row", source="cli")
        rows = get_episodic_store("sarah").retrieve(query=needle)
        self.assertEqual(rows, [])
        # Table still exists and holds the records - nothing got dropped.
        self.assertTrue(get_episodic_store("sarah").count() >= 1)
        conn = sqlite3.connect(get_episodic_store("sarah").storage_path)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        self.assertIn("episodes", tables)


class EpisodicContextAndDiscordTests(unittest.TestCase):
    """Context inclusion and Discord allowlist exclusion."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_episodic_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_context_includes_relevant_memories_for_caller_and_goal(self):
        from modules.memory.episodic_tools import record_episode
        active_person_id.set("local:operator")
        record_episode("task", "planning the garden redesign", source="cli",
                       salience=0.9)
        record_episode("task", "unrelated errand", source="cli", salience=0.5)
        active_person_id.set("local:operator")
        ctx = assemble_character_context(agent=None, goal="garden redesign")
        self.assertIn("[RELEVANT MEMORIES]", ctx)
        self.assertIn("planning the garden redesign", ctx)

    def test_tools_cannot_override_a_bound_caller_identity(self):
        from modules.memory.episodic_tools import record_episode, retrieve_episodes

        active_person_id.set("discord:trusted")
        self.assertIn(
            "Refused",
            record_episode("conversation", "attempted cross-person write", person_id="discord:other"),
        )
        self.assertIn(
            "Refused",
            retrieve_episodes(person_id="discord:other"),
        )
        self.assertEqual(get_episodic_store("sarah").count(), 0)

    def test_disord_allowlist_excludes_episodic_tools(self):
        import ast
        import pathlib
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
        for tool in ("record_episode", "retrieve_episodes", "get_memory_summary"):
            self.assertNotIn(tool, allowlist)


if __name__ == "__main__":
    unittest.main()
