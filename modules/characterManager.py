# ===============================
# CHARACTER MANAGER (Direct Port)
# ===============================

class CharacterManager:
    def __init__(self, agent=None):
        self.agent = agent
        
        self.charName = ""
        self.description = ""
        self.level = 1
        
        # Stats
        self.strength = 10
        self.dexterity = 10
        self.intelligence = 10
        self.wisdom = 10
        self.constitution = 10
        
        # Resources
        self.health = 100.0
        self.stamina = 100.0
        self.mana = 100.0
        self.maxHealth = 100.0
        self.maxStamina = 100.0
        self.maxMana = 100.0
        
        # Regen rates
        self.healthRegen = 1.0
        self.staminaRegen = 2.0
        self.manaRegen = 1.5

    def Regeneration(self, delta: float):
        if self.health < self.maxHealth:
            self.health += self.healthRegen * delta
            self.health = min(self.health, self.maxHealth)
        if self.stamina < self.maxStamina:
            self.stamina += self.staminaRegen * delta
            self.stamina = min(self.stamina, self.maxStamina)
        if self.mana < self.maxMana:
            self.mana += self.manaRegen * delta
            self.mana = min(self.mana, self.maxMana)

    def UpdateStats(self):
        # Calculate derived stats
        self.maxHealth = (self.constitution * self.strength) * 1.0
        self.maxStamina = (self.dexterity * self.strength) * 1.0
        self.maxMana = (self.intelligence * self.wisdom) * 1.0