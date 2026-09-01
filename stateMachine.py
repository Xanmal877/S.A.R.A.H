# ===============================
# STATE MACHINE (Direct Port)
# ===============================

import glob
import os
import random
from datetime import datetime

import psutil
import requests


class StateMachine:
    def __init__(self, agent=None):
        self.agent = agent
        self.currentState = None
        self.isProcessingState = False

    async def HandleState(self):
        pass

    def SetTask(self, taskName: str):
        if hasattr(self.agent, 'currentTask') and taskName == self.agent.currentTask:
            return
        if self.agent:
            self.agent.currentTask = taskName


class IdleState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def dream(self):
        energy = self.agent.personalityModule.energy
        nature = self.agent.personalityModule.nature
        if energy > 70:
            phrase = "vibrant landscapes and fast-paced rhythms" if nature > 50 else "complex architectural blueprints"
        elif energy < 30:
            phrase = "quiet whispers and soft colors" if nature > 50 else "deep, silent voids of logic"
        else:
            phrase = "floating through a sea of data" if nature > 50 else "solving a recursive equation"
        print(f"[Idle] dream: \"{phrase}\"")

    async def log_internal_state(self):
        char = self.agent.character
        pm = self.agent.personalityModule
        planning = pm.planningTendency
        if planning > 0.7:
            stats = f"HP:{char.health:.1f}, SP:{char.stamina:.1f}, MP:{char.mana:.1f} | Type:{pm.personalityType} | Risk:{pm.riskTolerance:.2f}"
        else:
            stats = f"System stability nominal. Personality: {pm.personalityType}"
        print(f"[Idle] log_internal_state: \"{stats}\"")

    async def observe_environment(self):
        now = datetime.now().strftime("%H:%M:%S")
        load = psutil.cpu_percent()
        mind = self.agent.personalityModule.mind
        if mind > 70:
            interpretation = f"The digital ether is {'surging' if load > 50 else 'serene'} at {now}."
        else:
            interpretation = f"Time: {now}, CPU Load: {load}%"
        print(f"[Idle] observe_environment: \"{interpretation}\"")

    async def HandleState(self, action_name=None):
        self.agent.isProcessingState = True
        if action_name and hasattr(self, action_name) and callable(getattr(self, action_name)):
            method = getattr(self, action_name)
        else:
            method = random.choice([self.dream, self.log_internal_state, self.observe_environment])
        
        await method()
        self.agent.isProcessingState = False

class WorkState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def perform_health_check(self):
        planning = self.agent.personalityModule.planningTendency
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        if planning > 0.7:
            result = f"CPU: {cpu}%, RAM: {ram}%, Disk: {disk}% - All systems within operational parameters."
        else:
            result = "System health check: Nominal."
        print(f"[Work] perform_health_check: \"{result}\"")

    async def scan_for_tasks(self):
        risk = self.agent.personalityModule.riskTolerance
        tasks = []
        # Search for .todo files
        for todo_file in glob.glob("**/*.todo", recursive=True):
            tasks.append(f"File: {todo_file}")
        
        # Search for TODO in .py files
        search_pattern = "**/*.py" if risk > 0.5 else "*.py"
        for py_file in glob.glob(search_pattern, recursive=(risk > 0.5)):
            try:
                with open(py_file, 'r', errors='ignore') as f:
                    if "TODO" in f.read():
                        tasks.append(f"Code: {py_file}")
            except Exception:
                pass
        
        result = ", ".join(tasks) if tasks else "No pending tasks found in workspace."
        print(f"[Work] scan_for_tasks: \"{result}\"")

    async def tidy_workspace(self):
        planning = self.agent.personalityModule.planningTendency
        empty_dirs = []
        temp_files = []
        for root, dirs, files in os.walk("."):
            for d in dirs:
                full_path = os.path.join(root, d)
                if not os.listdir(full_path):
                    empty_dirs.append(full_path)
            for f in files:
                if f.endswith(".tmp") or f.startswith("temp_"):
                    temp_files.append(os.path.join(root, f))
        
        if planning > 0.7:
            result = f"Cleaned empty dirs: {empty_dirs}, Removed temps: {temp_files}"
        else:
            result = "Workspace looks tidy enough." if not empty_dirs and not temp_files else "Some clutter detected and noted."
        print(f"[Work] tidy_workspace: \"{result}\"")

    async def HandleState(self, action_name=None):
        self.agent.isProcessingState = True
        if action_name and hasattr(self, action_name) and callable(getattr(self, action_name)):
            method = getattr(self, action_name)
        else:
            method = random.choice([self.perform_health_check, self.scan_for_tasks, self.tidy_workspace])
        
        await method()
        self.agent.isProcessingState = False

class ExploreState(StateMachine):
    def __init__(self, agent=None):
        super().__init__(agent)

    async def discover_files(self):
        py_files = []
        for root, _dirs, files in os.walk("."):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        if not py_files:
            print("[Explore] discover_files: \"No python files found to explore.\"")
            return

        target = random.choice(py_files)
        try:
            with open(target, 'r', errors='ignore') as f:
                first_line = f.readline().strip()
                result = f"Discovered {target} - Header: {first_line}"
        except Exception as e:
            result = f"Failed to explore {target}: {e}"
        print(f"[Explore] discover_files: \"{result}\"")

    async def fetch_random_fact(self):
        mind = self.agent.personalityModule.mind
        try:
            if mind > 50: # Intuitive -> cat facts
                resp = requests.get("https://catfact.ninja/fact", timeout=2)
                fact = resp.json().get('fact', 'No fact found')
            else: # Sensing -> number facts
                resp = requests.get("http://numbersapi.com/random", timeout=2)
                fact = resp.text
            result = fact
        except Exception as e:
            result = f"Could not fetch fact: {e}"
        print(f"[Explore] fetch_random_fact: \"{result}\"")

    async def analyze_logs(self):
        confidence = self.agent.personalityModule.decisionConfidence
        log_file = "agent.log"
        if not os.path.exists(log_file):
            result = "No agent logs available for analysis."
        else:
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    last_20 = "".join(lines[-20:])
                    if confidence > 0.7:
                        result = f"High confidence analysis of logs: {last_20.strip()}"
                    else:
                        result = f"Tentative analysis of logs: {last_20.strip()[:100]}..."
            except Exception as e:
                result = f"Error reading logs: {e}"
        print(f"[Explore] analyze_logs: \"{result}\"")

    async def HandleState(self, action_name=None):
        self.agent.isProcessingState = True
        if action_name and hasattr(self, action_name) and callable(getattr(self, action_name)):
            method = getattr(self, action_name)
        else:
            method = random.choice([self.discover_files, self.fetch_random_fact, self.analyze_logs])
        
        await method()
        self.agent.isProcessingState = False
