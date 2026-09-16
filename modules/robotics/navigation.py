"""Deterministic fake world for the robotics simulation.

Grid-based world with rectangular bounds, an obstacle set, charging pads,
sensor ray casting, and BFS navigation. Everything is deterministic: given
the same inputs the queries return the same results, so tests and the sim
are reproducible. No RNG is used and no external dependencies are required.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

from .state import DIRS


class FakeWorld:
    """A simple deterministic 2D world for simulation.

    ``width`` and ``height`` bound the walkable grid. Cells are addressed as
    ``(x, y)`` with ``x`` in ``[0, width)`` and ``y`` in ``[0, height)``.

    Safe defaults: the constructor builds a populated map (obstacles and one
    charger) so a freshly-created world is immediately usable. Callers may
    pass empty sets to start blank.
    """

    def __init__(
        self,
        width: int = 24,
        height: int = 18,
        obstacles: set[tuple[int, int]] | None = None,
        chargers: set[tuple[int, int]] | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.obstacles = (
            {
                (8, 6),
                (9, 6),
                (10, 6),
                (13, 10),
                (14, 10),
                (15, 10),
                (5, 14),
                (6, 14),
                (7, 14),
                (18, 7),
                (18, 8),
                (18, 9),
            }
            if obstacles is None
            else obstacles
        )
        self.chargers = {(2, 2)} if chargers is None else chargers

    # ---- geometry ---------------------------------------------------

    def in_bounds(self, pos: tuple[int, int]) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_blocked(self, pos: tuple[int, int]) -> bool:
        """A cell is blocked if out of bounds or occupied by an obstacle.

        Chargers are walkable (they are pads on the floor, not walls).
        """
        return not self.in_bounds(pos) or pos in self.obstacles

    def open_positions(self) -> list[tuple[int, int]]:
        """Every in-bounds, non-obstacle cell, in deterministic traversal order."""
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if not self.is_blocked((x, y))
        ]

    def is_charger(self, pos: tuple[int, int]) -> bool:
        return pos in self.chargers

    def nearest_charger(self, pos: tuple[int, int]) -> tuple[int, int]:
        """Charger closest to ``pos`` in Manhattan distance (deterministic on ties)."""
        return min(
            self.chargers,
            key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]),
        )

    # ---- sensors ----------------------------------------------------

    def sensor_ray(
        self,
        pos: tuple[int, int],
        heading: str,
        max_cells: int = 8,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Segment from ``pos`` outward up to ``max_cells`` along ``heading``.

        Returns ``(start, end)`` even if the ray leaves ``max_cells`` beyond
        the world bounds; the caller decides how to interpret an out-of-bounds
        readout. Deterministic.
        """
        dx, dy = DIRS[heading]
        end = (pos[0] + dx * max_cells, pos[1] + dy * max_cells)
        return (pos, end)

    def ultrasonic_cm(
        self,
        pos: tuple[int, int],
        heading: str,
        max_cells: int = 8,
    ) -> int | None:
        """Distance (in ``cm``-scale units) to the first blocking cell.

        Each cell step counts as 10 units. Returns ``None`` when no obstacle
        is found within ``max_cells``. Only obstacles and the world bounds
        stop the ray; other sensors (chargers) do not.
        """
        dx, dy = DIRS[heading]
        x, y = pos
        for distance in range(1, max_cells + 1):
            if self.is_blocked((x + dx * distance, y + dy * distance)):
                return distance * 10
        return None

    # ---- navigation -------------------------------------------------

    def neighbors(self, pos: tuple[int, int]) -> Iterator[tuple[int, int]]:
        """Adjacent open cells (north, east, south, west). Deterministic order."""
        x, y = pos
        for dx, dy in DIRS.values():
            nxt = (x + dx, y + dy)
            if not self.is_blocked(nxt):
                yield nxt

    def path_to(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> list[tuple[int, int]] | None:
        """Shortest BFS path (inclusive of start and goal), or ``None``.

        ``None`` is returned when ``goal`` is unreachable or is a blocked /
        out-of-bounds cell. BFS yields the shortest path in steps; ties are
        broken deterministically by traversal order.
        """
        if self.is_blocked(start):
            return None
        if start == goal:
            return [start]
        if self.is_blocked(goal):
            return None

        frontier: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        while frontier:
            current = frontier.popleft()
            if current == goal:
                break
            for nxt in self.neighbors(current):
                if nxt not in came_from:
                    came_from[nxt] = current
                    frontier.append(nxt)

        if goal not in came_from:
            return None

        # Reconstruct the path from goal back to start, then reverse it.
        path: list[tuple[int, int]] = [goal]
        current = goal
        while current != start:
            prev = came_from[current]
            if prev is None:
                return None  # defensive; should not happen
            path.append(prev)
            current = prev
        path.reverse()
        return path

    def next_step_toward(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> tuple[int, int] | None:
        """First cell on the shortest path from ``start`` to ``goal``.

        Returns ``start`` when already at the goal, or ``None`` when no path
        exists. Intended for one-forward-step planning loops.
        """
        path = self.path_to(start, goal)
        if path is None:
            return None
        return path[1] if len(path) > 1 else start


class NavigationHelper:
    """High-level navigation planner built on ``FakeWorld`` BFS.

    Tracks visited cells so a caller can pick an unvisited exploration target,
    then yields the next concrete cell on the shortest path toward a goal.

    Safe defaults: starts with no target and an empty visited set, so a
    freshly-constructed helper is inert until given a world.
    """

    def __init__(self) -> None:
        self.visited_positions: set[tuple[int, int]] = set()
        self.target_position: tuple[int, int] | None = None

    def record_position(self, position: tuple[int, int]) -> None:
        """Mark a position as visited (typically the body's current cell)."""
        self.visited_positions.add(position)

    @staticmethod
    def manhattan_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def choose_explore_target(
        self,
        world: FakeWorld,
        current_position: tuple[int, int],
    ) -> tuple[int, int] | None:
        """Pick the nearest unvisited open cell as an exploration target.

        Prefers cells never visited; falls back to any open cell when nothing
        is unvisited. Returns ``None`` only if the world has no open cells.
        Stores the choice on ``self.target_position``.
        """
        open_positions = world.open_positions()
        unvisited = [pos for pos in open_positions if pos not in self.visited_positions]
        candidates = unvisited or open_positions

        if not candidates:
            self.target_position = None
            return None

        self.target_position = min(
            candidates,
            key=lambda pos: self.manhattan_distance(current_position, pos),
        )
        return self.target_position

    def next_step(
        self,
        world: FakeWorld,
        current_position: tuple[int, int],
        goal: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        """Return the next cell toward ``goal`` (or ``self.target_position``).

        Returns the current cell when already at the goal, and ``None`` when
        the goal is missing or unreachable.
        """
        goal = goal or self.target_position
        if goal is None:
            return None
        return world.next_step_toward(current_position, goal)
