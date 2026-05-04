# ===============================
# STATE MACHINE (Direct Port)
# ===============================

import asyncio
import random


class StateMachine:
    def __init__(self, agent=None):
        self.agent = agent
        self.currentState = None
        self.isProcessingState = False

    async def HandleState(self):
        pass

    def SetTask(self, taskName: str):
        if hasattr(self.agent, 'currentTask') and taskName == self.agent.currentTask:
            return
        if self.agent:
            self.agent.currentTask = taskName


class IdleState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def HandleState(self):
        self.agent.isProcessingState = True
        randomTime = random.uniform(1, 3)
        print(f"{self.agent.characterName} is idling for {randomTime:.1f} seconds")
        await asyncio.sleep(randomTime)
        self.agent.isProcessingState = False

class WorkState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def HandleState(self):
        self.agent.isProcessingState = True
        
        # Personality-influenced work patterns
        baseWorkTime = 30  # base 30 minutes
        
        # Get personality modifiers
        planningModifier = self.agent.personalityModule.GetPersonalityModifier("planning")
        riskModifier = self.agent.personalityModule.GetPersonalityModifier("risk_taking")
        
        # High planning = longer focused work sessions
        planningInfluence = planningModifier * 20  # 0 to 20 minutes
        
        # High risk tolerance = shorter bursts, more experimental
        riskInfluence = (1.0 - riskModifier) * 15  # 0 to 15 minutes (inverted)
        
        workTime = baseWorkTime + planningInfluence + riskInfluence
        workTime = max(5, min(workTime, 120))  # clamp between 5 min and 2 hours
        
        print(f"{self.agent.characterName} working for {workTime:.1f} minutes")
        print(f"  Reasoning: planning={planningModifier:.2f}, risk={riskModifier:.2f}")
        
        # Simulate work (in real implementation, this would do actual tasks)
        await asyncio.sleep(workTime * 0.1)  # scaled down for demo
        
        self.agent.isProcessingState = False

class ExploreState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def HandleState(self):
        self.agent.isProcessingState = True
        
        # Personality-driven exploration
        baseExploreTime = 10
        
        riskTolerance = self.agent.personalityModule.GetPersonalityModifier("risk_taking")
        confidence = self.agent.personalityModule.GetPersonalityModifier("confidence")
        
        # High risk + high confidence = longer exploration
        exploreTime = baseExploreTime + (riskTolerance * confidence * 20)
        
        print(f"{self.agent.characterName} exploring for {exploreTime:.1f} minutes")
        print(f"  Risk tolerance: {riskTolerance:.2f}, Confidence: {confidence:.2f}")
        
        await asyncio.sleep(exploreTime * 0.1)  # scaled down for demo
        
        self.agent.isProcessingState = False