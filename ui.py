"""
ui.py - cartoon "garden defence" style widgets for Zombie Escape.

Chunky outlined text, wooden plank panels, seed-packet style cards,
bevelled buttons and a flag progress meter. Pure drawing, no game logic.
"""

import math
import pygame

# ---------------- Palette ----------------
WOOD = (150, 96, 48)
WOOD_LIGHT = (196, 136, 74)
WOOD_DARK = (92, 55, 24)
WOOD_EDGE = (52, 30, 12)
PAPER = (246, 232, 190)
PAPER_DARK = (214, 190, 136)
CARD = (238, 226, 176)
CARD_EDGE = (120, 90, 40)
INK = (60, 36, 14)
LEAF = (98, 178, 52)
LEAF_LIGHT = (150, 220, 90)
LEAF_DARK = (44, 100, 24)
GOLD = (255, 214, 64)
CREAM = (255, 248, 220)
RED = (220, 50, 40)

_FONT_CACHE = {}


def font(size):
    """Rounded, chunky cartoon font (falls back if Cooper Black is missing)."""
    if size not in _FONT_CACHE:
        name = None
        for cand in ("cooperblack", "comicsansms", "arialblack", "segoeuiblack"):
            if pygame.font.match_font(cand):
                name = cand
                break
        f = pygame.font.SysFont(name, size) if name else pygame.font.Font(None, int(size * 1.3))
        _FONT_CACHE[size] = f
    return _FONT_CACHE[size]


def text(surf, msg, size, pos, colour=CREAM, outline=WOOD_EDGE, width=2,
         anchor="center", shadow=True):
    """Draw text with a thick outline and drop shadow. Returns its rect."""
    f = font(size)
    base = f.render(msg, True, colour)
    w, h = base.get_width() + width * 2, base.get_height() + width * 2
    out = pygame.Surface((w + 3, h + 3), pygame.SRCALPHA)
    if outline:
        edge = f.render(msg, True, outline)
        if shadow:
            out.blit(f.render(msg, True, (0, 0, 0)), (width + 3, width + 3))
        for dx in range(-width, width + 1):
            for dy in range(-width, width + 1):
                if dx * dx + dy * dy <= width * width + 1:
                    out.blit(edge, (width + dx, width + dy))
    out.blit(base, (width, width))
    r = out.get_rect(**{anchor: pos})
    surf.blit(out, r)
    return r


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def wood_panel(surf, rect, radius=12, nails=True, base=WOOD):
    """Plank board with dark rim, bevel and nails."""
    rect = pygame.Rect(rect)
    shadow = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 110), shadow.get_rect(), border_radius=radius)
    surf.blit(shadow, rect.move(4, 5))
    pygame.draw.rect(surf, WOOD_EDGE, rect, border_radius=radius)
    inner = rect.inflate(-6, -6)
    board = pygame.Surface(inner.size, pygame.SRCALPHA)
    pygame.draw.rect(board, base, board.get_rect(), border_radius=radius - 3)
    # planks + grain
    plank_h = 22
    for i, y in enumerate(range(0, inner.h, plank_h)):
        tint = _shade(base, 1.0 + (0.06 if i % 2 else -0.04))
        board.fill(tint, (0, y, inner.w, plank_h), special_flags=0)
        board.fill(_shade(base, 0.7), (0, y, inner.w, 2))
        for g in range(3):
            gx = (i * 53 + g * 97) % max(1, inner.w - 40)
            pygame.draw.line(board, _shade(base, 0.85), (gx, y + 7 + g * 4), (gx + 30, y + 7 + g * 4), 1)
    # clip planks to rounded shape
    mask = pygame.Surface(inner.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius - 3)
    board.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(board, inner)
    pygame.draw.rect(surf, _shade(base, 1.3), inner, 2, border_radius=radius - 3)
    if nails and rect.w > 60 and rect.h > 40:
        for nx, ny in ((inner.left + 9, inner.top + 9), (inner.right - 10, inner.top + 9),
                       (inner.left + 9, inner.bottom - 10), (inner.right - 10, inner.bottom - 10)):
            pygame.draw.circle(surf, (70, 70, 74), (nx, ny), 4)
            pygame.draw.circle(surf, (180, 180, 186), (nx - 1, ny - 1), 2)


