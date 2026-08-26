from typing import Dict

class NeedsModule:
    def __init__(self):
        self.hunger = 0.5
        self.thirst = 0.5
        self.fatigue = 0.5
        self.bladder = 0.5
        self.warmth = 0.5
        self.comfort = 0.5
        self.hygiene = 0.5
        self.pain = 0.0
        self.sanity = 1.0
        self.morale = 0.5
        self.boredom = 0.0
        self.loneliness = 0.0
        self.toxicity = 0.0
        self.corruption = 0.0
        self.exhaustion = 0.0

    # Per-second drift applied by tick(). Positive values rise toward 1.0
    # (needs building up), negative values fall toward 0.0 (upkeep decaying).
    # Ported from Autumn's Dungeoneering (NeedsModule.gd).
    TICK_RATES = {
        "hunger": 0.0008, "thirst": 0.0012,
        "fatigue": 0.0005, "bladder": 0.0010,
        "warmth": -0.0003, "comfort": -0.0002,
        "hygiene": -0.0002, "pain": -0.0010,
        "sanity": 0.0001, "morale": 0.0,
        "boredom": 0.0006, "loneliness": 0.0004,
        "toxicity": -0.0005, "corruption": -0.00005,
        "exhaustion": 0.0002,
    }

    def startup(self, existing_save: Dict = {}):
        self.from_dict(existing_save)

    def tick(self, delta: float):
        for key, rate in self.TICK_RATES.items():
            value = getattr(self, key) + rate * delta
            setattr(self, key, max(0.0, min(1.0, value)))

    def to_dict(self) -> Dict:
        return {
            "hunger": self.hunger, "thirst": self.thirst, "fatigue": self.fatigue,
            "bladder": self.bladder, "warmth": self.warmth, "comfort": self.comfort,
            "hygiene": self.hygiene, "pain": self.pain, "sanity": self.sanity,
            "morale": self.morale, "boredom": self.boredom, "loneliness": self.loneliness,
            "toxicity": self.toxicity, "corruption": self.corruption, "exhaustion": self.exhaustion,
        }

    def from_dict(self, saved: Dict):
        if not saved: return
        for key, value in saved.items():
            if hasattr(self, key):
                setattr(self, key, value)

class DrivesModule:
    def __init__(self):
        self.stress = 0.0
        self.anxiety = 0.0
        self.social_need = 0.5
        self.recreation = 0.5
        self.purpose = 0.5
        self.spirituality = 0.5
        self.aggression = 0.5
        self.retreat = 0.5
        self.social = 0.5
        self.rest = 0.5
        self.explore = 0.5
        self.focus = 0.5

    # Per-second drift applied to the psychological inputs by tick().
    # Ported from Autumn's Dungeoneering (DrivesModule.gd).
    TICK_RATES = {
        "stress": -0.0004,
        "anxiety": -0.0003,
        "social_need": 0.0003,
        "recreation": 0.0002,
        "purpose": 0.0001,
        "spirituality": 0.00005,
    }

    def startup(self, existing_save: Dict = {}, needs=None, mbti=None):
        self.from_dict(existing_save)
        self.calculate_all(needs, mbti)

    def tick(self, delta: float, needs=None, mbti=None):
        for key, rate in self.TICK_RATES.items():
            value = getattr(self, key) + rate * delta
            setattr(self, key, max(0.0, min(1.0, value)))
        self.calculate_all(needs, mbti)

    def to_dict(self) -> Dict:
        return self.__dict__.copy()

    @staticmethod
    def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    def calculate_all(self, needs, mbti=None):
        """Derive behavioral-output drives from needs + personality.
        This is what makes personality affect *what Sarah wants to do*,
        not just how she phrases it (see agents/sarah_identity.md)."""
        if needs is None:
            return
        self.aggression = self.calculate_aggression(needs)
        self.retreat = self.calculate_retreat(needs)
        self.social = self.calculate_social(needs)
        self.rest = self.calculate_rest(needs)
        self.explore = self.calculate_explore(needs, mbti)
        self.focus = self.calculate_focus(needs)

    def calculate_aggression(self, needs) -> float:
        pos = self.stress * 0.003 + (1.0 - needs.sanity) * 0.005
        if needs.morale > 0.5:
            pos += (needs.morale - 0.5) * 0.4
        neg = self.anxiety * 0.004 + needs.pain * 0.002 + needs.fatigue * 0.003
        if needs.morale < 0.5:
            neg += (0.5 - needs.morale) * 0.3
        return self._clamp(pos - neg)

    def calculate_retreat(self, needs) -> float:
        pos = self.anxiety * 0.005 + needs.pain * 0.004 + self.stress * 0.002 + needs.corruption * 0.003
        neg = needs.sanity * 0.002
        if needs.morale < 0.5:
            pos += (0.5 - needs.morale) * 0.4
        if needs.morale > 0.5:
            neg += (needs.morale - 0.5) * 0.3
        return self._clamp(pos - neg)

    def calculate_social(self, needs) -> float:
        pos = needs.loneliness * 0.004 + needs.boredom * 0.003
        if needs.morale > 0.5:
            pos += (needs.morale - 0.5) * 0.2
        neg = self.anxiety * 0.003 + self.stress * 0.002 + needs.fatigue * 0.002 + (1.0 - needs.sanity) * 0.003
        return self._clamp(pos - neg)

    def calculate_rest(self, needs) -> float:
        pos = needs.fatigue * 0.15 + needs.hunger * 0.1 + needs.thirst * 0.1 + needs.pain * 0.1 + needs.exhaustion * 0.2
        neg = self.stress * 0.05 + needs.boredom * 0.1
        return self._clamp(pos - neg)

    def calculate_explore(self, needs, mbti=None) -> float:
        """Curiosity/exploration drive. `mbti.mind` (intuition) is Sarah's
        chaos-mind associative-thinking trait - the more intuitive she is,
        the more this drive pulls her toward investigating on her own."""
        pos = needs.boredom * 0.5
        if mbti is not None:
            curiosity = (mbti.mind - 50) / 50.0
            if curiosity > 0:
                pos += curiosity * 0.15
        if needs.fatigue < 0.3:
            pos += (0.3 - needs.fatigue) * 0.15
        neg = self.anxiety * 0.15 + self.stress * 0.15 + needs.pain * 0.15
        if needs.fatigue > 0.5:
            neg += (needs.fatigue - 0.5) * 0.4
        return self._clamp(pos - neg)

    def calculate_focus(self, needs) -> float:
        pos = needs.sanity * 0.003
        if self.stress < 0.3:
            pos += (0.3 - self.stress) * 0.2
        neg = (1.0 - needs.sanity) * 0.004 + needs.fatigue * 0.003 + needs.pain * 0.002 + self.anxiety * 0.003
        if self.stress > 0.5:
            neg += (self.stress - 0.5) * 0.3
        return self._clamp(pos - neg)

    def get_summary(self, name: str = "") -> str:
        return (
            f"=== DRIVES FOR {name} ===\n"
            f"Aggression: {self.aggression:.2f}\n"
            f"Retreat:    {self.retreat:.2f}\n"
            f"Social:     {self.social:.2f}\n"
            f"Rest:       {self.rest:.2f}\n"
            f"Explore:    {self.explore:.2f}\n"
            f"Focus:      {self.focus:.2f}\n"
        )

    def from_dict(self, saved: Dict):
        if not saved: return
        for key, value in saved.items():
            if hasattr(self, key):
                setattr(self, key, value)

