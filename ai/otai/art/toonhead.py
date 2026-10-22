"""Head drawings for the web-cartoon ("desi web cartoon") style.

Look: thick near-black outlines, big googly eyeballs almost touching with tiny
pupils, eyelids as shadow-skin caps (bored / angry / sad read from the lid
angle), chunky tapered brows, cloud-curl or swooping hair in two tones with
highlight strokes, big expressive mouths with teeth and tongue, hatched blush.

Coordinates are face units (x right, y down, face centre 0,0, width ~1).
"""

from __future__ import annotations

import math
import random

from PIL import ImageChops

from . import palette as pal
from .vec import Canvas, Path as VPath, bezier_points, taper_stroke

INK = '#1C1719'
MOUTH_IN, TONGUE, TEETH, TEETH_SH = '#7A2A2A', '#E07A8A', '#FFFFFF', '#DCDCE6'
LOOKS = {'c': (0.0, 0.0), 'l': (-0.075, 0.005), 'r': (0.075, 0.005), 'u': (0.0, -0.075), 'd': (0.0, 0.07)}


def _superellipse(cx, cy, rx, ry, n=2.6, steps=64):
    pts = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        c, s = math.cos(a), math.sin(a)
        x = rx * math.copysign(abs(c) ** (2 / n), c)
        y = ry * math.copysign(abs(s) ** (2 / n), s)
        pts.append((cx + x, cy + y))
    return pts


def _scallop(cx, cy, rx, ry, a0, a1, bumps, amp, steps=180, power=0.6):
    """Points along an elliptical arc from angle a0 to a1 (radians, y down)
    whose radius bulges outwards ``bumps`` times: a cloud-curl edge."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        a = a0 + (a1 - a0) * t
        bump = abs(math.sin(math.pi * bumps * t)) ** power
        k = 1 + amp * bump
        pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    return pts


class ToonHead:
    """Mirrors HeadPainter's interface (P, U, lw, warp, eye_geom, canvas...)."""

    def __init__(self, base) -> None:
        # ``base`` is a character.HeadPainter: reuse its canvas/coordinate setup
        self.b = base
        self.d, self.p, self.view, self.t = base.d, base.p, base.view, base.t
        self.U, self.W, self.Hpx = base.U, base.W, base.Hpx
        self.col = base.col
        self.male = base.male
        self.cartoon = True
        self.lw = base.lw
        self.skin = self.col['skin']
        self.skin_sh = pal.cel_shadow(self.skin, 'skin')
        self.lid = pal.mix(self.skin_sh, '#E79A9A', 0.25)
        self.hair = self.col['hair']
        self.hair_sh = pal.cel_shadow(self.hair, 'hair')
        self.hair_hi = pal.lighten(self.hair, 0.22)
        self.skin_line = INK
        self.hair_line = INK
        self.rnd = random.Random(sum(map(ord, self.d.name)) * 31 + (0 if self.view == 'front' else 1))

    # -- delegate geometry -------------------------------------------------
    def P(self, x, y):
        return self.b.P(x, y)

    def canvas(self, *a, **kw) -> Canvas:
        return self.b.canvas(*a, **kw)

    def blank(self):
        return self.b.blank()

    def warp(self, x: float, y: float = 0.0) -> float:
        t = self.t
        if t == 0:
            return x
        k = max(0.0, 1 - (x / 0.80) ** 2)
        return x * (1 - 0.10 * t) + t * 0.24 * k

    def W2(self, x, y):
        return self.P(self.warp(x), y)

    def path(self, pts, closed=True, smooth=True, warp=True, tension=0.5) -> VPath:
        conv = [(self.W2(x, y) if warp else self.P(x, y)) for x, y in pts]
        return VPath().smooth(conv, closed=closed, tension=tension) if smooth else VPath().poly(conv, closed=closed)

    def eye_geom(self, side: int):
        w, h = 0.35, 0.38
        if self.d.age == 'child':
            w, h = 0.37, 0.41
        cx = self.warp(side * 0.182)
        sc = 1.0
        if self.t:
            sc = 0.80 if side > 0 else 1.04
        return cx, 0.0, w * sc, h, sc

    def stroke(self, cv: Canvas, pts_px, w0, w1, wm, color=INK):
        cv.fill(taper_stroke(pts_px, w0, w1, wm), color)


# --------------------------------------------------------------------------
# Face
# --------------------------------------------------------------------------


