# ===============================
# BASE CHARACTER/AGENT (Direct Port)
# ===============================

import asyncio
from modules.personalityModule import PersonalityModule
from mainAgent import SarahStateMachine
from modules.characterManager import CharacterManager


class BaseCharacter:
    def __init__(self, name: str = "Agent"):
        self.characterName = name
        
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

    async def Run(self):
        """Main agent loop - equivalent to your _process function"""
        print(f"Starting {self.characterName} with personality: {self.personalityModule.get_debug_summary()}")
        
        while True:
            # Regeneration (equivalent to _physics_process)
            self.character.Regeneration(0.1)
            
            # State machine logic
            await self.stateMachine.StateMachineLogic()
            
            # Wait before next cycle
            await asyncio.sleep(1.0)

async def StateMachineLogic(self):
    """Override this in subclasses"""
    pass