def paper_panel(surf, rect, radius=10):
    """Parchment note pinned on the board."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, PAPER_DARK, rect.move(0, 3), border_radius=radius)
    pygame.draw.rect(surf, PAPER, rect, border_radius=radius)
    pygame.draw.rect(surf, CARD_EDGE, rect, 2, border_radius=radius)
    for y in range(rect.top + 34, rect.bottom - 10, 30):
        pygame.draw.line(surf, (226, 208, 160), (rect.left + 16, y), (rect.right - 16, y), 1)


def card(surf, rect, active=True):
    """Seed-packet style slot in the top bar."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, (0, 0, 0), rect.move(2, 3), border_radius=6)
    pygame.draw.rect(surf, CARD if active else (150, 140, 116), rect, border_radius=6)
    pygame.draw.rect(surf, LEAF if active else (110, 120, 96), (rect.x + 3, rect.y + 3, rect.w - 6, 6),
                     border_radius=3)
    pygame.draw.rect(surf, CARD_EDGE, rect, 2, border_radius=6)
    # value plate at the bottom
    plate = pygame.Rect(rect.x + 4, rect.bottom - 20, rect.w - 8, 16)
    pygame.draw.rect(surf, CREAM, plate, border_radius=4)
    pygame.draw.rect(surf, CARD_EDGE, plate, 1, border_radius=4)
    return plate


def button(surf, rect, label, hover=False, colour=LEAF, size=28):
    """Chunky bevelled button. Returns the rect for hit testing."""
    rect = pygame.Rect(rect)
    lift = 0 if not hover else -2
    r = rect.move(0, lift)
    pygame.draw.rect(surf, (0, 0, 0), rect.move(0, 5), border_radius=14)
    pygame.draw.rect(surf, _shade(colour, 0.55), r.move(0, 4), border_radius=14)
    body = _shade(colour, 1.12) if hover else colour
    pygame.draw.rect(surf, body, r, border_radius=14)
    pygame.draw.rect(surf, _shade(colour, 1.35), (r.x + 8, r.y + 4, r.w - 16, r.h // 3), border_radius=10)
    pygame.draw.rect(surf, _shade(colour, 0.4), r, 3, border_radius=14)
    text(surf, label, size, r.center, CREAM, _shade(colour, 0.3), 2)
    return rect


def bar(surf, rect, frac, colour, back=(70, 44, 20)):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, back, rect, border_radius=rect.h // 2)
    if frac > 0:
        fill = pygame.Rect(rect.x, rect.y, max(rect.h, int(rect.w * frac)), rect.h)
        pygame.draw.rect(surf, colour, fill, border_radius=rect.h // 2)
        pygame.draw.rect(surf, _shade(colour, 1.3), (fill.x + 3, fill.y + 2, fill.w - 6, max(2, rect.h // 3)),
                         border_radius=rect.h // 3)
    pygame.draw.rect(surf, WOOD_EDGE, rect, 2, border_radius=rect.h // 2)


def progress_meter(surf, rect, frac, flags, label, t=0.0):
    """Level progress bar with a zombie head creeping along and flags at milestones."""
    rect = pygame.Rect(rect)
    wood_panel(surf, rect.inflate(16, 14), radius=10, nails=False)
    bar(surf, rect, frac, LEAF)
    for f in flags:
        fx = rect.right - int(rect.w * (1 - f))
        reached = frac >= f - 1e-6
        pygame.draw.line(surf, WOOD_EDGE, (fx, rect.top - 12), (fx, rect.bottom), 2)
        pygame.draw.polygon(surf, RED if reached else (140, 120, 100),
                            [(fx, rect.top - 12), (fx + 11, rect.top - 8), (fx, rect.top - 4)])
    hx = rect.x + int(rect.w * frac)
    bob = int(math.sin(t * 4) * 1.5)
    pygame.draw.circle(surf, (120, 170, 80), (hx, rect.centery + bob), 9)
    pygame.draw.circle(surf, (50, 90, 30), (hx, rect.centery + bob), 9, 2)
    pygame.draw.circle(surf, (230, 40, 40), (hx - 3, rect.centery - 2 + bob), 2)
    pygame.draw.circle(surf, (230, 40, 40), (hx + 3, rect.centery - 2 + bob), 2)
    text(surf, label, 15, (rect.centerx, rect.bottom + 1), GOLD, WOOD_EDGE, 2, anchor="midtop")


def banner(surf, msg, center, size=22):
    """Hanging wooden sign used for toast messages."""
    f = font(size)
    w = f.size(msg)[0] + 44
    r = pygame.Rect(0, 0, w, size + 22)
    r.center = center
    for rx in (r.left + 18, r.right - 18):
        pygame.draw.line(surf, (60, 50, 40), (rx, r.top - 10), (rx, r.top + 4), 2)
    wood_panel(surf, r, radius=10, nails=False, base=WOOD_LIGHT)
    text(surf, msg, size, r.center, CREAM, WOOD_EDGE, 2)
