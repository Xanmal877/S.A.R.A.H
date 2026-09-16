"""
Versioned per-character person profiles.

A character (Sarah, Tama, Saki, ...) keeps structured relationship profiles
for the people they know, keyed by *stable person IDs* (not display names,
which change and aren't unique). Each profile is written by one character and
isolated from every other character under
~/.sarah/state/{character_id}/person_profiles.json.

This is a sibling to identity_state (which holds facts about the character
themselves): person profiles hold facts about *specific people* from that
character's perspective - display name, relationship notes, preferences,
consent boundaries, and the provenance (source, confidence, recorded-at) of
each fact so beliefs are auditable rather than a flat text blob.

The store is deliberately simple and versioned:
  { "version": 1, "people": { "<stable_person_id>": {profile...} } }
So a later phase can migrate the shape without misreading old files. Unknown
versions fail closed (loaded as empty) rather than guessing at a structure the
code doesn't understand.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from modules.memory.json_file_store import state_dir

logger = logging.getLogger("PersonProfileStore")

# Schema version for a person profile file. Bump and add a migration path
# (don't silently rewrite) if the on-disk shape ever changes.
PERSON_PROFILES_VERSION = 1

# Fact provenance keys every belief: where it came from, how confident we
# are, and when it was recorded, so a future fact can be reconsidered on
# better evidence instead of being indistinguishable from a guess.
FACT_SOURCE_KEYS = ("source",)


class PersonProfileStore:
    """Persistent, versioned person profiles for a single character.

    Layout:
      { "version": 1,
        "people": {
          "<person_id>": {
            "person_id": "<person_id>",
            "display_name": str,
            "relationship_notes": [{"note": str, "source": str, "confidence": float, "recorded_at": str}],
            "preferences": {"<pref_key>": {"value": str, "source": str, "confidence": float, "recorded_at": str}},
            "consent_boundaries": {"<boundary_key>": {"value": str, "source": str, "confidence": float, "recorded_at": str}},
            "provenance": ["<source_ref>"],
          }
        }
      }
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "person_profiles.json"
        )
        self.storage_path = os.path.expanduser(self.storage_path)
        self._people: dict = {}
        self._version = PERSON_PROFILES_VERSION
        self._load()

    # ── persistence ───────────────────────────────────────────────────
    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "Could not load person profiles from %s: %s", self.storage_path, e
            )
            return
        version = saved.get("version")
        if version != PERSON_PROFILES_VERSION:
            # Unknown/newer schema: fail closed rather than guess. A later
            # version's shape we haven't written yet might not round-trip
            # through this old store, so don't blindly load it.
            logger.warning(
                "Person profiles at %s have unsupported version %r (expected %d); "
                "loading as empty. A migration would be needed - not guessed.",
                self.storage_path, version, PERSON_PROFILES_VERSION,
            )
            return
        self._people = saved.get("people", {})
        self._version = version

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Could not save person profiles to %s: %s", self.storage_path, e)

    # ── person lifecycle ─────────────────────────────────────────────
    def upsert_profile(
        self,
        person_id: str,
        display_name: str = None,
        source: str = "unknown",
        confidence: float = 0.5,
    ) -> dict:
        """Create a person profile if new, or update the display name on an
        existing one. Identity is by stable person_id (never display_name).

        Facts are attributed with the given source/confidence so updates are
        auditable rather than silently overwriting with no record of where
        the new value came from.
        """
        person_id = person_id.strip()
        if not person_id:
            raise ValueError("person_id must be a non-empty string")
        profile = self._people.get(person_id)
        is_new = profile is None
        if is_new:
            profile = {
                "person_id": person_id,
                "display_name": "",
                "relationship_notes": [],
                "preferences": {},
                "consent_boundaries": {},
                "provenance": [],
            }
            self._people[person_id] = profile
        recorded_at = datetime.now().isoformat()
        if display_name is not None and display_name.strip():
            profile["display_name"] = display_name.strip()
        self._provenance(profile, source, confidence, recorded_at)
        self._save()
        return profile

    def get_profile(self, person_id: str) -> Optional[dict]:
        """Return the profile dict for a person id, or None."""
        return dict(self._people.get(person_id, {})) if person_id in self._people else None

    def list_profiles(self) -> list:
        """Return metadata (id + display name) for every known person."""
        return [
            {"person_id": p["person_id"], "display_name": p.get("display_name", "")}
            for p in self._people.values()
        ]

    # ── relationship notes ──────────────────────────────────────────
    def add_relationship_note(
        self,
        person_id: str,
        note: str,
        source: str = "unknown",
        confidence: float = 0.5,
    ) -> dict:
        """Add a sourced, timestamped relationship note to a person's profile.
        Returns the note record so callers can inspect provenance."""
        profile = self._ensure_profile(person_id)
        record = {
            "note": note,
            "source": source,
            "confidence": self._clamp_confidence(confidence),
            "recorded_at": datetime.now().isoformat(),
        }
        profile["relationship_notes"].append(record)
        self._provenance(profile, source, confidence, record["recorded_at"])
        self._save()
        return dict(record)

    # ── preferences / consent boundaries ─────────────────────────────
    def set_preference(
        self,
        person_id: str,
        pref_key: str,
        value: str,
        source: str = "unknown",
        confidence: float = 0.5,
    ) -> dict:
        """Record or update a person's preference. Keyed, so each preference
        is a discrete auditable fact rather than a blob of text."""
        profile = self._ensure_profile(person_id)
        record = {
            "value": value,
            "source": source,
            "confidence": self._clamp_confidence(confidence),
            "recorded_at": datetime.now().isoformat(),
        }
        profile["preferences"][pref_key] = record
        self._provenance(profile, source, confidence, record["recorded_at"])
        self._save()
        return dict(record)

    def set_consent_boundary(
        self,
        person_id: str,
        boundary_key: str,
        value: str,
        source: str = "unknown",
        confidence: float = 0.5,
    ) -> dict:
        """Record or update a person's consent boundary (e.g. what they've
        agreed to / declined). Boundary value is a discrete auditable fact."""
        profile = self._ensure_profile(person_id)
        record = {
            "value": value,
            "source": source,
            "confidence": self._clamp_confidence(confidence),
            "recorded_at": datetime.now().isoformat(),
        }
        profile["consent_boundaries"][boundary_key] = record
        self._provenance(profile, source, confidence, record["recorded_at"])
        self._save()
        return dict(record)

    def get_preference(self, person_id: str, pref_key: str):
        profile = self._people.get(person_id, {})
        return dict(profile.get("preferences", {}).get(pref_key, {}))

    def get_consent_boundary(self, person_id: str, boundary_key: str):
        profile = self._people.get(person_id, {})
        return dict(profile.get("consent_boundaries", {}).get(boundary_key, {}))

    # ── helpers ───────────────────────────────────────────────────────
    def _ensure_profile(self, person_id: str) -> dict:
        if person_id in self._people:
            return self._people[person_id]
        # Auto-vivify with a blank profile; name can be filled in later via
        # upsert_profile. Identity is the stable id, not a name.
        profile = {
            "person_id": person_id,
            "display_name": "",
            "relationship_notes": [],
            "preferences": {},
            "consent_boundaries": {},
            "provenance": [],
        }
        self._people[person_id] = profile
        return profile

    @staticmethod
    def _clamp_confidence(confidence: float) -> float:
        try:
            c = float(confidence)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, c))

    @staticmethod
    def _provenance(profile: dict, source: str, confidence: float, recorded_at: str):
        """Append an audited fact line about who asserted what, when."""
        profile["provenance"].append(
            {
                "source": source,
                "confidence": PersonProfileStore._clamp_confidence(confidence),
                "recorded_at": recorded_at,
            }
        )

    def to_dict(self) -> dict:
        return {"version": self._version, "people": self._people}

    def summary(self, person_id: str) -> str:
        """A compact, human/LLM-readable summary of one person's profile."""
        profile = self._people.get(person_id)
        if profile is None:
            return ""
        name = profile.get("display_name") or person_id
        lines = [f"Profile for {name} (id: {person_id})"]
        notes = profile.get("relationship_notes", [])
        if notes:
            most_recent = notes[-1]
            lines.append(
                f"Recent relationship note: {most_recent['note']} "
                f"(confidence {most_recent['confidence']}, from {most_recent['source']})"
            )
        prefs = profile.get("preferences", {})
        if prefs:
            lines.append("Preferences: " + "; ".join(
                f"{k} = {v['value']}" for k, v in prefs.items()
            ))
        boundaries = profile.get("consent_boundaries", {})
        if boundaries:
            lines.append("Consent boundaries: " + "; ".join(
                f"{k} = {v['value']}" for k, v in boundaries.items()
            ))
        return "\n".join(lines)
