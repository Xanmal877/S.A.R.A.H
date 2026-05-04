import time
import random
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

# ===============================
# PERSONALITY MODULE (Direct Port)
# ===============================

class PersonalityModule:
    def __init__(self, agent=None):
        self.agent = agent
        
        # Core MBTI dimensions (0-100 scale)
        self.energy = 50        # Introversion (0) vs Extraversion (100)
        self.mind = 50          # Sensing (0) vs Intuition (100) 
        self.nature = 50        # Thinking (0) vs Feeling (100)
        self.tactics = 50       # Judging (0) vs Prospecting (100)
        self.identity = 50      # Turbulent (0) vs Assertive (100)
        
        # Derived personality data
        self.personalityType = ""
        self.role = ""
        self.strategy = ""
        
        self.decisionConfidence = 1.0
        self.riskTolerance = 0.5
        self.socialPriority = 0.5
        self.planningTendency = 0.5
        
        self.debug_reasoning = ""

    def get_debug_summary(self) -> str:
        return f"{self.personalityType} | Risk:{self.riskTolerance:.1f} Social:{self.socialPriority:.1f} Planning:{self.planningTendency:.1f}"

    def DeterminePersonalityType(self):
        typeCode = ""
        typeCode += "I" if self.energy < 50 else "E"
        typeCode += "S" if self.mind < 50 else "N"
        typeCode += "T" if self.nature < 50 else "F"
        typeCode += "J" if self.tactics < 50 else "P"
        typeCode += "-T" if self.identity < 50 else "-A"

        self.personalityType = typeCode
        self.role = self.DetermineRole()
        self.strategy = self.DetermineStrategy()
        
        if self.agent:
            print(f"{self.agent.characterName} personality: {self.personalityType} ({self.role}, {self.strategy})")

    def DetermineRole(self) -> str:
        if self.mind >= 50:  # Intuitive
            if self.nature < 50:  # Thinking
                return "Analyst"
            else:  # Feeling
                return "Diplomat"
        else:  # Sensing
            if self.nature < 50:  # Thinking
                return "Sentinel" 
            else:  # Feeling
                return "Explorer"

    def DetermineStrategy(self) -> str:
        if self.energy >= 50 and self.identity >= 50:
            return "People Mastery"
        elif self.energy >= 50 and self.identity < 50:
            return "Social Engagement"
        elif self.energy < 50 and self.identity >= 50:
            return "Confident Individualism"
        else:
            return "Constant Improvement"

    def CalculateDecisionWeights(self):
        # Decision confidence based on identity (assertive vs turbulent)
        self.decisionConfidence = self.identity / 100.0
        
        # Risk tolerance based on tactics and identity
        self.riskTolerance = ((self.tactics + self.identity) / 2.0) / 100.0
        
        # Social priority based on energy and nature
        self.socialPriority = ((self.energy + self.nature) / 2.0) / 100.0
        
        # Planning tendency based on tactics (judging vs prospecting)
        self.planningTendency = (100 - self.tactics) / 100.0

    def GetPersonalityModifier(self, decision_type: str) -> float:
        modifiers = {
            "risk_taking": self.riskTolerance,
            "social_interaction": self.socialPriority,
            "planning": self.planningTendency,
            "confidence": self.decisionConfidence,
        }
        return modifiers.get(decision_type, 0.5)  # neutral modifier
