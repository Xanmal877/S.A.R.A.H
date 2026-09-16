import os
import tempfile
import unittest

from modules.soul.goals import _clear_goal_store_cache, get_goal_store
from modules.soul.goals.goal_selection import (
    ACTIONABLE_STATUSES,
    NON_ACTIONABLE_NON_TERMINAL,
    drive_fit_for_goal,
    select_goal,
)
from modules.soul.identity_state.identity_state import active_character_id, active_person_id


def _fresh_drives(**overrides):
    """A DrivesModule with baseline values, tweaked per-category as needed,
    so drive-fit selection is deterministically steerable in tests."""
    from modules.soul.mental_state.mental_state import DrivesModule
    d = DrivesModule()
    for k, v in overrides.items():
        setattr(d, k, float(v))
    return d


def _fresh_dict_drives(**overrides):
    d = {
        "stress": 0.0, "anxiety": 0.0, "social_need": 0.5, "recreation": 0.5,
        "purpose": 0.5, "spirituality": 0.5, "aggression": 0.5, "retreat": 0.5,
        "social": 0.0, "rest": 0.0, "explore": 0.0, "focus": 0.0,
    }
    d.update(overrides)
    return d


class GoalSelectionTestCase(unittest.TestCase):
    """Phase: deterministic drive-aware selection among explicit non-terminal
    goals. Covers candidate selection, exclusion, ranking order, determinism,
    and character/person scope. Selection never creates or mutates goals."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_STATE_DIR")
        os.environ["SARAH_STATE_DIR"] = self._tmpdir.name
        _clear_goal_store_cache()
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

    def _store(self, characteristic="sarah"):
        return get_goal_store(characteristic)

    def test_selects_from_two_actionable_goals(self):
        store = self._store()
        # One clearly actionable active goal; one proposed.
        store.create_goal("research the night sky", rationale="explore",
                          next_action="read observatory docs", status="proposed")
        store.create_goal("fix the flaky parser", rationale="focus",
                          next_action="reproduce bug", status="active", priority=5)
        dec = select_goal("sarah", drives=_fresh_dict_drives(explore=0.9, focus=0.9))
        self.assertEqual(dec["candidate_count"], 2)
        self.assertIsNotNone(dec["selected"])
        # Active goal wins outright because active ranks before proposed.
        self.assertEqual(dec["selected"]["title"], "fix the flaky parser")
        self.assertEqual(dec["selected"]["status"], "active")
        # The reason explains WHY that goal won (status + drive-fit).
        self.assertIn("focus", dec["reason"])
        self.assertIn(dec["selected"]["goal_id"], dec["reason"])

    def test_excludes_blocked_and_awaiting_approval_from_actionable(self):
        store = self._store()
        g_blocked = store.create_goal("blocked goal", status="active")
        store.mark_blocked(g_blocked, "waiting on keys")
        store.request_approval(store.create_goal("needs approval", status="active"))
        store.create_goal("fine to work on", status="active", priority=5)
        dec = select_goal("sarah", drives=_fresh_dict_drives())
        # blocked + awaiting_approval are NOT selectable even though non-terminal.
        self.assertEqual(dec["candidate_count"], 1)
        self.assertEqual(dec["selected"]["title"], "fine to work on")
        self.assertNotIn("blocked", dec["selected"]["status"])
        self.assertNotIn("awaiting_approval", dec["selected"]["status"])

    def test_excludes_terminal_completed_and_abandoned(self):
        store = self._store()
        done = store.create_goal("finished thing", status="active")
        store.complete_goal(done, "shipped")
        gone = store.create_goal("abandoned thing", status="active")
        store.abandon_goal(gone, "moot")
        store.create_goal("still going", status="active")
        # Terminal goals aren't even returned by list_active, and selection
        # additionally only ever picks actionable statuses.
        dec = select_goal("sarah", drives=_fresh_dict_drives())
        self.assertEqual(dec["candidate_count"], 1)
        self.assertEqual(dec["selected"]["title"], "still going")
        self.assertNotIn("finished thing", [c["title"] for c in dec["candidates"]])
        self.assertNotIn("abandoned thing", [c["title"] for c in dec["candidates"]])

    def test_no_actionable_goal_returns_none_and_preserves_no_goal_behavior(self):
        store = self._store()
        # Only blocked / awaiting_approval / terminal live goals.
        b = store.create_goal("blocked", status="active")
        store.mark_blocked(b, "pending")
        a = store.create_goal("approval", status="active")
        store.request_approval(a)
        done = store.create_goal("done", status="active")
        store.complete_goal(done, "x")
        dec = select_goal("sarah", drives=_fresh_dict_drives())
        self.assertEqual(dec["candidate_count"], 0)
        self.assertIsNone(dec["selected"])
        self.assertEqual(dec["candidates"], [])
        self.assertIn("actionable", dec["reason"])
        # Empty store also yields None with a reason.
        dec2 = select_goal("tama", drives=_fresh_dict_drives())
        self.assertIsNone(dec2["selected"])
        self.assertEqual(dec2["candidate_count"], 0)

    def test_status_ordering_active_before_proposed_equal_priority(self):
        store = self._store()
        # Two goals, identical priority and identical drive text -> the only
        # discriminating factor must be status (active wins).
        store.create_goal("same neutral task", status="proposed", priority=3)
        store.create_goal("same neutral task", status="active", priority=3)
        dec = select_goal("sarah", drives=_fresh_dict_drives(focus=0.5, explore=0.5,
                                                             social=0.5, rest=0.5))
        self.assertEqual(dec["selected"]["status"], "active")

    def test_priority_desc_ranking(self):
        store = self._store()
        # Both active, identical neutral drive text; higher priority wins.
        store.create_goal("neutral work", status="active", priority=1)
        store.create_goal("neutral work", status="active", priority=5)
        dec = select_goal("sarah", drives=_fresh_dict_drives())
        self.assertEqual(dec["selected"]["priority"], 5)

    def test_drive_fit_steers_within_equal_status_and_priority(self):
        store = self._store()
        # Active, equal priority, distinct drive signals.
        store.create_goal("write the project report", rationale="focus on writing",
                          next_action="draft the document", status="active", priority=3)
        store.create_goal("plan a social gathering", rationale="reach out to friends",
                          next_action="message the group", status="active", priority=3)
        # When the social drive is high and focus is low, the social goal must win.
        low_focus = _fresh_dict_drives(social=0.9, focus=0.0, explore=0.0, rest=0.0)
        dec = select_goal("sarah", drives=low_focus)
        self.assertEqual(dec["selected"]["title"], "plan a social gathering")
        # And flipping the drives to favor focus reverses the decision.
        high_focus = _fresh_dict_drives(social=0.0, focus=0.9, explore=0.0, rest=0.0)
        dec2 = select_goal("sarah", drives=high_focus)
        self.assertEqual(dec2["selected"]["title"], "write the project report")

    def test_recency_tie_breaker_within_equal_rank(self):
        store = self._store()
        # Two active goals, same priority, same drive-neutral text. The only
        # remaining discriminator is recency (most recently updated first).
        g1 = store.create_goal("neutral work", status="active", priority=3)
        g2 = store.create_goal("neutral work", status="active", priority=3)
        # Touch g1 after g2 so g1 is strictly more recent.
        store.update_goal(g1, next_action="touch")
        dec = select_goal("sarah", drives=_fresh_dict_drives())
        self.assertEqual(dec["selected"]["goal_id"], g1)
        # The goal_id tie-break still makes it deterministic when recency ties.
        dec2 = select_goal("sarah", drives=_fresh_dict_drives())
        self.assertEqual(dec2["selected"]["goal_id"], g1)

    def test_selection_is_deterministic_no_random_entropy(self):
        store = self._store()
        for i, (title, prio, status) in enumerate([
            ("social reach out to everyone", 3, "active"),
            ("focus writing a long report", 2, "active"),
            ("explore researching distant stars", 4, "proposed"),
        ]):
            store.create_goal(title, rationale=f"case {i}", status=status, priority=prio)
        drives = _fresh_drives(explore=0.8, focus=0.7, social=0.6, rest=0.4)
        # Repeated selection on the identical inputs must produce the identical
        # decision (ids and order), proving there is no randomized selection.
        first = select_goal("sarah", drives=drives)
        for _ in range(5):
            again = select_goal("sarah", drives=drives)
            self.assertEqual(again["selected"]["goal_id"], first["selected"]["goal_id"])
            self.assertEqual(
                [c["goal_id"] for c in again["candidates"]],
                [c["goal_id"] for c in first["candidates"]],
            )
        # Also deterministic with dict drives (the shape used by callers).
        first_dict = select_goal("sarah", drives=_fresh_dict_drives(
            explore=0.8, focus=0.7, social=0.6, rest=0.4))
        self.assertEqual(first_dict["selected"]["goal_id"], first["selected"]["goal_id"])

    def test_no_cross_character_or_person_scope(self):
        store_sarah = self._store("sarah")
        store_tama = self._store("tama")
        store_sarah.create_goal("sarah's secret focus task", status="active", priority=5)
        store_tama.create_goal("tama's separate focus task", status="active", priority=5)
        # Selection from Tama's store never sees Sarah's goals.
        dec_tama = select_goal("tama", drives=_fresh_dict_drives(focus=0.9))
        self.assertEqual(dec_tama["candidate_count"], 1)
        self.assertEqual(dec_tama["selected"]["title"], "tama's separate focus task")
        # Selection from Sarah's store never sees Tama's goals.
        dec_sarah = select_goal("sarah", drives=_fresh_dict_drives(focus=0.9))
        self.assertEqual(dec_sarah["candidate_count"], 1)
        self.assertEqual(dec_sarah["selected"]["title"], "sarah's secret focus task")
        # Person scoping: a goal for a specific person is selected only when
        # that person's context is active.
        store_sarah.create_goal("caller-specific task", status="active", person_id="discord:44", priority=5)
        scoped = select_goal("sarah", drives=_fresh_dict_drives(focus=0.9), person_id="discord:44")
        self.assertEqual(scoped["candidate_count"], 1)
        self.assertEqual(scoped["selected"]["title"], "caller-specific task")
        # Another person's scope never sees that goal (nor the general ones).
        scoped_other = select_goal("sarah", drives=_fresh_dict_drives(focus=0.9), person_id="discord:99")
        self.assertEqual(scoped_other["candidate_count"], 0)

    def test_drive_never_creates_a_goal(self):
        store = self._store()
        before = store.count()
        # A strong drive with zero goals must yield no selection AND add nothing.
        dec = select_goal("sarah", drives=_fresh_dict_drives(explore=0.99, focus=0.99))
        self.assertIsNone(dec["selected"])
        self.assertEqual(dec["candidate_count"], 0)
        self.assertEqual(store.count(), before)
        self.assertEqual(get_goal_store("tama").count(), 0)

    def test_drive_fit_score_is_transparent(self):
        goal = {
            "title": "investigate the anomaly and report findings",
            "rationale": "explore the data", "next_action": "read the docs",
            "priority": 3,
        }
        drives = _fresh_dict_drives(explore=0.5, focus=0.5, social=0.5, rest=0.5)
        fit = drive_fit_for_goal(goal, drives)
        # It has a bounded score and a full per-category breakdown.
        self.assertGreaterEqual(fit["fit"], 0.0)
        self.assertLessEqual(fit["fit"], 1.0)
        self.assertGreater(fit["total_keyword_hits"], 0)
        for cat in ("explore", "social", "rest", "focus"):
            self.assertIn(cat, fit["categories"])
        # Keyword-free text yields a zero fit (transparent, no blind preference).
        no_text = drive_fit_for_goal(
            {"title": "", "rationale": "", "next_action": ""}, drives)
        self.assertEqual(no_text["fit"], 0.0)
        self.assertEqual(no_text["total_keyword_hits"], 0)

    def test_reason_present_and_readable(self):
        store = self._store()
        store.create_goal("research the sky", status="active", priority=3)
        dec = select_goal("sarah", drives=_fresh_dict_drives(explore=0.8))
        self.assertIn("selected", dec["reason"].lower())
        self.assertIn("research the sky", dec["reason"])
        self.assertIn(dec["selected"]["goal_id"], dec["reason"])


if __name__ == "__main__":
    unittest.main()