def face_outline(th: ToonHead) -> list:
    t = th.t
    child = th.d.age == 'child'
    cheek = (0.56, 0.14) if not child else (0.58, 0.16)
    jaw = (0.44, 0.44) if th.male else (0.40, 0.45)
    chin = (0.0, 0.60) if not child else (0.0, 0.58)
    if t == 0:
        right = [(0.52, -0.40), (0.56, -0.12), cheek, jaw]
        pts = [(0.0, -0.70), (0.38, -0.62)] + right + [(0.20, 0.57), chin, (-0.20, 0.57)]
        pts += [(-x, y) for x, y in reversed(right)] + [(-0.38, -0.62)]
        return pts
    far = [(0.50, -0.40), (0.50, -0.10), (0.48, 0.08), (0.44, 0.30), (0.36, 0.47)]
    chin_pt = (0.16, 0.59)
    near = [(-0.56, -0.40), (-0.58, -0.10), (-cheek[0] - 0.03, cheek[1]), (-jaw[0] - 0.04, jaw[1]),
            (-0.18, 0.57)]
    return [(0.06, -0.70), (0.40, -0.62)] + far + [chin_pt] + list(reversed(near)) + [(-0.36, -0.63)]


def draw_face(th: ToonHead, cv: Canvas) -> None:
    U, lw = th.U, th.lw
    ears = [-1, 1] if th.t == 0 else [-1]
    for s in ears:
        ex = 0.56 * s if th.t == 0 else -0.59
        x, y = th.P(ex, 0.10)
        ear = VPath().smooth([(x, y - 0.15 * U), (x + s * 0.12 * U, y - 0.10 * U), (x + s * 0.13 * U, y + 0.06 * U),
                              (x + s * 0.02 * U, y + 0.14 * U), (x - s * 0.06 * U, y + 0.04 * U)], closed=True)
        cv.fill_stroke(ear, th.skin, INK, lw)
        inner = [(x + s * 0.02 * U, y - 0.07 * U), (x + s * 0.08 * U, y - 0.02 * U), (x + s * 0.03 * U, y + 0.06 * U)]
        th.stroke(cv, VPath().smooth(inner).subpaths[0], lw * 0.25, lw * 0.25, lw * 0.6)
    outline = face_outline(th)
    face = VPath().smooth([th.P(x, y) for x, y in outline], closed=True, tension=0.55)
    off = (-0.06 * U - 0.05 * U * th.t, -0.05 * U)
    cv.shaded(face, th.skin, th.skin_sh, off, INK, lw * 1.15)
    # nose: a small hook
    nx = th.warp(0.0) + 0.06 * th.t
    pts = [th.P(nx - 0.015, 0.16), th.P(nx + 0.035 + 0.03 * th.t, 0.23), th.P(nx - 0.02, 0.255)]
    th.stroke(cv, bezier_points(pts[0], pts[1], pts[1], pts[2], 10), lw * 0.3, lw * 0.3, lw * 0.75)


# --------------------------------------------------------------------------
# Eyes
# --------------------------------------------------------------------------

LID = {  # (inner, outer) lid-line height: -1 top of eyeball, +1 bottom
    'half': (-0.02, -0.06), 'angry': (0.12, -0.62), 'sad': (-0.62, 0.08),
    'sharp': (-0.32, -0.32), 'blink': (0.62, 0.58),
}
LOWER = {'sharp': (0.42, 0.42), 'sad': (0.70, 0.70)}


