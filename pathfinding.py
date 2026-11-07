"""
pathfinding.py - search algorithms used by the zombies.

* astar()          - A* search on a weighted grid (4-directional).
* bfs_reachable()  - Breadth-first search, used to check the map is connected.

Both functions take a `cost(x, y)` callback that returns:
    None   -> tile is impassable (a building)
    number -> cost of stepping onto that tile (1 for street, more for barricades)
"""

import heapq
from collections import deque

NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def manhattan(a, b):
    """Admissible heuristic for a 4-directional grid where the cheapest step costs 1."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(start, goal, cost, width, height, max_nodes=5000):
    """
    Find the cheapest path from start to goal.

    Returns (path, nodes_expanded) where path is a list of tiles from the
    first step up to and including goal ([] if start == goal, None if unreachable).
    """
    if start == goal:
        return [], 0
    if cost(goal[0], goal[1]) is None:
        return None, 0

    open_heap = [(manhattan(start, goal), 0, start)]   # (f, g, node)
    came_from = {start: None}
    g_score = {start: 0}
    expanded = 0

    while open_heap:
        f, g, node = heapq.heappop(open_heap)
        if g > g_score.get(node, float("inf")):
            continue                     # stale heap entry
        expanded += 1
        if node == goal:
            break
        if expanded > max_nodes:
            return None, expanded        # safety limit

        x, y = node
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            step = cost(nx, ny)
            if step is None:
                continue
            new_g = g + step
            if new_g < g_score.get((nx, ny), float("inf")):
                g_score[(nx, ny)] = new_g
                came_from[(nx, ny)] = node
                heapq.heappush(open_heap, (new_g + manhattan((nx, ny), goal), new_g, (nx, ny)))
    else:
        return None, expanded

    if goal not in came_from:
        return None, expanded

    # Walk back from goal to start to rebuild the path.
    path = []
    node = goal
    while node != start:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path, expanded


def bfs_reachable(start, cost, width, height):
    """Return the set of all tiles reachable from start (Breadth-First Search)."""
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if (0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen
                    and cost(nx, ny) is not None):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen
