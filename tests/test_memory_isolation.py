import os
import tempfile
import unittest

from modules.memory.change_history import ChangeHistory
from modules.memory.persistent_memory import PersistentMemory
from modules.soul.identity_state.identity_state import active_character_id


class CharacterMemoryIsolationTests(unittest.TestCase):
    """Phase 1: long-term memory and change history are character-scoped under
    ~/.sarah/state/{character_id} and resolve the character via
    active_character_id, so Sarah and Tama keep separate memories/history."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        # Redirect state elsewhere so tests never touch the real ~/.sarah tree.
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        # A fresh character context for each test; default reset so tests are
        # deterministic regardless of a previously-set contextvar.
        active_character_id.set("sarah")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_memory_stored_at_character_scoped_path(self):
        mem = PersistentMemory(character_id="sarah")
        mem.store("key_a", "alpha")
        expected = os.path.join(self._tmpdir.name, "state", "sarah", "memory.json")
        self.assertEqual(mem.storage_path, expected)
        self.assertTrue(os.path.exists(expected))

    def test_memories_are_isolated_between_characters(self):
        sarah = PersistentMemory(character_id="sarah")
        tama = PersistentMemory(character_id="tama")
        sarah.store("key", "Sarah's value")
        # Tama must not see Sarah's memory.
        self.assertIsNone(tama.retrieve("key"))
        tama.store("key", "Tama's value")
        self.assertEqual(sarah.retrieve("key"), "Sarah's value")
        self.assertEqual(tama.retrieve("key"), "Tama's value")

    def test_memory_is_persistent_after_reload(self):
        first = PersistentMemory(character_id="sarah")
        first.store("persisted", "still here")
        # Reload from disk - a fresh instance must see the saved value.
        second = PersistentMemory(character_id="sarah")
        self.assertEqual(second.retrieve("persisted"), "still here")

    def test_change_history_is_character_scoped(self):
        sarah = ChangeHistory(character_id="sarah")
        tama = ChangeHistory(character_id="tama")
        sarah.record("req", "act", "result")
        self.assertEqual(len(tama.get_recent()), 0)
        self.assertEqual(len(sarah.get_recent()), 1)

    def test_memory_tools_resolve_character_via_active_character_id(self):
        # The tools resolve "whose memory" from the contextvar, not a global.
        from modules.memory.memory_tools import retrieve_memory, store_memory
        active_character_id.set("sarah")
        store_memory("owner", "sarah-owned")
        active_character_id.set("tama")
        store_memory("owner", "tama-owned")
        active_character_id.set("sarah")
        self.assertEqual(retrieve_memory("owner"), "sarah-owned")
        active_character_id.set("tama")
        self.assertEqual(retrieve_memory("owner"), "tama-owned")


if __name__ == "__main__":
    unittest.main()
