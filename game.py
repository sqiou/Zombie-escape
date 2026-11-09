"""
game.py - all of Zombie Escape's rules and AI, with NO pygame code.

Keeping logic separate from drawing means:
  * it can be unit-tested without opening a window, and
  * the AI is easy to explain in a viva (everything is in one file).

AI concepts used here
---------------------
1. Finite State Machine (FSM)  - each zombie is WANDER, INVESTIGATE or CHASE.
2. A* search                   - zombies plan paths around buildings (pathfinding.py).
   Every tile has a COST: barricades, water and mud cost more than dry street,
   so A* naturally prefers dry, open routes but will still cross if it's shorter.
3. Perception                  - zombies SEE (sight range + line of sight)
                                 and HEAR (noise events with a radius).
4. Flocking                    - separation (don't overlap) + cohesion (stay as a horde).
5. Fog of war                  - the player only sees tiles in line of sight.
6. Prediction (Hunter)         - instead of chasing where you ARE, the Hunter
                                 extrapolates your velocity and runs A* to where
                                 you WILL BE, to cut you off.
7. Agent variety (Level 5)     - Runner / Screamer / Brute change the FSM's
                                 numbers and A* costs, not its structure.
8. BSP generation (Level 3)    - the hospital is built by Binary Space Partitioning:
                                 split the map in two again and again, put a room
                                 in each leaf, then join sibling rooms with corridors.
9. SLEEP state (Level 3)       - a fourth FSM state: no sight, reduced hearing.
"""

import math
import random

from settings import *
from pathfinding import astar, bfs_reachable

# Tile types
STREET, BUILDING, BARRICADE, WATER, MUD, CAR = 0, 1, 2, 3, 4, 5
WALKABLE = (STREET, WATER, MUD)

# Zombie states
WANDER, INVESTIGATE, CHASE, SLEEP = "WANDER", "INVESTIGATE", "CHASE", "SLEEP"

HELI_NOISE_INTERVAL = 3.0
FOG_UPDATE_INTERVAL = 0.08
NOISE_VISUAL_TIME = 0.9
NUM_CRATES = 4
MAX_BARRICADE_ATTACKERS = 2

# A* step cost for every tile type (None = impassable)
TILE_COST = {STREET: 1, WATER: WATER_PATH_COST, MUD: MUD_PATH_COST,
             BARRICADE: BARRICADE_PATH_COST, BUILDING: None, CAR: None}
TERRAIN_SPEED = {WATER: WATER_SPEED, MUD: MUD_SPEED}


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


# ======================================================================
#  Map
# ======================================================================
class Car:
    """An abandoned car: blocks movement AND sight. Its alarm can be set off once."""

    def __init__(self, tiles, colour_index):
        self.tiles = tiles
        self.colour = colour_index
        self.alarm_time = 0.0          # > 0 while wailing
        self.alarm_used = False
        self.noise_timer = 0.0

    @property
    def centre(self):
        return (sum(t[0] for t in self.tiles) / len(self.tiles) + 0.5,
                sum(t[1] for t in self.tiles) / len(self.tiles) + 0.5)

    @property
    def horizontal(self):
        return len(self.tiles) > 1 and self.tiles[0][1] == self.tiles[1][1]


