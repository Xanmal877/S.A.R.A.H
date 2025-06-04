import ollama
from typing import List, Dict, Any, Tuple

class ConsciousMind:
    def __init__(self, subconscious):
        self.client = ollama.Client(host='http://localhost:11434')
        self.model = "llama3.1:latest"
        self.subconscious = subconscious
        self.current_strategy = None
        
    def select_best_action(self, available_actions, current_context, goal):
        """Convert GDScript SelectSkillAction HandleState logic"""
        if not available_actions:
            print("Warning: No available actions")
            return None
        
        # Score all available actions
        scored_actions = []
        for action in available_actions:
            score_data = self._calculate_action_score(action, current_context)
            if score_data['score'] > 0:
                scored_actions.append({
                    "action": action,
                    "score": score_data['score'],
                    "reasoning": score_data['reasoning']
                })
        
        if not scored_actions:
            return None
        
        # Sort by score
        scored_actions.sort(key=lambda x: x['score'], reverse=True)
        
        # Apply personality-based final selection
        final_action = self._select_action_with_personality(scored_actions)
        
        print(f"SARAH choosing: {final_action['action']['name']} (Score: {final_action['score']})")
        print(f"Reasoning: {final_action['reasoning']}")
        
        return final_action['action']
    
    def _calculate_action_score(self, action, context) -> Dict[str, Any]:
        """Calculate effectiveness score for an action"""
        base_score = action.get('score', 50)  # Default base score
        reasoning = []
        
        # Simple scoring logic
        if action.get('name') == 'take_screenshot':
            base_score = 20  # Low priority unless nothing else works
            reasoning.append("Screenshot is fallback action")
        elif 'open' in action.get('name', ''):
            base_score = 60  # Higher priority for opening actions
            reasoning.append("Opening action prioritized")
        
        # Apply personality modifiers
        modified_score = self._apply_personality_modifiers(action, base_score)
        if modified_score != base_score:
            reasoning.append(f"Personality adjusted score by {modified_score - base_score}")
        
        return {
            'score': max(0, modified_score),
            'reasoning': "; ".join(reasoning) if reasoning else "Standard scoring"
        }
    
    def _calculate_action_effectiveness_score(self, action, context):
        """Calculate base effectiveness of action"""
        return action.get('score', 50)
    
    def _calculate_healing_score(self, action, context):
        """Calculate healing action score (placeholder)"""
        return action.get('score', 40)
    
    def _apply_personality_modifiers(self, action, base_score: int) -> int:
        """Apply personality-based modifications to action scores"""
        final_score = base_score
        risk_tolerance = self.subconscious.get_personality_modifier("risk_taking")
        confidence = self.subconscious.get_personality_modifier("confidence")
        
        # High-cost actions get personality-based modifiers
        cost_ratio = action.get('cost', 0) / action.get('max_cost', 100)
        
        if cost_ratio > 0.3:  # High-cost actions
            final_score += int(risk_tolerance * 20)
            final_score += int(confidence * 15)
        
        # Long duration actions
        if action.get('duration', 0) > 5.0:
            final_score += int(risk_tolerance * 15)
            final_score -= int((1.0 - confidence) * 10)
        
        return max(0, final_score)
    
    def _select_action_with_personality(self, sorted_actions: List) -> Dict:
        """Select action based on personality traits"""
        confidence = self.subconscious.get_personality_modifier("confidence")
        risk_tolerance = self.subconscious.get_personality_modifier("risk_taking")
        
        # High confidence always picks best action
        if confidence > 0.8:
            return sorted_actions[0]
        
        # Lower confidence might pick suboptimal actions
        chance_for_suboptimal = (1.0 - confidence) * 0.3 + risk_tolerance * 0.2
        
        if (len(sorted_actions) > 1 and 
            __import__('random').random() < chance_for_suboptimal):
            top_actions = sorted_actions[:min(3, len(sorted_actions))]
            return __import__('random').choice(top_actions)
        
        return sorted_actions[0]
    
    def plan_with_llm(self, goal, current_state, knowledge_summary):
        """Use LLM for high-level strategic planning"""
        system_prompt = f"""
You are SARAH's conscious strategic mind. You make deliberate, reasoned decisions.

PERSONALITY: {self.subconscious.personality_type} ({self.subconscious.role})
- Risk tolerance: {self.subconscious.risk_tolerance:.2f}
- Planning tendency: {self.subconscious.planning_tendency:.2f}
- Social priority: {self.subconscious.social_priority:.2f}
- Confidence: {self.subconscious.decision_confidence:.2f}

You think strategically and plan multiple steps ahead.
"""
        
        user_prompt = f"""
GOAL: {goal}
CURRENT STATE: {current_state}
KNOWLEDGE: {knowledge_summary}

Given my personality traits, what's the best strategic approach?
Consider my risk tolerance and planning tendencies.
"""
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={'temperature': 0.3, 'num_predict': 200}
            )
            return response['message']['content']
        except Exception as e:
            print(f"LLM planning error: {e}")
            return "Strategic planning unavailable, proceeding with heuristics"