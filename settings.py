"""
settings.py - all tunable numbers for Zombie Escape in one place.

Distances are measured in TILES and speeds in TILES PER SECOND,
so the game logic never depends on screen size.
"""

# ---------------- Screen ----------------
TILE = 32                 # pixels per tile
GRID_W = 30               # map width in tiles
GRID_H = 20               # map height in tiles
HUD_H = 84                # height of the top wooden seed-bar (pixels)
SCREEN_W = GRID_W * TILE
SCREEN_H = GRID_H * TILE + HUD_H
FPS = 60

# ---------------- Player ----------------
PLAYER_RADIUS = 0.30
PLAYER_WALK_SPEED = 2.4
PLAYER_RUN_SPEED = 4.2
PLAYER_MAX_HP = 3
INVULNERABLE_TIME = 2.0   # seconds of safety after being bitten
STAMINA_MAX = 100.0
STAMINA_DRAIN = 20.0      # per second while running
STAMINA_REGEN = 16.0      # per second while not running
STAMINA_MIN_TO_RUN = 20.0 # after exhaustion you must recover to this

VIEW_RADIUS = 6.0         # fog of war: how far the player can see

# ---------------- Noise (radius in tiles) ----------------
NOISE_WALK = 2.5
NOISE_RUN = 7.5
NOISE_BARRICADE = 5.0
NOISE_GROAN = 5.0         # a zombie that spots you alerts the horde
NOISE_HELICOPTER = 9.0    # rotor noise pulls nearby zombies to the helipad
NOISE_INTERVAL = 0.35     # how often footsteps make a noise event

# ---------------- Zombies ----------------
ZOMBIE_RADIUS = 0.30
ZOMBIE_TOUCH_DIST = 0.58  # centre distance at which a zombie bites
ZOMBIE_SEPARATION = 0.75  # flocking: keep this far from other zombies
ZOMBIE_COHESION_RANGE = 4.0
LOSE_SIGHT_TIME = 2.5     # seconds without seeing player before giving up chase
REPATH_INTERVAL = 0.4     # how often a chasing zombie recomputes A*
INVESTIGATE_LOOK_TIME = 2.0
SMELL_RANGE = 1.5         # zombies always notice you this close, even around corners
ZOMBIE_SPAWN_INTERVAL = 25.0
ZOMBIE_BITE_STUN = 1.2     # a zombie pauses after biting (gives you time to run)
ZOMBIE_MIN_SPAWN_DIST = 10.0

# ---------------- Barricades ----------------
BARRICADE_HP = 4.0        # seconds of zombie attacks needed to break one
BARRICADE_PATH_COST = 6   # A* cost of walking "through" a barricade (must break it)

# ---------------- Helicopter ----------------
RADIO_PARTS = 3           # collect these to radio for the helicopter
HELI_CALL_TIME = 20.0     # seconds from radio call until the helicopter lands
HELI_WAIT_TIME = 30.0     # how long it waits before leaving without you
BOARD_TIME = 3.0          # stand on the helipad this long to escape

# ---------------- Difficulty presets ----------------
DIFFICULTY = {
    "Easy":   {"zombies": 5,  "max_zombies": 8,  "wander": 0.9, "investigate": 1.6,
               "chase": 2.1, "sight": 4.5, "barricades": 7},
    "Normal": {"zombies": 7,  "max_zombies": 12, "wander": 1.0, "investigate": 1.8,
               "chase": 2.4, "sight": 5.0, "barricades": 5},
    "Hard":   {"zombies": 10, "max_zombies": 16, "wander": 1.1, "investigate": 2.0,
               "chase": 2.8, "sight": 6.0, "barricades": 4},
}
