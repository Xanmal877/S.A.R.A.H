import psutil
from datetime import datetime

class ObservationModule:
    """
    Aggregates the current 'World State' for the LLM,
    providing a snapshot of system, agent, and environmental data.
    """
    def __init__(self, agent=None):
        self.agent = agent

    def get_world_state(self, agent, screen_text: str = None, hive_summary: str = None) -> str:
        """
        Returns a formatted string representing the current state of the world.

        `screen_text` is a sanitized description from ScreenWatcher (see
        modules/perception/screen_watcher.py) - a local vision model has
        already redacted sensitive content out of it, so it's safe to pass
        through to any reasoning engine, cloud included. Pass None to omit
        the [SCREEN] section entirely (e.g. no capture has happened yet).

        `hive_summary` is HiveCore.get_hive_summary() (modules/hive/core.py)
        - only populated on role="core" nodes. Pass None to omit [HIVE].
        """
        # System Metrics
        cpu_usage = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent

        # Current Time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Agent Stats
        # Extracts health, stamina, and mana from the CharacterManager instance
        char = agent.character
        health = char.health
        stamina = char.stamina
        mana = char.mana
        current_task = agent.currentTask

        world_state = (
            f"[SYSTEM]\n"
            f"CPU Usage: {cpu_usage}%\n"
            f"RAM Usage: {ram_usage}%\n"
            f"Current Time: {now}\n\n"
            f"[AGENT]\n"
            f"Health: {health:.2f}/{char.maxHealth:.2f}\n"
            f"Stamina: {stamina:.2f}/{char.maxStamina:.2f}\n"
            f"Mana: {mana:.2f}/{char.maxMana:.2f}\n"
            f"Current Task: {current_task if current_task else 'Idle'}\n\n"
            f"[ENVIRONMENT]\n"
            f"Status: Operational"
        )

        if screen_text is not None:
            world_state += f"\n\n[SCREEN] (local vision model's description of what's currently visible)\n{screen_text}"

        if hive_summary is not None:
            world_state += f"\n\n[HIVE] (other Sarah nodes on the network)\n{hive_summary}"

        return world_state
