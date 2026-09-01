from enum import Enum


class LifeSkill(Enum):
    # Combat (1000-1009)
    BRAWLING = 1000; PIERCING = 1001; SLASHING = 1002; BLUDGEONING = 1003
    DEFENCE = 1004; BLOCK = 1005; DODGE = 1006; PARRY = 1007; RUNNING = 1008
    # Magic (1030-1039)
    FIRE_MAGIC = 1030; WATER_MAGIC = 1031; AIR_MAGIC = 1032; EARTH_MAGIC = 1033
    LIGHT_MAGIC = 1034; SHADOW_MAGIC = 1035; ARCANE_MAGIC = 1036; FAE_MAGIC = 1037
    VOID_MAGIC = 1038; CREATION_MAGIC = 1039
    # Survival (1070-1078)
    RESTING = 1070; EATING = 1071; SLEEPING = 1072; MEDITATION = 1073
    TRACKING = 1074; FIRE_STARTING = 1075; SHELTER_BUILDING = 1076
    WATER_PROCUREMENT = 1077; WEATHER_READING = 1078
    # Specialized (1090-1095)
    DUAL_WIELDING = 1090; TWO_HANDED = 1091; SHIELD_USE = 1092
    ARCHERY = 1093; CROSSBOW = 1094; THROWING = 1095
    # Support/Stealth
    HEALING = 1100; STEALTH = 1120; LOCKPICKING = 1121
    # Craft/Knowledge (1130-1139)
    ALCHEMY = 1130; ENCHANTING = 1131; APPRAISAL = 1132; BLACKSMITHING = 1133
    TAILORING = 1134; CARPENTRY = 1135; JEWELCRAFTING = 1136; RUNECRAFT = 1137; FORGERY = 1138
    # Nurture (1140-1149)
    HERBALISM = 1140; ANIMAL_HANDLING = 1141; COOKING = 1142
    # Universal
    TOTAL_LIFE_XP = 1199
    # Social (1200-1211)
    PERSUASION = 1200; INTIMIDATION = 1201; DECEPTION = 1202; BARTER = 1203
    DIPLOMACY = 1204; SEDUCTION = 1205; PERFORMANCE = 1206; LEADERSHIP = 1210; PICKPOCKETING = 1211
    # Physical (1300-1306)
    WALKING = 1300; CLIMBING = 1301; SWIMMING = 1302; BALANCE = 1303
    LIFTING = 1304; ENDURANCE = 1305; ACROBATICS = 1306
    # Academic (1400-1410)
    LITERACY = 1400; WRITING = 1401; MATHEMATICS = 1402; HISTORY = 1403
    NATURAL_PHILOSOPHY = 1404; MAGICAL_THEORY = 1405; RESEARCH = 1406
    LANGUAGES = 1407; PHILOSOPHY = 1408; ETHICS = 1409; LAW = 1410
    # Domestic/Commercial/Care/Medical/Artistic/Tech/Agri/Spiritual/Nav/Gov
    CLEANING = 1500; LAUNDRY = 1501; HOUSEHOLD_MAINTENANCE = 1502; SEWING = 1503
    ORGANIZATION = 1504; FOOD_PRESERVATION = 1505
    SALES = 1600; ACCOUNTING = 1601; BOOKKEEPING = 1602; MERCHANDISING = 1603
    LOGISTICS = 1604; BUSINESS_MANAGEMENT = 1605
    INFANT_CARE = 1700; CHILDCARE = 1701; PARENTING = 1702; ELDER_CARE = 1703
    TEACHING = 1704; EMOTIONAL_SUPPORT = 1705
    ANATOMY = 1800; DIAGNOSIS = 1801; FIRST_AID = 1802; SURGERY = 1803; PHARMACOLOGY = 1804
    VISUAL_ART = 1900; MUSIC = 1901; DANCE = 1902; CREATIVE_WRITING = 1903; DISGUISE = 1904
    MECHANISMS = 2000; CONSTRUCTION_ENGINEERING = 2001; SIEGE_ENGINEERING = 2002; TRAP_DISARMING = 2003
    FARMING = 2100; LAND_CULTIVATION = 2101
    RITUAL = 2200; FAITH_PRACTICE = 2201
    WAYFINDING = 2300; CARTOGRAPHY = 2301
    STATECRAFT = 2400; INSTITUTIONAL_MANAGEMENT = 2401; PUBLIC_ADMINISTRATION = 2402

