"""
Typed, person-scoped relationship profile tools.

These read/write a *specific person's* structured profile (stable person IDs)
for whichever character is currently reasoning, resolved via
active_character_id - see modules/soul/person_profiles/. Each fact written
carries source + confidence + timestamp provenance so it is auditable.

Design note on add_relationship_note (the existing /modules/memory/identity_tools.py
tool): it appends free-text notes to the character's OWN identity_state under
no person and is unaffected. The person-scoped tools here are the structured,
per-person replacement. We deliberately do NOT try to auto-migrate old
identity-level notes into some guessed "default person" - there is no sound
default person to route them to, so they are preserved as-is.

These writing tools are NOT added to Discord's allowlist: writing relationship
profiles about real people from an externally-reachable, untrusted-input
surface needs an authorization design first (see discord/main.py
DISCORD_ALLOWED_TOOLS). The write tools stay in the trusted local registry only
until that design exists.
"""

from modules.soul.person_profiles import _active_store


def upsert_person_profile(person_id: str, display_name: str = "", source: str = "unknown",
                          confidence: float = 0.5):
    """Create or update the profile for a specific person (stable person_id).
    Recorded under the current character only. Args: person_id (str, stable),
    display_name (str, optional), source (str, optional attribution),
    confidence (float, optional 0.0-1.0)."""
    store = _active_store()
    profile = store.upsert_profile(
        person_id, display_name=display_name or None, source=source, confidence=confidence
    )
    name = profile.get("display_name") or person_id
    return f"Profile for '{name}' (id: {person_id}) recorded."


def get_person_profile(person_id: str):
    """Return the structured profile for a person (display name, notes,
    preferences, consent boundaries, provenance). Args: person_id (str, stable)."""
    store = _active_store()
    profile = store.get_profile(person_id)
    if profile is None:
        return f"No profile yet for person id '{person_id}'."
    return store.summary(person_id)


def list_person_profiles():
    """List known people (stable ids + display names) for the current character."""
    store = _active_store()
    people = store.list_profiles()
    if not people:
        return "No person profiles recorded yet."
    return "\n".join(f"- {p['display_name'] or p['person_id']} (id: {p['person_id']})" for p in people)


def set_person_preference(person_id: str, pref_key: str, value: str,
                          source: str = "unknown", confidence: float = 0.5):
    """Record/update a specific person's preference (keyed, auditable).
    Args: person_id (str), pref_key (str), value (str), source (str, optional),
    confidence (float, optional)."""
    _active_store().set_preference(person_id, pref_key, value, source=source, confidence=confidence)
    return f"Recorded preference '{pref_key}' for person '{person_id}'."


def set_person_consent_boundary(person_id: str, boundary_key: str, value: str,
                                source: str = "unknown", confidence: float = 0.5):
    """Record/update a specific person's consent boundary. Args: person_id (str),
    boundary_key (str), value (str), source (str, optional), confidence (float, optional)."""
    _active_store().set_consent_boundary(
        person_id, boundary_key, value, source=source, confidence=confidence
    )
    return f"Recorded consent boundary '{boundary_key}' for person '{person_id}'."


def add_person_relationship_note(person_id: str, note: str,
                                 source: str = "unknown", confidence: float = 0.5):
    """Add a sourced relationship note to a specific person's profile.
    Args: person_id (str, stable), note (str), source (str, optional),
    confidence (float, optional)."""
    _active_store().add_relationship_note(person_id, note, source=source, confidence=confidence)
    return f"Relationship note added to person '{person_id}'."
