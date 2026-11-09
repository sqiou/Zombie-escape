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
| L | Flashlight on/off (Level 3) |
| T / mouse click | Throw a bottle (Level 4) - a dotted arc shows where it lands |
| F | Set off the alarm of the car you're standing next to (Level 4) |
| P / Esc | Pause (M = menu, Q = quit) |
| R / N | Play again / next level (on the end screen) |

In the menu, pick a level with the cards (or Left/Right) and a difficulty (Up/Down), then START.

### Levels
| Level | Hurdle | Goal |
| --- | --- | --- |
| 1 - The Dark City | Fog, noise, hordes | 3 radio parts, then the helicopter |
| 2 - The Flooded Market | **Water**: half speed and every step splashes (loud). **Mud**: slows you *and* zombies. Zombies prefer dry streets, so wade through water to shake off chasers. | 3 fuel cans, then the rescue boat at the dock |
| 3 - The Hospital Blackout | **Darkness**: you see only 3 tiles. **L** toggles a flashlight with a long beam, but zombies spot the light 1.5x further (in the dark they only see 0.6x as far). The battery drains, and battery pickups recharge it. **Sleeping zombies** (Zz) only wake to loud noise or if you bump into them. | 3 fuses, then the elevator |
| 4 - The Highway Bridge | Long, open, scrolling bridge. **Cars** block movement and sight (hide behind them). **Car alarms** (F, or hit a car with a bottle) wail for 8 s and pull zombies in. **Bottles** make noise where they land. | Reach the military checkpoint at the far end |
| 5 - The Final Stand | Hold a walled plaza for 90 s (the timer pauses if you leave). Reinforced barricades block sight. New zombies: **Runner**, **Screamer**, **Brute**, **Hunter**. | Survive, then board the helicopter |

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

### 7. Procedural generation (`CityMap.generate`)
Every game creates a new random level (city, flooded market, bridge or plaza), verified with BFS.

### 8. BSP map generation and the SLEEP state (Level 3)
- `CityMap._build_hospital` uses **Binary Space Partitioning**: the map is split in two, then each half
  is split again (up to 5 times). Each final piece gets a room, and each pair of sibling pieces is joined
  by a corridor, so every room is connected. Two extra corridors add loops. The elevator goes in the room
  furthest from the start (measured by BFS walking distance).
- A fourth FSM state, **SLEEP**: no sight; hears noise only within 60% of its radius; wakes up if you
  come within 1.2 tiles. Walking (2.5 -> 1.5) sneaks past, running (7.5 -> 4.5) wakes them.

### 8b. Terrain costs (Level 2)
A* step costs: street 1, mud 3, water 4, barricade 6. Water and mud also slow movement
(x0.5 and x0.6), so the costs combine travel time with a preference for dry ground. Zombies walk
around a flooded street when the detour is short and wade through only when it saves a lot.

### 9. Distractions use the noise system (Level 4)
A bottle creates a `Noise` where it lands, and a car alarm creates one every second for 8 s.
The zombies need no new code: their FSM already sends them to INVESTIGATE any noise they hear.
Cars block line of sight, so the sight check already handles hiding.

### 10. Zombie types (Level 5, `ZOMBIE_KINDS` in settings.py)
They all share the same FSM and A*. Only the numbers change:
| Type | Change |
| --- | --- |
| Runner | x1.6 chase speed; gives up after 0.9 s and goes straight back to WANDER |
| Screamer | Never bites. When it sees you, every zombie on the map gets an INVESTIGATE target at your position |
| Brute | Slow, bites for 2, breaks barricades in one hit, and its A* barricade cost is only 2 (it goes straight through) |
| Hunter | Uses **prediction** (`Game.predict_intercept`): it estimates where you are from your last seen position and velocity, looks ahead by (distance / its speed) seconds, and runs A* to that point to cut you off. The red crosshair shows its prediction |

Wandering zombies never smash barricades. Only zombies that are investigating or chasing break through.

---

## Files

| File | What it does |
| --- | --- |
| `main.py` | Pygame window, drawing, HUD, menus, sound effects (generated in code, no audio files) |
| `game.py` | Game rules and all zombie AI (no Pygame, so it can be tested) |
| `pathfinding.py` | A* search and BFS |
| `settings.py` | Every tunable number (speeds, noise radii, difficulty levels) |
| `ui.py` | Cartoon wooden UI widgets (panels, cards, buttons, signs) |
| `test_game.py` | 52 automated tests for A*, every level, terrain, distractions and each zombie type |

## Ideas to extend it
- Add a second AI algorithm (BFS or greedy best-first) and compare nodes expanded against A* in your report.
- Make zombies remember noises with a priority queue (loudest/closest first).
- Add a save file for high scores (fastest escape time per difficulty).
