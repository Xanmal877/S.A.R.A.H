"""
Tool-level wrappers for episodic memory.

These are the *trusted-local* registry tools (registered in init_tools.py and
therefore available to the desktop daemon / CLI / voice). They deliberately are
NOT added to Discord's allowlist (discord/main.py DISCORD_ALLOWED_TOOLS): capture
must remain explicit and controlled this phase, and an externally-reachable,
untrusted-input surface is not the right place to start writing episodes by
default.

Semantics stay safe:
  * record_episode is an explicit append by the model - not an automatic dump,
    so the model chooses what is worth remembering.
  * retrieve_episodes is read-only.
Person scope (when the active caller has a person bound) is enforced inside the
store: a caller never retrieves another person's private episodes.
"""

import json

from modules.memory.episodic_memory import (
    RELEVANT_MEMORY_LIMIT,
    _active_store,
    render_episodes,
)
from modules.soul.identity_state.identity_state import active_person_id


def record_episode(kind: str, content: str, source: str = "local",
                   confidence: float = 0.5, salience: float = 0.5,
                   goal_id: str = None, person_id: str = None,
                   metadata: str = None):
    """Explicitly record a durable episodic memory for the current character.
    Capture is deliberate - the model records only what is worth remembering.

    Args: kind (str, e.g. 'conversation'/'task'/'observation'), content (str,
    what happened), source (str, optional provenance), confidence (float 0-1),
    salience (float 0-1, how important), goal_id (str, optional), person_id
    (str, optional; defaults to the current caller)."""
    store = _active_store()
    meta = None
    if metadata:
        try:
            meta = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            meta = {"raw": metadata}
    active_person = active_person_id.get()
    # A caller-bound request must never let model-provided arguments redirect
    # an episode into somebody else's record. With no caller context (for
    # example an autonomous system observation), the trusted local runtime may
    # explicitly attach a person id.
    if active_person is not None and person_id not in (None, active_person):
        return "Refused: the current caller identity cannot be overridden."
    person = active_person if active_person is not None else person_id
    row_id = store.record(
        kind, content, source=source, person_id=person,
        confidence=confidence, salience=salience, goal_id=goal_id, metadata=meta,
    )
    if row_id is None:
        return "Failed to record episode (storage error)."
    return f"Recorded episode #{row_id}."


def retrieve_episodes(query: str = "", kinds: str = None, limit: int = RELEVANT_MEMORY_LIMIT,
                      rank: str = "salience", person_id: str = None):
    """Retrieve relevant episodic memories for the current character. Read-only,
    bounded, and never crosses character/person boundaries.

    Args: query (str, optional keyword filter), kinds (str, optional comma
    separated, e.g. 'conversation,task'), limit (int, default 6), rank
    ('salience' or 'recency'), person_id (str, optional override; defaults to
    the current caller)."""
    store = _active_store()
    kind_list = None
    if kinds:
        kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
    active_person = active_person_id.get()
    # Same boundary as recording: when an application has bound a caller, the
    # model cannot use a tool argument to read a different person's episodes.
    if active_person is not None and person_id not in (None, active_person):
        return "Refused: the current caller identity cannot be overridden."
    person = active_person if active_person is not None else person_id
    episodes = store.retrieve(
        query=query or None, person_id=person, kinds=kind_list,
        limit=limit, rank=rank,
    )
    if not episodes:
        return "No matching memories found."
    return render_episodes(store.character_id, episodes)


def get_memory_summary():
    """Return the character's current most-relevant episodic memory summary
    (used to surface context without raw person ids)."""
    return _active_store().summary(person_id=active_person_id.get())
