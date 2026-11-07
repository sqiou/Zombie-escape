"""
main.py - Zombie Escape front end (drawing, input, sound, menus).

Run:   python main.py

All game rules and AI live in game.py; this file only shows the game
and turns key presses into inputs.
"""

import math
import random
import sys
from array import array

import pygame

import ui
from settings import *
from game import (Game, STREET, BUILDING, BARRICADE, WANDER, INVESTIGATE, CHASE)

DIFF_NAMES = list(DIFFICULTY.keys())

# ---------------- Colours ----------------
BG = (10, 10, 16)
ASPHALT = (44, 46, 54)
ASPHALT_2 = (48, 50, 58)
LANE = (70, 72, 60)
ROOFS = [(58, 52, 70), (66, 56, 52), (50, 62, 70), (62, 62, 58), (54, 48, 60)]
WINDOW_ON = (230, 200, 110)
WINDOW_OFF = (34, 34, 44)
PLAYER_COL = (90, 220, 255)
ZOMBIE_COL = (110, 170, 80)
ZOMBIE_DARK = (60, 100, 45)
BARRICADE_COL = (140, 95, 50)
BARRICADE_DARK = (95, 60, 30)
STATE_COLOURS = {WANDER: (150, 200, 150), INVESTIGATE: (255, 210, 60), CHASE: (255, 70, 70)}
WHITE = (240, 240, 240)
GREY = (150, 150, 160)
RED = (230, 60, 60)
GREEN = (90, 220, 120)
YELLOW = (255, 210, 60)


