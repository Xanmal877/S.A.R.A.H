import json
import os
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class PersonalityTraits:
    energy: int = 50        # Introversion (0) vs Extraversion (100)
    mind: int = 50          # Sensing (0) vs Intuition (100) 
    nature: int = 50        # Thinking (0) vs Feeling (100)
    tactics: int = 50       # Judging (0) vs Prospecting (100)
    identity: int = 50      # Turbulent (0) vs Assertive (100)

class SubconsciousMind:
    def __init__(self):
        self.personality = PersonalityTraits()
        self.personality_type = ""
        self.role = ""
        self.strategy = ""
        
        # Derived decision weights
        self.decision_confidence = 1.0
        self.risk_tolerance = 0.5
        self.social_priority = 0.5
        self.planning_tendency = 0.5
        
        # Pattern recognition memory
        self.learned_patterns = {}
        self.spatial_memory = {}
        
        self._calculate_personality()
    
    def _calculate_personality(self):
        """Convert GDScript DeterminePersonalityType logic"""
        # Build MBTI type code
        type_code = ""
        type_code += "I" if self.personality.energy < 50 else "E"
        type_code += "S" if self.personality.mind < 50 else "N"
        type_code += "T" if self.personality.nature < 50 else "F"
        type_code += "J" if self.personality.tactics < 50 else "P"
        type_code += "-T" if self.personality.identity < 50 else "-A"
        
        self.personality_type = type_code
        self.role = self._determine_role()
        self.strategy = self._determine_strategy()
        self._calculate_decision_weights()
        
        print(f"SARAH's personality: {self.personality_type} ({self.role}, {self.strategy})")
    
    def _determine_role(self) -> str:
        """Convert GDScript DetermineRole logic"""
        if self.personality.mind >= 50:  # Intuitive
            if self.personality.nature < 50:  # Thinking
                return "Analyst"
            else:  # Feeling
                return "Diplomat"
        else:  # Sensing
            if self.personality.nature < 50:  # Thinking
                return "Sentinel"
            else:  # Feeling
                return "Explorer"
    
    def _determine_strategy(self) -> str:
        """Convert GDScript DetermineStrategy logic"""
        if self.personality.energy >= 50 and self.personality.identity >= 50:
            return "People Mastery"
        elif self.personality.energy >= 50 and self.personality.identity < 50:
            return "Social Engagement"
        elif self.personality.energy < 50 and self.personality.identity >= 50:
            return "Confident Individualism"
        else:
            return "Constant Improvement"
    
    def _calculate_decision_weights(self):
        """Convert GDScript CalculateDecisionWeights logic"""
        # Decision confidence based on identity (assertive vs turbulent)
        self.decision_confidence = self.personality.identity / 100.0
        
        # Risk tolerance based on tactics and identity
        self.risk_tolerance = ((self.personality.tactics + self.personality.identity) / 2.0) / 100.0
        
        # Social priority based on energy and nature
        self.social_priority = ((self.personality.energy + self.personality.nature) / 2.0) / 100.0
        
        # Planning tendency based on tactics
        self.planning_tendency = (100 - self.personality.tactics) / 100.0
    
    def get_personality_modifier(self, decision_type: str) -> float:
        """Convert GDScript GetPersonalityModifier logic"""
        modifiers = {
            "risk_taking": self.risk_tolerance,
            "social_interaction": self.social_priority,
            "planning": self.planning_tendency,
            "confidence": self.decision_confidence
        }
        return modifiers.get(decision_type, 0.5)  # neutral modifier as fallback
    
    def influence_action_selection(self, available_actions, context):
        """New method - unconscious bias toward certain actions"""
        influenced_actions = []
        
        for action in available_actions:
            base_score = action.get('score', 0)
            
            # Apply personality influence
            if action['type'] == 'high_risk' and self.risk_tolerance > 0.7:
                base_score *= 1.3  # Boost risky actions for risk-takers
            
            if action['type'] == 'social' and self.social_priority > 0.6:
                base_score *= 1.2  # Boost social actions for extraverts
            
            if action['type'] == 'planned' and self.planning_tendency > 0.7:
                base_score *= 1.25  # Boost structured actions for judging types
            
            influenced_actions.append({**action, 'influenced_score': base_score})
        
        return sorted(influenced_actions, key=lambda x: x['influenced_score'], reverse=True)