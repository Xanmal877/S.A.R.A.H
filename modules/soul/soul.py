from enum import Enum, auto
from typing import Any


class ResourceEnum(Enum):
    NONE = auto()
    HEALTH = auto()
    STAMINA = auto()
    MANA = auto()
    XP = auto()
    COIN_CURRENCY = auto()

class Species(Enum):
    HUMAN = auto()
    ELF = auto()
    HALF_ELF = auto()
    DWARF = auto()
    GNOME = auto()
    NEKOJIN = auto()
    KITSUNE = auto()
    FOXKIN = auto()
    GOBLIN = auto()
    WATER_SPIRIT = auto()
    BEAST = auto()
    OTHER = auto()
    TRAVELER = auto()

class Elements(Enum):
    NONE = auto()
    PHYSICAL = auto()
    ARCANE = auto()
    FIRE = auto()
    WATER = auto()
    AIR = auto()
    EARTH = auto()
    ICE = auto()
    LIGHTNING = auto()
    LIGHT = auto()
    SHADOW = auto()
    VOID = auto()
    CREATION = auto()
    FAE = auto()

class SoulModulesEnum(Enum):
    PARTY = auto()
    SOCIAL_STATE = auto()
    VITALS = auto()
    LIFESKILLS = auto()
    MENTAL_STATE = auto()
    EXPLORATION = auto()
    SOUL_DATA = auto()

class SoulEnum(Enum):
    NONE = auto()
    UID = auto()
    NAME = auto()
    DESCRIPTION = auto()
    ICON = auto()
    CURRENT_HEALTH = auto()
    CURRENT_STAMINA = auto()
    CURRENT_MANA = auto()
    CURRENT_FORM = auto()
    SPECIES = auto()
    GENDER = auto()
    AGE = auto()
    PRIMARY_ELEMENT = auto()
    SECONDARY_ELEMENT = auto()
    CURRENT_LOCATION = auto()
    INVENTORY = auto()
    EQUIPPED = auto()
    ACTIVE_EFFECTS = auto()
    GENERATED = auto()
    ONLINE = auto()
    DEAD = auto()
    INFLUENCE = auto()
    PERMADEATH = auto()
    SOUL_MODULE_DICTS = auto()

