"""
Tool-level wrappers for semantic memory.

These are the *trusted-local* registry tools (registered in init_tools.py and
therefore available to the desktop daemon / CLI / voice). They deliberately are
NOT added to Discord's allowlist (discord/main.py DISCORD_ALLOWED_TOOLS):
consolidation writes durable facts, and an externally-reachable, untrusted-input
surface is not the right place to start writing facts by default.

Semantics stay safe:
  * consolidate_episode is an explicit, provenance-preserving operation - the
    model chooses what to consolidate; nothing auto-consolidates and no LLM is
    called. It verifies the source episode belongs to the active character and,
    when a caller is bound, will not link to/read another person's episode nor
    write another person's fact.
  * retrieve_facts is read-only and bounded; raw person ids are omitted from
    model-visible summaries.
Person scope (when the active caller has a person bound) is enforced inside the
store: a caller never sees another person's private facts.
"""

import json

from modules.memory.episodic_memory import _active_store as _active_episode_store
from modules.memory.semantic_memory import (
    RELEVANT_FACT_LIMIT,
    _active_store,
    render_facts,
)
from modules.soul.identity_state.identity_state import active_person_id


def _resolve_bound_person() -> str:
    """Return the currently-bound caller person id, or None when unbound."""
    return active_person_id.get()


def _check_episode_access(store, episode_id, bound_person) -> tuple:
    """Verify we may read/consolidate an episode for the given caller context.

    Returns (episode, error) where episode is None on refusal. The episode must
    belong to this store's character (guaranteed by get_by_id). When a caller is
    bound, the episode's person_id must equal the caller or be NULL (a
    character-general episode) so we never read/link another person's episode.
    """
    episode = store.get_by_id(episode_id)
    if episode is None:
        return None, f"No episode #{episode_id} found for the active character {store.character_id}."
    if bound_person is not None and episode.get("person_id") not in (None, bound_person):
        return None, "Refused: cannot consolidate another person's episode."
    return episode, None


def consolidate_episode(episode_id: int, topic: str, value: str, *,
                        confidence: float = 0.5, salience: float = 0.5,
                        source_note: str = None, metadata: str = None):
    """Explicitly consolidate a durable semantic fact from a source episode.

    Provenance is recorded (the source episode id) and the resulting fact takes
    the person scope of the source episode. New facts with the same scope+topic
    supersede earlier active revisions rather than deleting history.

    Guards:
      * the source episode must belong to the active character;
      * when the current caller is bound, consolidation cannot read/link another
        person's episode, and the fact is written under that caller's scope.

    Args: episode_id (int, the episode to consolidate from), topic (str, the
    fact's key/subject), value (str, the asserted value), confidence (float
    0-1), salience (float 0-1), source_note (str, optional free-text
    provenance), metadata (str, optional JSON)."""
    store = _active_store()
    episode_store = _active_episode_store()
    bound_person = _resolve_bound_person()

    episode, error = _check_episode_access(episode_store, episode_id, bound_person)
    if error:
        return error

    meta = None
    if metadata:
        try:
            meta = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            meta = {"raw": metadata}

    # Person scope of the fact derives from the source episode. When a caller is
    # bound we have already verified the episode is that caller's (or general),
    # so this can never attach another person's identity to the fact.
    fact_person = episode.get("person_id")
    if bound_person is not None:
        # Bound caller: scope the fact to the caller (normalizing a general
        # episode into the caller's scope so we never write a general fact on a
        # bound session's behalf without an explicit episode carrying it).
        fact_person = bound_person

    fact_id = store.add_fact(
        topic, value, person_id=fact_person,
        source_episode_id=episode_id, source_note=source_note,
        confidence=confidence, salience=salience, metadata=meta,
    )
    if fact_id is None:
        return "Failed to consolidate fact (storage error)."
    return f"Consolidated fact #{fact_id} from episode #{episode_id}."


def add_semantic_fact(topic: str, value: str, *, person_id: str = None,
                      source_episode_id=None, source_note: str = None,
                      confidence: float = 0.5, salience: float = 0.5,
                      metadata: str = None):
    """Explicitly append a semantic fact for the current character (optionally
    sourced from an episode). If sourced from an episode, the episode must belong
    to the active character. When a caller is bound, a caller cannot write
    another person's fact.

    Args: topic (str), value (str), person_id (str, optional), source_episode_id
    (int, optional), source_note (str, optional), confidence (float 0-1),
    salience (float 0-1), metadata (str, optional JSON)."""
    store = _active_store()
    episode_store = _active_episode_store()
    bound_person = _resolve_bound_person()

    if source_episode_id is not None:
        episode, error = _check_episode_access(episode_store, source_episode_id, bound_person)
        if error:
            return error
        if bound_person is not None and person_id not in (None, bound_person):
            return "Refused: the current caller cannot write another person's fact."

    meta = None
    if metadata:
        try:
            meta = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            meta = {"raw": metadata}

    # Bound caller: never let model-provided args redirect a fact into another
    # person's record.
    if bound_person is not None and person_id not in (None, bound_person):
        return "Refused: the current caller identity cannot be overridden."
    fact_person = bound_person if bound_person is not None else person_id

    fact_id = store.add_fact(
        topic, value, person_id=fact_person,
        source_episode_id=source_episode_id, source_note=source_note,
        confidence=confidence, salience=salience, metadata=meta,
    )
    if fact_id is None:
        return "Failed to add fact (storage error)."
    return f"Added fact #{fact_id}."


def retrieve_facts(topic: str = None, query: str = "", limit: int = RELEVANT_FACT_LIMIT,
                   person_id: str = None):
    """Retrieve relevant active semantic facts for the current character.
    Read-only, bounded, and never crosses character/person boundaries. Raw
    person ids are omitted from the returned summary.

    Args: topic (str, optional exact topic), query (str, optional keyword
    filter), limit (int, default 6), person_id (str, optional override; defaults
    to the current caller)."""
    store = _active_store()
    bound_person = _resolve_bound_person()
    # Same boundary as writes: when an application has bound a caller, the model
    # cannot use a tool argument to read a different person's facts.
    if bound_person is not None and person_id not in (None, bound_person):
        return "Refused: the current caller identity cannot be overridden."
    person = bound_person if bound_person is not None else person_id
    facts = store.retrieve(
        person_id=person, topic=topic or None, query=query or None,
        active_only=True, limit=limit,
    )
    if not facts:
        return "No matching facts found."
    return render_facts(store.character_id, facts)


def get_semantic_fact_summary():
    """Return the character's current most-relevant semantic fact summary
    (used to surface context without raw person ids)."""
    return _active_store().summary(person_id=_resolve_bound_person())
