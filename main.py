"""
main.py - Zombie Escape front end (drawing, input, sound, menus).

Run:   python main.py

All game rules and AI live in game.py; this file only shows the game
and turns key presses into inputs.
"""

import math
import random
from array import array

import pygame

import ui
from settings import *
from game import (Game, Zombie, STREET, BUILDING, BARRICADE, WATER, MUD, CAR,
                  WANDER, INVESTIGATE, CHASE, SLEEP)

DIFF_NAMES = list(DIFFICULTY.keys())
VIEW_W, VIEW_H = GRID_W * TILE, GRID_H * TILE      # visible part of the map

# ---------------- Colours ----------------
BG = (10, 10, 16)
ASPHALT = (44, 46, 54)
ASPHALT_2 = (48, 50, 58)
LANE = (70, 72, 60)
ROOFS = [(58, 52, 70), (66, 56, 52), (50, 62, 70), (62, 62, 58), (54, 48, 60)]
AWNINGS = [(170, 50, 45), (50, 120, 70), (50, 80, 150), (190, 140, 40), (130, 60, 130)]
WINDOW_ON = (230, 200, 110)
WINDOW_OFF = (34, 34, 44)
WATER_COL = (34, 78, 110)
WATER_DEEP = (22, 52, 82)
MUD_COL = (92, 68, 40)
CAR_COLOURS = [(160, 50, 45), (60, 90, 150), (200, 190, 170), (60, 120, 80), (190, 150, 50), (90, 90, 100)]
PLAYER_COL = (90, 220, 255)
BARRICADE_COL = (140, 95, 50)
BARRICADE_DARK = (95, 60, 30)
STATE_COLOURS = {WANDER: (150, 200, 150), INVESTIGATE: (255, 210, 60), CHASE: (255, 70, 70),
                 SLEEP: (140, 160, 255)}
FLOOR_A, FLOOR_B = (74, 86, 88), (80, 92, 94)          # hospital lino
HALL_A, HALL_B = (58, 66, 70), (62, 70, 74)
WALL_TOP = (120, 140, 140)
WALL_FACE = (66, 82, 84)
WHITE = (240, 240, 240)
GREY = (150, 150, 160)
RED = (230, 60, 60)
GREEN = (90, 220, 120)
YELLOW = (255, 210, 60)

# body colour, outline colour per zombie type
KIND_COLOURS = {
    "normal": ((110, 170, 80), (60, 100, 45)),
    "runner": ((175, 200, 95), (95, 120, 40)),
    "screamer": ((195, 160, 210), (110, 70, 130)),
    "brute": ((85, 120, 70), (40, 60, 35)),
    "hunter": ((70, 80, 70), (150, 30, 30)),
}
KIND_INFO = {
    "runner": "RUNNER - fast, but gives up quickly",
    "screamer": "SCREAMER - won't bite, alerts the whole map",
    "brute": "BRUTE - smashes barricades, bites for 2",
    "hunter": "HUNTER - predicts your path to cut you off",
}
NOISE_COLOURS = {"step": (200, 200, 255), "groan": (255, 80, 80), "heli": (255, 230, 120),
                 "crash": (255, 150, 60), "barricade": (255, 190, 120), "splash": (120, 200, 255),
                 "glass": (180, 255, 180), "alarm": (255, 160, 40), "scream": (220, 120, 255)}


def level_name(n):
    return f"Level {n}: {LEVELS[n]['name']}"


# ======================================================================
#  Tiny sound synthesiser (no audio files needed)
# ======================================================================
class Sounds:
    def __init__(self):
        self.enabled = False
        self.bank = {}
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1)
            freq, _size, channels = pygame.mixer.get_init()
            self.freq, self.channels = freq, channels
            self.bank = {
                "spotted": self._tone(110, 0.45, wave="saw", slide=-40, vol=0.35),
                "bite": self._noise(0.25, vol=0.5),
                "pickup": self._tone(520, 0.15, slide=400, vol=0.3),
                "radio": self._tone(700, 0.35, wave="square", slide=500, vol=0.25),
                "place": self._tone(90, 0.12, wave="square", vol=0.35),
                "crash": self._noise(0.35, vol=0.45),
                "heli": self._tone(60, 1.0, wave="square", vol=0.3, chop=12),
                "win": self._tone(440, 0.8, slide=440, vol=0.3),
                "lose": self._tone(220, 1.0, wave="saw", slide=-160, vol=0.35),
                "click": self._tone(800, 0.05, vol=0.2),
                "splash": self._noise(0.12, vol=0.18),
                "throw": self._tone(300, 0.12, slide=300, vol=0.15),
                "glass": self._tone(1800, 0.18, wave="square", slide=-900, vol=0.18),
                "alarm": self._tone(700, 1.2, wave="square", vol=0.2, chop=4),
                "scream": self._tone(900, 0.7, wave="saw", slide=-500, vol=0.3),
                "wake": self._tone(80, 0.6, wave="saw", slide=30, vol=0.35),
            }
            self.enabled = True
        except Exception:
            self.enabled = False      # no audio device - play silently

    def _make(self, samples):
        data = array("h", samples)
        if self.channels == 2:
            stereo = array("h")
            for s in data:
                stereo.append(s)
                stereo.append(s)
            data = stereo
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _tone(self, f0, dur, wave="sine", slide=0, vol=0.3, chop=0):
        n = int(self.freq * dur)
        out, phase = [], 0.0
        for i in range(n):
            t = i / n
            f = f0 + slide * t
            phase += f / self.freq
            p = phase % 1.0
            if wave == "square":
                v = 1.0 if p < 0.5 else -1.0
            elif wave == "saw":
                v = 2.0 * p - 1.0
            else:
                v = math.sin(phase * math.tau)
            env = min(1.0, i / 200) * (1.0 - t)
            if chop:
                env *= 0.5 + 0.5 * math.sin(i / self.freq * chop * math.tau)
            out.append(int(v * env * vol * 32767))
        return self._make(out)

    def _noise(self, dur, vol=0.4):
        n = int(self.freq * dur)
        rnd = random.Random(7)
        return self._make([int(rnd.uniform(-1, 1) * (1 - i / n) * vol * 32767) for i in range(n)])

    def play(self, name):
        if self.enabled and name in self.bank:
            self.bank[name].play()


# ======================================================================
#  App
# ======================================================================
class App:
    def __init__(self):
        pygame.init()
        ui._FONT_CACHE.clear()        # fonts from an earlier pygame session are invalid
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Zombie Escape")
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 56)
        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)
        self.sounds = Sounds()

        self.scene = "menu"            # "menu", "intro", "play", "end"
        self.diff_index = 1
        self.level_index = 0           # index into LEVEL_ORDER
        self.paused = False
        self.debug = False
        self.game = None
        self.city = None
        self.cam = (0, 0)
        self.shake = 0.0
        self.red_flash = 0.0
        self.anim_t = 0.0
        self.buttons = []              # (rect, action) for mouse clicks
        self.place_pressed = self.alarm_pressed = self.light_pressed = False
        self.throw_target = None
        self._new_demo()

    # ------------------------------------------------------------------
    @property
    def level(self):
        return LEVEL_ORDER[self.level_index]

    def _make_surfaces(self, game):
        size = (game.map.w * TILE, game.map.h * TILE)
        self.fog = pygame.Surface(size, pygame.SRCALPHA)
        self.overlay = pygame.Surface(size, pygame.SRCALPHA)
        self.world = pygame.Surface(size)

    def _new_demo(self):
        self.demo = Game("Easy", seed=random.randint(0, 10 ** 6), level=self.level)
        self.demo.player.x = self.demo.player.y = -50     # hide the player off-map
        self.demo_city = self.render_city(self.demo)
        self._make_surfaces(self.demo)

    def new_game(self):
        self.game = Game(DIFF_NAMES[self.diff_index], level=self.level)
        self.city = self.render_city(self.game)
        self._make_surfaces(self.game)
        self.paused = False
        self.scene = "intro"           # show the level card first
        self.shake = self.red_flash = 0.0

    def next_level(self):
        if self.level_index + 1 < len(LEVEL_ORDER):
            self.level_index += 1
        self.new_game()

    def select_level(self, index):
        if index != self.level_index:
            self.level_index = index
            self._new_demo()
            self.sounds.play("click")

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------
    def run(self, max_frames=None):
        frames = 0
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.anim_t += dt
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
            pygame.display.flip()
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        pygame.quit()

    def screen_to_map(self, pos):
        return ((pos[0] + self.cam[0]) / TILE, (pos[1] - HUD_H + self.cam[1]) / TILE)

    def handle_events(self):
        self.place_pressed = self.alarm_pressed = self.light_pressed = False
        self.throw_target = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.click(event.pos):
                    return False
                continue
            if event.type != pygame.KEYDOWN:
                continue
            key = event.key

            if self.scene == "menu":
                if key in (pygame.K_LEFT, pygame.K_a):
                    self.select_level((self.level_index - 1) % len(LEVEL_ORDER))
                elif key in (pygame.K_RIGHT, pygame.K_d):
                    self.select_level((self.level_index + 1) % len(LEVEL_ORDER))
                elif key in (pygame.K_UP, pygame.K_w):
                    self.diff_index = (self.diff_index - 1) % len(DIFF_NAMES)
                    self.sounds.play("click")
                elif key in (pygame.K_DOWN, pygame.K_s):
                    self.diff_index = (self.diff_index + 1) % len(DIFF_NAMES)
                    self.sounds.play("click")
                elif pygame.K_1 <= key <= pygame.K_9 and (key - pygame.K_0) in LEVEL_ORDER:
                    self.select_level(LEVEL_ORDER.index(key - pygame.K_0))
                elif key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.new_game()
                elif key == pygame.K_ESCAPE:
                    return False

            elif self.scene == "intro":
                if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                    self.scene = "play"
                elif key == pygame.K_ESCAPE:
                    self.scene = "menu"

            elif self.scene == "play":
                if key in (pygame.K_p, pygame.K_ESCAPE):
                    self.paused = not self.paused
                elif key == pygame.K_F1 or key == pygame.K_TAB:
                    self.debug = not self.debug
                elif self.paused:
                    if key == pygame.K_m:
                        self.scene = "menu"
                        self._new_demo()
                    elif key == pygame.K_q:
                        return False
                elif key in (pygame.K_SPACE, pygame.K_e):
                    self.place_pressed = True
                elif key == pygame.K_l:
                    self.light_pressed = True
                elif key == pygame.K_f:
                    self.alarm_pressed = True
                elif key == pygame.K_t and self.game.cfg.get("bottles") is not None:
                    p = self.game.player
                    self.throw_target = (p.x + p.facing[0] * BOTTLE_RANGE * 0.75,
                                         p.y + p.facing[1] * BOTTLE_RANGE * 0.75)

            elif self.scene == "end":
                if key in (pygame.K_r, pygame.K_RETURN):
                    self.new_game()
                elif key == pygame.K_n and self.game.state == "won":
                    self.next_level()
                elif key == pygame.K_m:
                    self.scene = "menu"
                    self._new_demo()
                elif key == pygame.K_ESCAPE:
                    return False
        return True

    def click(self, pos):
        """Handle a mouse click on a button (or throw a bottle). Returns False to quit."""
        for rect, action in self.buttons:
            if not rect.collidepoint(pos):
                continue
            self.sounds.play("click")
            if isinstance(action, tuple):
                if action[0] == "level":
                    self.select_level(action[1])
                elif action[0] == "diff":
                    self.diff_index = action[1]
            elif action == "start" or action == "again":
                self.new_game()
            elif action == "go":
                self.scene = "play"
            elif action == "next":
                self.next_level()
            elif action == "resume":
                self.paused = False
            elif action == "menu":
                self.paused = False
                self.scene = "menu"
                self._new_demo()
            elif action == "quit":
                return False
            return True
        # Clicking on the map throws a bottle (levels that have them)
        if self.scene == "play" and not self.paused and pos[1] > HUD_H and \
                self.game.cfg.get("bottles") is not None:
            self.throw_target = self.screen_to_map(pos)
        return True

    def update(self, dt):
        self.shake = max(0.0, self.shake - dt)
        self.red_flash = max(0.0, self.red_flash - dt * 1.5)

        if self.scene == "menu":
            self.demo.update(dt)
            self.demo.pop_events()
            if self.demo.state != "playing":
                self._new_demo()
            return
        if self.scene != "play" or self.paused:
            return

        keys = pygame.key.get_pressed()
        mx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        my = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        run = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        self.game.update(dt, move=(mx, my), run=bool(run), place=self.place_pressed,
                         throw=self.throw_target, alarm=self.alarm_pressed, flashlight=self.light_pressed)

        splashed = False
        for ev in self.game.pop_events():
            if ev == "splash":
                if splashed:
                    continue
                splashed = True
            self.sounds.play(ev)
            if ev == "bite":
                self.shake = 0.35
                self.red_flash = 0.8
        if self.game.state != "playing":
            self.scene = "end"

    # ------------------------------------------------------------------
    #  Drawing: static level art (drawn once per game)
    # ------------------------------------------------------------------
    def render_city(self, game):
        m = game.map
        surf = pygame.Surface((m.w * TILE, m.h * TILE))
        rnd = random.Random(1234)
        theme = m.theme
        solid = (BUILDING, CAR)

        for y in range(m.h):
            for x in range(m.w):
                r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                tile = m.tiles[y][x]
                if tile == BUILDING:
                    self._draw_solid(surf, m, x, y, r, rnd)
                    continue
                # ground
                if theme == "hospital":
                    in_room = any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in m.rooms)
                    a, b = (FLOOR_A, FLOOR_B) if in_room else (HALL_A, HALL_B)
                    surf.fill(a if (x + y) % 2 else b, r)
                    if m.tile(x, y - 1) == BUILDING:
                        surf.fill((40, 48, 50), (r.x, r.y, TILE, 6))
                    if (x, y) in m.beds:
                        bed = pygame.Rect(r.x + 4, r.y + 3, TILE - 8, TILE - 6)
                        pygame.draw.rect(surf, (150, 150, 155), bed.move(1, 2), border_radius=3)
                        pygame.draw.rect(surf, (205, 210, 205), bed, border_radius=3)
                        pygame.draw.rect(surf, (120, 160, 170), (bed.x, bed.y + 9, bed.w, bed.h - 9), border_radius=3)
                        pygame.draw.rect(surf, (240, 240, 235), (bed.x + 3, bed.y + 2, bed.w - 6, 6), border_radius=2)
                    elif rnd.random() < 0.025 and m.tile(x, y) == STREET:      # blood stain
                        pygame.draw.circle(surf, (90, 30, 30), (r.x + 16, r.y + 16), rnd.randint(3, 6))
                    continue
                if (x, y) in m.safe_zone:
                    surf.fill((92, 88, 78) if (x + y) % 2 else (100, 96, 84), r)
                    pygame.draw.rect(surf, (76, 72, 64), r, 1)
                else:
                    surf.fill(ASPHALT if (x + y) % 2 else ASPHALT_2, r)
                if tile == WATER:
                    surf.fill(WATER_COL, r)
                    for dx, dy, edge in ((0, -1, (r.x, r.y, TILE, 3)), (0, 1, (r.x, r.bottom - 3, TILE, 3)),
                                         (-1, 0, (r.x, r.y, 3, TILE)), (1, 0, (r.right - 3, r.y, 3, TILE))):
                        if m.tile(x + dx, y + dy) != WATER:
                            surf.fill((80, 130, 160), edge)
                    continue
                if tile == MUD:
                    surf.fill(MUD_COL, r)
                    for _ in range(4):
                        pygame.draw.circle(surf, (70, 50, 28), (r.x + rnd.randint(5, 27), r.y + rnd.randint(5, 27)),
                                           rnd.randint(2, 4))
                    continue
                if theme == "bridge":
                    top, bot = 4, m.h - 5
                    if y in (top, bot):
                        surf.fill((200, 170, 60), (r.x, r.y + (2 if y == top else TILE - 4), TILE, 2))
                    elif (y - top) % 2 == 0 and x % 2 == 0:
                        surf.fill((170, 170, 160), (r.x + 4, r.y, 22, 2))
                    continue
                if tile in (STREET, BARRICADE, CAR):
                    if m.tile(x - 1, y) not in solid and m.tile(x + 1, y) not in solid and \
                            m.tile(x, y - 1) in solid and m.tile(x, y + 1) in solid:
                        surf.fill(LANE, (r.x + 8, r.centery - 1, 16, 2))
                    if m.tile(x, y - 1) not in solid and m.tile(x, y + 1) not in solid and \
                            m.tile(x - 1, y) in solid and m.tile(x + 1, y) in solid:
                        surf.fill(LANE, (r.centerx - 1, r.y + 8, 2, 16))
                    if m.tile(x, y - 1) == BUILDING:
                        surf.fill((30, 31, 37), (r.x, r.y, TILE, 5))
                    if m.tile(x - 1, y) == BUILDING:
                        surf.fill((34, 35, 41), (r.x, r.y, 4, TILE))

        for car in m.cars:
            self.draw_car(surf, car)
        self._draw_exit_static(surf, game)
        return surf

    def _draw_solid(self, surf, m, x, y, r, rnd):
        theme = m.theme
        if theme == "bridge":
            top, bot = 4, m.h - 5
            if y in (top - 1, bot + 1) and 0 < x < m.w - 1:            # concrete guard rail
                surf.fill(WATER_DEEP, r)
                surf.fill((150, 150, 145), (r.x, r.y + 8, TILE, 16))
                surf.fill((110, 110, 105), (r.x, r.y + 20, TILE, 4))
                if x % 3 == 0:
                    surf.fill((90, 90, 86), (r.x + 12, r.y + 4, 8, 24))
                return
            surf.fill(WATER_DEEP, r)                                     # river (or a hole)
            if top <= y <= bot:                                          # collapsed road
                pygame.draw.rect(surf, (70, 70, 75), r, 3)
                for _ in range(3):
                    pygame.draw.circle(surf, (90, 90, 95), (r.x + rnd.randint(0, 32), r.y + rnd.randint(0, 32)), 3)
            return
        if theme == "flood" and (x == m.w - 1 or y == m.h - 1):          # the river at the edge
            surf.fill(WATER_DEEP, r)
            return
        if theme == "hospital":
            surf.fill((28, 34, 36), r)
            open_below = m.tile(x, y + 1) != BUILDING
            if open_below:                                               # wall face you can see
                surf.fill(WALL_FACE, (r.x, r.y + 10, TILE, TILE - 10))
                surf.fill(WALL_TOP, (r.x, r.y + 6, TILE, 4))
                if rnd.random() < 0.15:                                  # green hospital sign
                    surf.fill((40, 150, 90), (r.x + 9, r.y + 14, 14, 8))
            elif any(m.tile(x + dx, y + dy) != BUILDING for dx, dy in ((1, 0), (-1, 0), (0, -1))):
                surf.fill(WALL_TOP, (r.x, r.y, TILE, TILE))
                surf.fill((96, 112, 112), (r.x + 2, r.y + 2, TILE - 4, TILE - 4))
            return
        if (x, y) in m.zone_walls:                                       # sandbag wall
            surf.fill((70, 66, 58), r)
            for row in range(3):
                for col in range(2):
                    bx = r.x + 2 + col * 15 + (7 if row % 2 else 0)
                    bag = pygame.Rect(min(bx, r.right - 15), r.y + 2 + row * 10, 14, 9)
                    pygame.draw.ellipse(surf, (190, 170, 120), bag)
                    pygame.draw.ellipse(surf, (120, 100, 66), bag, 1)
            return
        if theme == "flood" and 0 < x < m.w - 1 and 0 < y < m.h - 1:    # market stall awning
            col = AWNINGS[(x // 3 + y // 2 * 2) % len(AWNINGS)]
            surf.fill((235, 225, 205), r)
            for i in range(0, TILE, 8):
                surf.fill(col, (r.x + i, r.y, 4, TILE))
            pygame.draw.rect(surf, tuple(c // 2 for c in col), r, 1)
            return
        roof = ROOFS[(x // 3 + y // 2 * 2) % len(ROOFS)]
        surf.fill(roof, r)
        pygame.draw.rect(surf, tuple(max(0, c - 18) for c in roof), r, 1)
        for wy in range(2):
            for wx in range(3):
                colour = WINDOW_ON if rnd.random() < 0.18 else WINDOW_OFF
                surf.fill(colour, (r.x + 5 + wx * 9, r.y + 7 + wy * 12, 5, 6))

    def draw_car(self, surf, car, highlight=None):
        x0 = min(t[0] for t in car.tiles)
        y0 = min(t[1] for t in car.tiles)
        if car.horizontal:
            r = pygame.Rect(x0 * TILE + 3, y0 * TILE + 6, 2 * TILE - 6, TILE - 12)
        else:
            r = pygame.Rect(x0 * TILE + 6, y0 * TILE + 3, TILE - 12, 2 * TILE - 6)
        col = CAR_COLOURS[car.colour]
        dark = tuple(c // 2 for c in col)
        pygame.draw.rect(surf, (0, 0, 0), r.move(2, 3), border_radius=6)
        pygame.draw.rect(surf, col, r, border_radius=6)
        pygame.draw.rect(surf, dark, r, 2, border_radius=6)
        glass = (60, 80, 100)
        if car.horizontal:
            pygame.draw.rect(surf, glass, (r.x + r.w * 0.6, r.y + 3, 8, r.h - 6), border_radius=2)
            pygame.draw.rect(surf, glass, (r.x + r.w * 0.22, r.y + 3, 6, r.h - 6), border_radius=2)
            pygame.draw.rect(surf, tuple(min(255, c + 25) for c in col), (r.x + r.w * 0.33, r.y + 3, r.w * 0.27, r.h - 6))
        else:
            pygame.draw.rect(surf, glass, (r.x + 3, r.y + r.h * 0.6, r.w - 6, 8), border_radius=2)
            pygame.draw.rect(surf, glass, (r.x + 3, r.y + r.h * 0.22, r.w - 6, 6), border_radius=2)
            pygame.draw.rect(surf, tuple(min(255, c + 25) for c in col), (r.x + 3, r.y + r.h * 0.33, r.w - 6, r.h * 0.27))
        if highlight:
            pygame.draw.rect(surf, highlight, r.inflate(6, 6), 2, border_radius=8)
        return r

    def _exit_rect(self, game):
        xs = [t[0] for t in game.map.helipad]
        ys = [t[1] for t in game.map.helipad]
        return pygame.Rect(min(xs) * TILE, min(ys) * TILE, (max(xs) - min(xs) + 1) * TILE,
                           (max(ys) - min(ys) + 1) * TILE)

    def _draw_exit_static(self, surf, game):
        pad = self._exit_rect(game)
        mode = game.exit_mode
        if mode == "boat":                                   # wooden dock
            dock = pad.union(pygame.Rect(pad.right, pad.y, TILE, pad.h))
            surf.fill((120, 85, 50), dock)
            for i in range(dock.x, dock.right, 8):
                pygame.draw.line(surf, (80, 55, 30), (i, dock.y), (i, dock.bottom), 1)
            pygame.draw.rect(surf, (70, 45, 25), dock, 2)
            for px_ in (dock.right - 4,):
                for py_ in (dock.y + 4, dock.bottom - 4):
                    pygame.draw.circle(surf, (60, 40, 20), (px_, py_), 4)
        elif mode == "elevator":                             # lift lobby
            pygame.draw.rect(surf, (50, 55, 60), pad.inflate(4, 4), border_radius=4)
            pygame.draw.rect(surf, (150, 160, 165), pad, 3, border_radius=4)
            for i in range(0, pad.w, 10):
                pygame.draw.line(surf, (70, 76, 80), (pad.x + i, pad.y + 4), (pad.x + i, pad.bottom - 4), 1)
            t = ui.font(13).render("LIFT", True, (230, 230, 200))
            surf.blit(t, t.get_rect(center=(pad.centerx, pad.y - 8)))
        elif mode == "checkpoint":                           # sandbags, gate and tents
            for i in range(pad.h // 8):
                c = (230, 190, 40) if i % 2 else (40, 40, 40)
                surf.fill(c, (pad.x, pad.y + i * 8, 6, 8))
            wall_x = pad.right
            for y in range(4 * TILE, (game.map.h - 4) * TILE, 10):
                if not (pad.y <= y < pad.bottom):
                    pygame.draw.ellipse(surf, (190, 170, 120), (wall_x + 4, y, 22, 10))
                    pygame.draw.ellipse(surf, (120, 100, 66), (wall_x + 4, y, 22, 10), 1)
            pygame.draw.polygon(surf, (70, 95, 55), [(pad.x + 6, pad.y - 2), (pad.right - 6, pad.y - 2),
                                                     (pad.centerx, pad.y - 28)])
            t = ui.font(16).render("ARMY", True, (230, 230, 200))
            surf.blit(t, t.get_rect(center=(pad.centerx, pad.bottom + 12)))
        else:                                                # helipad
            pygame.draw.circle(surf, (70, 70, 80), pad.center, TILE - 2)
            pygame.draw.circle(surf, YELLOW, pad.center, TILE - 2, 3)
            h = self.font_big.render("H", True, YELLOW)
            surf.blit(h, h.get_rect(center=pad.center))

    # ------------------------------------------------------------------
    #  Drawing: dynamic world
    # ------------------------------------------------------------------
    def update_camera(self, game, follow):
        mw, mh = game.map.w * TILE, game.map.h * TILE
        if not follow:
            self.cam = (0, 0)
            return
        p = game.player
        cx = int(min(max(p.x * TILE - VIEW_W / 2, 0), max(0, mw - VIEW_W)))
        cy = int(min(max(p.y * TILE - VIEW_H / 2, 0), max(0, mh - VIEW_H)))
        self.cam = (cx, cy)

    def draw_world(self, game, city, use_fog=True, debug=False, offset=(0, 0)):
        ox, oy = offset
        playing = game is self.game
        self.update_camera(game, playing)
        world = self.world
        world.blit(city, (0, 0))
        m = game.map
        t = self.anim_t
        cam_x, cam_y = self.cam
        view = pygame.Rect(cam_x, cam_y, VIEW_W, VIEW_H)

        def px(x, y):
            return int(x * TILE), int(y * TILE)

        def shown(tile):
            return debug or not use_fog or tile in game.visible

        # Animated water ripples (only on screen)
        x0, x1 = cam_x // TILE, min(m.w, (cam_x + VIEW_W) // TILE + 1)
        for y in range(m.h):
            for x in range(x0, x1):
                tile = m.tiles[y][x]
                deep = tile == BUILDING and (m.theme == "bridge" and not (y in (3, m.h - 4))
                                             or m.theme == "flood" and (x == m.w - 1 or y == m.h - 1))
                if tile == WATER or deep:
                    k = (t * 1.6 + x * 0.37 + y * 0.61) % 1.0
                    wx = x * TILE + int(k * 22) + 2
                    wy = y * TILE + 8 + (x * 7 + y * 3) % 16
                    pygame.draw.line(world, (90, 150, 190) if tile == WATER else (50, 90, 125),
                                     (wx, wy), (wx + 7, wy), 2)

        # Level 5 safe zone outline
        if m.safe_zone:
            zx0 = min(a for a, _ in m.safe_zone) * TILE
            zy0 = min(b for _, b in m.safe_zone) * TILE
            zx1 = (max(a for a, _ in m.safe_zone) + 1) * TILE
            zy1 = (max(b for _, b in m.safe_zone) + 1) * TILE
            inside = game.in_safe_zone
            col = (120, 230, 120) if inside or not playing else (255, 90, 70)
            if not inside and playing and int(t * 3) % 2:
                col = (255, 200, 80)
            pygame.draw.rect(world, col, (zx0 + 2, zy0 + 2, zx1 - zx0 - 4, zy1 - zy0 - 4), 2, border_radius=4)

        # Barricades
        full_hp = game.barricade_hp
        for (bx, by), hp in m.barricade_hp.items():
            r = pygame.Rect(bx * TILE + 2, by * TILE + 4, TILE - 4, TILE - 8)
            reinforced = m.tall_barricades
            pygame.draw.rect(world, (70, 70, 80) if reinforced else BARRICADE_DARK, r, border_radius=3)
            for i in range(3):
                pygame.draw.rect(world, (150, 150, 160) if reinforced else BARRICADE_COL,
                                 (r.x + 1, r.y + 2 + i * 8, r.w - 2, 5))
            pygame.draw.line(world, BARRICADE_DARK, r.topleft, r.bottomright, 3)
            if hp < full_hp:
                pygame.draw.rect(world, RED, (r.x, r.y - 4, r.w, 3))
                pygame.draw.rect(world, GREEN, (r.x, r.y - 4, int(r.w * hp / full_hp), 3))

        # Car alarms + the car you can set off right now
        near_car = game.car_in_reach() if playing else None
        for car in m.cars:
            if car.alarm_time > 0:
                cx, cy = px(*car.centre)
                if int(t * 6) % 2:
                    self.draw_car(world, car, highlight=(255, 170, 40))
                    pygame.draw.circle(world, (255, 200, 60), (cx, cy), 6)
            elif car is near_car:
                self.draw_car(world, car, highlight=(255, 255, 255))
                cx, cy = px(*car.centre)
                ui.text(world, "F", 16, (cx, cy - 22), ui.GOLD, ui.WOOD_EDGE, 2)

        # Crates (only once explored)
        for c in game.crates:
            if use_fog and not debug and (c.x, c.y) not in game.explored:
                continue
            cx, cy = px(c.x + 0.5, c.y + 0.5)
            bob = int(math.sin(t * 3 + c.x) * 2)
            self.draw_crate(world, c.kind, cx, cy + bob, game)

        # Noise rings
        self.overlay.fill((0, 0, 0, 0))
        for n in game.noises:
            if n.kind == "groan" and not debug and (int(n.x), int(n.y)) not in game.visible:
                continue
            frac = n.age / 0.9
            radius = int(n.radius * TILE * math.sqrt(frac))
            alpha = int(160 * (1 - frac))
            colour = NOISE_COLOURS.get(n.kind, WHITE)
            if radius > 2:
                pygame.draw.circle(self.overlay, colour + (alpha,), px(n.x, n.y), radius, 2)
        world.blit(self.overlay, (0, 0))

        p = game.player
        if playing and game.state == "playing":
            # Barricade placement preview
            (tx, ty), ok, _ = game.barricade_target()
            if m.in_bounds(tx, ty):
                pygame.draw.rect(world, GREEN if ok else (160, 60, 60),
                                 (tx * TILE + 1, ty * TILE + 1, TILE - 2, TILE - 2), 1)
            # Bottle aim preview (follows the mouse)
            if game.cfg.get("bottles") is not None and p.bottles > 0 and not self.paused:
                mpos = pygame.mouse.get_pos()
                if mpos[1] > HUD_H:
                    (lx, ly), car = game.bottle_landing(*self.screen_to_map(mpos))
                    sx, sy = px(p.x, p.y)
                    ex, ey = px(lx, ly)
                    for i in range(1, 12):
                        f = i / 12
                        ax = sx + (ex - sx) * f
                        ay = sy + (ey - sy) * f - math.sin(f * math.pi) * 20
                        pygame.draw.circle(world, (230, 230, 230), (int(ax), int(ay)), 2)
                    pygame.draw.circle(world, (255, 160, 40) if car else (180, 255, 180), (ex, ey), 7, 2)

        # Debug: zombie paths and sight ranges
        if debug:
            for z in game.zombies:
                col = STATE_COLOURS[z.state]
                if z.path:
                    pts = [px(z.x, z.y)] + [px(a + 0.5, b + 0.5) for a, b in z.path]
                    if len(pts) > 1:
                        pygame.draw.lines(world, col, False, pts, 2)
                    pygame.draw.circle(world, col, pts[-1], 4)
                if z.state != SLEEP:
                    pygame.draw.circle(world, col, px(z.x, z.y), int(game.sight_range(z) * TILE), 1)

        # Zombies
        for z in game.zombies:
            if not shown(z.tile):
                continue
            # Hunter: show where it predicts you'll be
            if z.kind == "hunter" and z.state == CHASE and z.intercept:
                hx, hy = px(z.x, z.y)
                ix, iy = px(*z.intercept)
                for i in range(0, 10, 2):
                    a = (hx + (ix - hx) * i / 10, hy + (iy - hy) * i / 10)
                    b = (hx + (ix - hx) * (i + 1) / 10, hy + (iy - hy) * (i + 1) / 10)
                    pygame.draw.line(world, (220, 60, 60), a, b, 2)
                pygame.draw.circle(world, (220, 60, 60), (ix, iy), 8, 2)
                pygame.draw.line(world, (220, 60, 60), (ix - 11, iy), (ix + 11, iy), 2)
                pygame.draw.line(world, (220, 60, 60), (ix, iy - 11), (ix, iy + 11), 2)
            self.draw_zombie(world, z, *px(z.x, z.y), target=(p.x, p.y))
            zx, zy = px(z.x, z.y)
            r = int(z.radius * TILE)
            if z.state == CHASE:
                ui.text(world, "!", 18, (zx, zy - r - 12), RED, (60, 0, 0), 2, shadow=False)
            elif z.state == INVESTIGATE:
                ui.text(world, "?", 18, (zx, zy - r - 12), YELLOW, (80, 60, 0), 2, shadow=False)
            if debug:
                s = self.font_small.render(z.state[0] + ("" if z.kind == "normal" else " " + z.kind),
                                           True, STATE_COLOURS[z.state])
                world.blit(s, (zx + r, zy - r))

        # Bottles in flight
        for b in game.bottles:
            bx, by = px(*b.pos)
            pygame.draw.ellipse(world, (0, 0, 0), (bx - 4, by - 2, 8, 4))
            lift = int(b.height * 22)
            ang = b.t * 14
            ex, ey = math.cos(ang) * 5, math.sin(ang) * 5
            pygame.draw.line(world, (60, 160, 70), (bx - ex, by - lift - ey), (bx + ex, by - lift + ey), 4)

        # Player
        if playing:
            ppx, ppy = px(p.x, p.y)
            r = int(p.radius * TILE)
            if p.in_water:
                k = (t * 2) % 1.0
                pygame.draw.circle(world, (150, 210, 240), (ppx, ppy), int(r + 3 + k * 8), 1)
            flashing = p.invulnerable > 0 and int(t * 12) % 2 == 0
            if not flashing:
                pygame.draw.circle(world, (0, 0, 0), (ppx + 2, ppy + 3), r)
                pygame.draw.circle(world, PLAYER_COL, (ppx, ppy), r)
                pygame.draw.circle(world, WHITE, (ppx, ppy), r, 2)
                fx, fy = p.facing
                tip = (ppx + fx * (r + 7), ppy + fy * (r + 7))
                left = (ppx + fx * r - fy * 5, ppy + fy * r + fx * 5)
                right = (ppx + fx * r + fy * 5, ppy + fy * r - fx * 5)
                pygame.draw.polygon(world, WHITE, [tip, left, right])
            if game.heli_state == "landed" and game.board_progress > 0:
                w = 40
                pygame.draw.rect(world, (30, 30, 30), (ppx - w // 2, ppy - 26, w, 6))
                pygame.draw.rect(world, GREEN, (ppx - w // 2, ppy - 26,
                                                int(w * game.board_progress / game.board_time), 6))

        # Fog of war (only the part on screen)
        if use_fog and not debug:
            self.fog.fill((0, 0, 0, 0))
            for y in range(m.h):
                for x in range(x0, x1):
                    if (x, y) in game.visible:
                        reach = FLASH_RANGE if game.in_beam(x + 0.5, y + 0.5) else game.view_radius
                        d = math.hypot(x + 0.5 - p.x, y + 0.5 - p.y) / reach
                        a = min(150, int(max(0.0, d - 0.55) / 0.45 * 120))
                    elif (x, y) in game.explored:
                        a = 190 if game.dark else 150
                    else:
                        a = 236
                    if a:
                        self.fog.fill((4, 4, 12, a), (x * TILE, y * TILE, TILE, TILE))
            world.blit(self.fog, (0, 0))

            # Exit beacon always visible through the fog
            pad = self._exit_rect(game)
            pulse = (math.sin(t * 4) + 1) / 2
            if game.heli_state != "landed" or game.exit_mode == "checkpoint":
                pygame.draw.circle(world, (255, int(80 + 100 * pulse), 60), pad.center, int(4 + 4 * pulse))
            # Alarming cars flash through the fog too
            for car in m.cars:
                if car.alarm_time > 0 and int(t * 6) % 2:
                    pygame.draw.circle(world, (255, 180, 40), px(*car.centre), 6)

        # Flashlight beam glow
        if playing and game.dark and p.flashlight:
            self.overlay.fill((0, 0, 0, 0))
            sx, sy = px(p.x, p.y)
            ang = math.atan2(p.facing[1], p.facing[0])
            pts = [(sx, sy)]
            for i in range(9):
                a = ang - FLASH_ANGLE + 2 * FLASH_ANGLE * i / 8
                pts.append((sx + math.cos(a) * FLASH_RANGE * TILE, sy + math.sin(a) * FLASH_RANGE * TILE))
            flicker = 34 + (6 if int(t * 13) % 7 else 0)
            pygame.draw.polygon(self.overlay, (255, 240, 170, flicker), pts)
            world.blit(self.overlay, (0, 0))

        # Exit vehicles (loud and bright, so drawn above the fog)
        if game.exit_mode == "boat":
            self.draw_boat(world, game)
        elif game.exit_mode == "checkpoint":
            self.draw_checkpoint(world, game)
        elif game.exit_mode == "elevator":
            self.draw_elevator(world, game)
        else:
            self.draw_helicopter(world, game)

        # Danger border when something is chasing you
        if playing and any(z.state == CHASE for z in game.zombies):
            a = int(60 + 60 * (math.sin(t * 8) + 1) / 2)
            self.overlay.fill((0, 0, 0, 0))
            pygame.draw.rect(self.overlay, (255, 0, 0, a), view, 8)
            world.blit(self.overlay, (0, 0))

        if self.red_flash > 0 and playing:
            self.overlay.fill((200, 0, 0, int(110 * self.red_flash)))
            world.blit(self.overlay, (0, 0))

        self.screen.blit(world, (ox, HUD_H + oy), view)

    def draw_crate(self, surf, kind, cx, cy, game=None):
        t = self.anim_t
        if kind == "radio":
            if game is not None and game.exit_mode == "boat":       # red fuel can
                pygame.draw.rect(surf, (200, 40, 35), (cx - 7, cy - 8, 14, 17), border_radius=3)
                pygame.draw.rect(surf, (110, 20, 20), (cx - 7, cy - 8, 14, 17), 2, border_radius=3)
                pygame.draw.rect(surf, (230, 200, 60), (cx + 2, cy - 12, 4, 5))
                pygame.draw.line(surf, (240, 230, 220), (cx - 4, cy - 4), (cx + 3, cy + 5), 2)
                if int(t * 3) % 2:
                    pygame.draw.circle(surf, (255, 230, 120), (cx + 4, cy - 13), 2)
                return
            if game is not None and game.exit_mode == "elevator":   # glowing fuse
                self.draw_icon("fuse", cx, cy, surf=surf)
                if int(t * 3) % 2:
                    pygame.draw.circle(surf, (255, 200, 90), (cx, cy - 11), 2)
                return
            pygame.draw.rect(surf, (40, 60, 90), (cx - 9, cy - 6, 18, 13), border_radius=3)
            pygame.draw.rect(surf, (110, 170, 255), (cx - 9, cy - 6, 18, 13), 2, border_radius=3)
            pygame.draw.line(surf, (200, 200, 220), (cx + 5, cy - 6), (cx + 8, cy - 14), 2)
            if int(t * 3) % 2:
                pygame.draw.circle(surf, (120, 255, 140), (cx + 8, cy - 14), 3)
        elif kind == "medkit":
            pygame.draw.rect(surf, WHITE, (cx - 8, cy - 7, 16, 14), border_radius=3)
            surf.fill(RED, (cx - 2, cy - 5, 4, 10))
            surf.fill(RED, (cx - 5, cy - 2, 10, 4))
        elif kind == "battery":
            pygame.draw.rect(surf, (40, 40, 45), (cx - 8, cy - 5, 16, 11), border_radius=2)
            pygame.draw.rect(surf, (240, 200, 50), (cx - 8, cy - 5, 6, 11), border_radius=2)
            pygame.draw.rect(surf, (200, 200, 200), (cx + 8, cy - 2, 2, 5))
            if int(t * 3) % 2:
                pygame.draw.circle(surf, (255, 240, 150), (cx, cy - 10), 2)
        elif kind == "bottles":
            for i, dx in enumerate((-5, 0, 5)):
                pygame.draw.rect(surf, (60, 150, 70), (cx + dx - 2, cy - 4, 5, 11), border_radius=2)
                pygame.draw.rect(surf, (60, 150, 70), (cx + dx - 1, cy - 9, 3, 6))
            pygame.draw.rect(surf, BARRICADE_DARK, (cx - 9, cy + 3, 18, 6))
        else:
            pygame.draw.rect(surf, BARRICADE_COL, (cx - 8, cy - 7, 16, 14))
            pygame.draw.rect(surf, BARRICADE_DARK, (cx - 8, cy - 7, 16, 14), 2)
            pygame.draw.line(surf, BARRICADE_DARK, (cx - 8, cy - 7), (cx + 8, cy + 7), 2)

    def draw_zombie(self, surf, z, zx, zy, target=None, scale=1.0):
        t = self.anim_t
        if z.state == SLEEP:                                    # lying on a bed, Zz
            body, dark = KIND_COLOURS[z.kind]
            r = max(3, int(z.radius * TILE * scale))
            pygame.draw.ellipse(surf, body, (zx - r - 2, zy - r + 3, 2 * r + 4, 2 * r - 6))
            pygame.draw.ellipse(surf, dark, (zx - r - 2, zy - r + 3, 2 * r + 4, 2 * r - 6), 2)
            pygame.draw.line(surf, dark, (zx - 5, zy - 1), (zx - 2, zy - 1), 2)
            pygame.draw.line(surf, dark, (zx + 2, zy - 1), (zx + 5, zy - 1), 2)
            k = (t * 0.7 + z.wobble) % 1.0
            zt = ui.font(int(10 + 5 * k)).render("z", True, (170, 190, 255))
            zt.set_alpha(int(255 * (1 - k)))
            surf.blit(zt, (zx + 6 + k * 6, zy - 14 - k * 14))
            return
        if z.attacking:
            zx += random.randint(-2, 2)
        body, dark = KIND_COLOURS[z.kind]
        r = max(3, int(z.radius * TILE * scale))
        sway = math.sin(t * (10 if z.kind == "runner" else 6) + z.wobble) * 2
        pygame.draw.circle(surf, (0, 0, 0), (zx + 2, zy + 3), r)                 # shadow
        if z.state == CHASE and target is not None:
            ang = math.atan2(target[1] - z.y, target[0] - z.x)
        else:
            ang = z.wobble + t * 0.5
        # runners leave speed streaks
        if z.kind == "runner" and z.state == CHASE:
            for i in (1, 2):
                bx = zx - math.cos(ang) * (r + 4 * i)
                by = zy - math.sin(ang) * (r + 4 * i)
                pygame.draw.line(surf, (200, 220, 140), (bx - math.sin(ang) * 4, by + math.cos(ang) * 4),
                                 (bx + math.sin(ang) * 4, by - math.cos(ang) * 4), 1)
        arm_w = 6 if z.kind == "brute" else 4
        if z.kind != "screamer":
            for side in (-0.5, 0.5):
                ax = zx + math.cos(ang + side) * (r + 5 + sway)
                ay = zy + math.sin(ang + side) * (r + 5 + sway)
                pygame.draw.line(surf, dark, (zx, zy), (int(ax), int(ay)), arm_w)
        if z.kind == "brute":                                   # shoulder pads
            for side in (-1.3, 1.3):
                sx = zx + math.cos(ang + side) * r * 0.8
                sy = zy + math.sin(ang + side) * r * 0.8
                pygame.draw.circle(surf, (120, 120, 125), (int(sx), int(sy)), max(2, r // 2))
        pygame.draw.circle(surf, body, (zx, zy), r)
        pygame.draw.circle(surf, dark, (zx, zy), r, 2 if z.kind != "hunter" else 3)
        ex, ey = math.cos(ang) * r * 0.45, math.sin(ang) * r * 0.45
        eye = (255, 230, 60) if z.kind == "hunter" else (255, 40, 40)
        pygame.draw.circle(surf, eye, (int(zx + ex - ey * 0.6), int(zy + ey + ex * 0.6)), 2)
        pygame.draw.circle(surf, eye, (int(zx + ex + ey * 0.6), int(zy + ey - ex * 0.6)), 2)
        if z.kind == "screamer":                                # wide-open mouth + sound rings
            mx, my = zx + int(math.cos(ang) * r * 0.2), zy + int(math.sin(ang) * r * 0.2)
            pygame.draw.circle(surf, (30, 0, 20), (mx, my), max(2, r // 3))
            if z.scream_timer > SCREAM_COOLDOWN - 1.2:
                k = (t * 3) % 1.0
                pygame.draw.circle(surf, (220, 120, 255), (zx, zy), int(r + 4 + k * 14), 2)

    def draw_helicopter(self, surf, game):
        pad = self._exit_rect(game)
        pad_x, pad_y = pad.center
        left = game.heli_time_left
        if game.heli_state == "landed":
            cx, cy, height = pad_x, pad_y, 0
        elif game.heli_state == "incoming" and left is not None and left < 4:
            f = left / 4          # 1 -> far away, 0 -> landed
            cx, cy, height = pad_x + f * 260, pad_y - f * 300, f * 40
        else:
            return
        cx, cy = int(cx), int(cy)
        pygame.draw.ellipse(surf, (0, 0, 0), (cx - 26, cy - 8 + 6, 52, 18))
        cy -= int(height)
        pygame.draw.rect(surf, (60, 75, 50), (cx - 52, cy - 3, 34, 6))                    # tail
        pygame.draw.circle(surf, (80, 80, 80), (cx - 52, cy), 6, 2)                         # tail rotor
        pygame.draw.ellipse(surf, (70, 90, 55), (cx - 26, cy - 13, 52, 26))                 # body
        pygame.draw.ellipse(surf, (150, 200, 230), (cx + 6, cy - 9, 18, 18))                # cockpit
        ang = self.anim_t * 25
        for k in range(2):
            a = ang + k * math.pi / 2
            dx, dy = math.cos(a) * 34, math.sin(a) * 34
            pygame.draw.line(surf, (200, 200, 200), (cx - dx, cy - dy), (cx + dx, cy + dy), 3)
        pygame.draw.circle(surf, (30, 30, 30), (cx, cy), 4)

    def draw_boat(self, surf, game):
        pad = self._exit_rect(game)
        cx = pad.right + TILE // 2 + TILE          # in the river next to the dock
        final_y = pad.centery
        left = game.heli_time_left
        if game.heli_state == "landed":
            cy = final_y
        elif game.heli_state == "incoming" and left is not None and left < 5:
            cy = final_y + left / 5 * 260
        else:
            return
        cx = min(cx, game.map.w * TILE - 14)
        cy = int(cy + math.sin(self.anim_t * 2) * 2)
        hull = [(cx, cy - 34), (cx + 13, cy - 16), (cx + 13, cy + 26), (cx - 13, cy + 26), (cx - 13, cy - 16)]
        pygame.draw.polygon(surf, (0, 0, 0), [(x + 3, y + 4) for x, y in hull])
        pygame.draw.polygon(surf, (235, 235, 230), hull)
        pygame.draw.polygon(surf, (200, 60, 50), hull, 3)
        pygame.draw.rect(surf, (120, 170, 210), (cx - 8, cy - 8, 16, 14), border_radius=3)
        pygame.draw.rect(surf, (60, 60, 70), (cx - 6, cy + 20, 12, 8))                # outboard motor
        if game.heli_state == "incoming" or int(self.anim_t * 8) % 2:
            for i in range(3):
                pygame.draw.circle(surf, (200, 230, 250), (cx + random.randint(-6, 6), cy + 32 + i * 6), 2)

    def draw_elevator(self, surf, game):
        pad = self._exit_rect(game)
        left = game.heli_time_left
        if game.heli_state == "landed":
            gap = pad.w // 2 - 4
        elif game.heli_state == "incoming" and left is not None and left < 2:
            gap = int((1 - left / 2) * (pad.w // 2 - 4))
        else:
            gap = 0
        # light spilling out of the car once the doors open
        if gap:
            light = pygame.Surface(pad.size, pygame.SRCALPHA)
            light.fill((255, 240, 180, 70))
            surf.blit(light, pad)
        door = (165, 172, 178)
        pygame.draw.rect(surf, door, (pad.x + 3, pad.y + 3, pad.w // 2 - 3 - gap, pad.h - 6))
        pygame.draw.rect(surf, door, (pad.centerx + gap, pad.y + 3, pad.w // 2 - 3 - gap, pad.h - 6))
        # floor indicator
        lit = game.heli_state != "waiting"
        col = (90, 255, 120) if lit and int(self.anim_t * 3) % 2 else (90, 40, 30)
        pygame.draw.circle(surf, col, (pad.centerx, pad.y + 6), 3)

    def draw_checkpoint(self, surf, game):
        pad = self._exit_rect(game)
        t = self.anim_t
        # waving flag
        fx, fy = pad.right + 14, pad.y - 30
        pygame.draw.line(surf, (200, 200, 200), (fx, fy), (fx, fy + 40), 2)
        wave = [(fx, fy), (fx + 18, fy + 3 + math.sin(t * 5) * 2), (fx + 16, fy + 12 + math.sin(t * 5 + 1) * 2),
                (fx, fy + 10)]
        pygame.draw.polygon(surf, (60, 140, 70), wave)
        # soldiers
        for i, sy in enumerate((pad.y - 10, pad.bottom + 22)):
            sx = pad.centerx
            pygame.draw.circle(surf, (0, 0, 0), (sx + 2, sy + 3), 8)
            pygame.draw.circle(surf, (80, 105, 60), (sx, sy), 8)
            pygame.draw.circle(surf, (50, 70, 40), (sx, sy), 8, 2)
        # raised gate arm
        pygame.draw.line(surf, (240, 240, 240), (pad.x + 4, pad.bottom), (pad.x + 24, pad.bottom - 40), 4)
        pygame.draw.line(surf, (220, 50, 40), (pad.x + 12, pad.bottom - 16), (pad.x + 18, pad.bottom - 28), 4)

    # ------------------------------------------------------------------
    #  HUD  (wooden seed-bar style)
    # ------------------------------------------------------------------
    def draw_heart(self, x, y, filled):
        col = RED if filled else (90, 60, 50)
        edge = (90, 10, 10) if filled else (50, 30, 20)
        for c, grow in ((edge, 2), (col, 0)):
            pygame.draw.circle(self.screen, c, (x - 4, y - 2), 5 + grow)
            pygame.draw.circle(self.screen, c, (x + 4, y - 2), 5 + grow)
            pygame.draw.polygon(self.screen, c, [(x - 9 - grow, y), (x + 9 + grow, y), (x, y + 9 + grow)])
        if filled:
            pygame.draw.circle(self.screen, (255, 170, 160), (x - 5, y - 4), 2)

    def draw_icon(self, kind, cx, cy, extra=None, surf=None):
        s = surf or self.screen
        if kind == "stamina":
            pts = [(cx + 3, cy - 14), (cx - 7, cy + 1), (cx, cy + 1), (cx - 4, cy + 14),
                   (cx + 8, cy - 3), (cx + 1, cy - 3)]
            pygame.draw.polygon(s, ui.GOLD, pts)
            pygame.draw.polygon(s, ui.WOOD_EDGE, pts, 2)
        elif kind == "noise":
            pygame.draw.circle(s, (240, 200, 160), (cx - 8, cy), 9)
            pygame.draw.circle(s, ui.WOOD_EDGE, (cx - 8, cy), 9, 2)
            n, col = extra
            for i in range(3):
                c = col if i < n else (170, 150, 110)
                pygame.draw.arc(s, c, (cx - 6 - i * 5, cy - 8 - i * 5, 16 + i * 10, 16 + i * 10), -0.9, 0.9, 3)
        elif kind == "barricade":
            r = pygame.Rect(cx - 15, cy - 11, 30, 22)
            pygame.draw.rect(s, BARRICADE_DARK, r, border_radius=3)
            for i in range(3):
                pygame.draw.rect(s, BARRICADE_COL, (r.x + 2, r.y + 2 + i * 7, r.w - 4, 5))
            pygame.draw.line(s, BARRICADE_DARK, r.topleft, r.bottomright, 3)
        elif kind == "radio":
            pygame.draw.rect(s, (40, 60, 90), (cx - 14, cy - 8, 28, 20), border_radius=4)
            pygame.draw.rect(s, (110, 170, 255), (cx - 14, cy - 8, 28, 20), 3, border_radius=4)
            pygame.draw.line(s, (90, 90, 100), (cx + 8, cy - 8), (cx + 12, cy - 18), 3)
            pygame.draw.circle(s, (120, 255, 140), (cx + 12, cy - 18), 3)
            pygame.draw.circle(s, (200, 220, 255), (cx - 5, cy + 2), 4)
        elif kind == "fuel":
            pygame.draw.rect(s, (200, 40, 35), (cx - 10, cy - 11, 20, 24), border_radius=4)
            pygame.draw.rect(s, (110, 20, 20), (cx - 10, cy - 11, 20, 24), 2, border_radius=4)
            pygame.draw.rect(s, (230, 200, 60), (cx + 3, cy - 17, 6, 7))
            pygame.draw.line(s, (240, 230, 220), (cx - 6, cy - 6), (cx + 5, cy + 8), 3)
        elif kind == "bottle":
            pygame.draw.rect(s, (60, 150, 70), (cx - 6, cy - 4, 12, 18), border_radius=4)
            pygame.draw.rect(s, (60, 150, 70), (cx - 3, cy - 14, 6, 11))
            pygame.draw.rect(s, (30, 80, 35), (cx - 6, cy - 4, 12, 18), 2, border_radius=4)
            pygame.draw.line(s, (180, 240, 180), (cx - 3, cy), (cx - 3, cy + 9), 2)
        elif kind == "clock":
            pygame.draw.circle(s, (250, 245, 230), (cx, cy), 13)
            pygame.draw.circle(s, ui.WOOD_EDGE, (cx, cy), 13, 2)
            a = self.anim_t * 2
            pygame.draw.line(s, ui.WOOD_EDGE, (cx, cy), (cx, cy - 9), 2)
            pygame.draw.line(s, RED, (cx, cy), (cx + math.cos(a) * 9, cy + math.sin(a) * 9), 2)
        elif kind == "water":
            pygame.draw.rect(s, WATER_COL, (cx - 12, cy - 9, 24, 18), border_radius=4)
            for i in range(2):
                pygame.draw.line(s, (120, 190, 230), (cx - 8 + i * 6, cy - 3 + i * 6), (cx + i * 6, cy - 3 + i * 6), 2)
        elif kind == "fuse":
            pygame.draw.rect(s, (230, 220, 200), (cx - 12, cy - 6, 24, 12), border_radius=5)
            pygame.draw.rect(s, (90, 80, 60), (cx - 12, cy - 6, 24, 12), 2, border_radius=5)
            pygame.draw.rect(s, (200, 170, 60), (cx - 15, cy - 4, 4, 8))
            pygame.draw.rect(s, (200, 170, 60), (cx + 11, cy - 4, 4, 8))
            pygame.draw.line(s, (240, 120, 40), (cx - 8, cy), (cx + 8, cy), 2)
        elif kind == "battery":
            level = extra if extra is not None else 1.0
            pygame.draw.rect(s, (40, 40, 45), (cx - 13, cy - 8, 24, 16), border_radius=3)
            pygame.draw.rect(s, (200, 200, 200), (cx + 11, cy - 3, 3, 6))
            col = (90, 210, 90) if level > 0.3 else (230, 80, 50)
            pygame.draw.rect(s, col, (cx - 11, cy - 6, int(20 * level), 12), border_radius=2)
        elif kind == "flashlight":
            pygame.draw.polygon(s, (255, 240, 160), [(cx + 2, cy), (cx + 16, cy - 9), (cx + 16, cy + 9)])
            pygame.draw.rect(s, (70, 70, 80), (cx - 12, cy - 4, 15, 8), border_radius=2)
        elif kind == "sleeper":
            z = Zombie(0, 0)
            z.state = SLEEP
            z.wobble = 0.3
            self.draw_zombie(s, z, cx, cy)
        elif kind == "mud":
            pygame.draw.rect(s, MUD_COL, (cx - 12, cy - 9, 24, 18), border_radius=4)
            pygame.draw.circle(s, (70, 50, 28), (cx - 4, cy), 3)
            pygame.draw.circle(s, (70, 50, 28), (cx + 5, cy + 3), 2)

    def draw_hud(self, game):
        scr = self.screen
        p = game.player
        mode = game.exit_mode
        ui.wood_panel(scr, (0, -12, SCREEN_W, HUD_H + 12), radius=14, nails=False)
        pygame.draw.rect(scr, ui.WOOD_EDGE, (0, HUD_H - 4, SCREEN_W, 4))

        cw, ch, cy = 84, 66, 8
        xs = [10 + i * (cw + 8) for i in range(5)]

        # Health
        plate = ui.card(scr, (xs[0], cy, cw, ch))
        for i in range(PLAYER_MAX_HP):
            self.draw_heart(xs[0] + 18 + i * 24, cy + 24, i < p.hp)
        ui.text(scr, "HEALTH", 13, plate.center, ui.INK, None)

        # Stamina
        plate = ui.card(scr, (xs[1], cy, cw, ch), active=not p.exhausted)
        self.draw_icon("stamina", xs[1] + 16, cy + 27)
        ui.bar(scr, (xs[1] + 30, cy + 21, cw - 38, 12), p.stamina / STAMINA_MAX,
               (230, 120, 60) if p.exhausted else (90, 200, 255))
        ui.text(scr, "TIRED!" if p.exhausted else "STAMINA", 13, plate.center,
                RED if p.exhausted else ui.INK, None)

        # Noise
        if p.moving and p.in_water:
            txt, col, n = "SPLASH!", (30, 110, 200), 3
        elif p.running:
            txt, col, n = "LOUD", RED, 3
        elif p.moving:
            txt, col, n = "QUIET", (200, 150, 0), 1
        else:
            txt, col, n = "SILENT", (40, 150, 60), 0
        plate = ui.card(scr, (xs[2], cy, cw, ch))
        self.draw_icon("noise", xs[2] + cw // 2, cy + 27, (n, col))
        ui.text(scr, txt, 13, plate.center, col, None)

        # Barricades
        plate = ui.card(scr, (xs[3], cy, cw, ch), active=p.barricades > 0)
        self.draw_icon("barricade", xs[3] + cw // 2, cy + 27)
        ui.text(scr, f"x {p.barricades}", 15, plate.center, ui.INK, None)

        # Level-specific fifth card
        left = game.heli_time_left
        if mode == "elevator":
            xs.append(xs[4] + cw + 8)
            plate = ui.card(scr, (xs[5], cy, cw, ch), active=p.battery > 0)
            self.draw_icon("battery", xs[5] + 22, cy + 28, p.battery / BATTERY_MAX)
            on = p.flashlight
            ui.text(scr, "ON" if on else "OFF", 12, (xs[5] + 60, cy + 28),
                    (40, 150, 60) if on else (120, 100, 80), None)
            ui.text(scr, "L: LIGHT", 13, plate.center, ui.INK, None)
        if mode in ("heli", "boat", "elevator"):
            plate = ui.card(scr, (xs[4], cy, cw, ch))
            icon = {"heli": "radio", "boat": "fuel", "elevator": "fuse"}[mode]
            self.draw_icon(icon, xs[4] + 24, cy + 30)
            d = game.nearest_radio_distance
            strength = max(0, min(5, int(6 - d / 3.5))) if d is not None and game.heli_state == "waiting" else 0
            for i in range(5):
                h = 4 + i * 3
                c = (60, 130, 255) if i < strength else (170, 160, 130)
                pygame.draw.rect(scr, c, (xs[4] + 48 + i * 6, cy + 40 - h, 4, h))
            ui.text(scr, f"{game.parts_collected}/{game.parts_needed}", 15, plate.center, (40, 80, 180), None)
        elif mode == "checkpoint":
            plate = ui.card(scr, (xs[4], cy, cw, ch), active=p.bottles > 0)
            self.draw_icon("bottle", xs[4] + 26, cy + 28)
            ui.text(scr, "T / click", 11, (xs[4] + 58, cy + 30), ui.INK, None)
            ui.text(scr, f"x {p.bottles}", 15, plate.center, ui.INK, None)
        else:
            inside = game.in_safe_zone
            plate = ui.card(scr, (xs[4], cy, cw, ch), active=inside or game.heli_state != "incoming")
            self.draw_icon("clock", xs[4] + 22, cy + 28)
            secs = int(left) + 1 if left is not None else 0
            ui.text(scr, f"{secs // 60}:{secs % 60:02d}", 15, (xs[4] + 58, cy + 28), ui.INK, None)
            label, lc = ("HOLD!", (40, 150, 60)) if inside else ("PAUSED", RED)
            if game.heli_state == "landed":
                label, lc = "BOARD!", RED
            ui.text(scr, label, 13, plate.center, lc, None)

        # Objective sign
        flash = int(self.anim_t * 4) % 2
        if mode == "checkpoint":
            remaining = max(0, int(min(t[0] for t in game.map.helipad) - p.x))
            txt, col = (f"Checkpoint: {remaining} m east" if remaining else "Show your papers..."), ui.CREAM
        elif mode == "survive":
            if game.heli_state == "landed":
                txt, col = f"BOARD NOW!  {int(left) + 1}s left", RED if flash else ui.CREAM
            elif game.in_safe_zone:
                txt, col = f"Hold the zone! Helicopter in {int(left) + 1}s", ui.GOLD
            else:
                txt, col = "Back to the zone! Timer paused", RED if flash else ui.CREAM
        elif game.heli_state == "waiting":
            txt, col = f"Find the {game.cfg['item']}s!", ui.CREAM
        elif game.heli_state == "incoming":
            where = {"boat": "the dock", "elevator": "the lift"}.get(mode, "the pad")
            txt, col = f"{game.exit_name.capitalize()} in {int(left) + 1}s - go to {where}!", ui.GOLD
        else:
            txt, col = f"BOARD NOW!  {int(left) + 1}s left", RED if flash else ui.CREAM
        sx = xs[-1] + cw + 16
        sign = pygame.Rect(sx, cy + 2, SCREEN_W - sx - 10, 40)
        pygame.draw.rect(scr, ui.WOOD_DARK, sign, border_radius=10)
        pygame.draw.rect(scr, ui.WOOD_EDGE, sign, 3, border_radius=10)
        size = 21
        while size > 14 and ui.font(size).size(txt)[0] > sign.w - 24:
            size -= 1
        ui.text(scr, txt, size, sign.center, col, ui.WOOD_EDGE, 2)
        keys = {"checkpoint": "F: car alarm  |  ", "elevator": "L: light  |  "}.get(mode, "")
        ui.text(scr, f"Level {game.level} - {game.difficulty}   |   {keys}F1: AI view   |   P: pause", 13,
                (sign.centerx, sign.bottom + 13), (255, 230, 170), ui.WOOD_EDGE, 1)

        # Progress meter (bottom right)
        if mode == "checkpoint":
            frac, label = game.exit_progress, "BRIDGE CROSSED"
        elif mode == "survive":
            total = game.cfg["survive_time"]
            if game.heli_state == "incoming":
                frac, label = 0.9 * (1 - (left or 0) / total), "HOLD ON"
            else:
                frac, label = 0.9 + 0.1 * game.board_progress / game.board_time, "ESCAPE!"
        elif game.heli_state == "waiting":
            frac, label = 0.6 * game.parts_collected / max(1, game.parts_needed), game.cfg["items_label"]
        elif game.heli_state == "incoming":
            frac, label = 0.6 + 0.3 * (1 - (left or 0) / HELI_CALL_TIME), f"{game.exit_name.upper()} COMING"
        else:
            frac, label = 0.9 + 0.1 * game.board_progress / game.board_time, "ESCAPE!"
        ui.progress_meter(scr, (SCREEN_W - 214, SCREEN_H - 44, 190, 14), max(0.0, min(1.0, frac)),
                          [0.25, 0.5, 0.75, 1.0], label, self.anim_t)

        # Messages as hanging wooden signs
        for i, (msg, _secs) in enumerate(game.messages):
            ui.banner(scr, msg, (SCREEN_W // 2, HUD_H + 34 + i * 50), 20)

        if self.debug:
            lines = ["AI DEBUG VIEW (F1)",
                     f"Zombies: {len(game.zombies)}   "
                     + "  ".join(f"{st}: {sum(z.state == st for z in game.zombies)}" for st in (WANDER, INVESTIGATE, CHASE)),
                     f"A* paths planned: {game.stats['paths_planned']}   nodes expanded: {game.stats['nodes_expanded']}"]
            if game.map.theme == "hospital":
                lines.append("Zz = SLEEP state: blind, hears only 60% as far. Light = seen 1.5x further")
            elif game.map.theme == "flood":
                lines.append(f"A* costs: street 1, mud {MUD_PATH_COST}, water {WATER_PATH_COST}, barricade {BARRICADE_PATH_COST}")
            elif game.map.theme == "stand":
                lines.append("Red crosshair = Hunter's predicted intercept point")
            else:
                lines.append("Lines = A* paths   circles = sight range   W/I/C = FSM state")
            box = pygame.Rect(8, SCREEN_H - 22 * len(lines) - 30, 560, 22 * len(lines) + 20)
            ui.wood_panel(scr, box, radius=10, nails=False, base=ui.WOOD_DARK)
            for i, line in enumerate(lines):
                ui.text(scr, line, 15, (box.x + 16, box.y + 10 + i * 22), ui.GOLD if i == 0 else ui.CREAM,
                        ui.WOOD_EDGE, 1, anchor="topleft", shadow=False)

    # ------------------------------------------------------------------
    #  Screens
    # ------------------------------------------------------------------
    def draw(self):
        self.screen.fill(BG)
        self.buttons = []
        if self.scene == "menu":
            self.draw_menu()
            return
        offset = (random.randint(-4, 4), random.randint(-4, 4)) if self.shake > 0 else (0, 0)
        self.draw_world(self.game, self.city, use_fog=True, debug=self.debug, offset=offset)
        self.draw_hud(self.game)
        if self.scene == "intro":
            self.draw_intro()
        elif self.scene == "play" and self.paused:
            self.draw_panel("PAUSED", ["Take a breather...", "The zombies will wait.  (P / Esc)"], ui.CREAM,
                            [("Resume", "resume", ui.LEAF), ("Menu", "menu", (210, 150, 50)),
                             ("Quit", "quit", (190, 60, 50))])
        elif self.scene == "end":
            g = self.game
            mins, secs = divmod(int(g.time), 60)
            stats = [g.reason,
                     f"{level_name(g.level)}  -  {g.difficulty}",
                     f"Time: {mins}:{secs:02d}     Distance: {g.stats['distance']:.0f} tiles",
                     f"Spotted: {g.stats['times_spotted']}     Bites: {g.stats['bites']}",
                     f"Barricades placed: {g.stats['barricades_used']}     smashed: {g.stats['barricades_broken']}",
                     f"Zombie A* searches: {g.stats['paths_planned']}  ({g.stats['nodes_expanded']} nodes)"]
            if g.level == 4:
                stats.insert(4, f"Bottles thrown: {g.stats['bottles_thrown']}     Car alarms: {g.stats['alarms']}")
            elif g.level == 5:
                stats.insert(4, f"Screams heard: {g.stats['screams']}")
            if g.state == "won":
                btns = [("Replay (R)", "again", (210, 150, 50)), ("Menu (M)", "menu", (150, 120, 90))]
                if self.level_index + 1 < len(LEVEL_ORDER):
                    btns.insert(0, ("Next Level (N)", "next", ui.LEAF))
                title = "YOU ESCAPED!" if self.level_index + 1 < len(LEVEL_ORDER) else "YOU SURVIVED IT ALL!"
                self.draw_panel(title, stats, ui.LEAF_LIGHT, btns)
            else:
                self.draw_panel("THE ZOMBIES GOT YOU!", stats, RED,
                                [("Try Again (R)", "again", ui.LEAF), ("Menu (M)", "menu", (210, 150, 50))])

    def draw_panel(self, title, lines, colour, buttons=()):
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        w = 640
        h = 130 + len(lines) * 30 + (84 if buttons else 0)
        board = pygame.Rect(0, 0, w, h)
        board.center = (SCREEN_W // 2, SCREEN_H // 2 + 20)
        ui.wood_panel(self.screen, board, radius=18)
        ui.text(self.screen, title, 42, (board.centerx, board.top + 40), colour, ui.WOOD_EDGE, 3)
        note = pygame.Rect(board.x + 40, board.y + 78, w - 80, len(lines) * 30 + 24)
        ui.paper_panel(self.screen, note)
        for i, line in enumerate(lines):
            ui.text(self.screen, line, 18 if i else 20, (note.centerx, note.top + 26 + i * 30),
                    ui.INK if i else (150, 40, 20), None)
        self._button_row(buttons, board.centerx, note.bottom + 18)

    def _button_row(self, buttons, cx, y, bw=170):
        mouse = pygame.mouse.get_pos()
        total = len(buttons) * bw + (len(buttons) - 1) * 16
        for i, (label, action, col) in enumerate(buttons):
            r = pygame.Rect(cx - total // 2 + i * (bw + 16), y, bw, 50)
            ui.button(self.screen, r, label, r.collidepoint(mouse), col, 19)
            self.buttons.append((r, action))

    def draw_intro(self):
        """Level card shown before play: what's new and what the goal is."""
        g = self.game
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        self.screen.blit(shade, (0, 0))
        hurdles = g.cfg["hurdles"][:2] if g.level == 5 else g.cfg["hurdles"]   # L5 lists the zombie types below
        extra = 4 * 34 if g.level == 5 else 0
        h = 150 + len(hurdles) * 34 + extra + 84
        board = pygame.Rect(0, 0, 700, h)
        board.center = (SCREEN_W // 2, SCREEN_H // 2 + 30)
        ui.wood_panel(self.screen, board, radius=18)
        ui.text(self.screen, f"LEVEL {g.level}", 22, (board.centerx, board.top + 26), ui.GOLD, ui.WOOD_EDGE, 2)
        ui.text(self.screen, g.cfg["name"].upper(), 40, (board.centerx, board.top + 60), ui.LEAF_LIGHT, ui.LEAF_DARK, 3)
        note = pygame.Rect(board.x + 36, board.y + 96, board.w - 72, len(hurdles) * 34 + extra + 24)
        ui.paper_panel(self.screen, note)
        icons = {2: ["water", "mud", "water", "fuel"], 3: [None, "flashlight", "sleeper", "fuse"],
                 4: [None, None, "bottle", None]}.get(g.level, [])
        for i, line in enumerate(hurdles):
            y = note.y + 28 + i * 34
            icon = icons[i] if i < len(icons) else None
            if icon:
                self.draw_icon(icon, note.x + 26, y)
            elif g.level == 4 and i in (0, 1):
                self._mini_car(note.x + 26, y)
            else:
                pygame.draw.circle(self.screen, ui.LEAF, (note.x + 26, y), 6)
                pygame.draw.circle(self.screen, ui.LEAF_DARK, (note.x + 26, y), 6, 2)
            ui.text(self.screen, line, 17, (note.x + 50, y), ui.INK, None, anchor="midleft")
        if g.level == 5:
            for i, kind in enumerate(("runner", "screamer", "brute", "hunter")):
                y = note.y + 28 + (len(hurdles) + i) * 34
                z = Zombie(0, 0, kind)
                z.wobble = 0.0
                self.draw_zombie(self.screen, z, note.x + 26, y, scale=1.1)
                ui.text(self.screen, KIND_INFO[kind], 16, (note.x + 50, y), (120, 30, 20), None, anchor="midleft")
        self._button_row([("Let's go! (Enter)", "go", ui.LEAF), ("Menu", "menu", (210, 150, 50))],
                         board.centerx, note.bottom + 18, bw=200)

    def _mini_car(self, cx, cy):
        r = pygame.Rect(cx - 13, cy - 7, 26, 14)
        pygame.draw.rect(self.screen, CAR_COLOURS[0], r, border_radius=4)
        pygame.draw.rect(self.screen, (80, 25, 22), r, 2, border_radius=4)
        pygame.draw.rect(self.screen, (60, 80, 100), (cx + 2, cy - 4, 5, 8))

    def draw_menu(self):
        # zombies shambling around the selected level in the background
        self.draw_world(self.demo, self.demo_city, use_fog=False, debug=False)
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        self.screen.blit(shade, (0, 0))
        mouse = pygame.mouse.get_pos()

        # Title sign hanging from chains
        wobble = int(math.sin(self.anim_t * 1.5) * 3)
        sign = pygame.Rect(0, 0, 600, 110)
        sign.center = (SCREEN_W // 2, 76 + wobble)
        for cx in (sign.left + 60, sign.right - 60):
            pygame.draw.line(self.screen, (120, 120, 130), (cx, 0), (cx, sign.top + 8), 4)
        ui.wood_panel(self.screen, sign, radius=20)
        ui.text(self.screen, "ZOMBIE ESCAPE", 60, (sign.centerx, sign.centery - 10), ui.LEAF_LIGHT, ui.LEAF_DARK, 4)
        ui.text(self.screen, "Pick a level. Stay quiet. Get out alive!", 16,
                (sign.centerx, sign.bottom - 20), ui.CREAM, ui.WOOD_EDGE, 2)

        # Level cards (Level 3 hasn't been designed yet)
        slots = [1, 2, 3, 4, 5]
        cw, ch, gap = 168, 132, 14
        x0 = SCREEN_W // 2 - (len(slots) * cw + (len(slots) - 1) * gap) // 2
        for i, n in enumerate(slots):
            r = pygame.Rect(x0 + i * (cw + gap), 150, cw, ch)
            locked = n not in LEVELS
            selected = not locked and LEVEL_ORDER.index(n) == self.level_index
            hover = r.collidepoint(mouse) and not locked
            lift = -6 if selected else (-3 if hover else 0)
            card = r.move(0, lift)
            ui.card(self.screen, card, active=not locked)
            if selected:
                pygame.draw.rect(self.screen, ui.GOLD, card.inflate(8, 8), 4, border_radius=10)
            ui.text(self.screen, f"LEVEL {n}", 16, (card.centerx, card.y + 22),
                    ui.INK if not locked else (90, 80, 60), None)
            self._level_icon(n, card.centerx, card.y + 62, locked)
            name = LEVELS[n]["name"].replace("The ", "") if not locked else "Coming soon"
            ui.text(self.screen, name, 13 if len(name) > 13 else 14, (card.centerx, card.bottom - 12),
                    ui.INK if not locked else (90, 80, 60), None)
            if not locked:
                self.buttons.append((r, ("level", LEVEL_ORDER.index(n))))

        # Difficulty
        ui.text(self.screen, "DIFFICULTY", 16, (SCREEN_W // 2, 312), ui.GOLD, ui.WOOD_EDGE, 2)
        cols = [(110, 190, 60), (225, 160, 40), (205, 60, 50)]
        for i, name in enumerate(DIFF_NAMES):
            r = pygame.Rect(0, 0, 150, 44)
            r.center = (SCREEN_W // 2 + (i - 1) * 166, 350)
            selected = i == self.diff_index
            ui.button(self.screen, r, name.upper(), selected or r.collidepoint(mouse),
                      cols[i] if selected else (125, 112, 95), 20)
            self.buttons.append((r, ("diff", i)))

        # Start
        r = pygame.Rect(0, 0, 300, 58)
        r.center = (SCREEN_W // 2, 418)
        ui.button(self.screen, r, "START", r.collidepoint(mouse), ui.LEAF, 32)
        self.buttons.append((r, "start"))
        ui.text(self.screen, "Arrows: level / difficulty   -   Enter: start", 14, (SCREEN_W // 2, 462),
                ui.CREAM, ui.WOOD_EDGE, 1)

        # Controls + tips
        controls = ["WASD / Arrows - move", "Shift - run (fast but LOUD)", "Space / E - place barricade",
                    "L - flashlight (Lv 3)   T / click - bottle (Lv 4)", "F - car alarm (Lv 4)   F1 - AI view"]
        info = LEVELS[self.level]
        tips = info["hurdles"]
        for x, heading, lines in ((30, "HOW TO PLAY", controls),
                                  (SCREEN_W // 2 + 15, info["name"].upper(), tips)):
            board = pygame.Rect(x, 482, SCREEN_W // 2 - 45, 228)
            ui.wood_panel(self.screen, board, radius=14)
            note = pygame.Rect(board.x + 18, board.y + 44, board.w - 36, board.h - 60)
            ui.paper_panel(self.screen, note)
            ui.text(self.screen, heading, 18, (board.centerx, board.top + 24), ui.GOLD, ui.WOOD_EDGE, 2)
            for i, line in enumerate(lines):
                ui.text(self.screen, line, 13 if len(line) > 44 else 14, (note.x + 12, note.y + 10 + i * 32),
                        ui.INK, None, anchor="topleft")

    def _level_icon(self, n, cx, cy, locked):
        s = self.screen
        box = pygame.Rect(cx - 50, cy - 26, 100, 52)
        if locked:
            pygame.draw.rect(s, (120, 110, 90), box, border_radius=8)
            pygame.draw.rect(s, (90, 80, 60), (cx - 12, cy - 4, 24, 20), border_radius=3)
            pygame.draw.arc(s, (90, 80, 60), (cx - 9, cy - 18, 18, 22), 0, math.pi, 4)
            return
        if n == 1:
            pygame.draw.rect(s, (30, 32, 44), box, border_radius=8)
            for i in range(4):
                b = pygame.Rect(box.x + 6 + i * 23, box.y + 10 + (i % 2) * 8, 18, 34 - (i % 2) * 8)
                pygame.draw.rect(s, ROOFS[i], b)
                s.fill(WINDOW_ON, (b.x + 4, b.y + 5, 4, 4))
            pygame.draw.circle(s, YELLOW, (box.right - 10, box.y + 10), 5, 2)
        elif n == 2:
            pygame.draw.rect(s, WATER_COL, box, border_radius=8)
            for i in range(3):
                col = AWNINGS[i]
                b = pygame.Rect(box.x + 6 + i * 31, box.y + 6, 26, 14)
                pygame.draw.rect(s, (235, 225, 205), b)
                for k in range(0, 26, 6):
                    s.fill(col, (b.x + k, b.y, 3, 14))
            pygame.draw.rect(s, MUD_COL, (box.x + 8, box.bottom - 16, 30, 10), border_radius=4)
            for i in range(3):
                pygame.draw.line(s, (120, 190, 230), (box.x + 50 + i * 12, box.bottom - 12), (box.x + 57 + i * 12, box.bottom - 12), 2)
        elif n == 3:
            pygame.draw.rect(s, (24, 28, 30), box, border_radius=8)
            beam = [(box.x + 18, box.centery), (box.right - 8, box.y + 6), (box.right - 8, box.bottom - 6)]
            pygame.draw.polygon(s, (120, 115, 80), beam)
            pygame.draw.rect(s, (205, 210, 205), (box.x + 52, box.y + 18, 22, 14), border_radius=3)
            pygame.draw.rect(s, (220, 40, 40), (box.x + 10, box.y + 8, 12, 4))
            pygame.draw.rect(s, (220, 40, 40), (box.x + 14, box.y + 4, 4, 12))
            pygame.draw.circle(s, PLAYER_COL, (box.x + 18, box.centery), 5)
            ui.text(s, "z", 12, (box.x + 78, box.y + 14), (170, 190, 255), None)
        elif n == 4:
            pygame.draw.rect(s, WATER_DEEP, box, border_radius=8)
            deck = pygame.Rect(box.x, box.y + 12, box.w, 28)
            pygame.draw.rect(s, ASPHALT, deck)
            pygame.draw.rect(s, (150, 150, 145), (deck.x, deck.y - 3, deck.w, 3))
            pygame.draw.rect(s, (150, 150, 145), (deck.x, deck.bottom, deck.w, 3))
            for i, col in enumerate(CAR_COLOURS[:3]):
                pygame.draw.rect(s, col, (deck.x + 10 + i * 30, deck.y + 4 + (i % 2) * 10, 18, 9), border_radius=3)
        elif n == 5:
            pygame.draw.rect(s, (60, 58, 52), box, border_radius=8)
            pygame.draw.rect(s, (190, 170, 120), box.inflate(-20, -12), 4)
            pygame.draw.circle(s, YELLOW, box.center, 9, 2)
            z = Zombie(0, 0, "brute")
            z.wobble = 0.0
            self.draw_zombie(s, z, box.right - 12, box.y + 12, scale=0.7)


if __name__ == "__main__":
    App().run()
