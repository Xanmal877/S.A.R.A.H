# ===============================
# S.A.R.A.H SPECIFIC AGENT
# ===============================

from baseAgent import BaseCharacter


class SarahAgent(BaseCharacter):
    def __init__(self):
        super().__init__("S.A.R.A.H")
    
    def create_state_machine(self):
        from mainAgent import SarahStateMachine
        return SarahStateMachine(self)
        
    def SetupPersonality(self):
        # S.A.R.A.H specific personality - more analytical but social
        self.personalityModule.energy = 70      # Somewhat extraverted
        self.personalityModule.mind = 90        # Highly intuitive 
        self.personalityModule.nature = 60      # Balanced thinking/feeling
        self.personalityModule.tactics = 30     # More judging/planning
        self.personalityModule.identity = 80    # Assertive

        self.personalityModule.DeterminePersonalityType()
        self.personalityModule.CalculateDecisionWeights()
