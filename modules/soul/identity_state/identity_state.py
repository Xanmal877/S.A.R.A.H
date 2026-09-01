import contextvars
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("IdentityState")

def _default_state_path(character_id: str) -> str:
    return os.path.expanduser(f"~/.sarah/state/{character_id}/identity_state.json")


class IdentityState:
    """
    A character's persistent opinions, interests, dislikes, relationship
    notes, and goals - the structured facts an LLM should read and act on
    each turn, not improvise from scratch. Owned by Soul, independent of
    whichever model is currently doing the reasoning, and survives process
    restarts (~/.sarah/state/{character_id}/identity_state.json).
    """

    def __init__(self, storage_path: str = None, character_id: str = "sarah"):
        self.storage_path = storage_path or _default_state_path(character_id)
        self.opinions = {}          # topic -> {opinion, reasoning, updated_at}
        self.interests = []
        self.dislikes = []
        self.relationship_notes = []  # [{note, timestamp}]
        self.goals = []               # [{goal, status, created_at}]
        self._load()

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load identity state from {self.storage_path}: {e}")
            return
        self.opinions = saved.get("opinions", {})
        self.interests = saved.get("interests", [])
        self.dislikes = saved.get("dislikes", [])
        self.relationship_notes = saved.get("relationship_notes", [])
        self.goals = saved.get("goals", [])

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning(f"Could not save identity state to {self.storage_path}: {e}")

    def form_opinion(self, topic: str, opinion: str, reasoning: str = ""):
        self.opinions[topic] = {
            "opinion": opinion,
            "reasoning": reasoning,
            "updated_at": datetime.now().isoformat(),
        }
        self._save()

    def get_opinion(self, topic: str):
        return self.opinions.get(topic)

    def add_interest(self, interest: str):
        if interest not in self.interests:
            self.interests.append(interest)
            self._save()

    def add_dislike(self, dislike: str):
        if dislike not in self.dislikes:
            self.dislikes.append(dislike)
            self._save()

    def add_relationship_note(self, note: str):
        self.relationship_notes.append({"note": note, "timestamp": datetime.now().isoformat()})
        self._save()

    def add_goal(self, goal: str):
        self.goals.append({"goal": goal, "status": "active", "created_at": datetime.now().isoformat()})
        self._save()

    def complete_goal(self, goal: str) -> bool:
        for g in self.goals:
            if g["goal"] == goal and g["status"] == "active":
                g["status"] = "done"
                self._save()
                return True
        return False

    def summary(self, max_opinions: int = 5, max_notes: int = 5) -> str:
        parts = []
        if self.interests:
            parts.append("Interests: " + ", ".join(self.interests))
        if self.dislikes:
            parts.append("Dislikes: " + ", ".join(self.dislikes))
        if self.opinions:
            recent = list(self.opinions.items())[-max_opinions:]
            parts.append("Recent opinions: " + "; ".join(f"{t}: {d['opinion']}" for t, d in recent))
        active_goals = [g["goal"] for g in self.goals if g["status"] == "active"]
        if active_goals:
            parts.append("Active goals: " + ", ".join(active_goals))
        if self.relationship_notes:
            recent_notes = [n["note"] for n in self.relationship_notes[-max_notes:]]
            parts.append("Relationship notes: " + "; ".join(recent_notes))
        return "\n".join(parts) if parts else "(no stored opinions/interests/goals yet)"

    def to_dict(self) -> dict:
        return {
            "opinions": self.opinions,
            "interests": self.interests,
            "dislikes": self.dislikes,
            "relationship_notes": self.relationship_notes,
            "goals": self.goals,
        }


# Registry of one IdentityState per character, keyed by character_id, so
# tool calls (which don't get a handle to the live agent/Soul object - see
# modules/tools/executor.py) can look up the *right* character's identity
# instead of always sharing one. active_character_id is a contextvar (not a
# plain global) so concurrent asyncio tasks - e.g. Sarah's and Tama's
# reasoning loops running side by side - each see their own value instead of
# racing on a shared one; ToolOrchestrator.process_request sets it from
# self.agent.character_id before running a character's tool-call loop.
_identity_states: dict[str, "IdentityState"] = {}
active_character_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "active_character_id", default="sarah"
)


def get_identity_state(character_id: str = "sarah") -> "IdentityState":
    if character_id not in _identity_states:
        _identity_states[character_id] = IdentityState(character_id=character_id)
    return _identity_states[character_id]


# Backward-compatible singleton - Sarah's identity, sourced from the same
# registry so it's not a second, divergent instance.
identity_state = get_identity_state("sarah")
