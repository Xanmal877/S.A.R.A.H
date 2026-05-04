# ===============================
# MAIN AGENT STATE MACHINE (Direct Port)
# ===============================

import random
from stateMachine import ExploreState, IdleState, StateMachine, WorkState


class SarahStateMachine(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)
        self.idleState = IdleState(agent)
        self.workState = WorkState(agent)
        self.exploreState = ExploreState(agent)

    async def StateMachineLogic(self):
        if self.agent.isProcessingState:
            return

        # Get personality-influenced probabilities (direct port from your code)
        baseIdleChance = 10
        baseWorkChance = 40  # renamed from wander to work
        baseExploreChance = 50

        # Only get the personality modifiers we actually use
        riskModifier = self.agent.personalityModule.GetPersonalityModifier("risk_taking")
        planningModifier = self.agent.personalityModule.GetPersonalityModifier("planning")
        
        # Adjust probabilities based on personality
        # High energy (extraverted) characters explore more, idle less
        energyInfluence = (self.agent.personalityModule.energy - 50) * 0.2  # -10 to +10
        baseExploreChance += energyInfluence
        baseIdleChance -= energyInfluence
        
        # High risk tolerance increases exploration, reduces idle time
        riskInfluence = (riskModifier - 0.5) * 20  # -10 to +10
        baseExploreChance += riskInfluence
        baseIdleChance -= riskInfluence * 0.5
        
        # High planning tendency increases structured activities (work/explore)
        planningInfluence = (planningModifier - 0.5) * 15  # -7.5 to +7.5
        baseWorkChance += planningInfluence
        baseIdleChance -= planningInfluence

        # Ensure probabilities stay within reasonable bounds
        baseIdleChance = max(10, min(baseIdleChance, 60))
        baseWorkChance = max(15, min(baseWorkChance, 50))
        baseExploreChance = max(20, min(baseExploreChance, 70))
        
        # Normalize to 100%
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