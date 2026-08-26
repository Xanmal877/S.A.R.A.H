from enum import Enum, auto
from typing import Dict, List

class PerceptionType(Enum):
    ALLIES = auto()
    ENEMIES = auto()
    OBJECTS = auto()
    INTERACTABLES = auto()

class DetectionModule:
    def __init__(self):
        self.perception_dict: Dict[PerceptionType, List] = {
            PerceptionType.ALLIES: [],
            PerceptionType.ENEMIES: [],
            PerceptionType.OBJECTS: [],
            PerceptionType.INTERACTABLES: [],
        }

    @property
    def allies(self) -> List:
        return self.perception_dict.get(PerceptionType.ALLIES, [])

    @property
    def enemies(self) -> List:
        return self.perception_dict.get(PerceptionType.ENEMIES, [])

    @property
    def objects(self) -> List:
        return self.perception_dict.get(PerceptionType.OBJECTS, [])

    @property
    def interactables(self) -> List:
        return self.perception_dict.get(PerceptionType.INTERACTABLES, [])

    def add_ally(self, soul_data):
        if soul_data not in self.allies:
            self.allies.append(soul_data)

    def remove_ally(self, soul_data):
        if soul_data in self.allies:
            self.allies.remove(soul_data)

    def add_enemy(self, soul_data):
        if soul_data not in self.enemies:
            self.enemies.append(soul_data)

    def remove_enemy(self, soul_data):
        if soul_data in self.enemies:
            self.enemies.remove(soul_data)

    def add_object(self, object_data):
        if object_data not in self.objects:
            self.objects.append(object_data)

    def remove_object(self, object_data):
        if object_data in self.objects:
            self.objects.remove(object_data)

    def add_interactable(self, node):
        if node not in self.interactables:
            self.interactables.append(node)

    def remove_interactable(self, node):
        if node in self.interactables:
            self.interactables.remove(node)

    def clear_soul(self, soul_data):
        self.remove_ally(soul_data)
        self.remove_enemy(soul_data)
