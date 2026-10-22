"""Procedural background plates in a flat web-cartoon style.

Pastel fills with thin lines in a darker tint of each fill (never black, so
characters with black outlines pop), vertical wall gradients with ambient
occlusion at corners, light shafts from windows, perspective tile floors and
props for everyday (often Indian) settings. A plate is one PNG level wider
than the camera (24 x 13.5 in) so shots can pan and zoom; characters stand on
FLOOR_Y, interior walls meet the floor at HORIZON_IN.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

from . import palette as pal
from .vec import Canvas, Path as VPath

PLATE_W, PLATE_H = 24.0, 13.5   # inches
BG_DPI = 120
FLOOR_Y = -3.6
HORIZON_IN = -0.9
HORIZON_OUT = -0.4

INTERIORS = ['bedroom', 'living_room', 'kitchen', 'classroom', 'office', 'cafe',
             'shop', 'school_corridor', 'hospital']
EXTERIORS = ['street', 'park', 'school_gate', 'rooftop', 'beach', 'village',
             'city', 'forest']
ABSTRACT = ['speedlines', 'sparkle', 'gloom', 'plain', 'sunburst']
LOCATIONS = INTERIORS + EXTERIORS + ABSTRACT
TIMES = ['day', 'evening', 'night']

SKY = {
    'day': ('#8FCBF0', '#E2F3FC'),
    'evening': ('#F29A5E', '#FCDDAE'),
    'night': ('#141E40', '#34457C'),
}


@dataclass
class BackgroundDesign:
    name: str
    location: str = 'living_room'
    time_of_day: str = 'day'
    wall_color: str | None = None
    accent_color: str | None = None
    seed: int | None = None


class Plate:
    def __init__(self, dpi: int = BG_DPI, ss: int = 2) -> None:
        self.dpi = dpi
        self.W = int(PLATE_W * dpi)
        self.H = int(PLATE_H * dpi)
        self.cv = Canvas(self.W, self.H, ss=ss)
        self.lw = 0.022 * dpi

    def P(self, x: float, y: float) -> tuple[float, float]:
        return ((x + PLATE_W / 2) * self.dpi, (PLATE_H / 2 - y) * self.dpi)

    @staticmethod
    def ink(c: str) -> str:
        return pal.darken(pal.mix(c, '#5A4A6A', 0.25), 0.38)

    def _finish(self, path: VPath, fill, line, width):
        if fill is not None:
            self.cv.fill(path, fill)
        if line:
            self.cv.stroke(path, self.ink(fill) if line is True else line, self.lw * width)
        return path

    def poly(self, pts, fill, line=True, width=1.0, smooth=False):
        conv = [self.P(*q) for q in pts]
        path = VPath().smooth(conv, closed=True) if smooth else VPath().poly(conv)
        return self._finish(path, fill, line, width)

    def rect(self, x0, y0, x1, y1, fill, line=True, width=1.0, r=0.0):
        a, b = self.P(x0, y1), self.P(x1, y0)
        return self._finish(VPath().rect(a[0], a[1], b[0], b[1], r=r * self.dpi), fill, line, width)

    def grad_rect(self, x0, y0, x1, y1, top, bottom):
        a, b = self.P(x0, y1), self.P(x1, y0)
        self.cv.gradient(VPath().rect(a[0], a[1], b[0], b[1]), top, bottom)

    def ellipse(self, cx, cy, rx, ry, fill, line=True, width=1.0):
        x, y = self.P(cx, cy)
        return self._finish(VPath().ellipse(x, y, rx * self.dpi, ry * self.dpi), fill, line, width)

    def line(self, pts, color, width=1.0):
        self.cv.stroke(VPath().poly([self.P(*q) for q in pts], closed=False), color, self.lw * width)

    def shade_band(self, y0, y1, color='#3A2C4A', alpha_top=0, alpha_bottom=70):
        """Soft vertical darkening (ambient occlusion along corners/edges)."""
        top = pal.with_alpha(color, alpha_top)
        bottom = pal.with_alpha(color, alpha_bottom)
        self.grad_rect(-PLATE_W / 2, y0, PLATE_W / 2, y1, top, bottom)

    def light_shaft(self, x0, x1, y_top, y_bottom, slant, alpha=60):
        pts = [(x0, y_top), (x1, y_top), (x1 + slant, y_bottom), (x0 + slant, y_bottom)]
        self.poly(pts, pal.with_alpha('#FFFFFF', alpha), line=None)


# --------------------------------------------------------------------------
# props
# --------------------------------------------------------------------------


def sky(pl: Plate, tod: str, y0: float, rnd: random.Random) -> None:
    top, bottom = SKY[tod]
    pl.grad_rect(-PLATE_W / 2, y0, PLATE_W / 2, PLATE_H / 2, top, bottom)
    if tod == 'night':
        for _ in range(160):
            x = rnd.uniform(-PLATE_W / 2, PLATE_W / 2)
            y = rnd.uniform(y0 + 1, PLATE_H / 2)
            pl.ellipse(x, y, 0.025, 0.025, '#FFFFFF' if rnd.random() < 0.7 else '#FFE9A8', line=None)
        pl.ellipse(6.5, 4.6, 0.7, 0.7, '#FFF6D8', line=None)
        pl.ellipse(6.78, 4.78, 0.6, 0.6, SKY['night'][0], line=None)
    else:
        if tod == 'evening':
            pl.ellipse(-6.0, y0 + 1.6, 1.1, 1.1, '#FFD27A', line=None)
        for _ in range(5):
            cloud(pl, rnd.uniform(-11, 11), rnd.uniform(y0 + 2.5, 6.0), rnd.uniform(0.8, 1.6),
                  '#FFFFFF' if tod == 'day' else '#FFE1C2')


def cloud(pl: Plate, cx, cy, s, color) -> None:
    for dx, dy, r in ((-0.9, 0, 0.55), (-0.3, 0.3, 0.7), (0.4, 0.2, 0.6), (1.0, 0, 0.45), (0.0, -0.1, 0.6)):
        pl.ellipse(cx + dx * s, cy + dy * s, r * s * 1.2, r * s, color, line=None)


def window(pl: Plate, x0, y0, x1, y1, tod, frame='#F4F1EA', rnd=None, curtains=None, grill=False) -> None:
    pl.rect(x0 - 0.14, y0 - 0.14, x1 + 0.14, y1 + 0.14, frame)
    top, bottom = SKY[tod]
    pl.grad_rect(x0, y0, x1, y1, top, bottom)
    if rnd:
        if tod == 'night':
            for _ in range(12):
                pl.ellipse(rnd.uniform(x0, x1), rnd.uniform((y0 + y1) / 2, y1), 0.02, 0.02, '#FFFFFF', line=None)
        else:
            cloud(pl, rnd.uniform(x0 + 0.5, x1 - 0.5), rnd.uniform(y0 + 0.7, y1 - 0.4), 0.32,
                  '#FFFFFF' if tod == 'day' else '#FFE1C2')
        x = x0
        while x < x1:
            w = rnd.uniform(0.3, 0.7)
            h = rnd.uniform(0.3, 1.0)
            col = '#A9BFD3' if tod == 'day' else ('#C98A6B' if tod == 'evening' else '#1F2A4D')
            pl.rect(x, y0, min(x + w, x1), y0 + h, col, line=None)
            x += w
    if grill:
        for i in range(1, 6):
            xx = x0 + (x1 - x0) * i / 6
            pl.line([(xx, y0), (xx, y1)], '#6A6F7A', 1.1)
        for j in range(1, 4):
            yy = y0 + (y1 - y0) * j / 4
            pl.line([(x0, yy), (x1, yy)], '#6A6F7A', 0.9)
    else:
        pl.line([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)], frame, 2.4)
        pl.line([(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)], frame, 2.4)
    # glass glare
    pl.poly([(x0 + 0.2, y1 - 0.1), (x0 + 0.55, y1 - 0.1), (x0 + 0.05, y0 + 0.4), (x0 - 0.0, y0 + 0.75)],
            pal.with_alpha('#FFFFFF', 60), line=None)
    pl.rect(x0 - 0.22, y0 - 0.28, x1 + 0.22, y0 - 0.1, frame)
    if curtains:
        for sgn, xx in ((-1, x0), (1, x1)):
            pts = [(xx - sgn * 0.1, y1 + 0.3), (xx + sgn * 0.65, y1 + 0.3), (xx + sgn * 0.35, y0 + 0.5),
                   (xx + sgn * 0.55, y0 - 0.45), (xx - sgn * 0.18, y0 - 0.45)]
            pl.poly(pts, curtains, smooth=True)
            pl.line([(xx + sgn * 0.25, y1 + 0.2), (xx + sgn * 0.2, y0 - 0.3)], pal.cel_shadow(curtains), 1.2)
        pl.rect(x0 - 0.9, y1 + 0.28, x1 + 0.9, y1 + 0.4, '#8A6A4A')


def light_from_window(pl: Plate, x0, x1, y_top, tod, floor_y=HORIZON_IN) -> None:
    if tod == 'night':
        return
    alpha = 46 if tod == 'day' else 38
    pl.light_shaft(x0, x1, y_top, floor_y - 3.2, 2.4, alpha)


def ceiling_fan(pl: Plate, x, y) -> None:
    pl.rect(x - 0.04, y, x + 0.04, PLATE_H / 2, '#7A7A84')
    pl.ellipse(x, y, 0.32, 0.14, '#9A9AA6')
    for sgn in (-1, 1):
        pl.poly([(x + sgn * 0.25, y + 0.03), (x + sgn * 2.1, y + 0.10), (x + sgn * 2.1, y - 0.06),
                 (x + sgn * 0.25, y - 0.05)], '#B8B8C2')


def tube_light(pl: Plate, x, y, w=2.2) -> None:
    pl.rect(x - w / 2, y - 0.08, x + w / 2, y + 0.08, '#FFFFFF', r=0.06)
    pl.rect(x - w / 2 - 0.12, y - 0.04, x - w / 2, y + 0.04, '#C8C8D0')
    pl.rect(x + w / 2, y - 0.04, x + w / 2 + 0.12, y + 0.04, '#C8C8D0')


def bookshelf(pl: Plate, x, y, w, h, rnd, wood='#A8754E') -> None:
    pl.rect(x, y, x + w, y + h, wood)
    shelves = 4
    for i in range(shelves):
        sy = y + 0.12 + i * (h - 0.2) / shelves
        pl.rect(x + 0.1, sy, x + w - 0.1, sy + (h - 0.2) / shelves - 0.12, pal.darken(wood, 0.3), line=None)
        bx = x + 0.15
        while bx < x + w - 0.35:
            bw = rnd.uniform(0.1, 0.22)
            bh = rnd.uniform(0.6, 0.95) * ((h - 0.2) / shelves - 0.15)
            col = pal.mix(rnd.choice(list(pal.CLOTH.values())), '#FFFFFF', 0.15)
            pl.rect(bx, sy, bx + bw, sy + bh, col, width=0.5)
            bx += bw + 0.02


def plant(pl: Plate, x, y, s=1.0) -> None:
    pot = '#C9744A'
    for k in range(7):
        a = math.radians(-70 + k * 23)
        tip = (x + math.sin(a) * 1.1 * s, y + 0.7 * s + math.cos(a) * 1.3 * s)
        mid = (x + math.sin(a) * 0.5 * s + 0.15 * s, y + 0.9 * s + math.cos(a) * 0.6 * s)
        pl.poly([(x, y + 0.7 * s), mid, tip, (mid[0] - 0.3 * s, mid[1])], '#62A85C', smooth=True)
    pl.poly([(x - 0.35 * s, y + 0.75 * s), (x + 0.35 * s, y + 0.75 * s), (x + 0.25 * s, y), (x - 0.25 * s, y)], pot)


def poster(pl: Plate, x, y, w, h, rnd) -> None:
    col = rnd.choice(['#F2B8C6', '#B8D8F2', '#F7E1A0', '#C6E7C1', '#D9C6F2'])
    pl.rect(x, y, x + w, y + h, col)
    pl.ellipse(x + w / 2, y + h * 0.6, w * 0.25, w * 0.25, pal.darken(col, 0.18), line=None)
    pl.rect(x + w * 0.2, y + h * 0.12, x + w * 0.8, y + h * 0.24, pal.darken(col, 0.3), line=None)


def notice_board(pl: Plate, x, y, w, h, rnd) -> None:
    pl.rect(x, y, x + w, y + h, '#B88A5A')
    pl.rect(x + 0.12, y + 0.12, x + w - 0.12, y + h - 0.12, '#D9B88A', line=None)
    for _ in range(5):
        px, py = rnd.uniform(x + 0.2, x + w - 0.9), rnd.uniform(y + 0.2, y + h - 0.9)
        c = rnd.choice(['#FFFFFF', '#FFF4B0', '#CFE8FF', '#FFD6E0'])
        pl.rect(px, py, px + rnd.uniform(0.5, 0.8), py + rnd.uniform(0.5, 0.8), c, width=0.5)
        pl.ellipse(px + 0.25, py + 0.6, 0.04, 0.04, '#D04040', line=None)


def clock(pl: Plate, x, y, r=0.4) -> None:
    pl.ellipse(x, y, r, r, '#FFFFFF', line='#4A4458', width=1.4)
    pl.line([(x, y), (x, y + r * 0.7)], '#4A4458', 1.1)
    pl.line([(x, y), (x + r * 0.5, y)], '#4A4458', 1.1)


def door(pl: Plate, x, y, w=1.6, h=3.6, color='#B9875A') -> None:
    pl.rect(x - 0.12, y, x + w + 0.12, y + h + 0.12, '#F2EEE6')
    pl.rect(x, y, x + w, y + h, color)
    pl.rect(x + 0.2, y + h * 0.55, x + w - 0.2, y + h - 0.2, pal.darken(color, 0.08), width=0.6)
    pl.rect(x + 0.2, y + 0.2, x + w - 0.2, y + h * 0.45, pal.darken(color, 0.08), width=0.6)
    pl.ellipse(x + w - 0.25, y + h * 0.5, 0.08, 0.08, '#E8C25A')


def tree(pl: Plate, x, y, s=1.0, tod='day') -> None:
    trunk = '#8A5A3B'
    leaf = '#62AE5E' if tod == 'day' else ('#4E8F55' if tod == 'evening' else '#1F4A3A')
    pl.rect(x - 0.18 * s, y, x + 0.18 * s, y + 1.6 * s, trunk)
    for dx, dy, r in ((0, 2.3, 1.1), (-0.8, 1.8, 0.8), (0.8, 1.9, 0.85), (0, 1.6, 0.9)):
        pl.ellipse(x + dx * s, y + dy * s, r * s, r * s * 0.9, leaf)
    pl.ellipse(x - 0.3 * s, y + 2.6 * s, 0.4 * s, 0.25 * s, pal.lighten(leaf, 0.25), line=None)


def building(pl: Plate, x, y, w, h, color, tod, rnd) -> None:
    pl.rect(x, y, x + w, y + h, color)
    pl.rect(x - 0.08, y + h - 0.05, x + w + 0.08, y + h + 0.12, pal.darken(color, 0.12))
    lit = tod == 'night'
    rows = int(h / 0.8)
    cols = max(1, int(w / 0.7))
    for r in range(rows):
        for c in range(cols):
            wx = x + 0.2 + c * (w - 0.3) / cols
            wy = y + 0.5 + r * 0.8
            if wy + 0.45 > y + h - 0.1:
                continue
            on = lit and rnd.random() < 0.55
            col = '#FFE08A' if on else ('#C7DEF0' if tod == 'day' else ('#F2C2A0' if tod == 'evening' else '#2A3560'))
            pl.rect(wx, wy, wx + 0.38, wy + 0.45, col, width=0.5)


def streetlamp(pl: Plate, x, y, tod) -> None:
    pl.rect(x - 0.06, y, x + 0.06, y + 3.6, '#4A4A55')
    pl.rect(x - 0.3, y + 3.5, x + 0.3, y + 3.75, '#4A4A55')
    pl.ellipse(x, y + 3.45, 0.2, 0.12, '#FFE9A0' if tod != 'day' else '#F2F2F2')
    if tod == 'night':
        pl.poly([(x - 0.15, y + 3.4), (x + 0.15, y + 3.4), (x + 1.2, y), (x - 1.2, y)],
                pal.with_alpha('#FFE9A0', 40), line=None)


def desk(pl: Plate, x, y, w=1.6, h=1.3, wood='#C89A6A') -> None:
    pl.rect(x, y + h - 0.12, x + w, y + h, wood)
    pl.rect(x + 0.08, y, x + 0.2, y + h - 0.12, pal.darken(wood, 0.1), width=0.6)
    pl.rect(x + w - 0.2, y, x + w - 0.08, y + h - 0.12, pal.darken(wood, 0.1), width=0.6)


def bench(pl: Plate, x, y, w=2.6, wood='#B07A48') -> None:
    """Indian classroom desk-bench seen from the front."""
    pl.rect(x, y + 1.05, x + w, y + 1.25, wood)
    pl.rect(x + 0.05, y + 0.85, x + w - 0.05, y + 1.05, pal.darken(wood, 0.15), width=0.6)
    pl.rect(x, y + 0.45, x + w, y + 0.6, pal.darken(wood, 0.05))
    for lx in (x + 0.1, x + w - 0.22):
        pl.rect(lx, y, lx + 0.12, y + 1.05, '#5A5A66', width=0.5)


def locker_row(pl: Plate, x0, x1, y, h, color='#5AA37A') -> None:
    n = int((x1 - x0) / 0.9)
    w = (x1 - x0) / n
    for i in range(n):
        x = x0 + i * w
        pl.rect(x, y, x + w, y + h, color, width=0.8)
        for k in range(3):
            vy = y + h - 0.35 - k * 0.12
            pl.line([(x + 0.2, vy), (x + w - 0.2, vy)], pal.darken(color, 0.25), 0.8)
        pl.rect(x + w - 0.22, y + h * 0.45, x + w - 0.14, y + h * 0.6, '#D8D8E0', width=0.4)
    pl.rect(x0, y + h, x1, y + h + 0.12, pal.darken(color, 0.2))


def almirah(pl: Plate, x, y, w=2.0, h=4.2, color='#8FA3B8') -> None:
    """Steel cupboard common in Indian homes."""
    pl.rect(x, y, x + w, y + h, color, r=0.08)
    pl.line([(x + w / 2, y + 0.1), (x + w / 2, y + h - 0.1)], pal.darken(color, 0.3), 1.0)
    for sx in (x + w / 2 - 0.18, x + w / 2 + 0.1):
        pl.rect(sx, y + h * 0.5, sx + 0.08, y + h * 0.62, '#D8DCE2', width=0.4)
    pl.poly([(x + 0.15, y + h - 0.2), (x + 0.45, y + h - 0.2), (x + 0.15, y + h * 0.4)],
            pal.with_alpha('#FFFFFF', 50), line=None)


def auto_rickshaw(pl: Plate, x, y, s=1.0) -> None:
    yel, grn = '#F2C230', '#2F8A4A'
    pl.poly([(x - 1.4 * s, y + 0.35 * s), (x + 1.3 * s, y + 0.35 * s), (x + 1.45 * s, y + 1.2 * s),
             (x + 1.0 * s, y + 2.1 * s), (x - 1.3 * s, y + 2.1 * s), (x - 1.45 * s, y + 1.0 * s)], grn, smooth=False)
    pl.poly([(x - 1.35 * s, y + 2.05 * s), (x + 1.0 * s, y + 2.05 * s), (x + 0.95 * s, y + 2.45 * s),
             (x - 1.2 * s, y + 2.45 * s)], '#2A2A30')
    pl.rect(x - 1.42 * s, y + 0.35 * s, x + 1.42 * s, y + 0.95 * s, yel)
    pl.rect(x + 0.35 * s, y + 1.1 * s, x + 1.1 * s, y + 1.8 * s, '#BFE0F2', width=0.6)
    for wx in (x - 0.9 * s, x + 0.9 * s):
        pl.ellipse(wx, y + 0.32 * s, 0.32 * s, 0.32 * s, '#2A2A30')
        pl.ellipse(wx, y + 0.32 * s, 0.13 * s, 0.13 * s, '#9A9AA6', line=None)


def gas_stove(pl: Plate, x, y) -> None:
    pl.rect(x, y, x + 2.0, y + 0.35, '#3A3A44')
    for bx in (x + 0.5, x + 1.5):
        pl.ellipse(bx, y + 0.42, 0.28, 0.08, '#55555F')
    pl.rect(x + 1.15, y + 0.42, x + 1.85, y + 0.8, '#C9CCD4', r=0.06)
    pl.rect(x + 1.05, y + 0.8, x + 1.95, y + 0.86, '#B0B4BC')


def wires(pl: Plate, y, rnd) -> None:
    for k in range(3):
        pts = []
        y0 = y + k * 0.25
        for i in range(25):
            x = -PLATE_W / 2 + i * PLATE_W / 24
            sag = 0.35 * math.sin(math.pi * ((i % 6) / 6))
            pts.append((x, y0 - sag))
        pl.line(pts, '#3A3440', 0.8)


# --------------------------------------------------------------------------
# locations
# --------------------------------------------------------------------------


def _interior(pl: Plate, wall: str, floor_col: str, tiles: bool, rnd, dado: str | None = None) -> None:
    pl.grad_rect(-PLATE_W / 2, HORIZON_IN, PLATE_W / 2, PLATE_H / 2, pal.lighten(wall, 0.10), pal.darken(wall, 0.04))
    if dado:
        pl.rect(-PLATE_W / 2, HORIZON_IN, PLATE_W / 2, HORIZON_IN + 1.7, dado, line=None)
        pl.line([(-PLATE_W / 2, HORIZON_IN + 1.7), (PLATE_W / 2, HORIZON_IN + 1.7)], pal.darken(dado, 0.3), 1.2)
    pl.shade_band(PLATE_H / 2 - 1.2, PLATE_H / 2, alpha_top=55, alpha_bottom=0)
    pl.shade_band(HORIZON_IN, HORIZON_IN + 1.1, alpha_top=0, alpha_bottom=45)
    _floor(pl, floor_col, tiles, rnd)
    pl.rect(-PLATE_W / 2, HORIZON_IN, PLATE_W / 2, HORIZON_IN + 0.18, '#F2EEE6', width=0.6)


def _floor(pl: Plate, color: str, tiles: bool, rnd) -> None:
    y_top = HORIZON_IN
    pl.grad_rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, y_top, pal.darken(color, 0.06), pal.lighten(color, 0.06))
    ink = pal.with_alpha(pal.darken(color, 0.22), 160)
    if tiles:
        for i in range(-14, 15):
            pl.line([(i * 0.9, y_top), (i * 2.2, -PLATE_H / 2)], ink, 0.7)
        y, step = y_top, 0.32
        while y > -PLATE_H / 2:
            y -= step
            step *= 1.35
            pl.line([(-PLATE_W / 2, y), (PLATE_W / 2, y)], ink, 0.7)
    else:
        y, k = y_top, 0
        while y > -PLATE_H / 2:
            h = 0.35 + 0.09 * k
            y -= h
            pl.line([(-PLATE_W / 2, y), (PLATE_W / 2, y)], ink, 0.8)
            for _ in range(4):
                x = rnd.uniform(-PLATE_W / 2, PLATE_W / 2)
                pl.line([(x, y), (x, y + h)], ink, 0.6)
            k += 1
    # glossy sheen
    pl.poly([(-4.0, y_top), (2.0, y_top), (5.5, -PLATE_H / 2), (-1.5, -PLATE_H / 2)],
            pal.with_alpha('#FFFFFF', 22), line=None)


def draw_location(pl: Plate, d: BackgroundDesign, rnd: random.Random) -> None:
    loc, tod = d.location, d.time_of_day
    wall = d.wall_color and pal.resolve(d.wall_color, pal.CLOTH, '#EADFCF')
    accent = pal.resolve(d.accent_color, pal.CLOTH, '#E58F8F') if d.accent_color else None
    H = HORIZON_IN
    if loc == 'bedroom':
        _interior(pl, wall or '#E6D6EE', '#C9A07A', False, rnd)
        window(pl, -3.0, 0.6, 1.4, 3.8, tod, rnd=rnd, curtains=accent or '#F2A7B8')
        light_from_window(pl, -2.6, 1.0, 0.6, tod)
        bookshelf(pl, 5.0, H, 2.2, 4.0, rnd)
        desk(pl, 2.2, H - 0.2, 2.4, 1.6, '#C79A6B')
        pl.rect(3.1, H + 1.4, 3.9, H + 1.55, '#4A78C2', width=0.5)
        pl.rect(3.0, H + 1.55, 3.7, H + 1.7, '#E25C4E', width=0.5)
        bed = accent or '#8FB8E8'
        pl.rect(-10.4, H - 1.3, -4.4, H + 0.9, '#B07A55')
        pl.rect(-10.3, H - 0.4, -4.5, H + 0.5, bed)
        pl.poly([(-8.0, H + 0.5), (-4.5, H + 0.5), (-4.5, H - 0.4), (-7.2, H - 0.4)], pal.cel_shadow(bed), line=None)
        pl.rect(-10.0, H + 0.4, -8.4, H + 0.95, '#FFFFFF', width=0.6, r=0.18)
        poster(pl, -8.6, 1.6, 1.4, 1.9, rnd)
        plant(pl, 8.6, H - 0.4, 0.9)
        clock(pl, 3.0, 4.3)
    elif loc == 'living_room':
        _interior(pl, wall or '#F2DEC4', '#D9C7A6', True, rnd)
        window(pl, -2.2, 0.5, 2.2, 3.9, tod, rnd=rnd, curtains=accent or '#7FB6A8', grill=True)
        light_from_window(pl, -1.8, 1.8, 0.5, tod)
        ceiling_fan(pl, 0.0, 5.6)
        sofa = accent or '#C9605A'
        pl.rect(-10.2, H - 0.5, -4.2, H + 1.1, sofa, r=0.3)
        pl.rect(-9.9, H + 0.7, -4.5, H + 2.2, pal.darken(sofa, 0.08), r=0.35)
        for cx in (-9.0, -7.3, -5.6):
            pl.rect(cx - 0.6, H + 0.9, cx + 0.6, H + 1.9, pal.lighten(sofa, 0.2), r=0.25, width=0.6)
        almirah(pl, 7.4, H, 2.0, 4.4)
        pl.rect(3.5, H - 0.2, 6.6, H + 1.6, '#6B4C3B')
        pl.rect(3.8, H + 1.6, 6.3, H + 3.4, '#1F2330', r=0.08)
        pl.rect(4.0, H + 1.8, 6.1, H + 3.2, '#3D5A80' if tod != 'night' else '#6FA0D8', line=None)
        pl.ellipse(0.0, FLOOR_Y + 0.3, 4.5, 0.9, pal.with_alpha(accent or '#C9605A', 90), line=None)
        poster(pl, -7.6, 2.6, 1.8, 1.3, rnd)
        clock(pl, 3.6, 4.4)
    elif loc == 'kitchen':
        _interior(pl, wall or '#DCEDE4', '#E9E2D2', True, rnd)
        pl.rect(-PLATE_W / 2, H + 1.8, PLATE_W / 2, H + 3.4, '#F4F7FA', line=None)
        for i in range(-24, 25):
            pl.line([(i * 0.5, H + 1.8), (i * 0.5, H + 3.4)], '#D2DAE0', 0.6)
        pl.line([(-PLATE_W / 2, H + 2.6), (PLATE_W / 2, H + 2.6)], '#D2DAE0', 0.6)
        window(pl, -1.5, 1.6, 1.5, 3.9, tod, rnd=rnd, grill=True)
        light_from_window(pl, -1.2, 1.2, 1.6, tod)
        cab = accent or '#F4F1EA'
        pl.rect(-PLATE_W / 2, H - 0.5, PLATE_W / 2, H + 1.8, cab)
        pl.rect(-PLATE_W / 2, H + 1.8, PLATE_W / 2, H + 2.0, '#8C949A')
        for i in range(-11, 12, 2):
            pl.rect(i - 0.85, H - 0.35, i + 0.85, H + 1.6, pal.darken(cab, 0.04), width=0.6)
            pl.rect(i - 0.2, H + 1.3, i + 0.2, H + 1.38, '#7A7A80', line=None)
        for i in (-8.5, -6.5, 4.5, 6.5, 8.5):
            pl.rect(i - 0.9, 3.0, i + 0.9, 5.0, cab)
        gas_stove(pl, -5.0, H + 2.0)
        for k, x in enumerate((3.2, 3.8, 4.4)):
            pl.ellipse(x, H + 2.35, 0.22, 0.32, '#C9CCD4')
    elif loc == 'classroom':
        _interior(pl, wall or '#F3EBCF', '#C8A37A', False, rnd, dado='#8DBBD0')
        pl.rect(-5.6, 0.5, 5.6, 4.1, '#8A6A4A')
        pl.rect(-5.4, 0.7, 5.4, 3.9, '#3A6B4A', line=None)
        pl.shade_band(0.7, 3.9, '#1A2A1E', 30, 0)
        for k in range(3):
            pl.line([(-4.6, 3.3 - k * 0.6), (rnd.uniform(-1, 3), 3.3 - k * 0.6)], '#E8F0E8', 1.2)
        pl.rect(-5.2, 0.5, -3.4, 0.62, '#E8E8E8', line=None)
        window(pl, -11.6, 0.5, -7.6, 4.2, tod, rnd=rnd, grill=True)
        window(pl, 7.6, 0.5, 11.6, 4.2, tod, rnd=rnd, grill=True)
        light_from_window(pl, -11.2, -8.0, 0.5, tod)
        light_from_window(pl, 8.0, 11.2, 0.5, tod)
        ceiling_fan(pl, -3.0, 5.8)
        ceiling_fan(pl, 4.0, 5.8)
        tube_light(pl, 0.0, 4.9)
        clock(pl, 6.5, 4.4, 0.35)
        notice_board(pl, 6.0, 1.0, 1.4, 2.2, rnd)
        for row, (y, s) in enumerate(((H - 0.6, 1.0), (H - 2.4, 1.15))):
            for x in (-9.5, -5.5, 2.5, 6.5):
                bench(pl, x - 1.3 * s, y, 2.6 * s)
    elif loc == 'office':
        _interior(pl, wall or '#E3E7EC', '#9BA4AE', True, rnd)
        window(pl, -10.5, 0.2, -3.0, 4.6, tod, rnd=rnd)
        light_from_window(pl, -9.8, -3.6, 0.2, tod)
        tube_light(pl, 3.0, 5.2, 3.0)
        for x in (-1.0, 3.5):
            desk(pl, x, H - 0.4, 2.8, 1.5, '#D9D2C6')
            pl.rect(x + 0.9, H + 1.1, x + 2.0, H + 1.9, '#2A2E3A')
        bookshelf(pl, 7.5, H, 2.4, 3.8, rnd, wood='#8C8C96')
        plant(pl, -2.0, H - 0.4, 0.9)
        clock(pl, 6.0, 4.0)
    elif loc == 'cafe':
        _interior(pl, wall or '#E9D3B8', '#8E6448', False, rnd)
        window(pl, -10.5, 0.3, -2.5, 4.2, tod, rnd=rnd)
        light_from_window(pl, -9.8, -3.0, 0.3, tod)
        pl.rect(1.0, H - 0.4, 10.5, H + 1.6, '#7A4E35')
        pl.rect(1.0, H + 1.6, 10.5, H + 1.85, '#3A2A22')
        for i in range(5):
            pl.ellipse(2.0 + i * 1.8, 3.6, 0.35, 0.22, '#F7D58A')
            pl.line([(2.0 + i * 1.8, 3.8), (2.0 + i * 1.8, PLATE_H / 2)], '#3A3040', 0.6)
        pl.rect(3.5, 2.0, 8.5, 3.0, '#2A2A30')
        plant(pl, -1.5, H - 0.4, 0.8)
    elif loc == 'shop':
        _interior(pl, wall or '#F3EBDD', '#D9CFC0', True, rnd)
        for x in (-10.5, -6.0, 5.0, 9.5):
            bookshelf(pl, x - 2.0, H, 3.6, 4.6, rnd, wood='#D8D8DE')
        pl.rect(-2.5, H - 0.6, 2.5, H + 1.4, accent or '#E25C4E')
        pl.rect(-2.0, 3.0, 2.0, 4.2, '#FFFFFF')
        tube_light(pl, 0.0, 5.3, 3.0)
    elif loc == 'school_corridor':
        _interior(pl, wall or '#C9B4D6', '#D9CDB8', True, rnd)
        for x in (-11.0, -4.6, 1.8, 8.2):
            window(pl, x, 1.4, x + 2.8, 4.4, tod, rnd=rnd, frame='#F6F2FA')
            light_from_window(pl, x + 0.3, x + 2.5, 1.4, tod)
        locker_row(pl, -11.6, -5.0, H, 3.2, accent or '#5AA37A')
        locker_row(pl, 4.2, 11.6, H, 3.2, accent or '#5AA37A')
        for x in (-3.4, 2.9):
            pl.rect(x - 0.35, H, x + 0.35, PLATE_H / 2, '#E8A0C0')
            pl.rect(x - 0.45, H, x + 0.45, H + 0.3, pal.darken('#E8A0C0', 0.15))
        notice_board(pl, -2.4, 1.4, 1.9, 2.2, rnd)
        clock(pl, 0.0, 5.0, 0.32)
    elif loc == 'hospital':
        _interior(pl, wall or '#E6F2F0', '#D7E0E2', True, rnd)
        window(pl, -2.0, 0.8, 2.4, 4.0, tod, rnd=rnd, curtains='#BFE3DA')
        light_from_window(pl, -1.6, 2.0, 0.8, tod)
        pl.rect(-9.5, H - 0.6, -4.0, H + 0.6, '#C8D3D8')
        pl.rect(-9.4, H + 0.6, -4.1, H + 1.0, '#FFFFFF')
        pl.rect(5.0, H - 0.6, 5.2, H + 3.2, '#9AA3A8')
        pl.rect(4.6, H + 3.0, 5.6, H + 3.6, '#BFE3F5')
        tube_light(pl, 0.0, 5.3, 3.0)
    elif loc in ('street', 'city', 'school_gate', 'village'):
        sky(pl, tod, HORIZON_OUT, rnd)
        cols = ['#E8BD93', '#C9D9E6', '#E6CADC', '#D6E6C3', '#F2D9A8', '#C3CBD9', '#E0C2A8']
        x = -PLATE_W / 2
        if loc == 'village':
            pl.poly([(-PLATE_W / 2, HORIZON_OUT), (-6, 2.4), (2, HORIZON_OUT + 0.5), (8, 2.0),
                     (PLATE_W / 2, HORIZON_OUT)], '#8CB57F', smooth=True, line=None)
            for xx in (-9, -3.5, 4.0, 9.0):
                hut = rnd.choice(['#D9A066', '#E3C08A', '#C98B5A'])
                pl.rect(xx - 1.2, HORIZON_OUT, xx + 1.2, HORIZON_OUT + 1.6, hut)
                pl.poly([(xx - 1.5, HORIZON_OUT + 1.6), (xx, HORIZON_OUT + 2.6), (xx + 1.5, HORIZON_OUT + 1.6)],
                        '#9C5A3C')
                pl.rect(xx - 0.3, HORIZON_OUT, xx + 0.3, HORIZON_OUT + 1.0, '#6B4A33')
            for xx in (-11, -6.5, 1.0, 6.5, 11):
                tree(pl, xx, HORIZON_OUT - 0.3, 1.0, tod)
        else:
            while x < PLATE_W / 2:
                w = rnd.uniform(2.0, 3.6)
                h = rnd.uniform(3.0, 6.5) if loc == 'city' else rnd.uniform(2.5, 4.5)
                c = rnd.choice(cols)
                if tod == 'night':
                    c = pal.mix(c, '#20284A', 0.65)
                elif tod == 'evening':
                    c = pal.mix(c, '#E59A6A', 0.25)
                building(pl, x, HORIZON_OUT, w, h, c, tod, rnd)
                if loc == 'street' and rnd.random() < 0.6:
                    sign = rnd.choice(['#E25C4E', '#4A78C2', '#F2C230', '#2F9A55'])
                    pl.rect(x + 0.2, HORIZON_OUT + 1.2, x + w - 0.2, HORIZON_OUT + 1.75, sign)
                    pl.rect(x + 0.2, HORIZON_OUT, x + w - 0.2, HORIZON_OUT + 1.15, '#5A4A44', width=0.6)
                x += w + rnd.uniform(0.05, 0.3)
            if loc == 'street':
                wires(pl, HORIZON_OUT + 4.6, rnd)
        if loc == 'school_gate':
            pl.rect(-6, HORIZON_OUT, 6, HORIZON_OUT + 4.6, '#F0E2C8')
            pl.rect(-6.4, HORIZON_OUT + 4.4, 6.4, HORIZON_OUT + 5.0, '#B5523F')
            for i in range(9):
                pl.rect(-5.2 + i * 1.25, HORIZON_OUT + 1.6, -4.6 + i * 1.25, HORIZON_OUT + 3.2, '#BFD9EE', width=0.6)
            pl.rect(-1.2, HORIZON_OUT + 5.0, 1.2, HORIZON_OUT + 5.6, '#FFFFFF')
        road = '#8A8F99' if tod != 'night' else '#3A3F55'
        pl.rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, HORIZON_OUT, '#CFC6B4' if tod != 'night' else '#55576A',
                line=None)
        pl.rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, FLOOR_Y - 0.5, road, line=None)
        for i in range(-6, 7):
            pl.rect(i * 2.0 - 0.5, FLOOR_Y - 1.6, i * 2.0 + 0.5, FLOOR_Y - 1.45, '#F2F2F2', line=None)
        pl.line([(-PLATE_W / 2, FLOOR_Y - 0.5), (PLATE_W / 2, FLOOR_Y - 0.5)], '#6A6A70', 1.0)
        for xx in (-9, -1, 7):
            streetlamp(pl, xx, HORIZON_OUT - 0.2, tod)
        if loc in ('street', 'city'):
            auto_rickshaw(pl, 8.5, FLOOR_Y - 1.2, 0.9)
        if loc != 'village':
            for xx in (-5, 3, 10.5):
                tree(pl, xx, HORIZON_OUT - 0.4, 0.8, tod)
    elif loc in ('park', 'forest'):
        sky(pl, tod, HORIZON_OUT, rnd)
        grass = '#93CC76' if tod == 'day' else ('#7FAE62' if tod == 'evening' else '#2C4A3A')
        pl.poly([(-PLATE_W / 2, HORIZON_OUT + 0.4), (-5, HORIZON_OUT + 1.2), (3, HORIZON_OUT + 0.6),
                 (PLATE_W / 2, HORIZON_OUT + 1.0), (PLATE_W / 2, -PLATE_H / 2), (-PLATE_W / 2, -PLATE_H / 2)],
                pal.darken(grass, 0.08), line=None)
        pl.grad_rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, HORIZON_OUT, pal.darken(grass, 0.05), pal.lighten(grass, 0.08))
        n = 14 if loc == 'forest' else 6
        for i in range(n):
            tree(pl, -11 + i * (22 / max(1, n - 1)) + rnd.uniform(-0.4, 0.4), HORIZON_OUT - 0.2,
                 rnd.uniform(0.9, 1.4) if loc == 'forest' else 1.0, tod)
        if loc == 'park':
            pl.poly([(-PLATE_W / 2, FLOOR_Y - 0.6), (PLATE_W / 2, FLOOR_Y - 0.6), (PLATE_W / 2, FLOOR_Y + 0.6),
                     (-PLATE_W / 2, FLOOR_Y + 0.6)], '#E6D6B2', line=None)
            wood = '#A8754E'
            pl.rect(4.0, FLOOR_Y + 1.6, 8.0, FLOOR_Y + 1.85, wood)
            pl.rect(4.0, FLOOR_Y + 2.1, 8.0, FLOOR_Y + 2.6, wood)
            streetlamp(pl, -7, FLOOR_Y + 0.6, tod)
    elif loc == 'rooftop':
        sky(pl, tod, HORIZON_OUT - 1.5, rnd)
        x = -PLATE_W / 2
        while x < PLATE_W / 2:
            w = rnd.uniform(1.2, 2.4)
            h = rnd.uniform(0.6, 2.4)
            c = '#B3C4D8' if tod == 'day' else ('#C98A6B' if tod == 'evening' else '#1F2A4D')
            building(pl, x, HORIZON_OUT - 1.5, w, h, c, tod, rnd)
            x += w + 0.1
        pl.rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, HORIZON_OUT - 1.5, '#BDB8AF', line=None)
        for i in range(-24, 25):
            pl.line([(i * 0.5, HORIZON_OUT - 1.5), (i * 0.5, HORIZON_OUT + 0.3)], '#5A6270', 0.8)
        pl.line([(-PLATE_W / 2, HORIZON_OUT + 0.3), (PLATE_W / 2, HORIZON_OUT + 0.3)], '#5A6270', 1.5)
        pl.line([(-PLATE_W / 2, HORIZON_OUT - 0.6), (PLATE_W / 2, HORIZON_OUT - 0.6)], '#5A6270', 1.0)
    elif loc == 'beach':
        sky(pl, tod, HORIZON_OUT + 0.6, rnd)
        sea = '#4FA6D9' if tod == 'day' else ('#D98A6B' if tod == 'evening' else '#1B2E5A')
        pl.grad_rect(-PLATE_W / 2, HORIZON_OUT - 1.0, PLATE_W / 2, HORIZON_OUT + 0.6, sea, pal.lighten(sea, 0.3))
        sand = '#F2DDA7' if tod != 'night' else '#8A8070'
        pl.poly([(-PLATE_W / 2, HORIZON_OUT - 0.9), (-3, HORIZON_OUT - 0.6), (4, HORIZON_OUT - 1.1),
                 (PLATE_W / 2, HORIZON_OUT - 0.8), (PLATE_W / 2, -PLATE_H / 2), (-PLATE_W / 2, -PLATE_H / 2)],
                sand, line=None)
        pl.line([(-PLATE_W / 2, HORIZON_OUT - 0.95), (PLATE_W / 2, HORIZON_OUT - 0.95)], '#FFFFFF', 1.6)
    elif loc in ABSTRACT:
        _abstract(pl, loc, d, rnd)
    else:
        raise ValueError('unknown location %r' % loc)


def _abstract(pl: Plate, loc: str, d: BackgroundDesign, rnd) -> None:
    base = pal.resolve(d.accent_color or d.wall_color, pal.CLOTH, {
        'speedlines': '#FFFFFF', 'sparkle': '#F8C8DC', 'gloom': '#3A2E5A',
        'plain': '#F2EEE6', 'sunburst': '#FFD66B'}[loc])
    pl.rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, PLATE_H / 2, base, line=None)
    if loc == 'speedlines':
        for _ in range(150):
            a = rnd.uniform(0, 2 * math.pi)
            r0 = rnd.uniform(3.0, 4.6)
            w = rnd.uniform(0.02, 0.09)
            p0 = (math.cos(a) * r0, math.sin(a) * r0 * 0.8)
            p1 = (math.cos(a - w) * 20, math.sin(a - w) * 16)
            p2 = (math.cos(a + w) * 20, math.sin(a + w) * 16)
            pl.poly([p0, p1, p2], '#2A2A33', line=None)
    elif loc == 'sunburst':
        for k in range(24):
            a0 = k * 2 * math.pi / 24
            if k % 2:
                pl.poly([(0, 0), (math.cos(a0) * 20, math.sin(a0) * 20),
                         (math.cos(a0 + math.pi / 24) * 20, math.sin(a0 + math.pi / 24) * 20)],
                        pal.lighten(base, 0.35), line=None)
    elif loc == 'sparkle':
        pl.grad_rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, PLATE_H / 2, pal.lighten(base, 0.4), base)
        for _ in range(60):
            x, y = rnd.uniform(-12, 12), rnd.uniform(-6.5, 6.5)
            r = rnd.uniform(0.1, 0.6)
            pl.ellipse(x, y, r, r, pal.with_alpha('#FFFFFF', rnd.randint(60, 160)), line=None)
    elif loc == 'gloom':
        pl.grad_rect(-PLATE_W / 2, -PLATE_H / 2, PLATE_W / 2, PLATE_H / 2, '#1E1830', base)
        for i in range(40):
            x = -12 + i * 0.6
            pl.line([(x, 6.7), (x, rnd.uniform(-2, 4))], '#6A5A9A80', 1.4)


def _apply_time(img: Image.Image, tod: str, outdoor: bool) -> Image.Image:
    if tod == 'day':
        return img
    tint = Image.new('RGBA', img.size, (255, 170, 110, 255) if tod == 'evening' else (60, 80, 150, 255))
    mult = ImageChops.multiply(img, tint)
    return Image.blend(img, mult, 0.30 if tod == 'evening' else (0.35 if outdoor else 0.45))


def build_background(design: BackgroundDesign, out_dir: Path, level: str) -> dict:
    if design.location not in LOCATIONS:
        raise ValueError('unknown location %r; choose from %s' % (design.location, LOCATIONS))
    if design.time_of_day not in TIMES:
        raise ValueError('time_of_day must be one of %s' % TIMES)
    seed = design.seed if design.seed is not None else sum(map(ord, design.name))
    rnd = random.Random(seed)
    pl = Plate()
    draw_location(pl, design, rnd)
    img = pl.cv.result().convert('RGBA')
    if design.location not in ABSTRACT:
        img = _apply_time(img, design.time_of_day, design.location in EXTERIORS)
        # backgrounds stay a little softer and less saturated than characters
        img = ImageEnhance.Color(img).enhance(0.88)
        img = img.filter(ImageFilter.GaussianBlur(0.5))
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(out_dir / ('%s.0001.png' % level), compress_level=4)
    return {'level': level, 'dpi': BG_DPI, 'size_in': [PLATE_W, PLATE_H],
            'floor_y': FLOOR_Y, 'location': design.location, 'time_of_day': design.time_of_day}
