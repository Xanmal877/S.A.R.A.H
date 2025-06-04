import ollama
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ImmediateState:
    current_action: Optional[str] = None
    target_focus: Optional[str] = None
    screen_elements: list = None
    confidence_level: float = 1.0
    urgency: float = 0.0

class ThoughtStream:
    def __init__(self, conscious_mind, subconscious_mind):
        self.client = ollama.Client(host='http://localhost:11434')
        self.model = "llama3.1:latest"  # Could be different model for speed
        self.conscious = conscious_mind
        self.subconscious = subconscious_mind
        
        # Working memory - immediate thoughts
        self.current_state = ImmediateState()
        self.working_memory = []
        self.last_screen_analysis = {}
        
        # Action tracking (convert UseSkillAction casting logic)
        self.is_executing = False
        self.execution_start_time = None
        self.expected_duration = 0
        
    def process_immediate_screen(self, screenshot, visible_text, goal_context):
        """Real-time analysis of what's happening right now"""
        
        # Quick personality-influenced reaction
        urgency_modifier = self.subconscious.get_personality_modifier("confidence")
        self.current_state.urgency = (1.0 - urgency_modifier) * 0.5  # Less confident = more urgent
        
        # Immediate LLM thoughts about what I'm seeing
        thought_prompt = f"""
I'm looking at the screen right now. I can see: {visible_text[:10]}

My current goal: {goal_context}
My urgency level: {self.current_state.urgency:.2f}

What do I think about this situation? What catches my attention immediately?
What feels right or wrong about what I'm seeing?

Give me a quick, intuitive reaction - not a detailed plan.
"""
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_thoughts_system_prompt()},
                    {"role": "user", "content": thought_prompt}
                ],
                options={'temperature': 0.7, 'num_predict': 100}  # Higher temp for more natural thoughts
            )
            
            immediate_thought = response['message']['content']
            self.working_memory.append({
                'timestamp': time.time(),
                'type': 'screen_reaction',
                'content': immediate_thought
            })
            
            print(f"💭 SARAH thinks: {immediate_thought}")
            return immediate_thought
            
        except Exception as e:
            print(f"Thought stream error: {e}")
            return "Something doesn't feel right..."
    
    def start_action_execution(self, action, target, estimated_duration):
        """Convert UseSkillAction StartCasting logic"""
        if self.is_executing:
            self.internal_dialogue("I'm already doing something, need to focus...")
            return False
        
        self.is_executing = True
        self.execution_start_time = time.time()
        self.expected_duration = estimated_duration
        self.current_state.current_action = action
        self.current_state.target_focus = target
        
        # Immediate thought about starting action
        confidence = self.subconscious.get_personality_modifier("confidence")
        if confidence > 0.7:
            self.internal_dialogue(f"Starting {action} - this should work")
        else:
            self.internal_dialogue(f"Trying {action}... hope this works")
        
        return True
    
    def monitor_action_progress(self):
        """Convert UseSkillAction UpdateCastBar logic - real-time monitoring"""
        if not self.is_executing:
            return None
        
        elapsed = time.time() - self.execution_start_time
        progress = min(elapsed / self.expected_duration, 1.0) if self.expected_duration > 0 else 1.0
        
        # Stream of consciousness during execution
        if progress > 0.5 and progress < 0.8:
            planning_tendency = self.subconscious.get_personality_modifier("planning")
            if planning_tendency > 0.6:
                self.internal_dialogue("Almost there... staying focused...")
            else:
                self.internal_dialogue("Taking a while... maybe I should try something else?")
        
        return {
            'progress': progress,
            'elapsed': elapsed,
            'remaining': max(0, self.expected_duration - elapsed)
        }
    
    def complete_action_execution(self, success, result_context):
        """Convert UseSkillAction FinishCasting logic"""
        self.is_executing = False
        elapsed = time.time() - self.execution_start_time
        
        # Immediate emotional reaction based on personality
        risk_tolerance = self.subconscious.get_personality_modifier("risk_taking")
        
        if success:
            if risk_tolerance > 0.7:
                self.internal_dialogue("Yes! That worked perfectly. I knew it would.")
            else:
                self.internal_dialogue("Phew! That worked. I was a bit worried.")
        else:
            if risk_tolerance > 0.7:
                self.internal_dialogue("Hmm, that didn't work. No big deal, I'll try something else.")
            else:
                self.internal_dialogue("Oh no, that failed. Maybe I should be more careful...")
        
        # Clear current focus
        self.current_state.current_action = None
        self.current_state.target_focus = None
        
        # Store in working memory
        self.working_memory.append({
            'timestamp': time.time(),
            'type': 'action_result',
            'action': self.current_state.current_action,
            'success': success,
            'duration': elapsed,
            'context': result_context
        })
        
        return success
    
    def react_to_screen_change(self, before_state, after_state):
        """Immediate reaction to screen changes"""
        # Quick pattern recognition from subconscious
        significant_change = len(set(after_state.get('visible_text', [])) - 
                                set(before_state.get('visible_text', []))) > 3
        
        if significant_change:
            confidence = self.subconscious.get_personality_modifier("confidence")
            if confidence > 0.6:
                self.internal_dialogue("Something changed on the screen. Let me see what happened.")
            else:
                self.internal_dialogue("Whoa, the screen changed. Did I do that? Is that good?")
            
            return "significant_change"
        else:
            return "minor_change"
    
    def internal_dialogue(self, thought):
        """Stream of consciousness - SARAH talking to herself"""
        self.working_memory.append({
            'timestamp': time.time(),
            'type': 'internal_thought',
            'content': thought
        })
        print(f"🤔 SARAH to herself: {thought}")
    
    def get_current_focus(self):
        """What is SARAH thinking about right now?"""
        if self.is_executing:
            return f"Executing {self.current_state.current_action}"
        elif self.working_memory:
            latest = self.working_memory[-1]
            return f"Just thought: {latest['content'][:50]}..."
        else:
            return "Mind is clear"
    
    def _get_thoughts_system_prompt(self):
        return f"""
You are SARAH's immediate thought stream. You process what's happening RIGHT NOW.

Your personality: {self.subconscious.personality_type}
- You react based on confidence level: {self.subconscious.decision_confidence:.2f}
- Your risk tolerance: {self.subconscious.risk_tolerance:.2f}

You think in the moment, react emotionally, and have gut reactions.
You're not making strategic plans - that's the conscious mind's job.
You're just reacting to what you see and feel.

Keep responses short and immediate - like actual thoughts, not analysis.
"""