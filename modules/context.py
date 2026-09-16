"""
Reusable context assembly for a character.

One path that folds the pieces a reasoning loop needs into a single string:
identity, the actual mental/drive state, current goal/task, and whatever
perception is available (screen, hive, body). The autonomous loop and the
Discord bot both call this instead of each building their own ad-hoc prompt.

It deliberately replaces the legacy RPG health/mana/stamina readout with the
character's real digital state (needs/drives/mood).
"""

from modules.memory.identity_tools import get_identity_summary
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
    get_identity_state,
)


def _active_goals_context(person_id=None, character_id=None) -> str:
    """Bounded [ACTIVE GOALS] section, rendered from the explicit goal store.

    The explicit, versioned per-character goal store
    (modules/soul/goals/, goals.json) is the character's source of truth for
    goals this phase. Only when that store has no live (non-terminal) goals do
    we fall back to the legacy identity_state goals so nothing already recorded
    through the old add_goal/complete_goal tools is lost. Goal ids are shown as
    stable reference handles so the reasoning loop can address goals in
    follow-up tool calls (mark blocked / complete / abandon); person and
    linked-entity ids are omitted (see render_goals).
    """
    cid = character_id or active_character_id.get()
    try:
        from modules.soul.goals.goals import active_goals_summary

        section = active_goals_summary(cid, person_id=person_id)
        if section:
            return section
    except Exception:  # noqa: BLE001 - goal recall must never break context
        section = ""
    # Legacy fallback: only surfaced when the explicit store has nothing live.
    if not section:
        try:
            identity = get_identity_state(cid)
            legacy = [g["goal"] for g in identity.goals if g.get("status") == "active"]
            if legacy:
                return "- " + "\n- ".join(legacy)
        except Exception:  # noqa: BLE001
            return ""
    return section


def _goals_summary(agent) -> str:
    """Current goal/task: the agent's in-progress task plus any stored active
    goals from identity, so the model knows what the character is working
    toward right now."""
    current_task = getattr(agent, "currentTask", "") or "Idle"
    identity = getattr(getattr(agent, "soul", None), "identity", None)
    if identity is None:
        return current_task
    active_goals = [g["goal"] for g in identity.goals if g.get("status") == "active"]
    if not active_goals:
        return current_task
    return f"{current_task} (active goals: {', '.join(active_goals)})"


def _memory_reminder_summary(goal: str) -> str:
    """Summarize relevant episodic memories for the current caller + goal.

    Bounded by RELEVANT_MEMORY_LIMIT and scoped to the current character (via
    active_character_id) and the current caller (via active_person_id). The
    current goal string is used as lightweight query context so recent,
    goal-relevant episodes surface. Raw person ids are omitted by the renderer.
    Returns "" (so the caller omits the section) when nothing matches.
    """
    try:
        from modules.memory.episodic_memory import (
            RELEVANT_MEMORY_LIMIT,
            get_episodic_store,
        )

        cid = active_character_id.get()
        person_id = active_person_id.get()
        # Query terms drawn from the goal/task so goal-related memories surface
        # first; falls back to the plain salience-ranked recent set.
        terms = goal or None
        memories = get_episodic_store(cid).summary(
            person_id=person_id, query=terms, limit=RELEVANT_MEMORY_LIMIT,
        )
        if memories:
            return memories
        # No goal-matching memories: fall back to the most relevant recent ones.
        return get_episodic_store(cid).summary(
            person_id=person_id, limit=RELEVANT_MEMORY_LIMIT
        )
    except Exception:  # noqa: BLE001 - memory recall must never break context
        return ""


def _semantic_fact_summary(goal: str) -> str:
    """Summarize relevant semantic facts for the current caller + goal.

    Bounded by RELEVANT_FACT_LIMIT and scoped to the current character (via
    active_character_id) and the current caller (via active_person_id). The
    current goal string is used as lightweight query context so goal-relevant
    facts surface. Raw person ids are omitted by the renderer. Returns ""
    (so the caller omits the section) when nothing matches.
    """
    try:
        from modules.memory.semantic_memory import (
            RELEVANT_FACT_LIMIT,
            get_semantic_store,
        )

        cid = active_character_id.get()
        person_id = active_person_id.get()
        terms = goal or None
        facts = get_semantic_store(cid).summary(
            person_id=person_id, query=terms, limit=RELEVANT_FACT_LIMIT,
        )
        if facts:
            return facts
        return get_semantic_store(cid).summary(
            person_id=person_id, limit=RELEVANT_FACT_LIMIT
        )
    except Exception:  # noqa: BLE001 - fact recall must never break context
        return ""


