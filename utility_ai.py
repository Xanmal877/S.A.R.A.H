import os

import sys

import time

from typing import Dict, List, Any

from dataclasses import dataclass

from datetime import datetime

from knowledge_base import EnhancedKnowledgeBase, Experience



# Core imports

try:

    import pyautogui

    import pytesseract 

    import cv2

    import numpy as np

    from PIL import Image, ImageGrab, ImageDraw

    import psutil

except ImportError as e:

    print(f"❌ Missing required package: {e}")

    print("Install with: pip install pyautogui pytesseract opencv-python pillow psutil")

    sys.exit(1)



# Configure pyautogui safety

pyautogui.FAILSAFE = True

pyautogui.PAUSE = 0.1



@dataclass

class ActionResult:

    """Result of an action execution"""

    success: bool

    action: str

    target: str

    before_state: Dict[str, Any] = None

    after_state: Dict[str, Any] = None

    visible_text: List[str] = None

    clickable_elements: List[str] = None

    error_message: str = ""

    additional_info: Dict[str, Any] = None



    def to_dict(self) -> Dict[str, Any]:

        return {

            "success": self.success,

            "action": self.action,

            "target": self.target,

            "before_state": self.before_state or {},

            "after_state": self.after_state or {},

            "visible_text": self.visible_text or [],

            "clickable_elements": self.clickable_elements or [],

            "error_message": self.error_message,

            "additional_info": self.additional_info or {}

        }



