import time
import pyautogui
from PIL import ImageGrab
import pytesseract

from subconscious import SubconsciousMind
from conscious import ConsciousMind
from thoughts import ThoughtStream
from utility_ai import EnhancedLearningUtilityAI

class SARAH:
    def __init__(self):
        print("🤖 Initializing SARAH's three-layer mind...")
        
        # Initialize the three cognitive layers
        self.subconscious = SubconsciousMind()
        self.conscious = ConsciousMind(self.subconscious)
        self.thoughts = ThoughtStream(self.conscious, self.subconscious)
        
        # Utility AI for actions
        self.utility_ai = EnhancedLearningUtilityAI()
        
        print("✅ SARAH is fully conscious and ready!")
        print(f"Personality: {self.subconscious.personality_type}")
    
    def process_goal(self, user_goal):
        """Main processing loop - coordinates all three minds"""
        print(f"\n🎯 New Goal: {user_goal}")
        
        # 1. Conscious mind creates strategic plan
        current_state = self.utility_ai.capture_and_analyze_screen()
        knowledge = self.utility_ai.knowledge.get_knowledge_summary()
        
        strategic_plan = self.conscious.plan_with_llm(user_goal, current_state, knowledge)
        print(f"🧠 Strategic Plan: {strategic_plan}")
        
        # 2. Main execution loop
        max_iterations = 10
        for iteration in range(max_iterations):
            print(f"\n--- Iteration {iteration + 1} ---")
            
            # Thoughts: Immediate reaction to current screen
            screenshot = ImageGrab.grab()
            visible_text = pytesseract.image_to_string(screenshot).split('\n')[:10]
            
            immediate_reaction = self.thoughts.process_immediate_screen(
                screenshot, visible_text, user_goal
            )
            
            # Conscious: Decide what action to take
            available_actions = self._get_available_actions(current_state, user_goal)
            chosen_action = self.conscious.select_best_action(
                available_actions, current_state, user_goal
            )
            
            if not chosen_action:
                print("❌ No valid actions available")
                break
            
            # Thoughts: Start executing the action
            estimated_duration = chosen_action.get('duration', 2.0)
            if not self.thoughts.start_action_execution(
                chosen_action['name'], chosen_action.get('target'), estimated_duration
            ):
                continue
            
            # Execute through utility AI
            result = self.utility_ai.execute_action(
                chosen_action['action_type'], 
                chosen_action.get('target', ''),
                user_goal
            )
            
            # Thoughts: Monitor and complete
            while self.thoughts.is_executing:
                progress = self.thoughts.monitor_action_progress()
                if progress and progress['progress'] >= 1.0:
                    break
                time.sleep(0.5)
            
            success = self.thoughts.complete_action_execution(
                result.success, 
                result.additional_info
            )
            
            # Check if goal achieved
            goal_achieved = result.additional_info.get('goal_achieved', False) if result.additional_info else False
            if goal_achieved:
                print("🎉 Goal achieved!")
                return True
            
            # Update state for next iteration
            current_state = self.utility_ai.capture_and_analyze_screen()
        
        print("⚠️ Max iterations reached")
        return False
    
    def _get_available_actions(self, current_state, goal):
        """Convert current state and goal to available actions"""
        actions = []
        
        # Always available actions
        actions.append({
            'name': 'take_screenshot',
            'action_type': 'take_screenshot',
            'cost': 0,
            'duration': 0.5,
            'score': 20
        })
        
        # Goal-specific actions
        if 'open' in goal.lower():
            # Extract app name from goal
            words = goal.lower().split()
            app_name = None
            for i, word in enumerate(words):
                if word == 'open' and i + 1 < len(words):
                    app_name = words[i + 1]
                    break
            
            if app_name:
                actions.append({
                    'name': f'try_open_{app_name}',
                    'action_type': 'try_open_app',
                    'target': app_name,
                    'cost': 5,
                    'duration': 3.0,
                    'score': 60
                })
                
                actions.append({
                    'name': f'experiment_with_{app_name}',
                    'action_type': 'experiment_app', 
                    'target': app_name,
                    'cost': 10,
                    'duration': 10.0,
                    'score': 50
                })
        
        # Add more contextual actions based on screen content
        visible_text = current_state.get('visible_text', [])
        clickable_elements = current_state.get('clickable_elements', [])
        
        if clickable_elements:
            # Add click actions for visible buttons
            for element in clickable_elements[:3]:  # Limit to top 3
                actions.append({
                    'name': f'click_{element}',
                    'action_type': 'click_button',
                    'target': element,
                    'cost': 2,
                    'duration': 1.0,
                    'score': 40
                })
        
        return actions
    
    def chat_interface(self):
        """Interactive interface"""
        print("\n💬 SARAH is ready! Try commands like:")
        print("  'open notepad'")
        print("  'open calculator'")
        print("  'take a screenshot'")
        print("  'thoughts' - see what I'm thinking")
        print("  'quit' to exit")
        print("=" * 50)
        
        while True:
            try:
                user_input = input(f"\nYou: ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    print("👋 SARAH: Goodbye! Sweet dreams.")
                    break
                
                if user_input.lower() == 'thoughts':
                    print(f"🤔 Current focus: {self.thoughts.get_current_focus()}")
                    continue
                
                # Process the goal through all three minds
                success = self.process_goal(user_input)
                
                if success:
                    print("😊 SARAH: I did it! I'm learning so much.")
                else:
                    print("😅 SARAH: I tried my best, but couldn't complete that.")
                
            except KeyboardInterrupt:
                print("\n👋 SARAH: Goodbye!")
                break

if __name__ == "__main__":
    sarah = SARAH()
    sarah.chat_interface()