class MBTIModule:
    def __init__(self):
        self.energy = 50
        self.mind = 50
        self.nature = 50
        self.tactics = 50
        self.identity = 50
        self.confidence = 1.0
        self.risk_tolerance = 0.5
        self.empathy = 0.5
        self.patience = 0.5

    def startup(self, existing_save: Dict = {}):
        self.from_dict(existing_save)

    def to_dict(self) -> Dict:
        return self.__dict__.copy()

    def from_dict(self, saved: Dict):
        if not saved: return
        for key, value in saved.items():
            if hasattr(self, key):
                setattr(self, key, value)

class EnneagramModule:
    def __init__(self):
        self.type = "NONE"
        self.values = {}

    def startup(self, is_generated: bool, existing_save: Dict = {}):
        self.from_dict(existing_save)

    def to_dict(self) -> Dict:
        return {"type": self.type, "values": self.values}

    def from_dict(self, saved: Dict):
        if not saved: return
        self.type = saved.get("type", "NONE")
        self.values = saved.get("values", {})

class MentalState:
    def __init__(self):
        self.needs = NeedsModule()
        self.drives = DrivesModule()
        self.mbti = MBTIModule()
        self.enneagram = EnneagramModule()

    def startup(self, is_generated: bool, existing_save: Dict = {}):
        self.needs.startup(existing_save.get("needs", {}))
        self.mbti.startup(existing_save.get("mbti", {}))
        self.enneagram.startup(is_generated, existing_save.get("enneagram", {}))
        self.drives.startup(existing_save.get("drives", {}), self.needs, self.mbti)

    def tick(self, delta: float):
        self.needs.tick(delta)
        self.drives.tick(delta, self.needs, self.mbti)

    def to_dict(self) -> Dict:
        return {
            "needs": self.needs.to_dict(),
            "drives": self.drives.to_dict(),
            "mbti": self.mbti.to_dict(),
            "enneagram": self.enneagram.to_dict(),
        }

    def from_dict(self, saved: Dict):
        if not saved: return
        self.needs.from_dict(saved.get("needs", {}))
        self.drives.from_dict(saved.get("drives", {}))
        self.mbti.from_dict(saved.get("mbti", {}))
        self.enneagram.from_dict(saved.get("enneagram", {}))