def draw_eye(th: ToonHead, cv: Canvas, side: int, expr: str, look: str = 'c') -> None:
    cx, cy, w, h, sc = th.eye_geom(side)
    U, lw = th.U, th.lw
    if expr in ('closed', 'happy', 'squeeze'):
        if expr == 'squeeze':
            a = th.P(cx - side * w * 0.42, cy - 0.30 * h)
            b = th.P(cx + side * w * 0.30, cy + 0.02 * h)
            c = th.P(cx - side * w * 0.42, cy + 0.32 * h)
            th.stroke(cv, [a, b], lw * 1.1, lw * 1.2, lw * 1.2)
            th.stroke(cv, [b, c], lw * 1.2, lw * 1.1, lw * 1.2)
            return
        dy = 0.18 if expr == 'closed' else -0.26
        p0 = th.P(cx - w * 0.46, cy + 0.06 * h)
        p1 = th.P(cx, cy + dy * h)
        p2 = th.P(cx + w * 0.46, cy + 0.06 * h)
        pts = bezier_points(p0, p1, p1, p2, 18)
        th.stroke(cv, pts, lw * 0.7, lw * 0.7, lw * 1.35)
        if expr == 'closed':  # lash tick at the outer corner
            o = pts[-1] if side > 0 else pts[0]
            th.stroke(cv, [o, (o[0] + side * 0.035 * U, o[1] - 0.02 * U)], lw * 0.9, lw * 0.2, lw * 0.9)
        return
    if expr == 'hypno':
        from .character import hypno_eye
        x, y = th.P(cx, cy)
        hypno_eye(cv, x, y, w / 2 * 1.06 * U, h / 2 * 1.06 * U, lw, INK)
        return
    scale = 1.12 if expr in ('wide', 'blank') else 1.0
    pts = _superellipse(cx, cy, w / 2 * scale, h / 2 * scale, n=2.4)
    eye = VPath().poly([th.P(x, y) for x, y in pts])
    cv.fill(eye, '#FFFFFF')
    # work on a canvas just around this eyeball (much cheaper than the full region)
    bx0, by0, bx1, by1 = eye.bbox()
    ox, oy = int(bx0) - 4, int(by0) - 4
    inner = Canvas(int(bx1 - bx0) + 9, int(by1 - by0) + 9, cv.ss, (ox, oy))
    mask = inner.mask(eye)
    # subtle shading on the eyeball under the lid
    inner.fill(VPath().poly([th.P(x, y) for x, y in _superellipse(cx, cy - 0.30 * h, w / 2, h * 0.24, 2.4)]),
               '#E4E2EE')
    # pupil
    if expr != 'blank':
        lx, ly = LOOKS.get(look, (0.0, 0.0))
        lx += 0.035 * th.t
        r = 0.043 if expr != 'wide' else 0.032
        px, py = th.P(cx + lx * sc, cy + ly + 0.01)
        if expr == 'heart':
            from .character import _heart_path
            inner.fill(_heart_path(px, py, 0.11 * U), '#F0457A')
            inner.fill(VPath().ellipse(px - 0.035 * U, py - 0.03 * U, 0.018 * U, 0.018 * U), '#FFFFFF')
        else:
            inner.fill(VPath().ellipse(px, py, r * U * sc, r * 1.12 * U), '#141014')
            inner.fill(VPath().ellipse(px + 0.014 * U, py - 0.018 * U, r * 0.33 * U, r * 0.33 * U), '#FFFFFF')
    else:
        px, py = th.P(cx, cy)
        inner.fill(VPath().ellipse(px, py, 0.014 * U, 0.014 * U), '#141014')
    lid_line = None
    if expr in LID:
        li, lo = LID[expr]
        x_in, x_out = cx - side * w * 0.62, cx + side * w * 0.62
        y_in, y_out = cy + li * h / 2, cy + lo * h / 2
        lid = [(x_in, cy - h), (x_out, cy - h), (x_out, y_out), (cx, (y_in + y_out) / 2 + 0.012), (x_in, y_in)]
        inner.fill(VPath().poly([th.P(x, y) for x, y in lid]), th.lid)
        lid_line = bezier_points(th.P(x_in, y_in), th.P(cx, (y_in + y_out) / 2 + 0.014),
                                 th.P(cx, (y_in + y_out) / 2 + 0.014), th.P(x_out, y_out), 14)
    low_line = None
    if expr in LOWER:
        bi, bo = LOWER[expr]
        x_in, x_out = cx - side * w * 0.62, cx + side * w * 0.62
        y_in, y_out = cy + bi * h / 2, cy + bo * h / 2
        low = [(x_in, y_in), (x_out, y_out), (x_out, cy + h), (x_in, cy + h)]
        inner.fill(VPath().poly([th.P(x, y) for x, y in low]), th.lid)
        low_line = [th.P(x_in, y_in), th.P(x_out, y_out)]
    inner.img.putalpha(ImageChops.multiply(inner.img.getchannel('A'), mask))
    cv.img.alpha_composite(inner.img, (int((ox - cv.ox) * cv.ss), int((oy - cv.oy) * cv.ss)))
    cv.stroke(eye, INK, lw * 0.85)
    if lid_line:
        # keep the lid line inside the eyeball, slightly heavier than the outline
        th.stroke(cv, lid_line, lw * 0.9, lw * 0.9, lw * 1.05)
    if low_line:
        th.stroke(cv, low_line, lw * 0.6, lw * 0.6, lw * 0.75)
    if expr == 'sad':
        x0, y0 = th.P(cx - w * 0.3, cy + 0.38 * h)
        cv.fill(VPath().ellipse(x0 + w * 0.3 * U, y0, w * 0.22 * U, 0.018 * U), '#BFE6FA')


# --------------------------------------------------------------------------
# Brows, mouth, blush
# --------------------------------------------------------------------------


