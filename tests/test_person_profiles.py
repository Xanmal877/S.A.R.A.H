import os
import tempfile
import unittest

from modules.soul.person_profiles.person_profile import (
    PERSON_PROFILES_VERSION,
    PersonProfileStore,
)
from modules.soul.person_profiles import _clear_person_profile_store_cache
from modules.soul.identity_state.identity_state import (
    _clear_identity_state_cache,
    active_character_id,
)


class PersonProfileStoreTests(unittest.TestCase):
    """Phase: versioned, character-private, structured person profiles.

    Covers: per-character isolation (Sarah vs Tama), profile update/reload
    from disk, and fact provenance (source/confidence/timestamp) for each
    write. Also that the existing free-text add_relationship_note is
    preserved unchanged (not silently migrated into a guessed default
    person)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        # Fresh store instances per test - the registry caches stores keyed by
        # their construction-time storage_path, which would otherwise leak
        # across redirected temp dirs between test methods.
        _clear_person_profile_store_cache()
        _clear_identity_state_cache()
        active_character_id.set("sarah")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def _path(self, char):
        return os.path.join(self._tmpdir.name, "state", char, "person_profiles.json")

    def test_store_is_versioned_and_character_scoped(self):
        store = PersonProfileStore(character_id="sarah")
        self.assertEqual(store._version, PERSON_PROFILES_VERSION)
        self.assertEqual(store.storage_path, self._path("sarah"))
        store.upsert_profile("alice", display_name="Alice")
        self.assertTrue(os.path.exists(store.storage_path))
        with open(store.storage_path) as f:
            import json
            raw = json.load(f)
        self.assertEqual(raw["version"], PERSON_PROFILES_VERSION)
        self.assertIn("alice", raw["people"])

    def test_profiles_are_isolated_character_to_character(self):
        sarah = PersonProfileStore(character_id="sarah")
        tama = PersonProfileStore(character_id="tama")
        sarah.upsert_profile("bob", display_name="Bob")
        sarah.set_preference("bob", "tea", "earl grey", source="conversation")
        # Tama must not see Sarah's person profiles.
        self.assertIsNone(tama.get_profile("bob"))
        # Tama can have her own, different profile for the same person.
        tama.upsert_profile("bob", display_name="Mr. B")
        self.assertEqual(tama.get_profile("bob")["display_name"], "Mr. B")
        self.assertEqual(sarah.get_profile("bob")["display_name"], "Bob")
        # No cross-character file contamination.
        self.assertTrue(os.path.exists(self._path("sarah")))
        self.assertTrue(os.path.exists(self._path("tama")))

    def test_profile_update_and_reload_from_disk(self):
        store = PersonProfileStore(character_id="sarah")
        store.upsert_profile("carol", display_name="Carol")
        store.set_preference("carol", "coffee", "espresso", source="said")
        store.set_consent_boundary("carol", "photos", "declined", source="explicit")
        # A fresh instance (fresh process / reload) must see the saved profile.
        reloaded = PersonProfileStore(character_id="sarah")
        profile = reloaded.get_profile("carol")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["display_name"], "Carol")
        self.assertEqual(profile["preferences"]["coffee"]["value"], "espresso")
        self.assertEqual(profile["consent_boundaries"]["photos"]["value"], "declined")

    def test_display_name_update_keeps_same_stable_person_id(self):
        store = PersonProfileStore(character_id="sarah")
        store.upsert_profile("dave", display_name="Dave")
        store.upsert_profile("dave", display_name="David")  # same id, new name
        profile = store.get_profile("dave")
        self.assertEqual(profile["display_name"], "David")
        # Only one profile for the id - update, not a duplicate.
        self.assertEqual(len(store.list_profiles()), 1)

    def test_facts_carry_provenance_source_confidence_timestamp(self):
        store = PersonProfileStore(character_id="sarah")
        store.upsert_profile("erin", display_name="Erin", source="manual-entry", confidence=0.9)
        record = store.add_relationship_note(
            "erin", "loves hiking", source="self-reported", confidence=0.85
        )
        pref = store.set_preference(
            "erin", "cities", "prefers quiet suburbs", source="overheard", confidence=0.4
        )
        store.set_consent_boundary("erin", "contact", "email only", source="stated", confidence=0.95)

        profile = store.get_profile("erin")
        # Profile-level provenance was appended for each write.
        self.assertTrue(profile["provenance"])
        # Relationship note record is timestamped and attributed.
        self.assertEqual(record["source"], "self-reported")
        self.assertEqual(record["confidence"], 0.85)
        self.assertTrue(record["recorded_at"])
        # Preference record is timestamped and attributed.
        self.assertEqual(pref["source"], "overheard")
        self.assertEqual(pref["confidence"], 0.4)
        self.assertTrue(pref["recorded_at"])
        # Reload preserves every provenance line (nothing stripped on round-trip).
        reloaded = PersonProfileStore(character_id="sarah")
        self.assertEqual(len(reloaded.get_profile("erin")["provenance"]), 4)

    def test_unknown_profile_version_fails_closed(self):
        store = PersonProfileStore(character_id="sarah")
        store._version = 999
        store.upsert_profile("frank")
        # Corrupt the stored version to something the store can't parse.
        import json
        with open(store.storage_path, "w") as f:
            json.dump({"version": 999, "people": {"frank": {"person_id": "frank"}}}, f)
        # A store reading an unknown version must NOT guess; it loads empty.
        unknown = PersonProfileStore(character_id="sarah")
        self.assertIsNone(unknown.get_profile("frank"))

    def test_free_text_relationship_note_tool_preserved(self):
        # The legacy identity-level add_relationship_note remains the unchanged
        # free-text tool on the character's OWN identity_state (no person), and
        # is NOT auto-routed into a guessed default person profile.
        from modules.memory.identity_tools import add_relationship_note, _identity
        active_character_id.set("sarah")
        add_relationship_note("remember our running joke")
        self.assertTrue(
            any(n["note"] == "remember our running joke" for n in _identity().relationship_notes)
        )
        # And no person profile was created by it.
        store = PersonProfileStore(character_id="sarah")
        self.assertEqual(store.list_profiles(), [])


class PersonProfileToolTests(unittest.TestCase):
    """Tool-level coverage: the typed person-profile tools resolve 'whose
    store' via active_character_id, same as identity tools."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_person_profile_store_cache()
        _clear_identity_state_cache()
        active_character_id.set("sarah")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_tools_resolve_character_via_active_character_id(self):
        from modules.memory.person_profile_tools import (
            add_person_relationship_note,
            get_person_profile,
            set_person_preference,
            upsert_person_profile,
        )
        active_character_id.set("sarah")
        upsert_person_profile("grace", display_name="Grace")
        set_person_preference("grace", "book", "sci-fi", source="mentioned")
        add_person_relationship_note("grace", "we met at the cafe", source="conversation")

        active_character_id.set("tama")
        # Tama must not see Sarah's person profile.
        from modules.memory.person_profile_tools import list_person_profiles
        self.assertIn("No person profiles", list_person_profiles())

        active_character_id.set("sarah")
        profile_text = get_person_profile("grace")
        self.assertIn("Grace", profile_text)
        self.assertIn("sci-fi", profile_text)

    def test_new_write_tools_not_exported_to_discord(self):
        # These person-profile writes are not part of Discord's allowlist until
        # an authorization design exists. We read the allowlist from source
        # rather than importing discord.main (which runs bot bootstrap side
        # effects: .env creation, Ollama model pulls, log files).
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
        for tool in (
            "upsert_person_profile",
            "set_person_preference",
            "set_person_consent_boundary",
            "add_person_relationship_note",
            "list_person_profiles",
            "get_person_profile",
        ):
            self.assertNotIn(tool, allowlist)


if __name__ == "__main__":
    unittest.main()