class EnhancedLearningUtilityAI:

    """Enhanced Sarah - Learning utility AI that builds knowledge through experience"""

    

    def __init__(self):

        self.knowledge = EnhancedKnowledgeBase()

        self.last_screenshot = None

        self.current_context = {}

        print("🤖 Enhanced Learning Utility AI (Sarah) initialized")

    

    def capture_and_analyze_screen(self) -> Dict[str, Any]:

        """Capture screen and return analysis"""

        try:

            screenshot = ImageGrab.grab(all_screens=True)

            self.last_screenshot = screenshot

            

            # OCR analysis

            ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

            

            visible_text = []

            clickable_elements = []

            

            n_boxes = len(ocr_data['level'])

            for i in range(n_boxes):

                confidence = int(ocr_data['conf'][i])

                text = ocr_data['text'][i].strip()

                

                if confidence > 40 and text:

                    visible_text.append(text)

                    

                    # Check if likely clickable

                    if self._is_likely_clickable(text):

                        clickable_elements.append(text)

            

            analysis = {

                "screen_size": screenshot.size,

                "visible_text": visible_text[:50],

                "clickable_elements": clickable_elements[:20],

                "timestamp": datetime.now().isoformat(),

            }

            

            self.current_context = analysis

            return analysis

            

        except Exception as e:

            error_analysis = {

                "error": f"Screen analysis failed: {e}",

                "visible_text": [],

                "clickable_elements": [],

                "timestamp": datetime.now().isoformat(),

                "has_youtube_indicators": False

            }

            self.current_context = error_analysis

            return error_analysis

    

    def _has_youtube_indicators(self, visible_text: List[str]) -> bool:

        """Check if screen shows YouTube indicators using a simple heuristic"""

        # Instead of hardcoded keywords, look for URL-like patterns or learn from experience

        text_lower = [t.lower() for t in visible_text]

        combined_text = ' '.join(text_lower)

        

        # Simple heuristic: look for "youtube.com" or similar URL patterns

        # Sarah can refine this through experience by learning what text appears when YouTube is open

        return "youtube.com" in combined_text or "ytimg.com" in combined_text

    

    def _detect_goal_achieved(self, goal: str, before_state: Dict, after_state: Dict) -> bool:

        """Enhanced goal detection"""

        goal_lower = goal.lower()

        

        # YouTube-specific detection

        if 'youtube' in goal_lower:

            return after_state.get('has_youtube_indicators', False)

        

        # App-specific detection

        if 'open' in goal_lower:

            app_name = goal_lower.replace('open', '').strip()

            return self._detect_app_opened(app_name, before_state, after_state)

        

        return False

    

    def _detect_app_opened(self, app_name: str, before_state: Dict, after_state: Dict) -> bool:

        """Intelligently detect if an app actually opened using generic criteria"""

        before_text = set([t.lower() for t in before_state.get('visible_text', [])])

        after_text = set([t.lower() for t in after_state.get('visible_text', [])])

        

        # Generic criteria: look for new text that includes the app name and an increase in interface elements

        new_text = after_text - before_text

        app_name_appeared = app_name.lower() in new_text or any(app_name.lower() in t for t in new_text)

        

        # Check if interface elements appeared (indicating a new window or UI)

        interface_appeared = len(after_state.get('clickable_elements', [])) > len(before_state.get('clickable_elements', []))

        

        # Success if both new relevant text and interface elements appeared

        return app_name_appeared and interface_appeared

    

    def _is_likely_clickable(self, text: str) -> bool:

        """Determine if text represents clickable element"""

        clickable_keywords = {

            'play', 'start', 'stop', 'pause', 'ok', 'cancel', 'yes', 'no',

            'continue', 'next', 'back', 'submit', 'send', 'save', 'open',

            'close', 'install', 'update', 'login', 'download', 'buy', 'add',

            'file', 'edit', 'view', 'help', 'tools', 'settings', 'subscribe'

        }

        return text.lower() in clickable_keywords or len(text) < 20

    

    def execute_action(self, action: str, target: str = "", goal_context: str = "") -> ActionResult:

        """Execute action and learn from the experience"""

        

        # Capture before state

        before_state = self.capture_and_analyze_screen()

        

        print(f"🔄 Trying: {action} -> {target}")

        

        # Execute the action

        result = self._execute_raw_action(action, target, before_state)

        

        # Capture after state

        after_state = self.capture_and_analyze_screen()

        result.before_state = before_state

        result.after_state = after_state

        

        # Enhanced goal achievement detection

        if goal_context:

            goal_achieved = self._detect_goal_achieved(goal_context, before_state, after_state)

            if result.additional_info is None:

                result.additional_info = {}

            result.additional_info['goal_achieved'] = goal_achieved

        

        # Create experience record with proper additional_info handling

        context_additional_info = result.additional_info or {}

        

        experience = Experience(

            timestamp=datetime.now().isoformat(),

            action=action,

            target=target,

            context={

                'goal': goal_context,

                'before_state': before_state,

                'additional_info': context_additional_info

            },

            result={

                'after_state': after_state,

                'success': result.success,

                'goal_achieved': context_additional_info.get('goal_achieved', False),

                'error': result.error_message

            },

            success=result.success and context_additional_info.get('goal_achieved', False),

            outcome_description=self._describe_outcome(before_state, after_state, result)

        )

        

        # Learn from this experience

        self.knowledge.add_experience(experience)

        

        if experience.success:

            print(f"✅ Success: {experience.outcome_description}")

        else:

            print(f"❌ Failed: {experience.outcome_description}")

        

        return result

    

    def _execute_raw_action(self, action: str, target: str, before_state: Dict) -> ActionResult:

        """Execute the raw action without learning components"""

        

        if action == "take_screenshot":

            return self._take_screenshot()

        elif action == "try_open_app":

            return self._try_open_app(target)

        elif action == "open_browser_then_youtube":

            return self._open_browser_then_youtube(target)

        elif action == "experiment_app":

            return self._experiment_with_app(target)

        elif action == "click_button":

            return self._click_button(target)

        elif action == "type_text":

            return self._type_text(target)

        elif action == "search_for":

            return self._search_for(target)

        elif action == "navigate_to_youtube":

            return self._navigate_to_youtube()

        else:

            return ActionResult(

                success=False,

                action=action,

                target=target,

                error_message=f"Unknown action: {action}"

            )

    

    def _open_browser_then_youtube(self, browser: str) -> ActionResult:

        """Open browser and navigate to YouTube"""

        try:

            # First open the browser

            pyautogui.press('win')

            time.sleep(0.5)

            pyautogui.typewrite(browser, interval=0.05)

            time.sleep(1.5)

            pyautogui.press('enter')

            time.sleep(4)

            

            # Then navigate to YouTube

            pyautogui.hotkey('ctrl', 'l')

            time.sleep(0.5)

            pyautogui.typewrite('youtube.com', interval=0.05)

            time.sleep(0.5)

            pyautogui.press('enter')

            time.sleep(3)

            

            analysis = self.capture_and_analyze_screen()

            

            return ActionResult(

                success=True,

                action="open_browser_then_youtube",

                target=browser,

                visible_text=analysis.get("visible_text", []),

                clickable_elements=analysis.get("clickable_elements", []),

                additional_info={

                    "method": "browser_navigation",

                    "goal_achieved": analysis.get('has_youtube_indicators', False)

                }

            )

            

        except Exception as e:

            return ActionResult(

                success=False,

                action="open_browser_then_youtube",

                target=browser,

                error_message=f"Failed to open browser and navigate: {e}"

            )

    

    def _navigate_to_youtube(self) -> ActionResult:

        """Navigate to YouTube in current browser"""

        try:

            pyautogui.hotkey('ctrl', 'l')

            time.sleep(0.5)

            pyautogui.typewrite('youtube.com', interval=0.05)

            time.sleep(0.5)

            pyautogui.press('enter')

            time.sleep(3)

            

            analysis = self.capture_and_analyze_screen()

            

            return ActionResult(

                success=True,

                action="navigate_to_youtube",

                target="",

                visible_text=analysis.get("visible_text", []),

                clickable_elements=analysis.get("clickable_elements", []),

                additional_info={

                    "goal_achieved": analysis.get('has_youtube_indicators', False)

                }

            )

            

        except Exception as e:

            return ActionResult(

                success=False,

                action="navigate_to_youtube",

                target="",

                error_message=f"Navigation failed: {e}"

            )

    

    def _try_open_app(self, app_name: str) -> ActionResult:

        """Try to open an application"""

        if not app_name:

            return ActionResult(False, "try_open_app", app_name, error_message="No app name provided")

        

        try:

            before_analysis = self.capture_and_analyze_screen()

            

            # Use known successful strategy if available

            strategy = self.knowledge.app_opening_strategies.get(app_name, app_name)

            

            pyautogui.press('win')

            time.sleep(0.5)

            pyautogui.typewrite(strategy, interval=0.05)

            time.sleep(1.5)

            pyautogui.press('enter')

            time.sleep(4)

            

            after_analysis = self.capture_and_analyze_screen()

            

            # Goal-aware success detection

            success = self._detect_app_opened(app_name, before_analysis, after_analysis)

            

            return ActionResult(

                success=success,

                action="try_open_app",

                target=app_name,

                visible_text=after_analysis.get("visible_text", []),

                clickable_elements=after_analysis.get("clickable_elements", []),

                additional_info={

                    "method": "start_menu",

                    "strategy_used": strategy,

                    "goal_achieved": success

                }

            )

            

        except Exception as e:

            return ActionResult(

                success=False,

                action="try_open_app",

                target=app_name,

                error_message=f"Failed to open {app_name}: {e}"

            )

    

    def _experiment_with_app(self, app_name: str) -> ActionResult:

        """Experimental approach to finding and opening apps"""

        print(f"🧪 Experimenting with opening '{app_name}'...")

        

        initial_state = self.capture_and_analyze_screen()

        

        strategies = [

            f"{app_name}",

            f"{app_name}.exe",

            app_name.lower(),

            app_name.capitalize(),

            " ".join(app_name.split()[:1])

        ]

        

        for i, strategy in enumerate(strategies):

            print(f"  Strategy {i+1}: '{strategy}'")

            

            try:

                pyautogui.press('win')

                time.sleep(0.5)

                pyautogui.typewrite(strategy, interval=0.05)

                time.sleep(1.5)

                pyautogui.press('enter')

                time.sleep(4)

                

                after_state = self.capture_and_analyze_screen()

                goal_achieved = self._detect_app_opened(app_name, initial_state, after_state)

                

                if goal_achieved:

                    print(f"  ✅ Strategy {i+1} achieved the goal!")

                    return ActionResult(

                        success=True,

                        action="experiment_app",

                        target=app_name,

                        visible_text=after_state.get("visible_text", []),

                        clickable_elements=after_state.get("clickable_elements", []),

                        additional_info={

                            "successful_strategy": strategy,

                            "strategy_number": i+1,

                            "goal_achieved": True

                        }

                    )

                else:

                    print(f"  ❌ Strategy {i+1} failed to achieve goal")

                    time.sleep(1)

            

            except Exception as e:

                print(f"  ❌ Strategy {i+1} error: {e}")

                time.sleep(1)

        

        return ActionResult(

            success=False,

            action="experiment_app",

            target=app_name,

            error_message=f"All strategies failed to achieve goal for {app_name}",

            additional_info={"goal_achieved": False}

        )

    

    def _take_screenshot(self) -> ActionResult:

        """Take screenshot and analyze"""

        analysis = self.capture_and_analyze_screen()

        

        return ActionResult(

            success=True,

            action="take_screenshot",

            target="",

            visible_text=analysis.get("visible_text", []),

            clickable_elements=analysis.get("clickable_elements", []),

            additional_info=analysis

        )

    

    def _click_button(self, button_text: str) -> ActionResult:

        """Find and click button by text"""

        if not button_text:

            return ActionResult(False, "click_button", button_text, error_message="No button text provided")

        

        try:

            screenshot = ImageGrab.grab(all_screens=True)

            ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

            

            target_lower = button_text.lower()

            n_boxes = len(ocr_data['level'])

            

            for i in range(n_boxes):

                confidence = int(ocr_data['conf'][i])

                text = ocr_data['text'][i].strip()

                

                if confidence > 30 and text and target_lower in text.lower():

                    x = ocr_data['left'][i] + ocr_data['width'][i] // 2

                    y = ocr_data['top'][i] + ocr_data['height'][i] // 2

                    

                    pyautogui.click(x, y)

                    time.sleep(0.5)

                    

                    analysis = self.capture_and_analyze_screen()

                    

                    return ActionResult(

                        success=True,

                        action="click_button",

                        target=button_text,

                        visible_text=analysis.get("visible_text", []),

                        clickable_elements=analysis.get("clickable_elements", []),

                        additional_info={"clicked_at": (x, y), "matched_text": text}

                    )

            

            return ActionResult(

                success=False,

                action="click_button",

                target=button_text,

                error_message=f"Button '{button_text}' not found"

            )

            

        except Exception as e:

            return ActionResult(False, "click_button", button_text, error_message=f"Click failed: {e}")

    

    def _type_text(self, text: str) -> ActionResult:

        """Type text"""

        try:

            pyautogui.typewrite(text, interval=0.05)

            time.sleep(0.3)

            

            analysis = self.capture_and_analyze_screen()

            return ActionResult(

                success=True,

                action="type_text",

                target=text,

                visible_text=analysis.get("visible_text", []),

                clickable_elements=analysis.get("clickable_elements", [])

            )

            

        except Exception as e:

            return ActionResult(False, "type_text", text, error_message=f"Typing failed: {e}")

    

    def _search_for(self, search_term: str) -> ActionResult:

        """Search in address bar or search box"""

        try:

            pyautogui.hotkey('ctrl', 'l')

            time.sleep(0.3)

            pyautogui.typewrite(search_term, interval=0.05)

            time.sleep(0.3)

            pyautogui.press('enter')

            time.sleep(2)

            

            analysis = self.capture_and_analyze_screen()

            return ActionResult(

                success=True,

                action="search_for",

                target=search_term,

                visible_text=analysis.get("visible_text", []),

                clickable_elements=analysis.get("clickable_elements", []),

                additional_info={"method": "address_bar"}

            )

            

        except Exception as e:

            return ActionResult(False, "search_for", search_term, error_message=f"Search failed: {e}")

    

    def _describe_outcome(self, before: Dict, after: Dict, result: ActionResult) -> str:

        """Generate human-readable description of what happened"""

        if not result.success:

            return f"Action failed: {result.error_message}"

        

        goal_achieved = result.additional_info.get('goal_achieved', None) if result.additional_info else None

        

        if goal_achieved is True:

            return f"Goal achieved: {result.action} successfully completed the intended goal"

        elif goal_achieved is False:

            return f"Action completed but goal not achieved: {result.action} executed but didn't accomplish the intended result"

        

        # Fall back to change detection

        before_text = set(before.get('visible_text', []))

        after_text = set(after.get('visible_text', []))

        

        new_text = after_text - before_text

        

        if new_text:

            return f"Screen changed - new elements: {', '.join(list(new_text)[:3])}"

        

        return "Screen state changed"