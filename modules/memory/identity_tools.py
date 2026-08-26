from modules.soul.identity_state import identity_state


def form_opinion(topic: str, opinion: str, reasoning: str = ""):
    """Records Sarah's opinion on a topic, persisted independent of the LLM - use this
    instead of just saying an opinion, so it's still hers next time it comes up.
    Args: topic (str), opinion (str), reasoning (str, optional)."""
    identity_state.form_opinion(topic, opinion, reasoning)
    return f"Recorded opinion on '{topic}'."


def get_opinion(topic: str):
    """Retrieves Sarah's previously formed opinion on a topic, if any. Args: topic (str)."""
    o = identity_state.get_opinion(topic)
    return o["opinion"] if o else f"No opinion formed yet on '{topic}'."


def add_interest(interest: str):
    """Adds something to Sarah's persistent interests. Args: interest (str)."""
    identity_state.add_interest(interest)
    return f"Added '{interest}' to interests."


def add_dislike(dislike: str):
    """Adds something to Sarah's persistent dislikes. Args: dislike (str)."""
    identity_state.add_dislike(dislike)
    return f"Added '{dislike}' to dislikes."


def add_relationship_note(note: str):
    """Records a note about the relationship with the operator - an inside joke, a
    preference they mentioned, an ongoing thread worth remembering. Args: note (str)."""
    identity_state.add_relationship_note(note)
    return "Relationship note recorded."


def add_goal(goal: str):
    """Adds a persistent goal Sarah is working toward. Args: goal (str)."""
    identity_state.add_goal(goal)
    return f"Added goal: {goal}"


def complete_goal(goal: str):
    """Marks an active goal as done. Args: goal (str, must match an existing active goal)."""
    ok = identity_state.complete_goal(goal)
    return f"Marked goal complete: {goal}" if ok else f"No active goal matching '{goal}' found."


def get_identity_summary():
    """Returns Sarah's current interests, dislikes, recent opinions, active goals, and
    relationship notes - the same summary that's already included in her world state."""
    return identity_state.summary()
