from modules.avatar.avatar_bridge import get_bridge
from modules.soul.identity_state.identity_state import active_character_id


def _bridge():
    return get_bridge(active_character_id.get())


async def avatar_move_to(x: float, y: float, running: bool = False):
    """Sends the character's desktop avatar to a screen position. Args: x (float), y (float), running (bool, optional)."""
    bridge = _bridge()
    if not bridge:
        return "No avatar bridge running for this character."
    await bridge.move_to(x, y, running)
    return f"Avatar moving to ({x}, {y})."


async def avatar_say(text: str):
    """Shows a speech bubble over the character's desktop avatar. Args: text (str)."""
    bridge = _bridge()
    if not bridge:
        return "No avatar bridge running for this character."
    await bridge.say(text)
    return "Avatar spoke."


async def avatar_play(animation: str):
    """Plays a one-off animation (Cast/Attack/Hurt/Death) on the character's desktop avatar. Args: animation (str)."""
    bridge = _bridge()
    if not bridge:
        return "No avatar bridge running for this character."
    await bridge.play(animation)
    return f"Avatar played '{animation}'."