class CityMap:
    """A grid level: solid tiles, streets, terrain and player-placed barricades.

    `theme` picks the layout: "city" (Level 1), "flood" (2), "bridge" (4), "stand" (5).
    `helipad` is the set of exit tiles (helipad, dock, checkpoint or landing zone).
    """

    def __init__(self, width, height, rng, theme="city"):
        self.w, self.h = width, height
        self.rng = rng
        self.theme = theme
        self.tiles = []              # tiles[y][x]
        self.barricade_hp = {}       # (x, y) -> remaining hp
        self.helipad = set()
        self.start = (1, 1)
        self.reachable = set()
        self.safe_zone = set()       # Level 5: tiles you must hold
        self.zone_walls = set()      # Level 5: the sandbag ring (drawn differently)
        self.rooms = []              # Level 3: room rectangles (x, y, w, h)
        self.beds = []               # Level 3: where the sleepers lie
        self.cars = []
        self.car_at = {}             # (x, y) -> Car
        self.tall_barricades = theme == "stand"
        self.generate()

    # ---------- generation ----------
    def generate(self):
        for _ in range(80):
            self.cars, self.car_at = [], {}
            self.safe_zone, self.zone_walls = set(), set()
            self.rooms, self.beds = [], []
            if self.theme == "bridge":
                self._build_bridge()
            elif self.theme == "hospital":
                self._build_hospital()
            else:
                self._build_layout()
                if self.theme == "flood":
                    self._add_flood()
                elif self.theme == "stand":
                    self._add_safe_zone()
            self.reachable = bfs_reachable(self.start, self.zombie_cost, self.w, self.h)
            if self.helipad <= self.reachable and self.safe_zone <= self.reachable:
                return
        raise RuntimeError("Could not generate a connected map")

    def _build_layout(self):
        w, h, rng = self.w, self.h, self.rng
        t = [[STREET] * w for _ in range(h)]
        for x in range(w):
            t[0][x] = t[h - 1][x] = BUILDING
        for y in range(h):
            t[y][0] = t[y][w - 1] = BUILDING

        # City blocks separated by streets. Starting at 2 leaves a ring road
        # around the edge, which guarantees the city is connected.
        x = 2
        while x < w - 2:
            bw = rng.randint(2, 4)
            y = 2
            while y < h - 2:
                bh = rng.randint(2, 3)
                if rng.random() < 0.85:          # 15% of blocks are open lots
                    for yy in range(y, min(y + bh, h - 2)):
                        for xx in range(x, min(x + bw, w - 2)):
                            t[yy][xx] = BUILDING
                y += bh + rng.choice((1, 1, 2))
            x += bw + rng.choice((1, 1, 2))

        # Clear the start area (top-left) and helipad area (bottom-right).
        self.start = (1, 1)
        for yy in range(1, 4):
            for xx in range(1, 4):
                t[yy][xx] = STREET
        for yy in range(h - 4, h - 1):
            for xx in range(w - 4, w - 1):
                t[yy][xx] = STREET
        self.helipad = {(w - 3, h - 3), (w - 2, h - 3), (w - 3, h - 2), (w - 2, h - 2)}

        self.tiles = t
        self.barricade_hp = {}

    def _protected(self, x, y):
        """Start and exit areas stay dry and clear."""
        return (x <= 4 and y <= 4) or (x >= self.w - 6 and y >= self.h - 6)

    def _grow_blob(self, kind, size):
        """Flood-fill a random blob of `kind` over street tiles."""
        t, rng = self.tiles, self.rng
        options = [(x, y) for y in range(self.h) for x in range(self.w)
                   if t[y][x] == STREET and not self._protected(x, y)]
        if not options:
            return
        frontier = [rng.choice(options)]
        placed = 0
        while frontier and placed < size:
            x, y = frontier.pop(rng.randrange(len(frontier)))
            if t[y][x] != STREET or self._protected(x, y):
                continue
            t[y][x] = kind
            placed += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                frontier.append((x + dx, y + dy))

    def _add_flood(self):
        """Level 2: flooded streets and mud patches."""
        rng = self.rng
        for _ in range(rng.randint(5, 6)):
            self._grow_blob(WATER, rng.randint(9, 17))
        for _ in range(rng.randint(5, 7)):
            self._grow_blob(MUD, rng.randint(3, 7))

    def _add_safe_zone(self):
        """Level 5: a walled plaza in the middle with four one-tile gates."""
        t = self.tiles
        x0, y0, x1, y1 = 10, 6, 19, 13          # outer edge of the sandbag ring
        for y in range(y0 - 1, y1 + 2):         # clear a road all round it
            for x in range(x0 - 1, x1 + 2):
                t[y][x] = STREET
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if x in (x0, x1) or y in (y0, y1):
                    t[y][x] = BUILDING
                    self.zone_walls.add((x, y))
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        for gx, gy in ((x0, my), (x1, my + 1), (mx, y0), (mx + 1, y1)):   # gates
            t[gy][gx] = STREET
            self.zone_walls.discard((gx, gy))
        self.safe_zone = {(x, y) for y in range(y0 + 1, y1) for x in range(x0 + 1, x1)}
        self.helipad = {(mx, my), (mx + 1, my), (mx, my + 1), (mx + 1, my + 1)}
        self.start = (x0 + 2, y0 + 2)

    def _build_hospital(self):
        """Level 3: Binary Space Partitioning (BSP) rooms joined by corridors."""
        w, h, rng = self.w, self.h, self.rng
        t = [[BUILDING] * w for _ in range(h)]
        self.tiles = t
        self.barricade_hp = {}
        rooms = []

        def carve(x, y):
            if 0 < x < w - 1 and 0 < y < h - 1:
                t[y][x] = STREET

        def corridor(a, b):
            (ax, ay), (bx, by) = a, b
            if rng.random() < 0.5:
                for x in range(min(ax, bx), max(ax, bx) + 1):
                    carve(x, ay)
                for y in range(min(ay, by), max(ay, by) + 1):
                    carve(bx, y)
            else:
                for y in range(min(ay, by), max(ay, by) + 1):
                    carve(ax, y)
                for x in range(min(ax, bx), max(ax, bx) + 1):
                    carve(x, by)

        def split(x, y, rw, rh, depth):
            """Returns the centre of one room inside this region."""
            can_v, can_h = rw >= 11, rh >= 10
            if depth >= 5 or not (can_v or can_h) or (depth >= 3 and rng.random() < 0.2):
                # leaf: a room with a 1-tile wall margin, sometimes a bit smaller
                iw = rng.randint(max(3, rw - 4), rw - 2)
                ih = rng.randint(max(3, rh - 4), rh - 2)
                ix = x + 1 + rng.randint(0, rw - 2 - iw)
                iy = y + 1 + rng.randint(0, rh - 2 - ih)
                for yy in range(iy, iy + ih):
                    for xx in range(ix, ix + iw):
                        carve(xx, yy)
                rooms.append((ix, iy, iw, ih))
                return (ix + iw // 2, iy + ih // 2)
            vertical = can_v and (not can_h or rw / rh > 1.25 or (rw / rh > 0.8 and rng.random() < 0.5))
            if vertical:
                cut = rng.randint(x + 5, x + rw - 5)
                a = split(x, y, cut - x, rh, depth + 1)
                b = split(cut, y, x + rw - cut, rh, depth + 1)
            else:
                cut = rng.randint(y + 5, y + rh - 5)
                a = split(x, y, rw, cut - y, depth + 1)
                b = split(x, cut, rw, y + rh - cut, depth + 1)
            corridor(a, b)               # siblings are always joined -> fully connected
            return a if rng.random() < 0.5 else b

        split(0, 0, w, h, 0)
        # Two extra corridors make loops, so you're not always trapped in a dead end.
        centres = [(rx + rw_ // 2, ry + rh_ // 2) for rx, ry, rw_, rh_ in rooms]
        for _ in range(2):
            a, b = rng.sample(centres, 2)
            corridor(a, b)

        self.rooms = rooms
        sx, sy, sw, sh = rooms[0]
        self.start = (sx + sw // 2, sy + sh // 2)
        # Elevator: in the room furthest (by walking distance) from the start.
        dist_map = {self.start: 0}
        frontier = [self.start]
        while frontier:
            nxt = []
            for (x, y) in frontier:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (x + dx, y + dy)
                    if n not in dist_map and t[n[1]][n[0]] == STREET:
                        dist_map[n] = dist_map[(x, y)] + 1
                        nxt.append(n)
            frontier = nxt
        far = max(rooms[1:], key=lambda r: dist_map.get((r[0] + r[2] // 2, r[1] + r[3] // 2), -1))
        ex, ey = far[0] + far[2] // 2 - 1, far[1] + far[3] // 2 - 1
        ex = max(far[0], min(ex, far[0] + far[2] - 2))
        ey = max(far[1], min(ey, far[1] + far[3] - 2))
        self.helipad = {(ex, ey), (ex + 1, ey), (ex, ey + 1), (ex + 1, ey + 1)}
        # Hospital beds along room walls (sleeping zombies lie on some of them).
        for r in rooms:
            if r is rooms[0] or r is far:
                continue
            rx, ry, rw_, rh_ = r
            for _ in range(rng.randint(1, 2)):
                bx = rng.randint(rx, rx + rw_ - 1)
                by = rng.choice((ry, ry + rh_ - 1))
                if (bx, by) not in self.beds:
                    self.beds.append((bx, by))

    def _build_bridge(self):
        """Level 4: a long highway deck over a river, jammed with cars."""
        w, h, rng = self.w, self.h, self.rng
        t = [[BUILDING] * w for _ in range(h)]
        top, bot = 4, h - 5                      # deck rows (inclusive)
        for y in range(top, bot + 1):
            for x in range(1, w - 1):
                t[y][x] = STREET
        self.tiles = t
        self.barricade_hp = {}
        mid = (top + bot) // 2
        self.start = (2, mid)
        self.helipad = {(x, y) for x in (w - 3, w - 2) for y in range(mid - 2, mid + 2)}

        def free(x, y):
            return 6 <= x <= w - 7 and top <= y <= bot and t[y][x] == STREET

        # Collapsed sections of road (holes down to the river) create chokepoints.
        for _ in range(3):
            hx, hy = rng.randint(10, w - 12), rng.choice((top, bot - 1, mid - 1))
            for yy in range(hy, hy + 2):
                for xx in range(hx, hx + rng.randint(2, 4)):
                    if free(xx, yy):
                        t[yy][xx] = BUILDING

        # Abandoned cars: mostly in lanes, some skewed across them.
        n = 0
        for _ in range(400):
            if n >= 34:
                break
            if rng.random() < 0.75:
                x, y = rng.randint(6, w - 8), rng.randint(top, bot)
                tiles = [(x, y), (x + 1, y)]
            else:
                x, y = rng.randint(6, w - 7), rng.randint(top, bot - 1)
                tiles = [(x, y), (x, y + 1)]
            # keep a one-tile gap around every car so the deck stays walkable
            if not all(free(a, b) for a, b in tiles):
                continue
            if any(self.car_at.get((a + dx, b + dy)) for a, b in tiles
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue
            car = Car(tiles, rng.randrange(6))
            for a, b in tiles:
                t[b][a] = CAR
                self.car_at[(a, b)] = car
            self.cars.append(car)
            n += 1

    # ---------- queries ----------
    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y][x] if self.in_bounds(x, y) else BUILDING

    def is_solid(self, x, y):
        """Blocks movement (buildings, cars and barricades)."""
        return self.tile(x, y) not in WALKABLE

    def blocks_sight(self, x, y):
        """Buildings and cars block sight. Barricades are low, except the tall
        reinforced ones on the Final Stand level."""
        t = self.tile(x, y)
        return t in (BUILDING, CAR) or (t == BARRICADE and self.tall_barricades)

    def zombie_cost(self, x, y):
        """A* step cost for zombies. None = impassable."""
        return TILE_COST[self.tile(x, y)]

    def cost_for(self, kind):
        """Cost function for one zombie type (brutes barely mind barricades)."""
        if kind != "brute":
            return self.zombie_cost

        def cost(x, y):
            t = self.tile(x, y)
            return BRUTE_BARRICADE_COST if t == BARRICADE else TILE_COST[t]
        return cost

    def speed_factor(self, x, y):
        """Water and mud slow everyone down."""
        return TERRAIN_SPEED.get(self.tile(x, y), 1.0)

    def line_of_sight(self, ax, ay, bx, by, ignore=None):
        """True if no building or car lies on the straight line between two points."""
        d = dist(ax, ay, bx, by)
        steps = max(1, int(d / 0.2))
        for i in range(1, steps):
            f = i / steps
            tx, ty = int(ax + (bx - ax) * f), int(ay + (by - ay) * f)
            if (tx, ty) == ignore:
                continue
            if self.blocks_sight(tx, ty):
                return False
        return True

    def circle_free(self, x, y, r):
        """True if a circle of radius r at (x, y) does not overlap any solid tile."""
        for ty in range(math.floor(y - r), math.floor(y + r) + 1):
            for tx in range(math.floor(x - r), math.floor(x + r) + 1):
                if self.is_solid(tx, ty) and circle_hits_tile(x, y, r, tx, ty):
                    return False
        return True

    def move(self, ent, dx, dy):
        """Move an entity, sliding along walls (each axis checked separately)."""
        if dx and self.circle_free(ent.x + dx, ent.y, ent.radius):
            ent.x += dx
        if dy and self.circle_free(ent.x, ent.y + dy, ent.radius):
            ent.y += dy

    def damage_barricade(self, x, y, amount):
        """Returns True if the barricade broke."""
        if self.tile(x, y) != BARRICADE:
            return False
        self.barricade_hp[(x, y)] -= amount
        if self.barricade_hp[(x, y)] <= 0:
            del self.barricade_hp[(x, y)]
            self.tiles[y][x] = STREET
            return True
        return False


def circle_hits_tile(cx, cy, r, tx, ty):
    """Circle vs. square tile overlap test."""
    nx = min(max(cx, tx), tx + 1)
    ny = min(max(cy, ty), ty + 1)
    return (cx - nx) ** 2 + (cy - ny) ** 2 < r * r


# ======================================================================
#  Entities
# ======================================================================
class Entity:
    def __init__(self, x, y, radius):
        self.x, self.y, self.radius = x, y, radius

    @property
    def tile(self):
        return (int(self.x), int(self.y))


class Player(Entity):
    def __init__(self, x, y, barricades):
        super().__init__(x, y, PLAYER_RADIUS)
        self.hp = PLAYER_MAX_HP
        self.stamina = STAMINA_MAX
        self.exhausted = False
        self.facing = (1.0, 0.0)       # for drawing
        self.place_dir = (1, 0)        # grid direction for barricades
        self.invulnerable = 0.0
        self.noise_timer = 0.0
        self.barricades = barricades
        self.bottles = 0
        self.flashlight = False        # Level 3
        self.battery = BATTERY_MAX
        self.moving = False
        self.running = False
        self.terrain = STREET          # tile type under the player's feet
        self.vx = self.vy = 0.0        # smoothed velocity (the Hunter reads this)

    @property
    def in_water(self):
        return self.terrain == WATER

    @property
    def noise_level(self):
        if not self.moving:
            return 0.0
        base = NOISE_RUN if self.running else NOISE_WALK
        if self.in_water:
            return max(base, NOISE_SPLASH)
        return base


class Zombie(Entity):
    _next_id = 0

    def __init__(self, x, y, kind="normal"):
        super().__init__(x, y, ZOMBIE_KINDS[kind]["radius"])
        Zombie._next_id += 1
        self.id = Zombie._next_id
        self.kind = kind
        self.state = WANDER
        self.path = None           # list of tiles; None = needs (re)planning
        self.target = None         # goal tile of current path
        self.last_seen = None      # player position last time we saw them
        self.last_vel = (0.0, 0.0) # player velocity last time we saw them (Hunter)
        self.intercept = None      # Hunter: predicted cut-off point (for drawing)
        self.lose_timer = 0.0
        self.repath_timer = 0.0
        self.look_timer = 0.0
        self.pause_timer = 0.0
        self.stuck_timer = 0.0
        self.scream_timer = 0.0    # Screamer cooldown
        self.attacking = False
        self.stun = 0.0            # seconds frozen after biting
        self.wobble = random.random() * math.tau   # for drawing animation

    @property
    def stats(self):
        return ZOMBIE_KINDS[self.kind]

    def hear(self, noise):
        """React to a noise event. Chasing zombies ignore noises."""
        if self.state == CHASE:
            return
        goal = (int(noise.tx), int(noise.ty))
        if self.state != INVESTIGATE or goal != self.target:
            self.state = INVESTIGATE
            self.target = goal
            self.path = None
            self.look_timer = 0.0
            self.pause_timer = 0.0


class Noise:
    def __init__(self, x, y, radius, kind, target=None):
        self.x, self.y, self.radius, self.kind = x, y, radius, kind
        self.tx, self.ty = target if target else (x, y)
        self.age = 0.0


class Crate:
    def __init__(self, x, y, kind):
        # kind: "radio" (the level's objective item), "barricade", "medkit" or "bottles"
        self.x, self.y, self.kind = x, y, kind


class Bottle:
    """A thrown bottle flying in an arc towards where it will smash."""

    def __init__(self, sx, sy, tx, ty, car=None):
        self.sx, self.sy, self.tx, self.ty = sx, sy, tx, ty
        self.car = car             # the car it will hit, if any
        self.t = 0.0
        self.duration = max(0.2, dist(sx, sy, tx, ty) / BOTTLE_SPEED)

    @property
    def pos(self):
        f = min(1.0, self.t / self.duration)
        return self.sx + (self.tx - self.sx) * f, self.sy + (self.ty - self.sy) * f

    @property
    def height(self):
        f = min(1.0, self.t / self.duration)
        return 4 * f * (1 - f)     # 0 -> 1 -> 0 arc, for drawing


# ======================================================================
#  Game
# ======================================================================
class Game:
    def __init__(self, difficulty="Normal", seed=None, level=1):
        self.rng = random.Random(seed)
        self.difficulty = difficulty
        self.diff = dict(DIFFICULTY[difficulty])
        self.level = level
        self.cfg = LEVELS[level]
        self.exit_mode = self.cfg["exit"]
        self.diff["sight"] += self.cfg.get("sight_bonus", 0.0)
        self.map = CityMap(self.cfg["w"], self.cfg["h"], self.rng, self.cfg["theme"])
        sx, sy = self.map.start
        self.player = Player(sx + 0.5, sy + 0.5,
                             self.diff["barricades"] + self.cfg.get("bonus_barricades", 0))
        self.player.bottles = self.cfg.get("bottles", 0)
        self.parts_needed = self.cfg["items"]
        self.barricade_hp = BARRICADE_HP * self.cfg.get("barricade_hp_mult", 1.0)

        self.zombies = []
        self.noises = []
        self.crates = []
        self.bottles = []           # bottles in flight
        self.messages = []          # [text, seconds_left]
        self.events = []            # sound/effect events for the front end, e.g. "bite"
        self.time = 0.0
        self.state = "playing"      # "playing", "won", "lost"
        self.reason = ""
        # Exit state machine (named after the helicopter, but shared by every exit):
        #   "waiting" (collect items) -> "incoming" (countdown) -> "landed" (board it) -> "gone"
        self.heli_state = "waiting"
        self.heli_arrive_at = None
        if self.exit_mode == "checkpoint":
            self.heli_state = "landed"           # open from the start, never leaves
        elif self.exit_mode == "survive":
            self.heli_state = "incoming"
            self.heli_arrive_at = self.cfg["survive_time"]
        self.parts_collected = 0
        self.heli_noise_timer = 0.0
        self.board_progress = 0.0
        spawn_mult = SPAWN_MULT.get(difficulty, 1.0)
        self.spawn_interval = self.cfg.get("spawn_interval", ZOMBIE_SPAWN_INTERVAL) * spawn_mult
        self.spawn_timer = self.spawn_interval
        self.max_zombies = int(self.diff["max_zombies"] * self.cfg.get("max_mult", 1.0)) \
            + self.cfg.get("extra_zombies", 0)
        self.fog_timer = 0.0
        self.visible = set()
        self.explored = set()
        self.stats = {"nodes_expanded": 0, "paths_planned": 0, "times_spotted": 0,
                      "bites": 0, "barricades_used": 0, "barricades_broken": 0,
                      "distance": 0.0, "crates": 0, "bottles_thrown": 0, "alarms": 0,
                      "screams": 0}

        self.update_fog()
        count = self.diff["zombies"] + self.cfg.get("extra_zombies", 0)
        for kind in self.cfg.get("start_kinds", []):
            # Level 5: a Hunter and a Runner from the start; Brutes and Screamers arrive in waves
            self.spawn_zombie(kind)
            count -= 1
        for _ in range(max(0, count)):
            self.spawn_zombie()
        self._place_sleepers(self.cfg.get("sleepers", 0))
        self._place_crates()
        self.say(self.objective_hint, 5)

    # ------------------------------------------------------------------
    #  Level text helpers
    # ------------------------------------------------------------------
    @property
    def exit_name(self):
        return {"heli": "helicopter", "boat": "rescue boat", "checkpoint": "checkpoint",
                "survive": "helicopter", "elevator": "elevator"}[self.exit_mode]

    @property
    def dark(self):
        return self.cfg.get("dark", False)

    def in_beam(self, x, y):
        """True if map point (x, y) is inside the flashlight cone."""
        p = self.player
        if not (self.dark and p.flashlight):
            return False
        dx, dy = x - p.x, y - p.y
        d = math.hypot(dx, dy)
        if d > FLASH_RANGE:
            return False
        if d < 0.8:
            return True
        cos = (dx * p.facing[0] + dy * p.facing[1]) / d
        return cos >= math.cos(FLASH_ANGLE)

    @property
    def view_radius(self):
        return DARK_VIEW_RADIUS if self.dark else VIEW_RADIUS

    @property
    def objective_hint(self):
        if self.exit_mode == "checkpoint":
            return "Sneak across the bridge to the military checkpoint!"
        if self.exit_mode == "survive":
            return f"Hold the safe zone for {int(self.cfg['survive_time'])}s!"
        return f"Find {self.parts_needed} {self.cfg['item']}s to call the {self.exit_name}. Stay quiet!"

    @property
    def in_safe_zone(self):
        return self.player.tile in self.map.safe_zone

    @property
    def exit_progress(self):
        """Level 4: how far across the bridge you are (0..1)."""
        ex = min(t[0] for t in self.map.helipad)
        sx = self.map.start[0]
        return max(0.0, min(1.0, (self.player.x - sx) / max(1, ex - sx)))

    # ------------------------------------------------------------------
    #  Main update
    # ------------------------------------------------------------------
    def update(self, dt, move=(0, 0), run=False, place=False, throw=None, alarm=False,
               flashlight=False):
        """throw: None, or an (x, y) map position to throw a bottle at.
        alarm: True to set off a car alarm next to the player.
        flashlight: True to switch the flashlight on/off (Level 3)."""
        if self.state != "playing":
            return
        dt = min(dt, 0.05)          # avoid huge jumps if the window lags
        self.time += dt

        self._update_player(dt, move, run, place)
        if throw is not None:
            self.throw_bottle(*throw)
        if alarm:
            self.trigger_alarm()
        if flashlight:
            self.toggle_flashlight()
        self._update_bottles(dt)
        self._update_alarms(dt)
        self._update_zombies(dt)
        self._check_bites()
        self._update_helicopter(dt)
        self._update_spawning(dt)

        for n in self.noises:
            n.age += dt
        self.noises = [n for n in self.noises if n.age < NOISE_VISUAL_TIME]
        for m in self.messages:
            m[1] -= dt
        self.messages = [m for m in self.messages if m[1] > 0]

        self.fog_timer -= dt
        if self.fog_timer <= 0:
            self.update_fog()
            self.fog_timer = FOG_UPDATE_INTERVAL

    # ------------------------------------------------------------------
    #  Player
    # ------------------------------------------------------------------
    def _update_player(self, dt, move, run, place):
        p = self.player
        dx, dy = move
        length = math.hypot(dx, dy)
        if length:
            dx, dy = dx / length, dy / length
        p.moving = length > 0
        p.terrain = self.map.tile(*p.tile)

        # Stamina / running
        if p.exhausted and p.stamina >= STAMINA_MIN_TO_RUN:
            p.exhausted = False
        p.running = run and p.moving and not p.exhausted and p.stamina > 0
        if p.running:
            p.stamina -= STAMINA_DRAIN * dt
            if p.stamina <= 0:
                p.stamina = 0
                p.exhausted = True
                self.say("Out of breath!", 1.5)
        else:
            p.stamina = min(STAMINA_MAX, p.stamina + STAMINA_REGEN * dt)

        speed = (PLAYER_RUN_SPEED if p.running else PLAYER_WALK_SPEED) * self.map.speed_factor(*p.tile)
        old = (p.x, p.y)
        if p.moving:
            self.map.move(p, dx * speed * dt, dy * speed * dt)
            self.stats["distance"] += dist(old[0], old[1], p.x, p.y)
            p.facing = (dx, dy)
            if abs(dx) >= abs(dy):
                p.place_dir = (1 if dx > 0 else -1, 0)
            else:
                p.place_dir = (0, 1 if dy > 0 else -1)
        # smoothed real velocity (walls and water included) for the Hunter's prediction
        if dt > 0:
            k = min(1.0, dt * 8)
            p.vx += ((p.x - old[0]) / dt - p.vx) * k
            p.vy += ((p.y - old[1]) / dt - p.vy) * k

        # Footstep noise (splashes in water)
        p.noise_timer -= dt
        if p.moving and p.noise_timer <= 0:
            if p.in_water:
                self.emit_noise(p.x, p.y, p.noise_level, "splash")
                self.events.append("splash")
            else:
                self.emit_noise(p.x, p.y, p.noise_level, "step")
            p.noise_timer = NOISE_INTERVAL

        if p.invulnerable > 0:
            p.invulnerable -= dt

        # Flashlight battery
        if p.flashlight:
            p.battery -= BATTERY_DRAIN * dt
            if p.battery <= 0:
                p.battery = 0.0
                p.flashlight = False
                self.fog_timer = 0.0
                self.say("Flashlight battery is dead!", 2)

        # Supply crates
        item = self.cfg["item"] or "item"
        for c in self.crates[:]:
            if p.tile == (c.x, c.y):
                self.crates.remove(c)
                self.stats["crates"] += 1
                self.events.append("radio" if c.kind == "radio" else "pickup")
                if c.kind == "radio":
                    self.parts_collected += 1
                    if self.parts_collected >= self.parts_needed:
                        self.heli_state = "incoming"
                        self.heli_arrive_at = self.time + HELI_CALL_TIME
                        if self.exit_mode == "boat":
                            self.say(f"Fuel ready! The boat reaches the dock in {int(HELI_CALL_TIME)}s", 3)
                        elif self.exit_mode == "elevator":
                            self.say(f"Power restored! The elevator arrives in {int(HELI_CALL_TIME)}s", 3)
                        else:
                            self.say(f"Radio fixed! Helicopter lands in {int(HELI_CALL_TIME)}s", 3)
                    else:
                        self.say(f"{item.capitalize()} {self.parts_collected}/{self.parts_needed}", 2)
                elif c.kind == "medkit" and p.hp < PLAYER_MAX_HP:
                    p.hp += 1
                    self.say("Medkit! +1 health", 2)
                elif c.kind == "bottles":
                    p.bottles += 2
                    self.say("Found bottles! +2", 2)
                elif c.kind == "battery":
                    p.battery = min(BATTERY_MAX, p.battery + BATTERY_PICKUP)
                    self.say("Batteries! Flashlight recharged", 2)
                else:
                    p.barricades += 2
                    self.say("Supplies! +2 barricades", 2)

        if place:
            self.try_place_barricade()

    def barricade_target(self):
        """The tile a barricade would go on, plus (ok, reason). Used for the preview too."""
        p = self.player
        px, py = p.tile
        tx, ty = px + p.place_dir[0], py + p.place_dir[1]
        if p.barricades <= 0:
            return (tx, ty), False, "No barricades left"
        if self.map.tile(tx, ty) not in (STREET, MUD) or (tx, ty) in self.map.helipad:
            return (tx, ty), False, "Can't place a barricade there"
        if any(circle_hits_tile(z.x, z.y, z.radius, tx, ty) for z in self.zombies):
            return (tx, ty), False, "A zombie is in the way!"
        if any((c.x, c.y) == (tx, ty) for c in self.crates):
            return (tx, ty), False, "Can't place a barricade on supplies"
        return (tx, ty), True, ""

    def try_place_barricade(self):
        p = self.player
        (tx, ty), ok, reason = self.barricade_target()
        if not ok:
            self.say(reason, 1.5)
            return False
        px, py = p.tile
        # If the player is leaning into that tile, step them back to their tile centre.
        if circle_hits_tile(p.x, p.y, p.radius, tx, ty):
            if p.place_dir[0]:
                p.x = px + 0.5
            else:
                p.y = py + 0.5

        self.map.tiles[ty][tx] = BARRICADE
        self.map.barricade_hp[(tx, ty)] = self.barricade_hp
        p.barricades -= 1
        self.stats["barricades_used"] += 1
        self.emit_noise(tx + 0.5, ty + 0.5, NOISE_BARRICADE, "barricade")
        self.events.append("place")
        # Paths that went through this tile are now outdated.
        for z in self.zombies:
            if z.path and (tx, ty) in z.path:
                z.path = None
        return True

    # ------------------------------------------------------------------
    #  Bottles and car alarms (distractions that use the noise system)
    # ------------------------------------------------------------------
    def bottle_landing(self, tx, ty):
        """Where a bottle aimed at (tx, ty) would land, and the car it hits (or None).
        Bottles fly over barricades but stop at buildings and smash on cars."""
        p = self.player
        dx, dy = tx - p.x, ty - p.y
        d = math.hypot(dx, dy)
        if d < 0.5:                                  # no real aim: throw straight ahead
            dx, dy, d = p.facing[0], p.facing[1], 1.0
            dx, dy = dx * BOTTLE_RANGE * 0.7, dy * BOTTLE_RANGE * 0.7
            d = math.hypot(dx, dy)
        if d > BOTTLE_RANGE:
            dx, dy, d = dx / d * BOTTLE_RANGE, dy / d * BOTTLE_RANGE, BOTTLE_RANGE
        land = (p.x, p.y)
        steps = max(1, int(d / 0.1))
        for i in range(1, steps + 1):
            x, y = p.x + dx * i / steps, p.y + dy * i / steps
            tile = self.map.tile(int(x), int(y))
            if tile == CAR:
                return (x, y), self.map.car_at.get((int(x), int(y)))
            if tile == BUILDING:
                break
            land = (x, y)
        return land, None

    def throw_bottle(self, tx, ty):
        p = self.player
        if p.bottles <= 0:
            self.say("No bottles left", 1.2)
            return False
        (lx, ly), car = self.bottle_landing(tx, ty)
        p.bottles -= 1
        self.stats["bottles_thrown"] += 1
        self.bottles.append(Bottle(p.x, p.y, lx, ly, car))
        self.events.append("throw")
        return True

    def _update_bottles(self, dt):
        for b in self.bottles[:]:
            b.t += dt
            if b.t >= b.duration:
                self.bottles.remove(b)
                self.events.append("glass")
                self.emit_noise(b.tx, b.ty, NOISE_BOTTLE, "glass")
                if b.car is not None:
                    self._start_alarm(b.car)

    def car_in_reach(self):
        p = self.player
        for car in self.map.cars:
            if car.alarm_used:
                continue
            for (cx, cy) in car.tiles:
                nx = min(max(p.x, cx), cx + 1)
                ny = min(max(p.y, cy), cy + 1)
                if dist(p.x, p.y, nx, ny) <= ALARM_REACH:
                    return car
        return None

    def trigger_alarm(self):
        car = self.car_in_reach()
        if car is None:
            if self.map.cars:
                self.say("Stand next to a car to set off its alarm", 1.5)
            return False
        self._start_alarm(car)
        return True

    def _start_alarm(self, car):
        if car.alarm_used:
            return
        car.alarm_used = True
        car.alarm_time = CAR_ALARM_TIME
        car.noise_timer = 0.0
        self.stats["alarms"] += 1
        self.events.append("alarm")
        self.say("Car alarm! The horde is drawn to it...", 2)

    def _update_alarms(self, dt):
        for car in self.map.cars:
            if car.alarm_time <= 0:
                continue
            car.alarm_time -= dt
            car.noise_timer -= dt
            if car.noise_timer <= 0:
                cx, cy = car.centre
                self.emit_noise(cx, cy, NOISE_ALARM, "alarm")
                car.noise_timer = CAR_ALARM_INTERVAL

    # ------------------------------------------------------------------
    #  Noise and perception
    # ------------------------------------------------------------------
    def emit_noise(self, x, y, radius, kind, target=None):
        if radius <= 0:
            return
        n = Noise(x, y, radius, kind, target)
        self.noises.append(n)
        for z in self.zombies:
            # Sleepers only hear noises that are close (and loud) enough.
            reach = radius * (SLEEP_HEARING if z.state == SLEEP else 1.0)
            if dist(z.x, z.y, x, y) <= reach:
                was_asleep = z.state == SLEEP
                z.hear(n)
                if was_asleep:
                    self._woke_up(z)

    def _woke_up(self, z):
        self.stats["woken"] = self.stats.get("woken", 0) + 1
        if z.tile in self.visible:
            self.events.append("wake")
            self.say("You woke a sleeping zombie!", 1.5)

    def toggle_flashlight(self):
        p = self.player
        if not self.dark:
            return False
        if not p.flashlight and p.battery <= 0:
            self.say("The flashlight battery is dead", 1.5)
            return False
        p.flashlight = not p.flashlight
        self.events.append("click")
        self.fog_timer = 0.0           # update what you can see right away
        return True

    def sight_range(self, z):
        r = self.diff["sight"] * z.stats["sight"]
        if self.dark:
            r *= LIGHT_SIGHT if self.player.flashlight else DARK_SIGHT
        return r

    def zombie_senses_player(self, z):
        p = self.player
        d = dist(z.x, z.y, p.x, p.y)
        if d <= SMELL_RANGE:
            return True
        return d <= self.sight_range(z) and self.map.line_of_sight(z.x, z.y, p.x, p.y)

    def update_fog(self):
        p = self.player
        base = self.view_radius
        r = max(base, FLASH_RANGE) if self.in_beam(p.x, p.y) else base
        vis = set()
        for ty in range(int(p.y - r) - 1, int(p.y + r) + 2):
            for tx in range(int(p.x - r) - 1, int(p.x + r) + 2):
                if not self.map.in_bounds(tx, ty):
                    continue
                cx, cy = tx + 0.5, ty + 0.5
                d = dist(p.x, p.y, cx, cy)
                if (d <= base or self.in_beam(cx, cy)) and \
                        self.map.line_of_sight(p.x, p.y, cx, cy, ignore=(tx, ty)):
                    vis.add((tx, ty))
        self.visible = vis
        self.explored |= vis

    # ------------------------------------------------------------------
    #  Zombie AI (Finite State Machine)
    # ------------------------------------------------------------------
    def plan_path(self, z, goal):
        path, expanded = astar(z.tile, goal, self.map.cost_for(z.kind), self.map.w, self.map.h)
        self.stats["nodes_expanded"] += expanded
        self.stats["paths_planned"] += 1
        z.target = goal
        z.path = path if path is not None else []
        return path is not None

    def _walkable_goal(self, x, y):
        t = (int(x), int(y))
        return t in self.map.reachable and not self.map.is_solid(*t)

    def predict_intercept(self, z):
        """Hunter AI: where will the player be when I get there?

        1. Dead-reckon the player's current position from where they were last
           seen plus their velocity (even after they duck out of sight).
        2. Look ahead T seconds, where T is roughly how long the hunter needs
           to get there (distance / speed), capped at HUNTER_MAX_LOOKAHEAD.
        3. If that point is inside a wall, slide it back towards the player
           until it's on a reachable tile. A* then plans to THAT tile.
        """
        lx, ly = z.last_seen
        vx, vy = z.last_vel
        gone = min(z.lose_timer, 1.5)
        ex, ey = lx + vx * gone, ly + vy * gone          # estimated position now
        if not self._walkable_goal(ex, ey):
            ex, ey = lx, ly
        speed = math.hypot(vx, vy)
        d = dist(z.x, z.y, ex, ey)
        if speed < 0.4 or d < HUNTER_DIRECT_RANGE:
            return ex, ey
        my_speed = max(0.5, self.diff["chase"] * z.stats["chase"])
        look = min(HUNTER_MAX_LOOKAHEAD, d / my_speed)
        for i in range(10, 0, -1):
            f = i / 10
            px, py = ex + vx * look * f, ey + vy * look * f
            if self._walkable_goal(px, py) and \
                    self.map.line_of_sight(ex, ey, px, py):
                return px, py
        return ex, ey

    def _scream(self, z):
        """Screamer: every zombie on the map learns where the player is."""
        p = self.player
        z.scream_timer = SCREAM_COOLDOWN
        self.stats["screams"] += 1
        self.events.append("scream")
        alert = Noise(z.x, z.y, 8.0, "scream", target=(p.x, p.y))
        self.noises.append(alert)
        for o in self.zombies:
            if o is not z:
                o.hear(alert)
        self.say("A SCREAMER spotted you - the whole horde is coming!", 2.5)

    def _update_zombies(self, dt):
        p = self.player
        self._barricade_hits = {}
        for z in self.zombies:
            z.attacking = False
            k = z.stats
            if z.scream_timer > 0:
                z.scream_timer -= dt
            if z.stun > 0:                 # busy "feeding" after a bite
                z.stun -= dt
                continue
            if z.state == SLEEP:
                # Asleep: blind, half-deaf (see emit_noise). Bumping into it wakes it up.
                if dist(z.x, z.y, p.x, p.y) <= SLEEP_WAKE_DIST:
                    z.state = WANDER
                    self._woke_up(z)
                else:
                    continue
            terrain = self.map.speed_factor(*z.tile)
            sees = self.zombie_senses_player(z)
            # ---- 1. Perception -> state transitions ----
            if sees:
                z.last_seen = (p.x, p.y)
                z.last_vel = (p.vx, p.vy)
                z.lose_timer = 0.0
                if z.state != CHASE:
                    z.state = CHASE
                    z.path = None
                    self.stats["times_spotted"] += 1
                    if z.tile in self.visible:
                        self.events.append("spotted")
                    if z.kind != "screamer":
                        # Groan: nearby zombies come to help (group hunting).
                        self.emit_noise(z.x, z.y, NOISE_GROAN, "groan", target=(p.x, p.y))
                if z.kind == "screamer" and z.scream_timer <= 0:
                    self._scream(z)
            elif z.state == CHASE:
                z.lose_timer += dt
                if z.lose_timer >= k["lose"]:
                    z.path = None
                    z.intercept = None
                    if z.kind == "runner":          # runners lose interest completely
                        z.state = WANDER
                        z.pause_timer = self.rng.uniform(0.5, 1.5)
                    else:
                        z.state = INVESTIGATE
                        z.target = (int(z.last_seen[0]), int(z.last_seen[1]))
                        z.look_timer = 0.0

            # ---- 2. Behaviour for the current state ----
            speed = 0.0
            if z.state == CHASE:
                if z.kind == "hunter":
                    gx, gy = self.predict_intercept(z)
                    z.intercept = (gx, gy)
                else:
                    gx, gy = z.last_seen
                goal = (int(gx), int(gy))
                z.repath_timer -= dt
                if z.path is None or z.repath_timer <= 0 or goal != z.target:
                    self.plan_path(z, goal)
                    z.repath_timer = REPATH_INTERVAL
                speed = self.diff["chase"] * k["chase"] * terrain
                if z.kind == "screamer" and sees and dist(z.x, z.y, p.x, p.y) < SCREAMER_KEEP_DIST:
                    speed = 0.0                     # hang back and keep watching
                if not z.path:      # standing on the goal tile: step straight at them
                    tx, ty = z.last_seen if z.kind != "hunter" or sees else (gx, gy)
                    self._step_towards(z, tx, ty, speed, dt)
                    continue

            elif z.state == INVESTIGATE:
                if z.path is None:
                    self.plan_path(z, z.target)
                if not z.path:
                    z.look_timer += dt          # arrived: look around
                    look_time = INVESTIGATE_LOOK_TIME * (0.4 if z.kind == "runner" else 1.0)
                    if z.look_timer >= look_time:
                        z.state = WANDER
                        z.path = None
                        z.pause_timer = self.rng.uniform(0.5, 1.5)
                else:
                    speed = self.diff["investigate"] * k["wander"] * terrain

            else:  # WANDER
                if z.pause_timer > 0:
                    z.pause_timer -= dt
                elif not z.path:
                    goal = self._random_nearby_street(z, 6)
                    if goal is None or not self.plan_path(z, goal):
                        z.pause_timer = 1.0
                    elif not z.path:
                        z.pause_timer = self.rng.uniform(0.5, 2.0)
                else:
                    speed = self.diff["wander"] * k["wander"] * terrain

            self._follow_path(z, speed, dt)

    def _random_nearby_street(self, z, radius):
        zx, zy = z.tile
        for _ in range(20):
            tx = zx + self.rng.randint(-radius, radius)
            ty = zy + self.rng.randint(-radius, radius)
            if (tx, ty) != (zx, zy) and (tx, ty) in self.map.reachable and self.map.tile(tx, ty) == STREET:
                return (tx, ty)
        return None

    def _follow_path(self, z, speed, dt):
        """Walk along the A* path, attacking barricades that block it."""
        vx = vy = 0.0
        if z.path and speed > 0:
            if z.path[0] == z.tile and len(z.path) > 1:
                z.path.pop(0)
            nx, ny = z.path[0]
            if self.map.tile(nx, ny) == BARRICADE and z.state == WANDER:
                z.path = None          # aimless zombies don't bother smashing: pick another stroll
                z.pause_timer = self.rng.uniform(0.3, 1.0)
                self._apply_movement(z, 0.0, 0.0, dt)
                return
            if self.map.tile(nx, ny) == BARRICADE:
                zx, zy = z.tile
                if abs(nx - zx) + abs(ny - zy) == 1:
                    z.attacking = True
                    # Brutes smash a barricade in one blow.
                    # Only two zombies fit at a barricade, so damage stops stacking after two.
                    hits = self._barricade_hits.get((nx, ny), 0)
                    self._barricade_hits[(nx, ny)] = hits + 1
                    damage = 1e9 if z.kind == "brute" else (dt if hits < MAX_BARRICADE_ATTACKERS else 0.0)
                    if self.map.damage_barricade(nx, ny, damage):
                        self.stats["barricades_broken"] += 1
                        self.events.append("crash")
                        self.emit_noise(nx + 0.5, ny + 0.5, NOISE_BARRICADE, "crash")
                        if (nx, ny) in self.visible:
                            self.say("A BRUTE smashed a barricade!" if z.kind == "brute"
                                     else "A barricade was smashed!", 1.5)
                    # drift to own tile centre while hitting
                    self._step_towards(z, zx + 0.5, zy + 0.5, speed * 0.5, dt, flock=False)
                    return
                else:
                    z.path = None     # we drifted off the path; replan next frame
                    return
            if self.map.is_solid(nx, ny):
                z.path = None         # a car or wall is in the way (map changed): replan
                return
            tx, ty = nx + 0.5, ny + 0.5
            d = dist(z.x, z.y, tx, ty)
            if d < 0.12:
                z.path.pop(0)
            else:
                vx, vy = (tx - z.x) / d * speed, (ty - z.y) / d * speed
        self._apply_movement(z, vx, vy, dt, expected=speed)

    def _step_towards(self, z, tx, ty, speed, dt, flock=True):
        d = dist(z.x, z.y, tx, ty)
        vx = vy = 0.0
        if d > 0.05:
            vx, vy = (tx - z.x) / d * speed, (ty - z.y) / d * speed
        self._apply_movement(z, vx, vy, dt, expected=speed if d > 0.05 else 0, flock=flock)

    def _apply_movement(self, z, vx, vy, dt, expected=0.0, flock=True):
        """Add flocking forces, move with wall collisions, and detect getting stuck."""
        if flock:
            sx = sy = 0.0      # separation
            cx = cy = 0.0      # cohesion
            n = 0
            for o in self.zombies:
                if o is z:
                    continue
                d = dist(z.x, z.y, o.x, o.y)
                sep = ZOMBIE_SEPARATION + (z.radius + o.radius - 2 * ZOMBIE_RADIUS)
                if 0 < d < sep:
                    push = (sep - d) / sep * 2.5
                    sx += (z.x - o.x) / d * push
                    sy += (z.y - o.y) / d * push
                elif d == 0:
                    sx += self.rng.uniform(-1, 1)
                    sy += self.rng.uniform(-1, 1)
                if d < ZOMBIE_COHESION_RANGE:
                    cx += o.x
                    cy += o.y
                    n += 1
            vx += sx
            vy += sy
            if n and z.state == WANDER and expected > 0:
                cx, cy = cx / n - z.x, cy / n - z.y
                cd = math.hypot(cx, cy)
                if cd > 1.0:
                    vx += cx / cd * 0.3
                    vy += cy / cd * 0.3

        old_x, old_y = z.x, z.y
        self.map.move(z, vx * dt, vy * dt)
        moved = dist(old_x, old_y, z.x, z.y)
        if expected > 0 and moved < expected * dt * 0.25:
            z.stuck_timer += dt
            if z.stuck_timer > 0.6:
                z.stuck_timer = 0.0
                z.path = None                       # replan
                # snap back towards the tile centre to get unstuck
                tx, ty = z.tile
                self.map.move(z, (tx + 0.5 - z.x) * 0.5, (ty + 0.5 - z.y) * 0.5)
        else:
            z.stuck_timer = 0.0

    # ------------------------------------------------------------------
    #  Combat, exit, spawning
    # ------------------------------------------------------------------
    def _check_bites(self):
        p = self.player
        for z in self.zombies:
            damage = z.stats["damage"]
            if damage <= 0:                 # screamers never bite
                continue
            d = dist(z.x, z.y, p.x, p.y)
            reach = ZOMBIE_TOUCH_DIST + (z.radius - ZOMBIE_RADIUS)
            if d < reach and p.invulnerable <= 0:
                p.hp -= damage
                p.invulnerable = INVULNERABLE_TIME
                z.stun = ZOMBIE_BITE_STUN
                self.stats["bites"] += 1
                self.events.append("bite")
                if p.hp <= 0:
                    p.hp = 0
                    self.state = "lost"
                    self.events.append("lose")
                    self.reason = "A Brute crushed you." if z.kind == "brute" else "You were caught by the horde."
                    return
                self.say("A BRUTE hit you! -2" if damage > 1 else "Bitten! Run!", 1.5)
                # knock the player back
                if d > 0:
                    kx, ky = (p.x - z.x) / d, (p.y - z.y) / d
                    for _ in range(5 * damage):
                        self.map.move(p, kx * 0.12, ky * 0.12)

    def _update_helicopter(self, dt):
        p = self.player
        if self.heli_state == "incoming":
            # Level 5: the radio only works inside the safe zone - the clock pauses outside it.
            if self.exit_mode == "survive" and not self.in_safe_zone:
                self.heli_arrive_at += dt
            if self.time >= self.heli_arrive_at:
                self.heli_state = "landed"
                self.events.append("heli")
                if self.exit_mode == "boat":
                    self.say("The boat is at the dock! GET ON BOARD!", 3)
                elif self.exit_mode == "elevator":
                    self.say("Ding! The elevator is here - GET IN!", 3)
                else:
                    self.say("The helicopter has landed! GET TO THE HELIPAD!", 3)
        if self.heli_state != "landed":
            return

        hx = sum(t[0] for t in self.map.helipad) / len(self.map.helipad) + 0.5
        hy = sum(t[1] for t in self.map.helipad) / len(self.map.helipad) + 0.5
        if self.exit_mode != "checkpoint":
            self.heli_noise_timer -= dt
            if self.heli_noise_timer <= 0:
                self.emit_noise(hx, hy, NOISE_ELEVATOR if self.exit_mode == "elevator" else NOISE_HELICOPTER,
                                "heli")
                self.heli_noise_timer = HELI_NOISE_INTERVAL

        board_time = self.board_time
        if p.tile in self.map.helipad:
            self.board_progress += dt
            if self.board_progress >= board_time:
                self.state = "won"
                self.events.append("win")
                self.reason = {"heli": "You escaped on the helicopter!",
                               "boat": "You sailed away on the rescue boat!",
                               "checkpoint": "The soldiers let you through. You're safe!",
                               "survive": "You held the line and escaped!",
                               "elevator": "The elevator carried you to the roof. Escaped!"}[self.exit_mode]
                return
        else:
            self.board_progress = max(0.0, self.board_progress - dt * 2)

        if self.heli_arrive_at is not None and self.time >= self.heli_arrive_at + HELI_WAIT_TIME:
            self.heli_state = "gone"
            self.state = "lost"
            self.events.append("lose")
            self.reason = f"The {self.exit_name} left without you."

    @property
    def board_time(self):
        return 1.0 if self.exit_mode == "checkpoint" else BOARD_TIME

    @property
    def heli_time_left(self):
        if self.heli_state == "waiting" or self.heli_arrive_at is None:
            return None
        if self.heli_state == "incoming":
            return max(0.0, self.heli_arrive_at - self.time)
        return max(0.0, self.heli_arrive_at + HELI_WAIT_TIME - self.time)

    def _update_spawning(self, dt):
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = self.spawn_interval
            if len(self.zombies) < self.max_zombies:
                self.spawn_zombie()

    def _free_street_tiles(self, min_player_dist):
        p = self.player
        out = []
        for (tx, ty) in self.map.reachable:
            if self.map.tile(tx, ty) != STREET or (tx, ty) in self.map.helipad:
                continue
            if (tx, ty) in self.visible or (tx, ty) in self.map.safe_zone:
                continue
            if dist(tx + 0.5, ty + 0.5, p.x, p.y) < min_player_dist:
                continue
            if any(dist(tx + 0.5, ty + 0.5, z.x, z.y) < 1.0 for z in self.zombies):
                continue
            out.append((tx, ty))
        out.sort()   # deterministic order for a given seed
        return out

    def _place_sleepers(self, n):
        """Level 3: zombies asleep on hospital beds, away from the start."""
        if n <= 0:
            return
        sx, sy = self.map.start
        beds = [b for b in self.map.beds
                if dist(b[0], b[1], sx, sy) >= 6 and b not in self.visible]
        self.rng.shuffle(beds)
        for (bx, by) in beds[:n]:
            z = Zombie(bx + 0.5, by + 0.5)
            z.state = SLEEP
            self.zombies.append(z)

    def _pick_kind(self):
        kinds = self.cfg.get("kinds")
        if not kinds:
            return "normal"
        names = sorted(kinds)
        return self.rng.choices(names, weights=[kinds[n] for n in names])[0]

    def spawn_zombie(self, kind=None):
        options = self._free_street_tiles(ZOMBIE_MIN_SPAWN_DIST)
        if not options:
            return None
        tx, ty = self.rng.choice(options)
        z = Zombie(tx + 0.5, ty + 0.5, kind or self._pick_kind())
        z.pause_timer = self.rng.uniform(0, 2)
        self.zombies.append(z)
        return z

    def _place_crates(self):
        """Objective items go far from the start and far from each other; supplies anywhere."""
        options = self._free_street_tiles(8)
        self.rng.shuffle(options)
        picked = []
        for min_gap in (8, 6, 4, 0):          # relax the spacing rule if the map is cramped
            for (x, y) in options:
                if len(picked) == self.parts_needed:
                    break
                if all(dist(x, y, a, b) >= min_gap for a, b in picked) and (x, y) not in picked:
                    picked.append((x, y))
        for (x, y) in picked:
            self.crates.append(Crate(x, y, "radio"))

        if self.map.safe_zone:
            # Level 5: supplies are scattered just outside the walls - risky runs.
            supply = [t for t in self._free_street_tiles(3) if dist(t[0], t[1], 14.5, 9.5) < 9]
        else:
            supply = [t for t in self._free_street_tiles(5) if t not in picked]
        self.rng.shuffle(supply)
        kinds = self.cfg.get("supplies", ["barricade", "medkit", "barricade", "medkit"])
        for i in range(min(NUM_CRATES, len(supply))):
            x, y = supply[i]
            self.crates.append(Crate(x, y, kinds[i]))

    # ------------------------------------------------------------------
    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    @property
    def nearest_radio_distance(self):
        p = self.player
        radios = [c for c in self.crates if c.kind == "radio"]
        if not radios:
            return None
        return min(dist(p.x, p.y, c.x + 0.5, c.y + 0.5) for c in radios)

    def say(self, text, seconds=2.0):
        self.messages.append([text, seconds])
        self.messages = self.messages[-3:]
