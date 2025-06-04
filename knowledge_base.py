import json

import os

from typing import Dict, List, Optional, Tuple, Any, Set

from dataclasses import dataclass, asdict  # Added asdict import

from pathlib import Path

from datetime import datetime



@dataclass

class Experience:

    """A single learning experience"""

    timestamp: str

    action: str

    target: str

    context: Dict[str, Any]  # What was on screen before

    result: Dict[str, Any]   # What happened after

    success: bool

    outcome_description: str

    confidence: float = 1.0  # How confident we are in this experience



    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)



class EnhancedKnowledgeBase:

    """Sarah's enhanced experiential knowledge system"""

    

    def __init__(self, knowledge_file: str = "sarah_enhanced_knowledge.json"):

        self.knowledge_file = knowledge_file

        self.experiences: List[Experience] = []

        self.working_apps: Set[str] = set()

        self.failed_apps: Set[str] = set()

        self.successful_strategies: Dict[str, List[str]] = {}

        self.app_opening_strategies: Dict[str, str] = {}  # App -> successful strategy

        self.browser_preferences: List[str] = []  # Ordered list of working browsers

        self.load_knowledge()

    

    def load_knowledge(self):

        """Load previous experiences from file"""

        try:

            if os.path.exists(self.knowledge_file):

                with open(self.knowledge_file, 'r') as f:

                    data = json.load(f)

                    

                    # Load experiences

                    for exp_data in data.get('experiences', []):

                        exp = Experience(**exp_data)

                        self.experiences.append(exp)

                    

                    # Load cached knowledge

                    self.app_opening_strategies = data.get('app_opening_strategies', {})

                    self.browser_preferences = data.get('browser_preferences', [])

                    

                    # Rebuild derived knowledge from experiences

                    self._rebuild_knowledge()

                    

                    print(f"🧠 Loaded {len(self.experiences)} experiences")

                    if self.working_apps:

                        print(f"✅ Known working apps: {', '.join(list(self.working_apps)[:5])}")

                    if self.browser_preferences:

                        print(f"🌐 Browser preference order: {', '.join(self.browser_preferences)}")

        except Exception as e:

            print(f"⚠️ Could not load knowledge: {e}")

    

    def save_knowledge(self):

        """Save experiences to file"""

        try:

            data = {

                'experiences': [exp.to_dict() for exp in self.experiences],

                'app_opening_strategies': self.app_opening_strategies,

                'browser_preferences': self.browser_preferences,

                'last_updated': datetime.now().isoformat(),

                'total_experiences': len(self.experiences)

            }

            with open(self.knowledge_file, 'w') as f:

                json.dump(data, f, indent=2)

        except Exception as e:

            print(f"⚠️ Could not save knowledge: {e}")

    

    def add_experience(self, experience: Experience):

        """Add new experience and update knowledge"""

        self.experiences.append(experience)

        self._update_knowledge_from_experience(experience)

        self.save_knowledge()

    

    def _rebuild_knowledge(self):

        """Rebuild derived knowledge from all experiences"""

        self.working_apps.clear()

        self.failed_apps.clear()

        self.successful_strategies.clear()

        

        for exp in self.experiences:

            self._update_knowledge_from_experience(exp, save=False)

    

    def _update_knowledge_from_experience(self, exp: Experience, save: bool = True):

        """Update knowledge based on single experience"""

        if exp.action in ["try_open_app", "experiment_app"]:

            if exp.success and exp.result.get('goal_achieved', False):

                self.working_apps.add(exp.target)

                self.failed_apps.discard(exp.target)

                

                # Remember successful strategy from context additional_info

                context_info = exp.context.get('additional_info', {})

                if context_info and 'successful_strategy' in context_info:

                    self.app_opening_strategies[exp.target] = context_info['successful_strategy']

                

                # If it's a browser, add to browser preferences

                if self._is_browser(exp.target):

                    if exp.target not in self.browser_preferences:

                        self.browser_preferences.insert(0, exp.target)  # Add to front

            else:

                self.failed_apps.add(exp.target)

        

        # Learn successful strategies for goals

        if exp.success and 'goal' in exp.context:

            goal = exp.context['goal'].lower()

            if goal not in self.successful_strategies:

                self.successful_strategies[goal] = []

            

            strategy = f"{exp.action}:{exp.target}"

            if strategy not in self.successful_strategies[goal]:

                self.successful_strategies[goal].append(strategy)

    

    def _is_browser(self, app_name: str) -> bool:

        """Check if app is likely a browser"""

        browsers = ['chrome', 'firefox', 'edge', 'browser', 'safari', 'opera']

        return any(browser in app_name.lower() for browser in browsers)

    

    def get_best_browser(self) -> Optional[str]:

        """Get the best known working browser"""

        for browser in self.browser_preferences:

            if browser in self.working_apps:

                return browser

        return None

    

    def get_youtube_strategy(self) -> List[Tuple[str, str]]:

        """Get best strategy for opening YouTube based on experience"""

        strategies = []

        

        # If we know YouTube works directly

        if 'youtube' in self.working_apps:

            strategies.append(('try_open_app', 'youtube'))

        

        # Try browsers in preference order

        for browser in self.browser_preferences:

            if browser in self.working_apps:

                strategies.append(('open_browser_then_youtube', browser))

        

        # Fallback to common browsers

        common_browsers = ['chrome', 'firefox', 'edge']

        for browser in common_browsers:

            if browser not in [s[1] for s in strategies]:

                strategies.append(('try_open_app', browser))

        

        return strategies

    

    def get_knowledge_summary(self) -> str:

        """Get human-readable summary of current knowledge"""

        summary = []

        summary.append(f"Total experiences: {len(self.experiences)}")

        

        if self.working_apps:

            summary.append(f"Working apps: {', '.join(sorted(self.working_apps))}")

        

        if self.browser_preferences:

            summary.append(f"Preferred browsers: {', '.join(self.browser_preferences)}")

        

        if self.failed_apps:

            summary.append(f"Failed apps: {', '.join(sorted(self.failed_apps))}")

        

        return "\n".join(summary)