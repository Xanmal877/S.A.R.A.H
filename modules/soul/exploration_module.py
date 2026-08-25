from typing import Any, Dict, List, Optional, Tuple

class ExplorationModule:
    cell_size: float = 100.0

    def __init__(self, owner_soul=None):
        self.soul = owner_soul
        self.exploration_dict: Dict[str, Any] = {
            "visitedCells": {},
            "knownLocations": {},
        }

    @property
    def visited_cells(self) -> Dict:
        return self.exploration_dict["visitedCells"]

    @property
    def known_locations(self) -> Dict:
        return self.exploration_dict["knownLocations"]

    def sync_data(self, from_soul: bool = False):
        if self.soul is None:
            return
        
        if from_soul:
            # Note: In Python, we access the dict via the SoulData instance
            from .soul import SoulModulesEnum
            saved = self.soul.soulModuleDicts.get(SoulModulesEnum.EXPLORATION, {})
            if saved:
                self.exploration_dict = saved.copy()
                return
        
        from .soul import SoulModulesEnum
        self.soul.soulModuleDicts[SoulModulesEnum.EXPLORATION] = self.exploration_dict.copy()

    @staticmethod
    def world_to_grid(world_pos: Tuple[float, float, float]) -> Tuple[int, int, int]:
        return (
            int(world_pos[0] // ExplorationModule.cell_size),
            int(world_pos[1] // ExplorationModule.cell_size),
            int(world_pos[2] // ExplorationModule.cell_size),
        )

    def add_known_location(self, location_type: int, location_pos: Tuple[float, float, float]):
        known = self.known_locations
        if location_type not in known:
            known[location_type] = []
        
        locations = known[location_type]
        if location_pos not in locations:
            locations.append(location_pos)
        
        known[location_type] = locations

    def has_known_location(self, location_type: int, location_pos: Tuple[float, float, float]) -> bool:
        known = self.known_locations
        if location_type not in known:
            return False
        return location_pos in known[location_type]

    def get_known_locations(self, location_type: int) -> List:
        return self.known_locations.get(location_type, [])

    def mark_cell_as_visited(self, cell_pos: Tuple[int, int, int]):
        self.visited_cells[cell_pos] = True

    def mark_as_visited(self, world_pos: Tuple[float, float, float]):
        if self.is_visited(world_pos):
            return
        grid_coord = self.world_to_grid(world_pos)
        self.mark_cell_as_visited(grid_coord)

    def is_cell_visited(self, cell_pos: Tuple[int, int, int]) -> bool:
        return cell_pos in self.visited_cells

    def is_visited(self, world_pos: Tuple[float, float, float]) -> bool:
        grid_coord = self.world_to_grid(world_pos)
        return self.is_cell_visited(grid_coord)