class LevelModule:
    def __init__(self):
        self.current_level = 1
        self.max_level = 100
        self.current_xp = 0.0
        self.required_xp = 100.0

    def startup(self, existing_save: dict = {}):
        self.from_dict(existing_save)

    def give_xp(self, amount: float):
        self.current_xp += amount
        while self.current_xp >= self.required_xp:
            self.current_xp -= self.required_xp
            self.current_level += 1
            self.required_xp *= 1.2

    def to_dict(self) -> dict:
        return {"current_level": self.current_level, "current_xp": self.current_xp, "required_xp": self.required_xp}

    def from_dict(self, saved: dict):
        if not saved: return
        self.current_level = saved.get("current_level", 1)
        self.current_xp = saved.get("current_xp", 0.0)
        self.required_xp = saved.get("required_xp", 100.0)

class LiteracyModule:
    def __init__(self):
        self.total_items_read = 0
        self.total_words_learned = 0
        self.reading_sessions = 0

    def startup(self, existing_save: dict = {}):
        self.from_dict(existing_save)

    def to_dict(self) -> dict:
        return {"total_items_read": self.total_items_read, "total_words_learned": self.total_words_learned, "reading_sessions": self.reading_sessions}

    def from_dict(self, saved: dict):
        if not saved: return
        self.total_items_read = saved.get("total_items_read", 0)
        self.total_words_learned = saved.get("total_words_learned", 0)
        self.reading_sessions = saved.get("reading_sessions", 0)

class ProfessionsModule:
    def __init__(self):
        self.professions = {}

    def startup(self, existing_save: dict = {}):
        self.from_dict(existing_save)

    def to_dict(self) -> dict:
        return {"professions": self.professions}

    def from_dict(self, saved: dict):
        if not saved: return
        self.professions = saved.get("professions", {}).copy()

class LifeSkills:
    def __init__(self):
        self.level_module = LevelModule()
        self.literacy = LiteracyModule()
        self.professions = ProfessionsModule()
        self.skills_dict: dict[LifeSkill, float] = {}
        self.total_life_xp = 0.0

    def startup(self, species, primary_element, secondary_element, existing_save: dict = {}):
        if existing_save:
            self.from_dict(existing_save)
        else:
            # Basic starting XP for baseline skills
            baseline_skills = [LifeSkill.WALKING, LifeSkill.CLIMBING, LifeSkill.RESTING, LifeSkill.LITERACY, LifeSkill.BARTER, LifeSkill.INTIMIDATION]
            for skill in baseline_skills:
                self.give_life_xp(skill, 5.0, species)

    def give_life_xp(self, skill: LifeSkill, amount: float, species):
        if skill == LifeSkill.TOTAL_LIFE_XP: return
        self.skills_dict[skill] = self.skills_dict.get(skill, 0.0) + amount
        self.total_life_xp += amount
        self.level_module.give_xp(amount)

    def to_dict(self) -> dict:
        return {
            "skills": self.skills_dict.copy(),
            "total": self.total_life_xp,
            "level": self.level_module.to_dict(),
            "literacy": self.literacy.to_dict(),
            "professions": self.professions.to_dict(),
        }

    def from_dict(self, saved: dict):
        if not saved: return
        self.skills_dict = saved.get("skills", {}).copy()
        self.total_life_xp = saved.get("total", 0.0)
        self.level_module.from_dict(saved.get("level", {}))
        self.literacy.from_dict(saved.get("literacy", {}))
        self.professions.from_dict(saved.get("professions", {}))