class SoulData:
    def __init__(self):
        self.soulModuleDicts: dict[SoulModulesEnum, dict] = {
            SoulModulesEnum.SOUL_DATA: {},
            SoulModulesEnum.PARTY: {},
            SoulModulesEnum.SOCIAL_STATE: {},
            SoulModulesEnum.VITALS: {},
            SoulModulesEnum.LIFESKILLS: {},
            SoulModulesEnum.MENTAL_STATE: {},
            SoulModulesEnum.EXPLORATION: {},
        }
        
        self.soulDataDict: dict[SoulEnum, Any] = {
            SoulEnum.UID: -1,
            SoulEnum.NAME: "",
            SoulEnum.DESCRIPTION: "",
            SoulEnum.ICON: "",
            SoulEnum.GENDER: 0,
            SoulEnum.SPECIES: Species.HUMAN,
            SoulEnum.AGE: 18,
            SoulEnum.CURRENT_FORM: "",
            SoulEnum.CURRENT_LOCATION: (0.0, 0.0, 0.0),
            SoulEnum.INVENTORY: [],
            SoulEnum.EQUIPPED: {},
            SoulEnum.ACTIVE_EFFECTS: {},
            SoulEnum.CURRENT_HEALTH: 0.0,
            SoulEnum.CURRENT_STAMINA: 0.0,
            SoulEnum.CURRENT_MANA: 0.0,
            SoulEnum.PRIMARY_ELEMENT: Elements.NONE,
            SoulEnum.SECONDARY_ELEMENT: Elements.NONE,
            SoulEnum.GENERATED: False,
            SoulEnum.ONLINE: False,
            SoulEnum.DEAD: False,
            SoulEnum.PERMADEATH: False,
            SoulEnum.SOUL_MODULE_DICTS: self.soulModuleDicts,
            SoulEnum.INFLUENCE: 0.0,
        }

    @property
    def uid(self) -> int:
        return self.soulDataDict.get(SoulEnum.UID, -1)
    
    @uid.setter
    def uid(self, value: int):
        self.soulDataDict[SoulEnum.UID] = value

    @property
    def soul_name(self) -> str:
        return self.soulDataDict.get(SoulEnum.NAME, "")
    
    @soul_name.setter
    def soul_name(self, value: str):
        self.soulDataDict[SoulEnum.NAME] = value

    @property
    def description(self) -> str:
        return self.soulDataDict.get(SoulEnum.DESCRIPTION, "")
    
    @description.setter
    def description(self, value: str):
        self.soulDataDict[SoulEnum.DESCRIPTION] = value

    @property
    def species(self) -> Species:
        return self.soulDataDict.get(SoulEnum.SPECIES, Species.HUMAN)
    
    @species.setter
    def species(self, value: Species):
        self.soulDataDict[SoulEnum.SPECIES] = value

    @property
    def age(self) -> int:
        return self.soulDataDict.get(SoulEnum.AGE, 18)
    
    @age.setter
    def age(self, value: int):
        self.soulDataDict[SoulEnum.AGE] = value

    @property
    def current_health(self) -> float:
        return self.soulDataDict.get(SoulEnum.CURRENT_HEALTH, 0.0)
    
    @current_health.setter
    def current_health(self, value: float):
        self.soulDataDict[SoulEnum.CURRENT_HEALTH] = value

    @property
    def primary_element(self) -> Elements:
        return self.soulDataDict.get(SoulEnum.PRIMARY_ELEMENT, Elements.NONE)
    
    @primary_element.setter
    def primary_element(self, value: Elements):
        self.soulDataDict[SoulEnum.PRIMARY_ELEMENT] = value

class Soul:
    def __init__(self, character_id: str = "sarah"):
        self.character_id = character_id
        self.soul_data = SoulData()
        # Modules (Equivalent to the GD setup)
        from .detection_module import DetectionModule
        from .exploration_module import ExplorationModule
        from .identity_state.identity_state import get_identity_state
        from .life_skills.life_skills import LifeSkills
        from .mental_state.mental_state import MentalState
        from .party_module import PartyModule
        from .social_state.social_state import SocialState

        self.mental_state = MentalState()
        self.social_state = SocialState()
        self.life_skills = LifeSkills()
        self.exploration = ExplorationModule(self.soul_data)
        self.party = PartyModule(self.soul_data)
        self.detection = DetectionModule()

        # Opinions/interests/dislikes/relationship notes/goals - the facts
        # that make this character who they are, independent of which LLM is
        # reasoning about them. Pulled from the same per-character registry
        # identity_tools.py resolves via active_character_id (see
        # identity_state.py), so a tool call and this Soul's world-state
        # summary always agree on whose identity they're reading/writing.
        self.identity = get_identity_state(character_id)

        # Restore mood/needs/drives from the last run instead of resetting
        # to defaults every process start (see modules/soul/persistence.py).
        # mbti (the personality baseline) gets overwritten right after this
        # by SetupPersonality() in agents/*.py - that's intentional, mbti is
        # treated as static configuration, not state that drifts and persists.
        from .persistence import load_mental_state
        self.mental_state.startup(is_generated=False, existing_save=load_mental_state(character_id))

    @property
    def uid(self) -> int:
        return self.soul_data.uid
    
    @property
    def soul_name(self) -> str:
        return self.soul_data.soul_name
    
    @soul_name.setter
    def soul_name(self, value: str):
        self.soul_data.soul_name = value

    @property
    def species(self) -> Species:
        return self.soul_data.species
    
    @species.setter
    def species(self, value: Species):
        self.soul_data.species = value

    @property
    def age(self) -> int:
        return self.soul_data.age
    
    @age.setter
    def age(self, value: int):
        self.soul_data.age = value

    def __repr__(self):
        return f"<Soul {self.soul_name} ({self.species.name}, Age: {self.age})>"