def draw_brows(th: ToonHead, cv: Canvas, variant: str) -> None:
    color = pal.darken(th.hair, 0.35) if th.hair.upper() not in ('#2A2530', '#26262C') else '#1E1A1E'
    for side in (-1, 1):
        cx, cy, w, h, sc = th.eye_geom(side)
        by = cy - h / 2 - 0.085
        inner_dy, outer_dy, arch = {
            'neutral': (0.0, 0.0, 0.025), 'raised': (-0.075, -0.06, 0.04),
            'angry': (0.07, -0.05, -0.005), 'sad': (-0.07, 0.035, 0.015),
            'flat': (0.03, 0.03, 0.0),
        }.get(variant, (0.0, 0.0, 0.025))
        if variant == 'skeptic':
            inner_dy, outer_dy, arch = ((-0.09, -0.08, 0.05) if side > 0 else (0.03, 0.04, 0.0))
        inner = (cx - side * w * 0.42, by + inner_dy)
        outer = (cx + side * w * 0.55 * sc, by + outer_dy + 0.015)
        mid = ((inner[0] + outer[0]) / 2, min(inner[1], outer[1]) - arch)
        pts = bezier_points(th.P(*inner), th.P(*mid), th.P(*mid), th.P(*outer), 16)
        thick = 0.062 * th.U if th.male else 0.048 * th.U
        cv.fill(taper_stroke(pts, thick, thick * 0.35, thick * 0.95), color)


def draw_mouth(th: ToonHead, cv: Canvas, variant: str) -> None:
    U, lw = th.U, th.lw
    mx = th.warp(0.0) + 0.05 * th.t
    my = 0.38
    k = 1.0 - 0.12 * th.t

    def P(dx, dy):
        return th.P(mx + dx * k, my + dy)

    def line(a, c, b, wm=1.1):
        pts = bezier_points(P(*a), P(*c), P(*c), P(*b), 16)
        th.stroke(cv, pts, lw * 0.5, lw * 0.5, lw * wm)

    def opened(pts, teeth_top=0.0, teeth_bot=0.0, tongue=True):
        shape = VPath().smooth([P(*q) for q in pts], closed=True, tension=0.55)
        m = cv.mask(shape)
        cv.fill(shape, MOUTH_IN)
        x0, y0, x1, y1 = shape.bbox()
        sub = Canvas(cv.w, cv.h, cv.ss, (cv.ox, cv.oy))
        if tongue:
            sub.fill(VPath().ellipse((x0 + x1) / 2 + (x1 - x0) * 0.1, y1, (x1 - x0) * 0.36, (y1 - y0) * 0.42), TONGUE)
        if teeth_top:
            sub.fill(VPath().rect(x0, y0 - 2, x1, y0 + (y1 - y0) * teeth_top), TEETH)
            sub.fill(VPath().rect(x0, y0 + (y1 - y0) * teeth_top * 0.7, x1, y0 + (y1 - y0) * teeth_top), TEETH_SH)
        if teeth_bot:
            sub.fill(VPath().rect(x0, y1 - (y1 - y0) * teeth_bot, x1, y1 + 2), TEETH)
        sub.img.putalpha(ImageChops.multiply(sub.img.getchannel('A'), m))
        cv.img.alpha_composite(sub.img)
        cv.stroke(shape, INK, lw * 1.0)
        return x0, y0, x1, y1

    v = variant
    if v == 'rest':
        line((-0.08, 0.0), (0.0, 0.03), (0.09, -0.01))
    elif v == 'M':
        line((-0.07, 0.01), (0.0, 0.0), (0.07, 0.01), 1.3)
    elif v == 'smile':
        line((-0.14, -0.03), (0.0, 0.10), (0.14, -0.03), 1.2)
        for s in (-1, 1):
            th.stroke(cv, [P(s * 0.14, -0.03), P(s * 0.165, -0.055)], lw * 0.8, lw * 0.3, lw * 0.8)
    elif v == 'frown':
        line((-0.11, 0.05), (0.0, -0.05), (0.11, 0.05))
    elif v == 'flat':
        line((-0.10, 0.01), (0.0, 0.0), (0.10, -0.005))
    elif v == 'smirk':
        line((-0.09, 0.03), (0.02, 0.04), (0.12, -0.04))
    elif v == 'wavy':
        pts = [P(-0.13 + i * 0.0325, 0.01 + (0.022 if i % 2 else -0.022)) for i in range(9)]
        th.stroke(cv, VPath().smooth(pts).subpaths[0], lw * 0.7, lw * 0.7, lw * 0.95)
    elif v == 'cat':
        pts = [P(-0.13, -0.01), P(-0.065, 0.05), P(0.0, 0.0), P(0.065, 0.05), P(0.13, -0.01)]
        th.stroke(cv, VPath().smooth(pts).subpaths[0], lw * 0.8, lw * 0.8, lw * 1.0)
    elif v == 'grin':
        opened([(-0.19, -0.04), (0.0, -0.02), (0.19, -0.04), (0.13, 0.12), (0.0, 0.17), (-0.13, 0.12)],
               teeth_top=0.42, tongue=True)
    elif v == 'A':
        opened([(-0.10, -0.03), (0.0, -0.05), (0.10, -0.03), (0.09, 0.12), (0.0, 0.19), (-0.09, 0.12)], teeth_top=0.18)
    elif v == 'I':
        opened([(-0.14, -0.01), (0.0, -0.02), (0.14, -0.01), (0.09, 0.06), (0.0, 0.075), (-0.09, 0.06)],
               teeth_top=0.5, teeth_bot=0.3, tongue=False)
    elif v == 'E':
        opened([(-0.12, -0.02), (0.0, -0.035), (0.12, -0.02), (0.09, 0.08), (0.0, 0.11), (-0.09, 0.08)], teeth_top=0.3)
    elif v == 'O':
        opened([(-0.075, 0.0), (0.0, -0.06), (0.075, 0.0), (0.07, 0.10), (0.0, 0.14), (-0.07, 0.10)])
    elif v == 'U':
        opened([(-0.045, 0.01), (0.0, -0.03), (0.045, 0.01), (0.04, 0.06), (0.0, 0.08), (-0.04, 0.06)], tongue=False)
    elif v == 'shout':
        opened([(-0.21, -0.07), (0.0, -0.09), (0.21, -0.07), (0.16, 0.20), (0.0, 0.30), (-0.16, 0.20)],
               teeth_top=0.14)
    elif v == 'buck':
        x0, y0, x1, y1 = opened([(-0.09, -0.02), (0.0, -0.03), (0.09, -0.02), (0.07, 0.07), (0.0, 0.09),
                                 (-0.07, 0.07)], tongue=True)
        for s in (-1, 1):
            tooth = VPath().rect(*P(s * 0.005 if s > 0 else -0.045, -0.03), *P(0.045 if s > 0 else -0.005, 0.06),
                                 r=0.01 * U)
            cv.fill_stroke(tooth, TEETH, INK, lw * 0.6)
    elif v == 'clench':
        shape = VPath().rect(*P(-0.15, -0.035), *P(0.15, 0.075), r=0.03 * U)
        cv.fill(shape, TEETH)
        for i in range(1, 6):
            x = -0.15 + i * 0.05
            th.stroke(cv, [P(x, -0.035), P(x, 0.075)], lw * 0.35, lw * 0.35, lw * 0.4, '#9A9AA8')
        th.stroke(cv, [P(-0.15, 0.02), P(0.15, 0.02)], lw * 0.35, lw * 0.35, lw * 0.4, '#9A9AA8')
        cv.stroke(shape, INK, lw)


def draw_blush(th: ToonHead, cv: Canvas, variant: str) -> None:
    U, lw = th.U, th.lw
    for side in (-1, 1):
        cx, cy, w, h, sc = th.eye_geom(side)
        x, y = th.P(cx + side * 0.06, cy + h / 2 + 0.07)
        cv.fill(VPath().ellipse(x, y, 0.10 * U * sc, 0.045 * U), '#FF8A8A50' if variant == 'soft' else '#FF7A7A40')
        n = 3 if variant == 'lines' else 2
        for k in range(n):
            dx = (k - (n - 1) / 2) * 0.045 * U * sc
            th.stroke(cv, [(x + dx + 0.018 * U, y - 0.028 * U), (x + dx - 0.018 * U, y + 0.028 * U)],
                      lw * 0.55, lw * 0.25, lw * 0.6, '#E8705A')


# --------------------------------------------------------------------------
# Hair
# --------------------------------------------------------------------------


def _shade_hair(th: ToonHead, cv: Canvas, path: VPath, off=(-0.16, -0.10), clip=None) -> None:
    cv.shaded(path, th.hair, th.hair_sh, (off[0] * th.U, off[1] * th.U), INK, th.lw * 1.15, clip=clip)


def _highlights(th: ToonHead, cv: Canvas, strokes) -> None:
    for pts in strokes:
        conv = [th.W2(x, y) for x, y in pts]
        conv = VPath().smooth(conv).subpaths[0]
        cv.fill(taper_stroke(conv, th.lw * 0.15, th.lw * 0.15, th.lw * 0.75), '#FFFFFFD8')


def _curls(th: ToonHead, cv: Canvas, region, n=9) -> None:
    """Small C-shaped curl strokes inside curly hair for texture."""
    x0, y0, x1, y1 = region
    for i in range(n):
        x = x0 + (x1 - x0) * th.rnd.random()
        y = y0 + (y1 - y0) * th.rnd.random()
        r = 0.05 + 0.03 * th.rnd.random()
        a0 = th.rnd.uniform(0, math.pi)
        pts = [th.W2(x + math.cos(a0 + j * 0.45) * r, y + math.sin(a0 + j * 0.45) * r * 0.8) for j in range(6)]
        cv.fill(taper_stroke(pts, th.lw * 0.15, th.lw * 0.15, th.lw * 0.55), pal.with_alpha(th.hair_sh, 230))


def hair_front_shape(th: ToonHead) -> list | None:
    style = th.d.hair_style
    female = th.d.gender == 'female'
    if style == 'bald':
        return None
    if style == 'buzz':
        return _scallop(0, -0.30, 0.60, 0.42, math.pi * 1.05, math.pi * 1.95, 1, 0.0, 60) + \
            [(0.40, -0.40), (0.0, -0.46), (-0.40, -0.40)]
    if style in ('curly', 'undercut'):
        rx = 0.66 if style == 'curly' else 0.56
        top = _scallop(0, -0.36, rx, 0.56, math.pi * 1.02, math.pi * 1.98, 11, 0.10)
        fringe = []
        n = 5
        for i in range(n * 12 + 1):
            t = i / (n * 12)
            x = rx * 0.95 - t * rx * 1.9
            bump = abs(math.sin(math.pi * n * t)) ** 0.6
            fringe.append((x, -0.33 + 0.09 * bump + 0.03 * math.cos(t * 6)))
        return top + fringe
    if style == 'messy':
        top = _scallop(0, -0.34, 0.64, 0.58, math.pi * 1.0, math.pi * 1.96, 3, 0.06)
        locks = [(0.60, -0.32), (0.44, -0.31), (0.52, -0.21), (0.30, -0.30), (0.32, -0.21),
                 (0.10, -0.30), (0.06, -0.22), (-0.14, -0.30), (-0.20, -0.22), (-0.38, -0.31),
                 (-0.50, -0.23), (-0.62, -0.29)]
        return top + locks
    if style == 'spiky':
        pts = []
        for i in range(15):
            a = math.pi * (1.0 + i / 14)
            r = 0.78 if i % 2 else 0.60
            pts.append((math.cos(a) * r * 0.95, -0.34 + math.sin(a) * r))
        return pts + [(0.50, -0.30), (0.32, -0.21), (0.18, -0.31), (0.0, -0.21), (-0.18, -0.31),
                      (-0.34, -0.21), (-0.52, -0.30)]
    # neat cap with a chunky fringe (short) or side-swept bangs (long styles)
    top = _scallop(0, -0.34, 0.63, 0.58, math.pi * 1.0, math.pi * 2.0, 2, 0.04)
    if female and style != 'short':
        side_l = [(0.63, -0.30), (0.62, 0.20), (0.50, 0.42), (0.47, 0.05)]
        bangs = [(0.44, -0.26), (0.28, -0.21), (0.20, -0.30), (0.02, -0.22), (-0.10, -0.32),
                 (-0.30, -0.23), (-0.40, -0.32)]
        side_r = [(-0.47, 0.05), (-0.50, 0.42), (-0.62, 0.20), (-0.63, -0.30)]
        return top + side_l + bangs + side_r
    fringe = [(0.60, -0.28), (0.40, -0.22), (0.30, -0.33), (0.12, -0.22), (0.0, -0.33), (-0.16, -0.22),
              (-0.28, -0.33), (-0.44, -0.22), (-0.60, -0.28)]
    return top + fringe


