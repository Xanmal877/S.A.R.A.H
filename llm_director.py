import sys
import ollama
from typing import Tuple

from utility_ai import EnhancedLearningUtilityAI


class EXPDirector:
    def __init__(self):

        self.client = None

        self.model = "llama3.1:latest"

        self._initialize()

    

    def _initialize(self):

        """Initialize Ollama connection"""
        try:

            self.client = ollama.Client(host='http://localhost:11434')

            self.client.list()

            print("🧠 Enhanced Experiential LLM Director connected to Ollama")

        except Exception as e:

            raise Exception(f"Failed to connect to Ollama: {e}")

    

    def ProcessUserCommand(self, user_command: str, utility_ai: EnhancedLearningUtilityAI) -> bool:
        """Process user command using enhanced experiential learning"""
        print(f"\n{'='*60}")

        print(f"🎯 User Goal: {user_command}")

        print(f"{'='*60}")

        

        # Get current knowledge and screen state

        knowledge_summary = utility_ai.knowledge.get_knowledge_summary()

        current_state = utility_ai.capture_and_analyze_screen()

        

        print(f"📚 Sarah's Knowledge:\n{knowledge_summary}")

        # Get strategic recommendations

        strategy_recommendations = self._get_strategy_recommendations(user_command, utility_ai.knowledge)

        

        # Initial LLM planning

        system_prompt = self._get_enhanced_system_prompt()

        initial_prompt = f"""

GOAL: {user_command}


SARAH'S KNOWLEDGE:

{knowledge_summary}



STRATEGIC RECOMMENDATIONS:

{strategy_recommendations}



AVAILABLE ACTIONS:

- try_open_app: [app_name] - Try to open specific app

- open_browser_then_youtube: [browser] - Open browser and navigate to YouTube

- navigate_to_youtube - Navigate to YouTube in current browser

- experiment_app: [app_name] - Try multiple strategies

- take_screenshot - See current state

- click_button: [text], type_text: [text], search_for: [term]



CRITICAL: If goal is to open YouTube, don't just take screenshots! TRY ACTIONS!



RESPONSE FORMAT (use exact format):

ACTION: [action name]

TARGET: [target if needed, or leave blank]

REASONING: [explain strategy]



FIRST ACTION (be proactive):"""



        try:

            response = self._get_llm_response(system_prompt, initial_prompt)

            

            max_iterations = 10

            iteration = 0

            

            while iteration < max_iterations:

                iteration += 1

                print(f"\n--- Iteration {iteration} ---")

                

                action, target, reasoning = self._parse_llm_action(response)

                

                # Validate parsed action

                if not action:

                    print("⚠️ LLM didn't provide a valid action, defaulting to take_screenshot")

                    action = "take_screenshot"

                    target = ""

                    reasoning = "LLM response was unclear, taking screenshot to assess situation"

                

                if action == "COMPLETE":

                    print("✅ LLM reports task completed successfully!")

                    return True

                elif action == "FAILED":

                    print("❌ LLM reports task failed - no more strategies to try")

                    return False

                

                print(f"🧠 LLM Decision: {reasoning}")

                

                # Execute action

                result = utility_ai.execute_action(action, target, goal_context=user_command)

                

                # Check for goal achievement

                goal_achieved = result.additional_info.get('goal_achieved', False) if result.additional_info else False

                

                if goal_achieved:

                    print("🎉 Goal achieved!")

                    return True

                

                # Get next action

                updated_knowledge = utility_ai.knowledge.get_knowledge_summary()

                

                result_prompt = f"""

PREVIOUS ACTION: {action} -> {target}

RESULT: {"SUCCESS" if result.success else "FAILED"}

GOAL ACHIEVED: {goal_achieved}

{f"ERROR: {result.error_message}" if result.error_message else ""}



GOAL: {user_command}



UPDATED KNOWLEDGE:

{updated_knowledge}



CURRENT SCREEN:

- Visible text: {result.visible_text[:8] if result.visible_text else ['None']}

STRATEGY:

- If GOAL ACHIEVED: True → ACTION: COMPLETE

- If GOAL ACHIEVED: False → try next recommended strategy

- Don't repeat failed actions unless with different targets



RESPONSE FORMAT (use exact format):

ACTION: [action name]

TARGET: [target if needed, or leave blank]  

REASONING: [explain strategy]



NEXT ACTION:"""



                response = self._get_llm_response(system_prompt, result_prompt)

            

            print("⚠️ Max iterations reached")

            return False

            

        except Exception as e:

            print(f"❌ LLM Director error: {e}")

            return False


    def GetSystemPrompt(self) -> str:

        """Get enhanced system prompt"""

        return """You are directing Sarah, an experiential learning AI that builds knowledge through trial and error.



CORE PRINCIPLES:

1. BE PROACTIVE - Don't just take screenshots, TRY ACTIONS to achieve goals

2. USE SARAH'S KNOWLEDGE - Leverage what she's learned about working apps

3. GOAL-FOCUSED - Only declare COMPLETE when GOAL ACHIEVED: True

4. STRATEGIC - Follow recommended strategies based on past success



GOAL ACHIEVEMENT LOGIC:

- Sarah reports "GOAL ACHIEVED: True/False" for each action

- Only declare COMPLETE when GOAL ACHIEVED: True

- If GOAL ACHIEVED: False, try different approaches

- Don't repeat exact same failing actions


NEVER get stuck in screenshot loops - always try to make progress toward the goal!

You are action-oriented, strategic, and focused on actual goal achievement."""



    def ParseLLMAction(self, response: str) -> Tuple[str, str, str]:

        """Parse LLM response for action, target, and reasoning"""

        print(f"🔍 LLM Response: {response}")

        

        lines = response.strip().split('\n')

        

        action = ""

        target = ""

        reasoning = ""

        

        for line in lines:

            line = line.strip()

            # Handle both plain and markdown formatting

            if line.startswith("ACTION:") or line.startswith("**ACTION:**"):

                action = line.replace("ACTION:", "").replace("**ACTION:**", "").strip()

            elif line.startswith("TARGET:") or line.startswith("**TARGET:**"):

                target = line.replace("TARGET:", "").replace("**TARGET:**", "").strip()

            elif line.startswith("REASONING:") or line.startswith("**REASONING:**"):

                reasoning = line.replace("REASONING:", "").replace("**REASONING:**", "").strip()

        

        # Handle case where target might be "None" string

        if target.lower() in ["none", "null", ""]:

            target = ""

        

        return action, target, reasoning

    

    def GetLLMResponse(self, system_prompt: str, user_prompt: str) -> str:

        """Get response from LLM"""

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

            raise Exception(f"LLM request failed: {e}")