def assemble_character_context(agent=None, *, goal: str = None, screen_text: str = None,
                               hive_summary: str = None, body_state: str = None) -> str:
    """Assemble the character's full context into a single string.

    `agent` is the live BaseCharacter whose soul/state we read. When agent is
    None the call resolves identity via the current active_character_id
    contextvar (so a caller with no live agent - e.g. the Discord bot - still
    gets the right character's identity/mental state).

    Sections:
      [AGENT]        identity summary + current goal/task
      [MENTAL STATE] needs/drives/personality (the real digital state)
      [PERCEPTION]   screen + hive + body, as provided
    """
    if getattr(agent, "soul", None) is not None:
        identity_summary = agent.soul.identity.summary()
        mental_state_summary = agent.soul.mental_state.get_summary()
        if goal is None:
            goal = _goals_summary(agent)
    else:
        identity_summary = get_identity_summary()
        mental_state_summary = "(no soul loaded - mental state unavailable)"
        if goal is None:
            goal = "Idle"

    lines = [f"[AGENT]\n{identity_summary}\nCurrent goal/task: {goal}"]

    # Bounded, explicit goal lifecycle summary sourced from the versioned goal
    # store (goals.json), with legacy identity goals as a fallback when the
    # store has nothing live. This is the character's authoritative goal view
    # and replaces the ad-hoc "active goals" line buried in the identity
    # summary for models that need to act on / transition goals. Person scope
    # follows the active caller (active_person_id). Raw goal ids are shown (so
    # the loop can reference them in tools), but person/linked-entity ids are
    # omitted. The section is omitted when there is nothing live.
    active_goals = _active_goals_context(person_id=active_person_id.get())
    if active_goals:
        lines.append(f"\n[ACTIVE GOALS] (explicit goal lifecycle, bounded)\n{active_goals}")

    lines.append(f"\n[MENTAL STATE] (needs/drives/personality; 0.0-1.0 unless noted)\n{mental_state_summary}")

    # Only bind the active *caller's* person profile when the trusted boundary
    # has set active_person_id. The LLM never chooses this id - it's provided
    # by the application (Discord -> "discord:{author.id}", CLI/voice ->
    # "local:operator"). With no caller context the value is None and no
    # person profile section is emitted, preserving existing behavior.
    person_id = active_person_id.get()
    if person_id:
        from modules.soul.person_profiles import _active_store
        summary = _active_store().summary(person_id)
        if summary:
            lines.append(f"\n[ACTIVE PERSON] (the caller's known profile)\n{summary}")

    # Relevant episodic memories: bounded, derived from the current caller
    # (active_person_id / active_character_id) and the current goal/task. Raw
    # stable person ids are omitted by the renderer. When nothing matches, the
    # section is omitted so we don't pad context with an empty block. Capture
    # stays explicit - memory appears here only from deliberate record_episode
    # calls, never from auto-capturing every message.
    memories = _memory_reminder_summary(goal)
    if memories:
        lines.append(f"\n[RELEVANT MEMORIES] (recalled by the model, bounded)\n{memories}")

    # Relevant semantic facts: durable facts consolidated from episodes, scoped
    # to the current character (active_character_id) and caller
    # (active_person_id), rendered without raw person ids. Facts are surfaced
    # only when present, so the section is omitted when nothing is stored.
    # Nothing here triggers an LLM call or auto-consolidates episodes - facts
    # appear only from explicit consolidate_episode / add_semantic_fact calls.
    semantic_summary = _semantic_fact_summary(goal)
    if semantic_summary:
        lines.append(f"\n[RELEVANT FACTS] (consolidated semantic facts, bounded)\n{semantic_summary}")

    perception = []
    if screen_text:
        perception.append(f"[SCREEN] (local vision model's description of what's currently visible)\n{screen_text}")
    if hive_summary:
        perception.append(f"[HIVE] (other Sarah nodes on the network)\n{hive_summary}")
    if body_state:
        perception.append(f"[BODY] (robotics telemetry)\n{body_state}")
    if perception:
        lines.append("\n[PERCEPTION]\n" + "\n\n".join(perception))

    return "\n".join(lines)


def assemble_autonomous_context(agent, screen_text: str = None, hive_summary: str = None,
                                body_state: str = None) -> str:
    """Context for the autonomous observe-and-suggest loop: the character's
    identity, mental state, current goal, and available perception. This is
    what the state machine folds into the system context for its request."""
    active_character_id.set(getattr(agent, "character_id", "sarah"))
    return assemble_character_context(
        agent, screen_text=screen_text, hive_summary=hive_summary, body_state=body_state
    )