def draw_hair_front(th: ToonHead, cv: Canvas) -> None:
    style = th.d.hair_style
    pts = hair_front_shape(th)
    acc = set(th.d.accessories)
    if style == 'undercut':
        # shaved sides: stubble-tinted skin on the temples
        for s in (-1, 1):
            if th.t and s > 0:
                continue
            patch = [(s * 0.52, -0.42), (s * 0.60, -0.32), (s * 0.58, -0.10), (s * 0.50, -0.16)]
            cv.fill(th.path(patch), pal.mix(th.skin, th.hair, 0.16))
    if pts:
        # forehead shadow cast by the fringe (only where it falls on skin)
        face_mask = cv.mask(VPath().smooth([th.P(x, y) for x, y in face_outline(th)], closed=True, tension=0.55))
        shadow = th.path([(x, y + 0.07) for x, y in pts], smooth=False)
        sm = ImageChops.multiply(cv.mask(shadow), face_mask)
        cv.paint(sm, th.skin_sh)
        path = th.path(pts, smooth=False)
        _shade_hair(th, cv, path)
        if style in ('curly', 'undercut'):
            _curls(th, cv, (-0.45, -0.75, 0.40, -0.40), 10)
            _highlights(th, cv, [[(-0.40, -0.62), (-0.30, -0.73), (-0.16, -0.78)],
                                 [(-0.48, -0.48), (-0.45, -0.56)]])
        elif style == 'messy':
            band = [(x, y) for x, y in _scallop(0, -0.34, 0.52, 0.46, math.pi * 1.15, math.pi * 1.6, 1, 0.0, 30)]
            band += [(x * 0.9, y + 0.10) for x, y in reversed(band)]
            cv.fill(th.path(band, smooth=True), pal.with_alpha(th.hair_hi, 200))
            _highlights(th, cv, [[(0.30, -0.80), (0.46, -0.72), (0.55, -0.60)],
                                 [(0.38, -0.84), (0.50, -0.78)]])
        else:
            _highlights(th, cv, [[(-0.42, -0.58), (-0.30, -0.72), (-0.12, -0.80)],
                                 [(0.20, -0.82), (0.32, -0.77)]])
    if 'headband' in acc:
        band = [(-0.64, -0.45), (0.0, -0.84), (0.64, -0.45), (0.66, -0.36), (0.0, -0.74), (-0.66, -0.36)]
        cv.fill_stroke(th.path(band, smooth=False), th.col['accent'], INK, th.lw * 0.8)
    if 'bow' in acc:
        bx, by = th.W2(0.44, -0.66)
        s = 0.17 * th.U
        for sg in (-1, 1):
            wing = VPath().poly([(bx, by), (bx + sg * s, by - s * 0.6), (bx + sg * s, by + s * 0.6)])
            cv.fill_stroke(wing, th.col['accent'], INK, th.lw * 0.8)
        cv.fill_stroke(VPath().ellipse(bx, by, s * 0.25, s * 0.25), pal.darken(th.col['accent'], 0.2), INK, th.lw * 0.6)
    if 'cap' in acc:
        cap = [(-0.66, -0.30), (-0.62, -0.72), (0.0, -0.98), (0.62, -0.72), (0.66, -0.30), (0.0, -0.38)]
        cv.shaded(th.path(cap), th.col['accent'], pal.cel_shadow(th.col['accent']), (-0.12 * th.U, -0.06 * th.U),
                  INK, th.lw)
        brim = [(-0.20 + 0.4 * th.t, -0.40), (0.86, -0.32), (0.80, -0.20), (-0.20 + 0.4 * th.t, -0.28)]
        cv.fill_stroke(th.path(brim, smooth=False), pal.cel_shadow(th.col['accent']), INK, th.lw)


def draw_hair_back(th: ToonHead, cv: Canvas) -> None:
    style = th.d.hair_style
    if style == 'bald':
        if th.d.age == 'elder':
            for s in (-1, 1):
                patch = [(s * 0.52, -0.30), (s * 0.64, -0.18), (s * 0.62, 0.06), (s * 0.52, 0.02)]
                cv.fill_stroke(th.path(patch), th.hair, INK, th.lw * 0.8)
        return
    shapes = []
    if style in ('curly', 'undercut'):
        rx = 0.74 if style == 'curly' else 0.62
        shapes.append(_scallop(0, -0.32, rx, 0.62, 0, 2 * math.pi, 16, 0.08))
    elif style == 'long':
        shapes.append([(-0.66, -0.40), (-0.46, -0.86), (0.0, -0.94), (0.46, -0.86), (0.66, -0.40), (0.78, 0.4),
                       (0.86, 1.3), (0.88, 1.9), (0.55, 1.75), (0.28, 1.95), (0.0, 1.8), (-0.28, 1.95),
                       (-0.55, 1.75), (-0.88, 1.9), (-0.86, 1.3), (-0.78, 0.4)])
    elif style == 'bob':
        shapes.append([(-0.66, -0.40), (-0.46, -0.86), (0.0, -0.94), (0.46, -0.86), (0.66, -0.40), (0.76, 0.30),
                       (0.74, 0.70), (0.40, 0.64), (0.0, 0.68), (-0.40, 0.64), (-0.74, 0.70), (-0.76, 0.30)])
    else:
        shapes.append([(-0.62, -0.40), (-0.44, -0.86), (0.0, -0.94), (0.44, -0.86), (0.62, -0.40),
                       (0.60, 0.10), (0.42, 0.28), (-0.42, 0.28), (-0.60, 0.10)])
    if style == 'ponytail':
        shapes.append([(0.30, -0.70), (0.66, -0.58), (0.86, 0.0), (0.84, 0.7), (0.66, 1.3), (0.52, 0.8),
                       (0.52, 0.10), (0.36, -0.40)])
    if style == 'twintails':
        for s in (-1, 1):
            shapes.append([(s * 0.56, -0.55), (s * 0.88, -0.42), (s * 1.08, 0.2), (s * 1.02, 0.9), (s * 0.86, 1.45),
                           (s * 0.76, 0.9), (s * 0.74, 0.2), (s * 0.62, -0.30)])
    for s in shapes:
        smooth = style not in ('curly', 'undercut')
        _shade_hair(th, cv, th.path(s, smooth=smooth), off=(0.10, -0.08))
    if style == 'bun':
        x, y = th.W2(0.0, -1.0)
        bun = VPath().ellipse(x, y, 0.28 * th.U, 0.24 * th.U)
        _shade_hair(th, cv, bun)
    if style == 'twintails':
        for s in (-1, 1):
            x, y = th.W2(s * 0.72, -0.48)
            cv.fill_stroke(VPath().ellipse(x, y, 0.08 * th.U, 0.08 * th.U), th.col['accent'], INK, th.lw * 0.7)


