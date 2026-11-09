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

# How fast new zombies arrive on each difficulty (multiplies spawn intervals)
SPAWN_MULT = {"Easy": 1.25, "Normal": 1.0, "Hard": 0.8}

# ---------------- Terrain (Level 2) ----------------
WATER_SPEED = 0.5         # wading: half speed, for the player AND zombies
MUD_SPEED = 0.6           # mud: slow for everyone
WATER_PATH_COST = 4       # A* cost: zombies prefer dry streets...
MUD_PATH_COST = 3         # ...but will still cross if it is much shorter
NOISE_SPLASH = 6.0        # every step in water splashes (as loud as running, almost)

# ---------------- Darkness and sleepers (Level 3) ----------------
DARK_VIEW_RADIUS = 3.0    # how far you see in the blackout without a light
FLASH_RANGE = 8.5         # flashlight beam length (tiles)
FLASH_ANGLE = 0.5         # half-width of the beam (radians, about 29 degrees)
BATTERY_MAX = 100.0
BATTERY_DRAIN = 2.5       # per second while the light is on (40 s from full)
BATTERY_PICKUP = 45.0
DARK_SIGHT = 0.6          # zombies see you 40% less far in the dark...
LIGHT_SIGHT = 1.5         # ...but 50% further while your flashlight is on
SLEEP_HEARING = 0.6       # sleepers only hear noises within 60% of the normal radius
SLEEP_WAKE_DIST = 1.2     # walk right next to a sleeper and it wakes up
NOISE_ELEVATOR = 6.0      # the elevator's ding is quieter than a helicopter

# ---------------- Bottles and car alarms (Level 4) ----------------
BOTTLE_RANGE = 7.0        # max throw distance in tiles
BOTTLE_SPEED = 11.0       # flight speed, tiles per second
NOISE_BOTTLE = 7.0        # smash noise radius where it lands
CAR_ALARM_TIME = 8.0      # an alarm wails this long
CAR_ALARM_INTERVAL = 1.0  # one noise pulse per second while wailing
NOISE_ALARM = 11.0
ALARM_REACH = 1.0         # how close you must be to set off an alarm by hand

# ---------------- Zombie types (Level 5) ----------------
# wander/chase = speed multipliers, sight = sight-range multiplier,
# lose = seconds without seeing you before it gives up, damage = hearts per bite.
ZOMBIE_KINDS = {
    "normal":   {"wander": 1.0,  "chase": 1.0,  "sight": 1.0,  "lose": LOSE_SIGHT_TIME, "damage": 1, "radius": 0.30},
    "runner":   {"wander": 1.25, "chase": 1.6,  "sight": 0.9,  "lose": 0.9,             "damage": 1, "radius": 0.27},
    "screamer": {"wander": 0.9,  "chase": 0.9,  "sight": 1.25, "lose": LOSE_SIGHT_TIME, "damage": 0, "radius": 0.30},
    "brute":    {"wander": 0.7,  "chase": 0.72, "sight": 0.9,  "lose": 4.0,             "damage": 2, "radius": 0.38},
    "hunter":   {"wander": 1.0,  "chase": 1.05, "sight": 1.3,  "lose": 4.0,             "damage": 1, "radius": 0.30},
}
BRUTE_BARRICADE_COST = 2      # brutes smash barricades instantly, so A* barely avoids them
SCREAM_COOLDOWN = 7.0         # seconds between screams
SCREAMER_KEEP_DIST = 4.0      # screamers hang back and watch instead of attacking
HUNTER_MAX_LOOKAHEAD = 2.5    # seconds into the future the hunter predicts
HUNTER_DIRECT_RANGE = 2.5     # closer than this, the hunter just lunges at you

# ---------------- Levels ----------------
# exit: "heli" | "boat" | "checkpoint" (just reach it) | "survive" (hold the zone)
LEVELS = {
    1: {"name": "The Dark City", "theme": "city", "w": 30, "h": 20,
        "items": 3, "item": "radio part", "items_label": "RADIO", "exit": "heli",
        "hurdles": ["Find 3 radio parts hidden in the fog",
                    "Call the helicopter and reach the helipad",
                    "Walk quietly - zombies hear running"]},
    2: {"name": "The Flooded Market", "theme": "flood", "w": 30, "h": 20,
        "items": 3, "item": "fuel can", "items_label": "FUEL", "exit": "boat",
        "hurdles": ["Water: half speed, and every step SPLASHES (loud)",
                    "Mud: slows you AND the zombies",
                    "Zombies avoid water - use it to slow chasers",
                    "Collect 3 fuel cans, then reach the boat at the dock"]},
    3: {"name": "The Hospital Blackout", "theme": "hospital", "w": 30, "h": 20,
        "items": 3, "item": "fuse", "items_label": "FUSES", "exit": "elevator",
        "dark": True, "sleepers": 7, "extra_zombies": -3, "spawn_interval": 35.0,
        "supplies": ["battery", "medkit", "battery", "barricade"],
        "hurdles": ["Blackout: you can only see a few steps around you",
                    "L: flashlight - see far, but zombies spot the light too",
                    "Sleeping zombies (Zz) wake up to loud noise - tiptoe past",
                    "Find 3 fuses to power the elevator, then ride it out"]},
    4: {"name": "The Highway Bridge", "theme": "bridge", "w": 56, "h": 20,
        "items": 0, "item": "", "items_label": "", "exit": "checkpoint",
        "bottles": 3, "extra_zombies": 4, "sight_bonus": 1.0,
        "supplies": ["bottles", "medkit", "bottles", "barricade"],
        "hurdles": ["Hide behind cars - they block zombie sight",
                    "F next to a car: set off its alarm (or hit it with a bottle)",
                    "T or mouse click: throw a bottle to make noise elsewhere",
                    "Reach the military checkpoint at the far end"]},
    5: {"name": "The Final Stand", "theme": "stand", "w": 30, "h": 20,
        "items": 0, "item": "", "items_label": "", "exit": "survive",
        "survive_time": 90.0, "bonus_barricades": 6, "spawn_interval": 9.0, "max_mult": 1.0,
        "barricade_hp_mult": 3.0, "extra_zombies": -2, "start_kinds": ["hunter", "runner"],
        "kinds": {"normal": 48, "runner": 18, "brute": 12, "screamer": 9, "hunter": 13},
        "supplies": ["barricade", "medkit", "barricade", "medkit"],
        "hurdles": ["Hold the safe zone for 90s - the timer stops if you leave",
                    "Reinforced barricades block sight - seal the 4 gates and hide!",
                    "Runner: fast, gives up quickly.  Brute: smashes barricades, 2 damage",
                    "Screamer: alerts the WHOLE map when it sees you",
                    "Hunter: predicts where you're going and cuts you off"]},
}
LEVEL_ORDER = [1, 2, 3, 4, 5]
