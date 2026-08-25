from typing import Any, Dict, List, Optional

class SocialModule:
    def __init__(self):
        self.relationships: Dict[int, float] = {}

    def startup(self, existing_save: Dict = {}):
        self.from_dict(existing_save)

    def get_reputation(self, other_uid: int) -> float:
        return self.relationships.get(other_uid, 0.0)

    def to_dict(self) -> Dict:
        return {"relationships": self.relationships.copy()}

    def from_dict(self, saved: Dict):
        if not saved: return
        self.relationships = saved.get("relationships", {}).copy()

class FactionModule:
    def __init__(self):
        self.reputations: Dict[int, float] = {}
        self.current_faction = -1

    def startup(self, existing_save: Dict = {}):
        self.from_dict(existing_save)

    def get_reputation(self, faction_id: int) -> float:
        return self.reputations.get(faction_id, 0.0)

    def to_dict(self) -> Dict:
        return {
            "reputations": self.reputations.copy(),
            "current_faction": self.current_faction
        }

    def from_dict(self, saved: Dict):
        if not saved: return
        self.reputations = saved.get("reputations", {}).copy()
        self.current_faction = saved.get("current_faction", -1)

class SocialState:
    def __init__(self):
        self.social = SocialModule()
        self.faction = FactionModule()

    def startup(self, existing_save: Dict = {}):
        self.social.startup(existing_save.get("social", {}))
        self.faction.startup(existing_save.get("faction", {}))

    def resolve_hostility(self, other_uid: int, other_faction_id: int, my_faction_id: int) -> bool:
        if other_uid in self.social.relationships:
            return self.social.get_reputation(other_uid) < 0.0

        if other_faction_id in self.faction.reputations:
            return self.faction.get_reputation(other_faction_id) < 0.0

        # Fallback to a static DB check (would be implemented in a separate DB module)
        return False 

    def to_dict(self) -> Dict:
        return {
            "social": self.social.to_dict(),
            "faction": self.faction.to_dict(),
        }

    def from_dict(self, saved: Dict):
        if not saved: return
        self.social.from_dict(saved.get("social", {}))
        self.faction.from_dict(saved.get("faction", {}))
