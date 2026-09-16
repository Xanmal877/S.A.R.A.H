# ===============================
# MAIN AGENT STATE MACHINE (Direct Port)
# ===============================

import logging
import random

from modules.llmClient import LLMClient
from modules.observationModule import ObservationModule
from modules.perception import ScreenWatcher
from modules.personaMapper import PersonaMapper
from stateMachine import ExploreState, IdleState, StateMachine, WorkState

logger = logging.getLogger("SarahStateMachine")


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
            body_state = self.observation_module._body_state(self.agent)

            # Reusable context path (identity + mental state + goal/task +
            # available perception). This folds the same per-character
            # identity/manifest the tool layer resolves via active_character_id.
            from modules.context import assemble_autonomous_context
            world_state = assemble_autonomous_context(
                self.agent, screen_text=screen_text, hive_summary=hive_summary,
                body_state=body_state,
            )

            # Deterministically select the single explicit goal this turn should
            # focus on (an active/proposed non-terminal goal, drive-aware but
            # fully deterministic). Selection never creates/governs goals and may
            # be empty when nothing actionable exists - we then fall back to the
            # generic observe-and-suggest behavior exactly as before.
            goal_dec = None
            try:
                from modules.soul.goals.goal_selection import select_goal
                goal_dec = select_goal(
                    getattr(self.agent, "character_id", "sarah"),
                    drives=self.agent.soul.mental_state.drives,
                )
            except Exception:  # noqa: BLE001 - selection must never break the loop
                goal_dec = None

            selected = goal_dec["selected"] if goal_dec else None
            goal_focus = ""
            if selected:
                goal_focus = (
                    f"\n[SELECTED GOAL] (deterministic focus for this turn)\n"
                    f"{selected['title']} [{selected['status']}, priority "
                    f"{selected['priority']}]\n"
                    f"why: {goal_dec['reason']}"
                )

            # Use the ToolOrchestrator for autonomous reasoning
            # Instead of fixed states, we ask her what she wants to do.
            # observe_only=True restricts her to a read-only observe
            # allowlist (policy, see ToolOrchestrator) - she may never act.
            from modules.tools.tool_orchestrator import ToolOrchestrator
            orchestrator = ToolOrchestrator(
                self.llm_client, agent=self.agent, observe_only=True,
            )

            prompt = (
                f"You are {self.agent.characterName} in your autonomous loop. "
                f"Current context:\n{world_state}\n"
                f"{goal_focus}\n\n"
                f"You observe ONLY, in service of the selected goal above (if a "
                f"goal is present). Look only for what might inform the next step "
                f"for that goal and suggest concrete next steps for it. If no "
                f"goal was selected, simply observe generally. If you spot "
                f"something worth reporting to the operator, say so clearly. You "
                f"do not take action on your own and you do not create, modify, "
                f"or complete goals; you only notice and suggest. What have you "
                f"observed / what next step do you suggest for the goal?"
            )

            response_text = await orchestrator.process_request(prompt, system_context=world_state)
            print(f"[S.A.R.A.H. Autonomous]: {response_text}")

        except Exception as e:
            # Never kill the daemon on a background-loop error, but do surface
            # it in the logs so a recurring failure is visible and debuggable
            # rather than silently swallowed.
            logger.exception("Error in autonomous StateMachineLogic: %s", e)