def to_screen(x, y):
    """Tile coordinates -> pixel coordinates (map is drawn below the HUD)."""
    return int(x * TILE), int(y * TILE) + HUD_H


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
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Zombie Escape")
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.Font(None, 96)
        self.font_big = pygame.font.Font(None, 56)
        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)
        self.sounds = Sounds()

        self.scene = "menu"            # "menu", "play", "end"
        self.diff_index = 1
        self.paused = False
        self.debug = False
        self.game = None
        self.city = None
        self.shake = 0.0
        self.red_flash = 0.0
        self.anim_t = 0.0
        self.buttons = []          # (rect, action) for mouse clicks

        self.fog = pygame.Surface((GRID_W * TILE, GRID_H * TILE), pygame.SRCALPHA)
        self.overlay = pygame.Surface((GRID_W * TILE, GRID_H * TILE), pygame.SRCALPHA)
        self._new_demo()

    # ------------------------------------------------------------------
    def _new_demo(self):
        self.demo = Game("Easy", seed=random.randint(0, 10 ** 6))
        self.demo.player.x = self.demo.player.y = -50     # hide the player off-map
        self.demo_city = self.render_city(self.demo)

    def new_game(self):
        self.game = Game(DIFF_NAMES[self.diff_index])
        self.city = self.render_city(self.game)
        self.paused = False
        self.scene = "play"
        self.shake = self.red_flash = 0.0

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

    def handle_events(self):
        self.place_pressed = False
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
                if key in (pygame.K_UP, pygame.K_w):
                    self.diff_index = (self.diff_index - 1) % len(DIFF_NAMES)
                    self.sounds.play("click")
                elif key in (pygame.K_DOWN, pygame.K_s):
                    self.diff_index = (self.diff_index + 1) % len(DIFF_NAMES)
                    self.sounds.play("click")
                elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    self.diff_index = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2}[key]
                    self.new_game()
                elif key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.new_game()
                elif key == pygame.K_ESCAPE:
                    return False

            elif self.scene == "play":
                if key in (pygame.K_p, pygame.K_ESCAPE):
                    self.paused = not self.paused
                elif key == pygame.K_F1 or key == pygame.K_TAB:
                    self.debug = not self.debug
                elif key in (pygame.K_SPACE, pygame.K_e) and not self.paused:
                    self.place_pressed = True
                elif self.paused and key == pygame.K_m:
                    self.scene = "menu"
                elif self.paused and key == pygame.K_q:
                    return False

            elif self.scene == "end":
                if key in (pygame.K_r, pygame.K_RETURN):
                    self.new_game()
                elif key == pygame.K_m:
                    self.scene = "menu"
                elif key == pygame.K_ESCAPE:
                    return False
        return True

    def click(self, pos):
        """Handle a mouse click on a button. Returns False to quit."""
        for rect, action in self.buttons:
            if not rect.collidepoint(pos):
                continue
            self.sounds.play("click")
            if isinstance(action, tuple):
                self.diff_index = action[1]
                self.new_game()
            elif action == "resume":
                self.paused = False
            elif action in ("menu", "again"):
                self.paused = False
                if action == "menu":
                    self.scene = "menu"
                else:
                    self.new_game()
            elif action == "quit":
                return False
            break
        return True

    def update(self, dt):
        self.shake = max(0.0, self.shake - dt)
        self.red_flash = max(0.0, self.red_flash - dt * 1.5)

        if self.scene == "menu":
            self.demo.update(dt)
            if self.demo.state != "playing":
                self._new_demo()
            return
        if self.scene != "play" or self.paused:
            return

        keys = pygame.key.get_pressed()
        mx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        my = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        run = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        self.game.update(dt, move=(mx, my), run=bool(run), place=self.place_pressed)

        for ev in self.game.pop_events():
            self.sounds.play(ev)
            if ev == "bite":
                self.shake = 0.35
                self.red_flash = 0.8
        if self.game.state != "playing":
            self.scene = "end"

    # ------------------------------------------------------------------
    #  Drawing: static city
    # ------------------------------------------------------------------
    def render_city(self, game):
        """Pre-draw streets and buildings once (they never change)."""
        surf = pygame.Surface((GRID_W * TILE, GRID_H * TILE))
        rnd = random.Random(1234)
        m = game.map
        for y in range(m.h):
            for x in range(m.w):
                r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if m.tiles[y][x] == BUILDING:
                    roof = ROOFS[(x // 3 + y // 2 * 2) % len(ROOFS)]
                    surf.fill(roof, r)
                    pygame.draw.rect(surf, tuple(max(0, c - 18) for c in roof), r, 1)
                    for wy in range(2):
                        for wx in range(3):
                            colour = WINDOW_ON if rnd.random() < 0.18 else WINDOW_OFF
                            surf.fill(colour, (r.x + 5 + wx * 9, r.y + 7 + wy * 12, 5, 6))
                else:
                    surf.fill(ASPHALT if (x + y) % 2 else ASPHALT_2, r)
                    # lane markings on long straight streets
                    if m.tile(x - 1, y) != BUILDING and m.tile(x + 1, y) != BUILDING and \
                            m.tile(x, y - 1) == BUILDING and m.tile(x, y + 1) == BUILDING:
                        surf.fill(LANE, (r.x + 8, r.centery - 1, 16, 2))
                    if m.tile(x, y - 1) != BUILDING and m.tile(x, y + 1) != BUILDING and \
                            m.tile(x - 1, y) == BUILDING and m.tile(x + 1, y) == BUILDING:
                        surf.fill(LANE, (r.centerx - 1, r.y + 8, 2, 16))
                    # building shadows
                    if m.tile(x, y - 1) == BUILDING:
                        surf.fill((30, 31, 37), (r.x, r.y, TILE, 5))
                    if m.tile(x - 1, y) == BUILDING:
                        surf.fill((34, 35, 41), (r.x, r.y, 4, TILE))

        # Helipad
        xs = [t[0] for t in m.helipad]
        ys = [t[1] for t in m.helipad]
        pad = pygame.Rect(min(xs) * TILE, min(ys) * TILE, 2 * TILE, 2 * TILE)
        pygame.draw.circle(surf, (70, 70, 80), pad.center, TILE - 2)
        pygame.draw.circle(surf, YELLOW, pad.center, TILE - 2, 3)
        h = self.font_big.render("H", True, YELLOW)
        surf.blit(h, h.get_rect(center=pad.center))
        return surf

    # ------------------------------------------------------------------
    #  Drawing: dynamic world
    # ------------------------------------------------------------------
    def draw_world(self, game, city, use_fog=True, debug=False, offset=(0, 0)):
        ox, oy = offset
        world = pygame.Surface((GRID_W * TILE, GRID_H * TILE))
        world.blit(city, (0, 0))
        m = game.map
        t = self.anim_t

        def px(x, y):
            return int(x * TILE), int(y * TILE)

        def shown(tile):
            return debug or not use_fog or tile in game.visible

        # Barricades
        for (bx, by), hp in m.barricade_hp.items():
            r = pygame.Rect(bx * TILE + 2, by * TILE + 4, TILE - 4, TILE - 8)
            pygame.draw.rect(world, BARRICADE_DARK, r, border_radius=3)
            for i in range(3):
                pygame.draw.rect(world, BARRICADE_COL, (r.x + 1, r.y + 2 + i * 8, r.w - 2, 5))
            pygame.draw.line(world, BARRICADE_DARK, r.topleft, r.bottomright, 3)
            if hp < BARRICADE_HP:
                pygame.draw.rect(world, RED, (r.x, r.y - 4, r.w, 3))
                pygame.draw.rect(world, GREEN, (r.x, r.y - 4, int(r.w * hp / BARRICADE_HP), 3))

        # Crates (only once explored)
        for c in game.crates:
            if use_fog and not debug and (c.x, c.y) not in game.explored:
                continue
            cx, cy = px(c.x + 0.5, c.y + 0.5)
            bob = int(math.sin(t * 3 + c.x) * 2)
            if c.kind == "radio":
                pygame.draw.rect(world, (40, 60, 90), (cx - 9, cy - 6 + bob, 18, 13), border_radius=3)
                pygame.draw.rect(world, (110, 170, 255), (cx - 9, cy - 6 + bob, 18, 13), 2, border_radius=3)
                pygame.draw.line(world, (200, 200, 220), (cx + 5, cy - 6 + bob), (cx + 8, cy - 14 + bob), 2)
                if int(t * 3) % 2:
                    pygame.draw.circle(world, (120, 255, 140), (cx + 8, cy - 14 + bob), 3)
            elif c.kind == "medkit":
                pygame.draw.rect(world, WHITE, (cx - 8, cy - 7 + bob, 16, 14), border_radius=3)
                world.fill(RED, (cx - 2, cy - 5 + bob, 4, 10))
                world.fill(RED, (cx - 5, cy - 2 + bob, 10, 4))
            else:
                pygame.draw.rect(world, BARRICADE_COL, (cx - 8, cy - 7 + bob, 16, 14))
                pygame.draw.rect(world, BARRICADE_DARK, (cx - 8, cy - 7 + bob, 16, 14), 2)
                pygame.draw.line(world, BARRICADE_DARK, (cx - 8, cy - 7 + bob), (cx + 8, cy + 7 + bob), 2)

        # Noise rings
        self.overlay.fill((0, 0, 0, 0))
        for n in game.noises:
            if n.kind == "groan" and not debug and (int(n.x), int(n.y)) not in game.visible:
                continue
            frac = n.age / 0.9
            radius = int(n.radius * TILE * math.sqrt(frac))
            alpha = int(160 * (1 - frac))
            colour = {"step": (200, 200, 255), "groan": (255, 80, 80), "heli": (255, 230, 120),
                      "crash": (255, 150, 60), "barricade": (255, 190, 120)}.get(n.kind, WHITE)
            if radius > 2:
                pygame.draw.circle(self.overlay, colour + (alpha,), px(n.x, n.y), radius, 2)
        world.blit(self.overlay, (0, 0))

        # Barricade placement preview
        p = game.player
        if game is self.game and game.state == "playing":
            (tx, ty), ok, _ = game.barricade_target()
            if m.in_bounds(tx, ty):
                pygame.draw.rect(world, GREEN if ok else (160, 60, 60),
                                 (tx * TILE + 1, ty * TILE + 1, TILE - 2, TILE - 2), 1)

        # Debug: zombie paths and sight ranges
        if debug:
            for z in game.zombies:
                col = STATE_COLOURS[z.state]
                if z.path:
                    pts = [px(z.x, z.y)] + [px(a + 0.5, b + 0.5) for a, b in z.path]
                    if len(pts) > 1:
                        pygame.draw.lines(world, col, False, pts, 2)
                    pygame.draw.circle(world, col, pts[-1], 4)
                pygame.draw.circle(world, col, px(z.x, z.y), int(game.diff["sight"] * TILE), 1)

        # Zombies
        for z in game.zombies:
            if not shown(z.tile):
                continue
            zx, zy = px(z.x, z.y)
            if z.attacking:
                zx += random.randint(-2, 2)
            sway = math.sin(t * 6 + z.wobble) * 2
            r = int(z.radius * TILE)
            pygame.draw.circle(world, (0, 0, 0), (zx + 2, zy + 3), r)           # shadow
            # arms reach towards the player when chasing
            if z.state == CHASE:
                ang = math.atan2(p.y - z.y, p.x - z.x)
            else:
                ang = z.wobble + t * 0.5
            for side in (-0.5, 0.5):
                ax = zx + math.cos(ang + side) * (r + 5 + sway)
                ay = zy + math.sin(ang + side) * (r + 5 + sway)
                pygame.draw.line(world, ZOMBIE_DARK, (zx, zy), (int(ax), int(ay)), 4)
            pygame.draw.circle(world, ZOMBIE_COL, (zx, zy), r)
            pygame.draw.circle(world, ZOMBIE_DARK, (zx, zy), r, 2)
            ex, ey = math.cos(ang) * 4, math.sin(ang) * 4
            pygame.draw.circle(world, (255, 40, 40), (int(zx + ex - ey * 0.6), int(zy + ey + ex * 0.6)), 2)
            pygame.draw.circle(world, (255, 40, 40), (int(zx + ex + ey * 0.6), int(zy + ey - ex * 0.6)), 2)
            # state icon
            if z.state == CHASE:
                s = self.font.render("!", True, RED)
                world.blit(s, s.get_rect(center=(zx, zy - r - 10)))
            elif z.state == INVESTIGATE:
                s = self.font.render("?", True, YELLOW)
                world.blit(s, s.get_rect(center=(zx, zy - r - 10)))
            if debug:
                s = self.font_small.render(z.state[0], True, STATE_COLOURS[z.state])
                world.blit(s, (zx + r, zy - r))

        # Player
        if game is self.game:
            ppx, ppy = px(p.x, p.y)
            r = int(p.radius * TILE)
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
            # boarding progress
            if game.heli_state == "landed" and game.board_progress > 0:
                w = 40
                pygame.draw.rect(world, (30, 30, 30), (ppx - w // 2, ppy - 26, w, 6))
                pygame.draw.rect(world, GREEN, (ppx - w // 2, ppy - 26, int(w * game.board_progress / BOARD_TIME), 6))

        # Fog of war
        if use_fog and not debug:
            self.fog.fill((0, 0, 0, 0))
            for y in range(m.h):
                for x in range(m.w):
                    if (x, y) in game.visible:
                        d = math.hypot(x + 0.5 - p.x, y + 0.5 - p.y) / VIEW_RADIUS
                        a = min(150, int(max(0.0, d - 0.55) / 0.45 * 120))
                    elif (x, y) in game.explored:
                        a = 150
                    else:
                        a = 236
                    if a:
                        self.fog.fill((4, 4, 12, a), (x * TILE, y * TILE, TILE, TILE))
            world.blit(self.fog, (0, 0))

            # Helipad beacon always visible through the fog
            xs = [tt[0] for tt in m.helipad]
            ys = [tt[1] for tt in m.helipad]
            bx, by = (min(xs) + 1) * TILE, (min(ys) + 1) * TILE
            pulse = (math.sin(t * 4) + 1) / 2
            if game.heli_state != "landed":
                pygame.draw.circle(world, (255, int(80 + 100 * pulse), 60), (bx, by), int(4 + 4 * pulse))

        # Helicopter (loud and bright, so drawn above the fog)
        self.draw_helicopter(world, game)

        # Danger border when something is chasing you
        if game is self.game and any(z.state == CHASE for z in game.zombies):
            a = int(60 + 60 * (math.sin(t * 8) + 1) / 2)
            self.overlay.fill((0, 0, 0, 0))
            pygame.draw.rect(self.overlay, (255, 0, 0, a), self.overlay.get_rect(), 8)
            world.blit(self.overlay, (0, 0))

        if self.red_flash > 0 and game is self.game:
            self.overlay.fill((200, 0, 0, int(110 * self.red_flash)))
            world.blit(self.overlay, (0, 0))

        self.screen.blit(world, (ox, HUD_H + oy))

    def draw_helicopter(self, surf, game):
        xs = [tt[0] for tt in game.map.helipad]
        ys = [tt[1] for tt in game.map.helipad]
        pad_x, pad_y = (min(xs) + 1) * TILE, (min(ys) + 1) * TILE
        if game.heli_state == "landed":
            cx, cy, height = pad_x, pad_y, 0
        elif game.heli_state == "incoming" and game.heli_time_left is not None and game.heli_time_left < 4:
            f = game.heli_time_left / 4          # 1 -> far away, 0 -> landed
            cx, cy, height = pad_x + f * 260, pad_y - f * 300, f * 40
        else:
            return
        cx, cy = int(cx), int(cy)
        # shadow on the ground
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

    def draw_icon(self, kind, cx, cy, extra=None):
        s = self.screen
        if kind == "stamina":                       # lightning bolt
            pts = [(cx + 3, cy - 14), (cx - 7, cy + 1), (cx, cy + 1), (cx - 4, cy + 14),
                   (cx + 8, cy - 3), (cx + 1, cy - 3)]
            pygame.draw.polygon(s, ui.GOLD, pts)
            pygame.draw.polygon(s, ui.WOOD_EDGE, pts, 2)
        elif kind == "noise":                       # ear with sound waves
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

    def draw_hud(self, game):
        scr = self.screen
        p = game.player
        ui.wood_panel(scr, (0, -12, SCREEN_W, HUD_H + 12), radius=14, nails=False)
        pygame.draw.rect(scr, ui.WOOD_EDGE, (0, HUD_H - 4, SCREEN_W, 4))

        cw, ch, cy = 84, 66, 8
        xs = [10 + i * (cw + 8) for i in range(5)]

        # Health card
        plate = ui.card(scr, (xs[0], cy, cw, ch))
        for i in range(PLAYER_MAX_HP):
            self.draw_heart(xs[0] + 18 + i * 24, cy + 24, i < p.hp)
        ui.text(scr, "HEALTH", 13, plate.center, ui.INK, None)

        # Stamina card
        plate = ui.card(scr, (xs[1], cy, cw, ch), active=not p.exhausted)
        self.draw_icon("stamina", xs[1] + 16, cy + 27)
        ui.bar(scr, (xs[1] + 30, cy + 21, cw - 38, 12), p.stamina / STAMINA_MAX,
               (230, 120, 60) if p.exhausted else (90, 200, 255))
        ui.text(scr, "TIRED!" if p.exhausted else "STAMINA", 13, plate.center,
                RED if p.exhausted else ui.INK, None)

        # Noise card
        if p.running:
            txt, col, n = "LOUD", RED, 3
        elif p.moving:
            txt, col, n = "QUIET", (200, 150, 0), 1
        else:
            txt, col, n = "SILENT", (40, 150, 60), 0
        plate = ui.card(scr, (xs[2], cy, cw, ch))
        self.draw_icon("noise", xs[2] + cw // 2, cy + 27, (n, col))
        ui.text(scr, txt, 13, plate.center, col, None)

        # Barricades card
        plate = ui.card(scr, (xs[3], cy, cw, ch), active=p.barricades > 0)
        self.draw_icon("barricade", xs[3] + cw // 2, cy + 27)
        ui.text(scr, f"x {p.barricades}", 15, plate.center, ui.INK, None)

        # Radio card + signal meter
        plate = ui.card(scr, (xs[4], cy, cw, ch))
        self.draw_icon("radio", xs[4] + 24, cy + 30)
        d = game.nearest_radio_distance
        strength = max(0, min(5, int(6 - d / 3.5))) if d is not None and game.heli_state == "waiting" else 0
        for i in range(5):
            h = 4 + i * 3
            c = (60, 130, 255) if i < strength else (170, 160, 130)
            pygame.draw.rect(scr, c, (xs[4] + 48 + i * 6, cy + 40 - h, 4, h))
        ui.text(scr, f"{game.parts_collected}/{RADIO_PARTS}", 15, plate.center, (40, 80, 180), None)

        # Objective sign on the right
        left = game.heli_time_left
        if game.heli_state == "waiting":
            txt, col = "Find the radio parts!", ui.CREAM
        elif game.heli_state == "incoming":
            txt, col = f"Helicopter in {int(left) + 1}s - go to the pad!", ui.GOLD
        else:
            flash = int(self.anim_t * 4) % 2
            txt, col = f"BOARD NOW!  {int(left) + 1}s left", RED if flash else ui.CREAM
        sx = xs[4] + cw + 16
        sign = pygame.Rect(sx, cy + 2, SCREEN_W - sx - 10, 40)
        pygame.draw.rect(scr, ui.WOOD_DARK, sign, border_radius=10)
        pygame.draw.rect(scr, ui.WOOD_EDGE, sign, 3, border_radius=10)
        ui.text(scr, txt, 22, sign.center, col, ui.WOOD_EDGE, 2)
        ui.text(scr, f"{game.difficulty}   |   F1: AI view   |   P: pause", 14,
                (sign.centerx, sign.bottom + 13), (255, 230, 170), ui.WOOD_EDGE, 1)

        # Level progress meter (bottom right)
        if game.heli_state == "waiting":
            frac, label = 0.6 * game.parts_collected / RADIO_PARTS, "RADIO PARTS"
        elif game.heli_state == "incoming":
            frac, label = 0.6 + 0.3 * (1 - (left or 0) / HELI_CALL_TIME), "HELICOPTER COMING"
        else:
            frac, label = 0.9 + 0.1 * game.board_progress / BOARD_TIME, "ESCAPE!"
        ui.progress_meter(scr, (SCREEN_W - 214, SCREEN_H - 44, 190, 14), max(0.0, min(1.0, frac)),
                          [0.2, 0.4, 0.6, 1.0], label, self.anim_t)

        # Messages as hanging wooden signs
        for i, (msg, _secs) in enumerate(game.messages):
            ui.banner(scr, msg, (SCREEN_W // 2, HUD_H + 34 + i * 50), 20)

        if self.debug:
            lines = ["AI DEBUG VIEW (F1)",
                     f"Zombies: {len(game.zombies)}   "
                     + "  ".join(f"{st}: {sum(z.state == st for z in game.zombies)}" for st in (WANDER, INVESTIGATE, CHASE)),
                     f"A* paths planned: {game.stats['paths_planned']}   nodes expanded: {game.stats['nodes_expanded']}",
                     "Lines = A* paths   circles = sight range   W/I/C = FSM state"]
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
        if self.scene == "play" and self.paused:
            self.draw_panel("PAUSED", ["Take a breather...", "The zombies will wait.  (P / Esc)"], ui.CREAM,
                            [("Resume", "resume", ui.LEAF), ("Menu", "menu", (210, 150, 50)),
                             ("Quit", "quit", (190, 60, 50))])
        elif self.scene == "end":
            g = self.game
            mins, secs = divmod(int(g.time), 60)
            stats = [g.reason,
                     f"Time: {mins}:{secs:02d}     Difficulty: {g.difficulty}",
                     f"Radio parts: {g.parts_collected}/{RADIO_PARTS}     Distance: {g.stats['distance']:.0f} tiles",
                     f"Spotted: {g.stats['times_spotted']}     Bites: {g.stats['bites']}",
                     f"Barricades placed: {g.stats['barricades_used']}     smashed: {g.stats['barricades_broken']}",
                     f"Zombie A* searches: {g.stats['paths_planned']}  ({g.stats['nodes_expanded']} nodes)"]
            btns = [("Play Again (R)", "again", ui.LEAF), ("Menu (M)", "menu", (210, 150, 50))]
            if g.state == "won":
                self.draw_panel("YOU ESCAPED!", stats, ui.LEAF_LIGHT, btns)
            else:
                self.draw_panel("THE ZOMBIES GOT YOU!", stats, RED, btns)

    def draw_panel(self, title, lines, colour, buttons=()):
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        w = 620
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
        mouse = pygame.mouse.get_pos()
        bw = 170
        total = len(buttons) * bw + (len(buttons) - 1) * 16
        for i, (label, action, col) in enumerate(buttons):
            r = pygame.Rect(board.centerx - total // 2 + i * (bw + 16), note.bottom + 18, bw, 50)
            ui.button(self.screen, r, label, r.collidepoint(mouse), col, 20)
            self.buttons.append((r, action))

    def draw_menu(self):
        # zombies shambling around a dark city in the background
        self.draw_world(self.demo, self.demo_city, use_fog=False, debug=False)
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        self.screen.blit(shade, (0, 0))

        # Title sign hanging from chains
        wobble = int(math.sin(self.anim_t * 1.5) * 3)
        sign = pygame.Rect(0, 0, 640, 124)
        sign.center = (SCREEN_W // 2, 92 + wobble)
        for cx in (sign.left + 60, sign.right - 60):
            pygame.draw.line(self.screen, (120, 120, 130), (cx, 0), (cx, sign.top + 8), 4)
        ui.wood_panel(self.screen, sign, radius=20)
        ui.text(self.screen, "ZOMBIE ESCAPE", 66, (sign.centerx, sign.centery - 12), ui.LEAF_LIGHT, ui.LEAF_DARK, 4)
        ui.text(self.screen, "Find 3 radio parts. Call the chopper. Get out alive!", 17,
                (sign.centerx, sign.bottom - 22), ui.CREAM, ui.WOOD_EDGE, 2)

        # Difficulty buttons
        mouse = pygame.mouse.get_pos()
        cols = [(110, 190, 60), (225, 160, 40), (205, 60, 50)]
        for i, name in enumerate(DIFF_NAMES):
            d = DIFFICULTY[name]
            r = pygame.Rect(0, 0, 300, 56)
            r.center = (SCREEN_W // 2, 222 + i * 76)
            hover = r.collidepoint(mouse)
            if hover:
                self.diff_index = i
            selected = i == self.diff_index
            ui.button(self.screen, r, name.upper(), selected, cols[i] if selected else (125, 112, 95), 30)
            ui.text(self.screen, f"{d['zombies']} zombies  -  {d['barricades']} barricades", 14,
                    (r.centerx, r.bottom + 12), ui.CREAM if selected else (190, 180, 160), ui.WOOD_EDGE, 1)
            self.buttons.append((r, ("start", i)))
            if selected:
                bob = int(math.sin(self.anim_t * 6) * 4)
                ui.text(self.screen, ">", 38, (r.left - 26 + bob, r.centery), ui.GOLD, ui.WOOD_EDGE, 2)

        if int(self.anim_t * 2) % 2:
            ui.text(self.screen, "Click a level or press ENTER", 18, (SCREEN_W // 2, 452), ui.GOLD, ui.WOOD_EDGE, 2)

        # Controls + tips on two pinned notes
        controls = ["WASD / Arrows - move", "Shift - run (fast but LOUD)",
                    "Space / E - place barricade", "F1 - AI debug view", "P - pause"]
        tips = ["Zombies hear noise and investigate (?)",
                "If one sees you it chases (!) and groans",
                "Barricades block - A* tries to go around",
                "Fog: you only see your line of sight"]
        for x, heading, lines in ((30, "HOW TO PLAY", controls), (SCREEN_W // 2 + 15, "SURVIVAL TIPS", tips)):
            board = pygame.Rect(x, 478, SCREEN_W // 2 - 45, 220)
            ui.wood_panel(self.screen, board, radius=14)
            note = pygame.Rect(board.x + 18, board.y + 44, board.w - 36, board.h - 62)
            ui.paper_panel(self.screen, note)
            ui.text(self.screen, heading, 20, (board.centerx, board.top + 24), ui.GOLD, ui.WOOD_EDGE, 2)
            for i, line in enumerate(lines):
                ui.text(self.screen, line, 15, (note.x + 14, note.y + 10 + i * 28), ui.INK, None,
                        anchor="topleft")


if __name__ == "__main__":
    App().run()
