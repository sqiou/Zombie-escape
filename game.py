"""
game.py - all of Zombie Escape's rules and AI, with NO pygame code.

Keeping logic separate from drawing means:
  * it can be unit-tested without opening a window, and
  * the AI is easy to explain in a viva (everything is in one file).

AI concepts used here
---------------------
1. Finite State Machine (FSM)  - each zombie is WANDER, INVESTIGATE or CHASE.
2. A* search                   - zombies plan paths around buildings (pathfinding.py).
   Barricades have a higher path cost, so A* prefers going around them
   but will break through if that is still the cheapest route.
3. Perception                  - zombies SEE (sight range + line of sight)
                                 and HEAR (noise events with a radius).
4. Flocking                    - separation (don't overlap) + cohesion (stay as a horde).
5. Fog of war                  - the player only sees tiles in line of sight.
"""

import math
import random

from settings import *
from pathfinding import astar, bfs_reachable

# Tile types
STREET, BUILDING, BARRICADE = 0, 1, 2

# Zombie states
WANDER, INVESTIGATE, CHASE = "WANDER", "INVESTIGATE", "CHASE"

HELI_NOISE_INTERVAL = 3.0
FOG_UPDATE_INTERVAL = 0.08
NOISE_VISUAL_TIME = 0.9
NUM_CRATES = 4


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


# ======================================================================
#  Map
# ======================================================================
class CityMap:
    """A grid city: buildings (solid), streets, and player-placed barricades."""

    def __init__(self, width, height, rng):
        self.w, self.h = width, height
        self.rng = rng
        self.tiles = []              # tiles[y][x]
        self.barricade_hp = {}       # (x, y) -> remaining hp
        self.helipad = set()
        self.start = (1, 1)
        self.reachable = set()
        self.generate()

    # ---------- generation ----------
    def generate(self):
        for _ in range(50):
            self._build_layout()
            self.reachable = bfs_reachable(self.start, self.zombie_cost, self.w, self.h)
            if self.helipad <= self.reachable:
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

    # ---------- queries ----------
    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y][x] if self.in_bounds(x, y) else BUILDING

    def is_solid(self, x, y):
        """Blocks movement (buildings and barricades)."""
        return self.tile(x, y) != STREET

    def blocks_sight(self, x, y):
        """Only buildings block sight - barricades are low."""
        return self.tile(x, y) == BUILDING

    def zombie_cost(self, x, y):
        """A* step cost for zombies. None = impassable."""
        t = self.tile(x, y)
        if t == BUILDING:
            return None
        if t == BARRICADE:
            return BARRICADE_PATH_COST
        return 1

    def line_of_sight(self, ax, ay, bx, by, ignore=None):
        """True if no building lies on the straight line between two points."""
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
        self.moving = False
        self.running = False

    @property
    def noise_level(self):
        if self.running:
            return NOISE_RUN
        if self.moving:
            return NOISE_WALK
        return 0.0


class Zombie(Entity):
    _next_id = 0

    def __init__(self, x, y):
        super().__init__(x, y, ZOMBIE_RADIUS)
        Zombie._next_id += 1
        self.id = Zombie._next_id
        self.state = WANDER
        self.path = None           # list of tiles; None = needs (re)planning
        self.target = None         # goal tile of current path
        self.last_seen = None      # player position last time we saw them
        self.lose_timer = 0.0
        self.repath_timer = 0.0
        self.look_timer = 0.0
        self.pause_timer = 0.0
        self.stuck_timer = 0.0
        self.attacking = False
        self.stun = 0.0            # seconds frozen after biting
        self.wobble = random.random() * math.tau   # for drawing animation

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
        self.x, self.y, self.kind = x, y, kind      # kind: "barricade" or "medkit"