# --------------------------------------------------------------------------
# Accessories
# --------------------------------------------------------------------------


def draw_accessories(th: ToonHead, cv: Canvas) -> None:
    acc = set(th.d.accessories)
    U, lw = th.U, th.lw
    if 'mask' in acc:
        mx = th.warp(0.0)
        m = [(mx - 0.50, 0.22), (mx + 0.48 - 0.06 * th.t, 0.22), (mx + 0.42 - 0.06 * th.t, 0.46),
             (mx + 0.04 * th.t, 0.60), (mx - 0.40, 0.46)]
        cv.shaded(th.path(m, warp=False), '#262428', '#141216', (-0.06 * U, -0.05 * U), INK, lw)
        cv.fill(taper_stroke([th.P(mx - 0.38, 0.27), th.P(mx + 0.30, 0.27)], lw * 0.2, lw * 0.2, lw * 0.5), '#55525A')
    if 'glasses' in acc:
        for side in (-1, 1):
            cx, cy, w, h, sc = th.eye_geom(side)
            rim = VPath().ellipse(*th.P(cx, cy), w * 0.62 * U, h * 0.60 * U)
            cv.fill(rim, '#DDEEFF38')
            cv.stroke(rim, INK, lw * 1.1)
        l, cy, w, _, _ = th.eye_geom(-1)
        r = th.eye_geom(1)[0]
        cv.stroke(VPath().poly([th.P(l + w * 0.6, cy - 0.03), th.P(r - w * 0.6, cy - 0.03)], closed=False), INK, lw)
    if 'bindi' in acc:
        cv.fill(VPath().ellipse(*th.W2(0.0, -0.20), 0.025 * U, 0.03 * U), '#C81E3A')
    if 'mustache' in acc or 'beard' in acc:
        mx = th.warp(0.0) + 0.04 * th.t
        must = [(mx - 0.17, 0.33), (mx, 0.28), (mx + 0.17, 0.33), (mx + 0.11, 0.36), (mx, 0.32), (mx - 0.11, 0.36)]
        cv.fill_stroke(th.path(must, warp=False), pal.darken(th.hair, 0.1), INK, lw * 0.6)
    if 'beard' in acc:
        mx = th.warp(0.0)
        beard = [(mx - 0.42, 0.22), (mx - 0.30, 0.50), (mx + 0.06 * th.t, 0.64), (mx + 0.30, 0.50),
                 (mx + 0.42, 0.22), (mx + 0.24, 0.42), (mx, 0.47), (mx - 0.24, 0.42)]
        cv.fill(th.path(beard, warp=False), pal.with_alpha(pal.darken(th.hair, 0.1), 225))
    if 'earrings' in acc:
        cv.fill_stroke(VPath().ellipse(*th.P(-0.57 if th.t else -0.56, 0.26), 0.03 * U, 0.03 * U), '#F2C94C', INK,
                       lw * 0.5)
        if th.t == 0:
            cv.fill_stroke(VPath().ellipse(*th.P(0.56, 0.26), 0.03 * U, 0.03 * U), '#F2C94C', INK, lw * 0.5)
    if 'freckles' in acc:
        for side in (-1, 1):
            cx, cy, w, h, sc = th.eye_geom(side)
            for k in range(4):
                x, y = th.P(cx + (k - 1.5) * 0.04, cy + h / 2 + 0.06 + 0.02 * (k % 2))
                cv.fill(VPath().ellipse(x, y, 0.009 * U, 0.009 * U), '#D07070')
