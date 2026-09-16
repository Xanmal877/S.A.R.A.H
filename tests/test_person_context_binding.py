import os
import tempfile
import unittest

from modules.context import assemble_character_context
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
)
from modules.soul.person_profiles import (
    _clear_person_profile_store_cache,
    get_person_profile_store,
)
from modules.memory.person_profile_tools import set_person_preference


class PersonContextBindingTests(unittest.TestCase):
    """Bind trusted caller identity (active_person_id) and retrieve only that
    caller's person profile during context assembly.

    Covers: the app boundary owns active_person_id (the LLM never sets it);
    context includes the active caller's profile only when a caller-bound id is
    set; no cross-person profile leakage; and no caller context preserves the
    prior behavior (no [ACTIVE PERSON] section)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_person_profile_store_cache()
        active_character_id.set("sarah")
        active_person_id.set(None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SARAH_STATE_DIR", None)
        else:
            os.environ["SARAH_STATE_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_person_id_bound_by_application_and_resolves_own_profile(self):
        # The trusted boundary sets the caller id (Discord-style) before
        # assembly. Only that caller's profile should surface.
        active_person_id.set("discord:12345")
        store = get_person_profile_store("sarah")
        store.upsert_profile("discord:12345", display_name="Alice")

        ctx = assemble_character_context(agent=None)
        self.assertIn("[ACTIVE PERSON]", ctx)
        self.assertIn("Alice", ctx)
        # The stable person id itself must not leak into model-visible context
        # when a display name is known.
        self.assertNotIn("discord:12345", ctx)

    def test_person_profile_retrieval_is_isolated_by_caller(self):
        # Two callers with different ids, same character store: each context
        # must show only its own profile, never the other caller's.
        store = get_person_profile_store("sarah")
        store.upsert_profile("discord:111", display_name="One")
        store.upsert_profile("discord:222", display_name="Two")

        active_person_id.set("discord:111")
        ctx1 = assemble_character_context(agent=None)
        self.assertIn("[ACTIVE PERSON]", ctx1)
        self.assertIn("One", ctx1)
        self.assertNotIn("Two", ctx1)

        active_person_id.set("discord:222")
        ctx2 = assemble_character_context(agent=None)
        self.assertIn("[ACTIVE PERSON]", ctx2)
        self.assertIn("Two", ctx2)
        self.assertNotIn("One", ctx2)

    def test_no_caller_context_preserves_prior_behavior(self):
        # With active_person_id unset (None), the caller's profile section is
        # omitted entirely - context reads exactly as before this feature.
        set_person_preference("local:operator", "tea", "earl grey")
        ctx = assemble_character_context(agent=None)
        self.assertNotIn("[ACTIVE PERSON]", ctx)
        self.assertNotIn("earl grey", ctx)
        self.assertIn("[AGENT]", ctx)  # rest of context still assembled

    def test_discord_person_id_format(self):
        # Discord binds "discord:<author.id>" - a stable, non-LLM-chosen key.
        active_person_id.set("discord:98765")
        store = get_person_profile_store("sarah")
        store.upsert_profile("discord:98765", display_name="Carol")
        # Changing the display name must NOT re-key identity.
        store.upsert_profile("discord:98765", display_name="Caroline")
        ctx = assemble_character_context(agent=None)
        self.assertIn("Caroline", ctx)
        self.assertIn("[ACTIVE PERSON]", ctx)


if __name__ == "__main__":
    unittest.main()
