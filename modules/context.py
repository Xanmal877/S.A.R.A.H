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
from modules.soul.identity_state.identity_state import active_character_id


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

    lines.append(f"\n[MENTAL STATE] (needs/drives/personality; 0.0-1.0 unless noted)\n{mental_state_summary}")

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
