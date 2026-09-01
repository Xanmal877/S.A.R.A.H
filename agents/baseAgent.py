# ===============================
# BASE CHARACTER/AGENT (Direct Port)
# ===============================

import asyncio

from mainAgent import SarahStateMachine
from modules.avatar import AVATAR_PORTS, DEFAULT_PORT, AvatarBridge, register_bridge
from modules.characterManager import CharacterManager
from modules.personalityModule import PersonalityModule
from modules.soul import Soul
from modules.soul.persistence import save_mental_state

MENTAL_STATE_SAVE_INTERVAL_S = 30


class BaseCharacter:
    def __init__(self, name: str = "Agent", character_id: str = None):
        self.characterName = name
        self.character_id = character_id or name.lower()

        # Core Soul Data (from Autumn's Dungeoneering)
        self.soul = Soul(character_id=self.character_id)
        self.soul.soul_name = name
        
        # Modules (direct port of your modular system)
        self.character = CharacterManager(self)
        self.personalityModule = PersonalityModule(self)
        self.stateMachine = SarahStateMachine(self)
        
        # State tracking
        self.isProcessingState = False
        self.currentTask = ""
        
        # Initialize
        self.SetupCharacter()
        self.SetupPersonality()

    def SetupCharacter(self):
        self.character.charName = self.characterName
        self.character.description = "A digital agent"
        self.character.level = 1
        self.character.UpdateStats()

    def SetupPersonality(self):
        # Default ENFP-T personality (like Tama from your code)
        self.personalityModule.energy = 85      # Extraverted 
        self.personalityModule.mind = 80        # Intuitive
        self.personalityModule.nature = 75      # Feeling
        self.personalityModule.tactics = 85     # Prospecting
        self.personalityModule.identity = 25    # Turbulent

        self.personalityModule.DeterminePersonalityType()
        self.personalityModule.CalculateDecisionWeights()

    async def _start_hive(self):
        """
        Starts this node's hive presence: mDNS discovery (every node) plus
        a read-only HiveServer (every node), and - only for nodes
        configured with role="core" in ~/.sarah/hive_config.json - the
        HiveCore poller that aggregates other peers' info. See
        modules/hive/ and the [HIVE] section of ObservationModule.
        """
        from modules.hive import HiveCore, HiveDiscovery, HiveServer, load_config

        hive_cfg = load_config()
        screen_watcher = getattr(self.stateMachine, "screen_watcher", None)

        discovery = HiveDiscovery(hive_cfg["node_name"], hive_cfg["port"])
        await discovery.start()

        server = HiveServer(hive_cfg["node_name"], hive_cfg["port"], screen_watcher=screen_watcher)
        await server.start()

        if hive_cfg.get("role") == "core":
            hive_core = HiveCore(poll_interval=hive_cfg.get("poll_interval", 20.0))
            await hive_core.start()
            self.stateMachine.hive_core = hive_core

    async def _start_llm_server(self):
        """
        Auto-starts a local llama-server for this node if configured to
        (~/.sarah/hive_config.json: "auto_start_llama_server", "api_type",
        "base_url", "llama_model_path", "llama_port") - only relevant for
        nodes running a local GGUF model (see llama.cpp/bin, models/) rather
        than Ollama. No-op (fast) if a server is already up on that port,
        or if this node isn't configured to use one at all.
        """
        from modules.hive.config import load_config
        from modules.llm_server import llama_manager

        cfg = load_config()
        if not cfg.get("auto_start_llama_server"):
            return
        if cfg.get("api_type") != "openai":
            return
        base_url = cfg.get("base_url") or ""
        if "127.0.0.1" not in base_url and "localhost" not in base_url:
            return  # only auto-manage a genuinely local server

        await asyncio.to_thread(
            llama_manager.ensure_running,
            cfg["llama_model_path"],
            cfg.get("llama_port", 8090),
        )

    async def _start_avatar_bridge(self):
        """
        Starts this character's desktop-avatar IPC (modules/avatar/) so the
        avatar_move_to/avatar_say/avatar_play tools have something to talk
        to. Listens whether or not a Godot avatar process ever connects -
        see AvatarBridge's own docstring for why "no avatar" is a normal,
        not an error, state.
        """
        port = AVATAR_PORTS.get(self.character_id, DEFAULT_PORT)
        self.avatar_bridge = AvatarBridge(character_id=self.character_id, port=port, on_event=self._on_avatar_event)
        await self.avatar_bridge.start()
        register_bridge(self.character_id, self.avatar_bridge)

    def _on_avatar_event(self, name: str, args: dict) -> None:
        # Just observability for now - no reaction logic invented here.
        print(f"[{self.characterName}] Avatar event: {name} {args}")

    async def Run(self):
        """Main agent loop - equivalent to your _process function"""
        print(f"Starting {self.characterName} with personality: {self.personalityModule.get_debug_summary()}")

        await self._start_llm_server()
        await self._start_hive()
        await self._start_avatar_bridge()

        seconds_since_save = 0.0
        try:
            while True:
                # Regeneration (equivalent to _physics_process)
                self.character.Regeneration(0.1)

                # Needs/drives drift - keeps the chaos-mind explore/social/rest
                # drives (modules/soul/mental_state/mental_state.py) alive so
                # personality actually shifts internal state over time.
                self.soul.mental_state.tick(0.1)

                # State machine logic
                await self.stateMachine.StateMachineLogic()

                # Persist mood/needs/drives periodically, not every tick -
                # this is state, not a hot loop write. See modules/soul/persistence.py.
                seconds_since_save += 1.0
                if seconds_since_save >= MENTAL_STATE_SAVE_INTERVAL_S:
                    save_mental_state(self.soul.mental_state, self.character_id)
                    seconds_since_save = 0.0

                # Wait before next cycle
                await asyncio.sleep(1.0)
        finally:
            save_mental_state(self.soul.mental_state, self.character_id)

async def StateMachineLogic(self):
    """Override this in subclasses"""