# ======================================================================
#  Game
# ======================================================================
class Game:
    def __init__(self, difficulty="Normal", seed=None):
        self.rng = random.Random(seed)
        self.difficulty = difficulty
        self.diff = DIFFICULTY[difficulty]
        self.map = CityMap(GRID_W, GRID_H, self.rng)
        sx, sy = self.map.start
        self.player = Player(sx + 0.5, sy + 0.5, self.diff["barricades"])

        self.zombies = []
        self.noises = []
        self.crates = []
        self.messages = []          # [text, seconds_left]
        self.events = []            # sound/effect events for the front end, e.g. "bite"
        self.time = 0.0
        self.state = "playing"      # "playing", "won", "lost"
        self.reason = ""
        self.heli_state = "waiting"    # "waiting" (need radio parts), "incoming", "landed", "gone"
        self.heli_arrive_at = None
        self.parts_collected = 0
        self.heli_noise_timer = 0.0
        self.board_progress = 0.0
        self.spawn_timer = ZOMBIE_SPAWN_INTERVAL
        self.fog_timer = 0.0
        self.visible = set()
        self.explored = set()
        self.stats = {"nodes_expanded": 0, "paths_planned": 0, "times_spotted": 0,
                      "bites": 0, "barricades_used": 0, "barricades_broken": 0,
                      "distance": 0.0, "crates": 0}

        self.update_fog()
        for _ in range(self.diff["zombies"]):
            self.spawn_zombie()
        self._place_crates()
        self.say(f"Find {RADIO_PARTS} radio parts to call the helicopter. Stay quiet!", 5)

    # ------------------------------------------------------------------
    #  Main update
    # ------------------------------------------------------------------
    def update(self, dt, move=(0, 0), run=False, place=False):
        if self.state != "playing":
            return
        dt = min(dt, 0.05)          # avoid huge jumps if the window lags
        self.time += dt

        self._update_player(dt, move, run, place)
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

        speed = PLAYER_RUN_SPEED if p.running else PLAYER_WALK_SPEED
        if p.moving:
            old = (p.x, p.y)
            self.map.move(p, dx * speed * dt, dy * speed * dt)
            self.stats["distance"] += dist(old[0], old[1], p.x, p.y)
            p.facing = (dx, dy)
            if abs(dx) >= abs(dy):
                p.place_dir = (1 if dx > 0 else -1, 0)
            else:
                p.place_dir = (0, 1 if dy > 0 else -1)

        # Footstep noise
        p.noise_timer -= dt
        if p.moving and p.noise_timer <= 0:
            self.emit_noise(p.x, p.y, p.noise_level, "step")
            p.noise_timer = NOISE_INTERVAL

        if p.invulnerable > 0:
            p.invulnerable -= dt

        # Supply crates
        for c in self.crates[:]:
            if p.tile == (c.x, c.y):
                self.crates.remove(c)
                self.stats["crates"] += 1
                self.events.append("radio" if c.kind == "radio" else "pickup")
                if c.kind == "radio":
                    self.parts_collected += 1
                    if self.parts_collected >= RADIO_PARTS:
                        self.heli_state = "incoming"
                        self.heli_arrive_at = self.time + HELI_CALL_TIME
                        self.say(f"Radio fixed! Helicopter lands in {int(HELI_CALL_TIME)}s", 3)
                    else:
                        self.say(f"Radio part {self.parts_collected}/{RADIO_PARTS}", 2)
                elif c.kind == "medkit" and p.hp < PLAYER_MAX_HP:
                    p.hp += 1
                    self.say("Medkit! +1 health", 2)
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
        if self.map.tile(tx, ty) != STREET or (tx, ty) in self.map.helipad:
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
        self.map.barricade_hp[(tx, ty)] = BARRICADE_HP
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
    #  Noise and perception
    # ------------------------------------------------------------------
    def emit_noise(self, x, y, radius, kind, target=None):
        if radius <= 0:
            return
        n = Noise(x, y, radius, kind, target)
        self.noises.append(n)
        for z in self.zombies:
            if dist(z.x, z.y, x, y) <= radius:
                z.hear(n)

    def zombie_senses_player(self, z):
        p = self.player
        d = dist(z.x, z.y, p.x, p.y)
        if d <= SMELL_RANGE:
            return True
        return d <= self.diff["sight"] and self.map.line_of_sight(z.x, z.y, p.x, p.y)

    def update_fog(self):
        p = self.player
        r = VIEW_RADIUS
        vis = set()
        for ty in range(int(p.y - r) - 1, int(p.y + r) + 2):
            for tx in range(int(p.x - r) - 1, int(p.x + r) + 2):
                if not self.map.in_bounds(tx, ty):
                    continue
                cx, cy = tx + 0.5, ty + 0.5
                if dist(p.x, p.y, cx, cy) <= r and self.map.line_of_sight(p.x, p.y, cx, cy, ignore=(tx, ty)):
                    vis.add((tx, ty))
        self.visible = vis
        self.explored |= vis

    # ------------------------------------------------------------------
    #  Zombie AI (Finite State Machine)
    # ------------------------------------------------------------------
    def plan_path(self, z, goal):
        path, expanded = astar(z.tile, goal, self.map.zombie_cost, self.map.w, self.map.h)
        self.stats["nodes_expanded"] += expanded
        self.stats["paths_planned"] += 1
        z.target = goal
        z.path = path if path is not None else []
        return path is not None

    def _update_zombies(self, dt):
        p = self.player
        for z in self.zombies:
            z.attacking = False
            if z.stun > 0:                 # busy "feeding" after a bite
                z.stun -= dt
                continue
            # ---- 1. Perception -> state transitions ----
            if self.zombie_senses_player(z):
                z.last_seen = (p.x, p.y)
                z.lose_timer = 0.0
                if z.state != CHASE:
                    z.state = CHASE
                    z.path = None
                    self.stats["times_spotted"] += 1
                    if z.tile in self.visible:
                        self.events.append("spotted")
                    # Groan: nearby zombies come to help (group hunting).
                    self.emit_noise(z.x, z.y, NOISE_GROAN, "groan", target=(p.x, p.y))
            elif z.state == CHASE:
                z.lose_timer += dt
                if z.lose_timer >= LOSE_SIGHT_TIME:
                    z.state = INVESTIGATE
                    z.target = (int(z.last_seen[0]), int(z.last_seen[1]))
                    z.path = None
                    z.look_timer = 0.0

            # ---- 2. Behaviour for the current state ----
            speed = 0.0
            if z.state == CHASE:
                goal = (int(z.last_seen[0]), int(z.last_seen[1]))
                z.repath_timer -= dt
                if z.path is None or z.repath_timer <= 0 or goal != z.target:
                    self.plan_path(z, goal)
                    z.repath_timer = REPATH_INTERVAL
                speed = self.diff["chase"]
                if not z.path:      # standing on the player's last tile: step straight at them
                    self._step_towards(z, z.last_seen[0], z.last_seen[1], speed, dt)
                    continue

            elif z.state == INVESTIGATE:
                if z.path is None:
                    self.plan_path(z, z.target)
                if not z.path:
                    z.look_timer += dt          # arrived: look around
                    if z.look_timer >= INVESTIGATE_LOOK_TIME:
                        z.state = WANDER
                        z.path = None
                        z.pause_timer = self.rng.uniform(0.5, 1.5)
                else:
                    speed = self.diff["investigate"]

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
                    speed = self.diff["wander"]

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
            if self.map.tile(nx, ny) == BARRICADE:
                zx, zy = z.tile
                if abs(nx - zx) + abs(ny - zy) == 1:
                    z.attacking = True
                    if self.map.damage_barricade(nx, ny, dt):
                        self.stats["barricades_broken"] += 1
                        self.events.append("crash")
                        self.emit_noise(nx + 0.5, ny + 0.5, NOISE_BARRICADE, "crash")
                        if (nx, ny) in self.visible:
                            self.say("A barricade was smashed!", 1.5)
                    # drift to own tile centre while hitting
                    self._step_towards(z, zx + 0.5, zy + 0.5, speed * 0.5, dt, flock=False)
                    return
                else:
                    z.path = None     # we drifted off the path; replan next frame
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
                if 0 < d < ZOMBIE_SEPARATION:
                    push = (ZOMBIE_SEPARATION - d) / ZOMBIE_SEPARATION * 2.5
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
    #  Combat, helicopter, spawning
    # ------------------------------------------------------------------
    def _check_bites(self):
        p = self.player
        for z in self.zombies:
            d = dist(z.x, z.y, p.x, p.y)
            if d < ZOMBIE_TOUCH_DIST and p.invulnerable <= 0:
                p.hp -= 1
                p.invulnerable = INVULNERABLE_TIME
                z.stun = ZOMBIE_BITE_STUN
                self.stats["bites"] += 1
                self.events.append("bite")
                if p.hp <= 0:
                    self.state = "lost"
                    self.events.append("lose")
                    self.reason = "You were caught by the horde."
                    return
                self.say("Bitten! Run!", 1.5)
                # knock the player back
                if d > 0:
                    kx, ky = (p.x - z.x) / d, (p.y - z.y) / d
                    for _ in range(5):
                        self.map.move(p, kx * 0.12, ky * 0.12)

    def _update_helicopter(self, dt):
        p = self.player
        if self.heli_state == "incoming" and self.time >= self.heli_arrive_at:
            self.heli_state = "landed"
            self.events.append("heli")
            self.say("The helicopter has landed! GET TO THE HELIPAD!", 3)
        if self.heli_state != "landed":
            return

        hx = sum(t[0] for t in self.map.helipad) / 4 + 0.5
        hy = sum(t[1] for t in self.map.helipad) / 4 + 0.5
        self.heli_noise_timer -= dt
        if self.heli_noise_timer <= 0:
            self.emit_noise(hx, hy, NOISE_HELICOPTER, "heli")
            self.heli_noise_timer = HELI_NOISE_INTERVAL

        if p.tile in self.map.helipad:
            self.board_progress += dt
            if self.board_progress >= BOARD_TIME:
                self.state = "won"
                self.events.append("win")
                self.reason = "You escaped on the helicopter!"
                return
        else:
            self.board_progress = max(0.0, self.board_progress - dt * 2)

        if self.time >= self.heli_arrive_at + HELI_WAIT_TIME:
            self.heli_state = "gone"
            self.state = "lost"
            self.events.append("lose")
            self.reason = "The helicopter left without you."

    @property
    def heli_time_left(self):
        if self.heli_state == "waiting":
            return None
        if self.heli_state == "incoming":
            return max(0.0, self.heli_arrive_at - self.time)
        return max(0.0, self.heli_arrive_at + HELI_WAIT_TIME - self.time)

    def _update_spawning(self, dt):
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = ZOMBIE_SPAWN_INTERVAL
            if len(self.zombies) < self.diff["max_zombies"]:
                self.spawn_zombie()

    def _free_street_tiles(self, min_player_dist):
        p = self.player
        out = []
        for (tx, ty) in self.map.reachable:
            if self.map.tile(tx, ty) != STREET or (tx, ty) in self.map.helipad:
                continue
            if (tx, ty) in self.visible:
                continue
            if dist(tx + 0.5, ty + 0.5, p.x, p.y) < min_player_dist:
                continue
            if any(dist(tx + 0.5, ty + 0.5, z.x, z.y) < 1.0 for z in self.zombies):
                continue
            out.append((tx, ty))
        out.sort()   # deterministic order for a given seed
        return out

    def spawn_zombie(self):
        options = self._free_street_tiles(ZOMBIE_MIN_SPAWN_DIST)
        if not options:
            return None
        tx, ty = self.rng.choice(options)
        z = Zombie(tx + 0.5, ty + 0.5)
        z.pause_timer = self.rng.uniform(0, 2)
        self.zombies.append(z)
        return z

    def _place_crates(self):
        """Radio parts go far from the start and far from each other; supplies anywhere."""
        options = self._free_street_tiles(8)
        self.rng.shuffle(options)
        picked = []
        for min_gap in (8, 6, 4, 0):          # relax the spacing rule if the map is cramped
            for (x, y) in options:
                if len(picked) == RADIO_PARTS:
                    break
                if all(dist(x, y, a, b) >= min_gap for a, b in picked) and (x, y) not in picked:
                    picked.append((x, y))
        for (x, y) in picked:
            self.crates.append(Crate(x, y, "radio"))

        supply = [t for t in self._free_street_tiles(5) if t not in picked]
        self.rng.shuffle(supply)
        kinds = ["barricade", "medkit", "barricade", "medkit"]
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
