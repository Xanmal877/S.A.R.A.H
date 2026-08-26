# ===============================
# S.A.R.A.H SPECIFIC AGENT
# ===============================

from .baseAgent import BaseCharacter


class SarahAgent(BaseCharacter):
    def __init__(self):
        super().__init__("S.A.R.A.H", character_id="sarah")
    
    def create_state_machine(self):
        from mainAgent import SarahStateMachine
        return SarahStateMachine(self)
        
    def SetupPersonality(self):
        # S.A.R.A.H specific personality - the numeric backbone of the "chaos mind"
        # described in agents/sarah_identity.md. High `mind` drives the
        # pattern-driven/associative hypothesis generation; high `identity`
        # drives the assertive "I found it, I'm fixing it" tone; low `tactics`
        # keeps that chaos structured (methodical follow-through) rather than
        # scattered.
        self.personalityModule.energy = 70      # Somewhat extraverted, socially expressive
        self.personalityModule.mind = 90        # Highly intuitive, associative, pattern-driven
        self.personalityModule.nature = 60      # Balanced thinking/feeling
        self.personalityModule.tactics = 30     # More judging/planning - structured underneath the chaos
        self.personalityModule.identity = 80    # Assertive - willing to form opinions and challenge the user

        self.personalityModule.DeterminePersonalityType()
        self.personalityModule.CalculateDecisionWeights()

        # Mirror the trait values into the Soul's MentalState so the
        # needs/drives simulation (chaos-mind curiosity/explore drive, etc.)
        # is actually driven by the same personality, not a separate default.
        mbti = self.soul.mental_state.mbti
        mbti.energy = self.personalityModule.energy
        mbti.mind = self.personalityModule.mind
        mbti.nature = self.personalityModule.nature
        mbti.tactics = self.personalityModule.tactics
        mbti.identity = self.personalityModule.identity
        mbti.confidence = self.personalityModule.decisionConfidence
        mbti.risk_tolerance = self.personalityModule.riskTolerance
