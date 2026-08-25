# ===============================
# MAIN AGENT STATE MACHINE (Direct Port)
# ===============================

import random
import json
from stateMachine import ExploreState, IdleState, StateMachine, WorkState
from modules.llmClient import LLMClient
from modules.personaMapper import PersonaMapper
from modules.observationModule import ObservationModule
from modules.perception import ScreenWatcher


class SarahStateMachine(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)
        self.idleState = IdleState(agent)
        self.workState = WorkState(agent)
        self.exploreState = ExploreState(agent)
        
        # LLM Integration Modules
        self.llm_client = LLMClient.from_node_config()
        self.persona_mapper = PersonaMapper()
        self.observation_module = ObservationModule(agent)

        # Continuous screen awareness. A LOCAL vision model does the actual
        # looking and redaction - it never leaves this machine (see
        # LLMClient.is_local / ScreenWatcher). Only its sanitized text
        # description is ever handed to self.llm_client (which may be the
        # cloud engine) below.
        self.vision_client = LLMClient(model="gemma4:e4b", api_type="ollama")
        self.screen_watcher = ScreenWatcher(vision_client=self.vision_client, interval=7.0)

        # Set by BaseCharacter._start_hive() only on role="core" nodes.
        self.hive_core = None

    async def _probabilistic_decision(self):
        """
        Original probabilistic state selection based on personality traits.
        Used as a fallback when the LLM fails.
        """
        baseIdleChance = 10
        baseWorkChance = 40
        baseExploreChance = 50

        riskModifier = self.agent.personalityModule.GetPersonalityModifier("risk_taking")
        planningModifier = self.agent.personalityModule.GetPersonalityModifier("planning")
        
        energyInfluence = (self.agent.personalityModule.energy - 50) * 0.2
        baseExploreChance += energyInfluence
        baseIdleChance -= energyInfluence
        
        riskInfluence = (riskModifier - 0.5) * 20
        baseExploreChance += riskInfluence
        baseIdleChance -= riskInfluence * 0.5
        
        planningInfluence = (planningModifier - 0.5) * 15
        baseWorkChance += planningInfluence
        baseIdleChance -= planningInfluence

        baseIdleChance = max(10, min(baseIdleChance, 60))
        baseWorkChance = max(15, min(baseWorkChance, 50))
        baseExploreChance = max(20, min(baseExploreChance, 70))

        total = baseIdleChance + baseWorkChance + baseExploreChance
        idleThreshold = (baseIdleChance / total) * 100
        workThreshold = idleThreshold + (baseWorkChance / total) * 100
        
        local_rand = random.randint(1, 100)
        
        if local_rand <= idleThreshold:
            self.SetTask("Idle")
            await self.idleState.HandleState()
        elif local_rand <= workThreshold:
            self.SetTask("Work") 
            await self.workState.HandleState()
        else:
            self.SetTask("Explore")
            await self.exploreState.HandleState()

    async def StateMachineLogic(self):
        if self.agent.isProcessingState:
            return

        try:
            # 1. Aggregate Context
            # The raw screenshot goes only to the local vision model, which
            # redacts sensitive content on the way out (see
            # modules/perception/screen_watcher.py). What comes back here is
            # already safe to hand to self.llm_client, cloud or not.
            await self.screen_watcher.maybe_capture()
            screen_text = self.screen_watcher.get_summary()
            hive_summary = self.hive_core.get_hive_summary() if self.hive_core else None
            world_state = self.observation_module.get_world_state(
                self.agent, screen_text=screen_text, hive_summary=hive_summary
            )

            # Use the ToolOrchestrator for autonomous reasoning
            # Instead of fixed states, we ask her what she wants to do.
            from modules.tools.tool_orchestrator import ToolOrchestrator
            orchestrator = ToolOrchestrator(self.llm_client, agent=self.agent)

            prompt = (
                f"You are Sarah in your autonomous loop. "
                f"Current World State:\n{world_state}\n\n"
                f"You can choose to perform a system check, explore, tidy up, "
                f"react to something you noticed on screen, "
                f"or just stay idle and dream. What do you feel like doing right now?"
            )
            
            response_text = await orchestrator.process_request(prompt, system_context=world_state)
            print(f"[S.A.R.A.H. Autonomous]: {response_text}")

        except Exception as e:
            # Silently handle errors in the background loop to prevent daemon crashes
            pass

