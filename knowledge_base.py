import json
import os
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

@dataclass
class Experience:
    timestamp: str
    action: str
    target: str
    context: Dict[str, Any]
    result: Dict[str, Any]
    success: bool
    outcome_description: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class EnhancedKnowledgeBase:  # Fixed class name
    def __init__(self, knowledge_file: str = "sarah_enhanced_knowledge.json"):
        self.knowledge_file = knowledge_file
        self.experiences: List[Experience] = []
        self.working_apps: Set[str] = set()
        self.failed_apps: Set[str] = set()
        self.successful_strategies: Dict[str, List[str]] = {}
        self.app_opening_strategies: Dict[str, str] = {}
        self.browser_preferences: List[str] = []
        self.load_knowledge()

    def load_knowledge(self):  # Fixed method name
        """Load previous experiences from file"""
        try:
            if os.path.exists(self.knowledge_file):
                with open(self.knowledge_file, 'r') as f:
                    data = json.load(f)
                    for exp_data in data.get('experiences', []):
                        exp = Experience(**exp_data)
                        self.experiences.append(exp)
                    self.app_opening_strategies = data.get('app_opening_strategies', {})
                    self.browser_preferences = data.get('browser_preferences', [])
                    self._rebuild_knowledge()
                    print(f"🧠 Loaded {len(self.experiences)} experiences")
        except Exception as e:
            print(f"⚠️ Could not load knowledge: {e}")

    def save_knowledge(self):  # Fixed method name
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

    def add_experience(self, experience: Experience):  # Fixed method name
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
                
                context_info = exp.context.get('additional_info', {})
                if context_info and 'successful_strategy' in context_info:
                    self.app_opening_strategies[exp.target] = context_info['successful_strategy']
                
                if self._is_browser(exp.target):
                    if exp.target not in self.browser_preferences:
                        self.browser_preferences.insert(0, exp.target)
            else:
                self.failed_apps.add(exp.target)

    def _is_browser(self, app_name: str) -> bool:
        """Check if app is likely a browser"""
        browsers = ['chrome', 'firefox', 'edge', 'browser', 'safari', 'opera']
        return any(browser in app_name.lower() for browser in browsers)

    def get_knowledge_summary(self) -> str:  # Fixed method name
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