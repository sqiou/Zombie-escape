# Zombie Escape

A top-down survival game where AI zombies hunt you through a dark city.
Find 3 radio parts hidden in the fog, call the rescue helicopter, and reach
the helipad before the horde gets you.

Built with Python + Pygame for an AI semester project.

---

## How to run

1. Install Python 3.9 or newer.
2. Install Pygame:
   ```
   pip install -r requirements.txt
   ```
3. Start the game:
   ```
   python main.py
   ```

Run the automated tests (no Pygame needed):
```
python -m unittest test_game.py -v
```

---

## How to play

| Key | Action |
| --- | --- |
| WASD / Arrow keys | Move |
| Shift (hold) | Run: fast, but LOUD, and uses stamina |
| Space / E | Place a barricade on the tile you are facing (green outline = allowed) |
| F1 / Tab | AI debug view: shows every zombie, its A* path, sight range and state |
| P / Esc | Pause (M = menu, Q = quit) |
| R | Play again (on the end screen) |

**Goal:** collect 3 radio parts (blue boxes) → the helicopter lands 20 s later
→ stand on the helipad for 3 s to escape. It leaves after 30 s!

**Tips**
- Walking is quiet, running is loud. The NOISE meter in the top bar tells you how loud you are.
- The **signal bars** next to RADIO get stronger as you get closer to a radio part.
- A zombie with **?** heard something and is investigating. A zombie with **!** has seen you.
  When one sees you it groans, and nearby zombies come to help.
- Break line of sight around corners and they lose track of you after 2.5 s.
- Barricades block zombies. They will try to find a way around, and only smash through if there is no shorter route.
- Supply crates: white box = +1 health, wooden box = +2 barricades.
- The helicopter is noisy and attracts zombies to the helipad. Be ready.

---

## Where the AI is (for the report and viva)

All AI code is in **`game.py`** and **`pathfinding.py`**. `main.py` only draws the game.

### 1. Intelligent agents (PEAS)
Each zombie is a goal-based agent.

| PEAS | Zombie |
| --- | --- |
| Performance | Reach and bite the player |
| Environment | Grid city with buildings, streets, barricades, noise |
| Actuators | Move, attack barricades, bite, groan |
| Sensors | Sight (range + line of sight), hearing (noise radius), smell (very close range) |

### 2. Finite State Machine (`Game._update_zombies`)
```
            hears noise                    sees player
  WANDER  -------------->  INVESTIGATE  --------------->  CHASE
    ^                          |   ^                        |
    |   looked around 2 s,     |   |  lost sight for 2.5 s  |
    +----- found nothing ------+   +------------------------+
    (WANDER also goes straight to CHASE if it sees the player)
```
- **WANDER**: walks to random nearby tiles slowly, staying loosely grouped.
- **INVESTIGATE**: walks to where a noise came from and looks around.
- **CHASE**: re-plans an A* path to the player every 0.4 s, at the fastest speed.

### 3. A* search (`pathfinding.astar`)
- 4-directional grid, heuristic = **Manhattan distance** (admissible because each step costs at least 1).
- **Weighted costs**: street = 1, barricade = 6, building = impassable.
  So A* goes around barricades when the detour is shorter than 6 steps, and breaks through otherwise.
- The debug view and end screen show how many A* searches ran and how many nodes they expanded.
- **BFS** (`bfs_reachable`) checks that every generated map is fully connected.

### 4. Perception
- **Sight**: within range AND no building on the straight line between zombie and player (`CityMap.line_of_sight`).
- **Hearing**: every action creates a `Noise` with a radius (walk 2.5, run 7.5, barricade 5, helicopter 9 tiles).
  Zombies inside the radius investigate it.
- **Communication**: a zombie that spots you emits a groan noise pointing at your position, so the horde hunts as a group.

### 5. Flocking (`Game._apply_movement`)
- **Separation**: zombies push away from each other so they don't overlap.
- **Cohesion**: wandering zombies drift towards nearby zombies, forming hordes.

### 6. Fog of war (`Game.update_fog`)
The player only sees tiles within 6 tiles that are in line of sight. Explored tiles stay dimly visible.

### 7. Procedural generation (`CityMap._build_layout`)
Every game creates a new random city, verified with BFS.

---

## Files

| File | What it does |
| --- | --- |
| `main.py` | Pygame window, drawing, HUD, menus, sound effects (generated in code, no audio files) |
| `game.py` | Game rules and all zombie AI (no Pygame, so it can be tested) |
| `pathfinding.py` | A* search and BFS |
| `settings.py` | Every tunable number (speeds, noise radii, difficulty levels) |
| `test_game.py` | 27 automated tests for A*, the map, the player and the zombie AI |

## Ideas to extend it
- Add a second AI algorithm (BFS or greedy best-first) and compare nodes expanded against A* in your report.
- Make zombies remember noises with a priority queue (loudest/closest first).
- Add a "smart" zombie type that predicts where you are heading and cuts you off.
- Add a save file for high scores (fastest escape time per difficulty).
