from modules.soul.identity_state.identity_state import (
    active_character_id,
    get_identity_state,
)


def _identity():
    """Resolves the IdentityState for whichever character's tool-call loop is
    currently running (see active_character_id in identity_state.py), instead
    of always operating on Sarah's regardless of who's actually speaking."""
    return get_identity_state(active_character_id.get())


def form_opinion(topic: str, opinion: str, reasoning: str = ""):
    """Records the character's opinion on a topic, persisted independent of the LLM - use
    this instead of just saying an opinion, so it's still theirs next time it comes up.
    Args: topic (str), opinion (str), reasoning (str, optional)."""
    _identity().form_opinion(topic, opinion, reasoning)
    return f"Recorded opinion on '{topic}'."


def get_opinion(topic: str):
    """Retrieves the character's previously formed opinion on a topic, if any. Args: topic (str)."""
    o = _identity().get_opinion(topic)
    return o["opinion"] if o else f"No opinion formed yet on '{topic}'."


def add_interest(interest: str):
    """Adds something to the character's persistent interests. Args: interest (str)."""
    _identity().add_interest(interest)
    return f"Added '{interest}' to interests."


def add_dislike(dislike: str):
    """Adds something to the character's persistent dislikes. Args: dislike (str)."""
    _identity().add_dislike(dislike)
    return f"Added '{dislike}' to dislikes."


def add_relationship_note(note: str):
    """Records a note about the relationship with the operator - an inside joke, a
    preference they mentioned, an ongoing thread worth remembering. Args: note (str)."""
    _identity().add_relationship_note(note)
    return "Relationship note recorded."


def add_goal(goal: str):
    """Adds a persistent goal the character is working toward. Args: goal (str)."""
    _identity().add_goal(goal)
    return f"Added goal: {goal}"


def complete_goal(goal: str):
    """Marks an active goal as done. Args: goal (str, must match an existing active goal)."""
    ok = _identity().complete_goal(goal)
    return f"Marked goal complete: {goal}" if ok else f"No active goal matching '{goal}' found."


def get_identity_summary():
    """Returns the character's current interests, dislikes, recent opinions, active goals, and
    relationship notes - the same summary that's already included in their world state."""
    return _identity().summary()
