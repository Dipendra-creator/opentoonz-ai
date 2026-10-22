"""Body parts shared by every style.

Torso (front and three-quarter), 2-bone legs with shoes, 2-bone arms with
chunky 4-finger hands, and a ground contact shadow. Every part is drawn in
root coordinates (inches, feet at 0, y up) on its own canvas; the rig builder
records where each canvas sits and where it pivots.

Shading is flat colour + one hard cel shadow per part, hue-shifted
(``palette.cel_shadow``), placed on the side away from an upper-left light.
"""

from __future__ import annotations

import math

from . import palette as pal
from .vec import Canvas, Path as VPath, bezier_points, rgba, taper_stroke

BODY_DPI = 240
TOON_INK = '#1C1719'
HAND_DRAWINGS = ['open', 'fist', 'point', 'palm']


class Kit:
    """Drawing helpers for one body canvas."""

    def __init__(self, d, p, x0: float, y0: float, x1: float, y1: float,
                 view: str = 'front', dpi: int = BODY_DPI, warp: bool = False) -> None:
        self.d, self.p, self.dpi = d, p, dpi
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.W = int(math.ceil((x1 - x0) * dpi))
        self.Hpx = int(math.ceil((y1 - y0) * dpi))
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.col = d.resolved()
        self.toon = d.style == 'cartoon'
        self.t = 0.0 if view == 'front' else 0.5
        self.warp_on = warp and self.t > 0
        self.lw = p.lw * dpi
        self.skin = self.col['skin']

    # -- coordinates -------------------------------------------------------
    def warp(self, x: float) -> float:
        if not self.warp_on:
            return x
        sx = self.p.shoulder_x * 1.1
        k = max(0.0, 1 - (x / sx) ** 2)
        return x * (1 - 0.10 * self.t) + self.t * 0.30 * self.p.hh * 0.5 * k

    def P(self, x: float, y: float) -> tuple[float, float]:
        return ((self.warp(x) - self.x0) * self.dpi, (self.y1 - y) * self.dpi)

    def canvas(self, ss: int = 3) -> Canvas:
        return Canvas(self.W, self.Hpx, ss=ss)

    def path(self, pts, smooth=True, tension=0.5, closed=True) -> VPath:
        conv = [self.P(x, y) for x, y in pts]
        if smooth:
            return VPath().smooth(conv, closed=closed, tension=tension)
        return VPath().poly(conv, closed=closed)

    # -- painting -----------------------------------------------------------
    def ink(self, color: str) -> str:
        if self.toon:
            return TOON_INK
        return pal.mix(pal.line_color(color), '#241A20', 0.3)

    def part(self, cv: Canvas, pts, color: str, kind: str = 'cloth', smooth=True,
             tension=0.5, shade=(-0.09, -0.05), lw_mul: float = 1.0, line=True,
             sides=None) -> VPath:
        """Filled shape with a hard cel shadow and outline. ``shade`` is the
        shift (in head heights) towards the light; None for flat. ``sides``
        (list of polylines) strokes only those edges, leaving joint ends open
        so overlapping limb segments read as one limb."""
        if sides is not None:
            path = self.part(cv, pts, color, kind, smooth, tension, shade, lw_mul, line=False)
            for poly in sides:
                cv.stroke(self.path(poly, smooth=len(poly) > 2, closed=False), self.ink(color), self.lw * lw_mul)
            return path
        path = self.path(pts, smooth=smooth, tension=tension)
        hh = self.p.hh
        if shade is not None:
            off = (shade[0] * hh * self.dpi, shade[1] * hh * self.dpi)
            cv.shaded(path, color, pal.cel_shadow(color, kind), off,
                      self.ink(color) if line else None, self.lw * lw_mul if line else 0)
        else:
            cv.fill(path, color)
            if line:
                cv.stroke(path, self.ink(color), self.lw * lw_mul)
        return path

    def detail(self, cv: Canvas, pts, color: str | None = None, w: float = 0.45,
               smooth: bool = True) -> None:
        """Tapered inner line (folds, seams, finger separations)."""
        conv = [self.P(x, y) for x, y in pts]
        if smooth and len(conv) >= 3:
            conv = VPath().smooth(conv).subpaths[0]
        cv.fill(taper_stroke(conv, self.lw * w * 0.35, self.lw * w * 0.35, self.lw * w),
                color or (TOON_INK if self.toon else self.ink(self.skin)))


# --------------------------------------------------------------------------
# Torso
# --------------------------------------------------------------------------


def torso_bounds(p) -> tuple[float, float, float, float]:
    return (-1.35 * p.hh, -0.1 * p.hh + min(p.knee_y, p.crotch_y - 0.6 * p.hh), 1.35 * p.hh,
            p.chin + 0.14 * p.hh)


def draw_torso(k: Kit, cv: Canvas) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    female = d.gender == 'female'
    top, bottom = d.top, d.bottom
    accent = c['accent']
    nw = p.neck_w
    # neck ----------------------------------------------------------------
    neck = [(-nw, p.chin + 0.10 * hh), (nw, p.chin + 0.10 * hh), (nw * 1.08, p.shoulder_y - 0.02 * hh),
            (-nw * 1.08, p.shoulder_y - 0.02 * hh)]
    k.part(cv, neck, k.skin, 'skin', smooth=False, shade=None)
    chin_shadow = [(-nw * 1.1, p.chin + 0.10 * hh), (nw * 1.1, p.chin + 0.10 * hh), (nw * 1.1, p.chin - 0.05 * hh),
                   (0, p.chin - 0.12 * hh), (-nw * 1.1, p.chin - 0.05 * hh)]
    cv.fill(k.path(chin_shadow, smooth=False), pal.cel_shadow(k.skin, 'skin'))
    # bottom wear on the pelvis ------------------------------------------
    long_top = top in ('kurta', 'dress')
    bc = c['bottom']
    if bottom == 'skirt' and not long_top:
        hem = p.crotch_y - 0.42 * (p.crotch_y - p.knee_y)
        skirt = [(-p.waist_x, p.waist_y + 0.04 * hh), (p.waist_x, p.waist_y + 0.04 * hh),
                 (p.hip_x * 1.35, hem), (-p.hip_x * 1.35, hem)]
        k.part(cv, skirt, bc, smooth=False)
        for i in range(-2, 3):
            k.detail(cv, [(i * p.waist_x * 0.3, p.waist_y - 0.02 * hh), (i * p.hip_x * 0.45, hem + 0.04 * hh)],
                     pal.cel_shadow(bc) if not k.toon else TOON_INK, 0.4, smooth=False)
    elif not long_top:
        legh = 0.10 * hh if bottom != 'shorts' else 0.24 * hh
        pelvis = [(-p.waist_x, p.waist_y + 0.04 * hh), (p.waist_x, p.waist_y + 0.04 * hh),
                  (p.hip_x, p.crotch_y + 0.05 * hh), (p.hip_x * 0.98, p.crotch_y - legh),
                  (0.03 * hh, p.crotch_y - legh * 0.4), (0.0, p.crotch_y - 0.02 * hh),
                  (-0.03 * hh, p.crotch_y - legh * 0.4), (-p.hip_x * 0.98, p.crotch_y - legh),
                  (-p.hip_x, p.crotch_y + 0.05 * hh)]
        k.part(cv, pelvis, bc, smooth=False)
        if bottom == 'jeans':
            k.detail(cv, [(0, p.waist_y), (0, p.crotch_y + 0.02 * hh)], pal.cel_shadow(bc), 0.4, smooth=False)
            k.detail(cv, [(-p.waist_x * 0.75, p.waist_y - 0.03 * hh), (-p.waist_x * 0.35, p.waist_y - 0.12 * hh)],
                     '#E8C25A', 0.35)
            k.detail(cv, [(p.waist_x * 0.75, p.waist_y - 0.03 * hh), (p.waist_x * 0.35, p.waist_y - 0.12 * hh)],
                     '#E8C25A', 0.35)
    # top garment -----------------------------------------------------------
    hem = p.crotch_y + 0.16 * hh
    flare = 1.0
    if top == 'kurta':
        hem, flare = p.knee_y + 0.18 * hh, 1.25
    elif top == 'dress':
        hem, flare = p.crotch_y - 0.45 * (p.crotch_y - p.knee_y), 1.5
    elif top in ('hoodie', 'sweater', 'suit'):
        hem = p.crotch_y + 0.06 * hh
    tc = c['top']
    if top == 'school_uniform' and d.top_color in ('', None):
        tc = '#F4F4F8'
    sx, cx, wx, hx = p.shoulder_x, p.chest_x, p.waist_x, p.hip_x
    torso = [(-nw * 1.25, p.shoulder_y + 0.04 * hh), (-sx * 0.82, p.shoulder_y + 0.0 * hh),
             (-sx, p.shoulder_y - 0.12 * hh), (-cx, p.chest_y), (-wx * 1.02, p.waist_y),
             (-hx * flare, hem), (hx * flare, hem), (wx * 1.02, p.waist_y), (cx, p.chest_y),
             (sx, p.shoulder_y - 0.12 * hh), (sx * 0.82, p.shoulder_y + 0.0 * hh),
             (nw * 1.25, p.shoulder_y + 0.04 * hh)]
    k.part(cv, torso, tc, smooth=True, tension=0.3, shade=(-0.12, -0.03))
    ink = k.ink(tc)
    sh = pal.cel_shadow(tc)
    if top == 'tshirt' and d.accent_color and 'stripe' in d.accessories:
        band = [(-cx, p.chest_y + 0.02 * hh), (cx, p.chest_y + 0.02 * hh), (cx * 1.0, p.chest_y - 0.20 * hh),
                (-cx * 1.0, p.chest_y - 0.20 * hh)]
        k.part(cv, band, accent, smooth=False, shade=(-0.12, 0), lw_mul=0.6)
    if top in ('tshirt', 'sweater', 'hoodie', 'dress'):
        neck_open = [(-nw * 1.2, p.shoulder_y + 0.04 * hh), (0, p.shoulder_y - 0.11 * hh),
                     (nw * 1.2, p.shoulder_y + 0.04 * hh)]
        cv.fill(k.path(neck_open + [(0, p.shoulder_y + 0.05 * hh)], smooth=False), pal.cel_shadow(k.skin, 'skin'))
        cv.stroke(k.path(neck_open, closed=False, smooth=True), ink, k.lw * 0.8)
        if top == 'tshirt':
            rib = pal.cel_shadow(tc) if not d.accent_color or 'stripe' not in d.accessories else accent
            k.detail(cv, [(-nw * 1.35, p.shoulder_y + 0.0 * hh), (0, p.shoulder_y - 0.16 * hh),
                          (nw * 1.35, p.shoulder_y + 0.0 * hh)], rib, 0.55)
    if top == 'hoodie':
        hood = [(-nw * 2.3, p.shoulder_y + 0.01 * hh), (-nw * 1.3, p.shoulder_y + 0.15 * hh),
                (nw * 1.3, p.shoulder_y + 0.15 * hh), (nw * 2.3, p.shoulder_y + 0.01 * hh),
                (nw * 1.4, p.shoulder_y - 0.05 * hh), (-nw * 1.4, p.shoulder_y - 0.05 * hh)]
        k.part(cv, hood, sh, smooth=True, shade=None, lw_mul=0.8)
        for s in (-1, 1):
            x0 = s * 0.07 * hh
            pts = [(x0, p.shoulder_y - 0.09 * hh), (x0 + s * 0.01 * hh, p.chest_y - 0.02 * hh),
                   (x0 - s * 0.005 * hh, p.chest_y - 0.14 * hh)]
            cv.stroke(k.path(pts, closed=False), ink, k.lw * 1.25)
            cv.stroke(k.path(pts, closed=False), '#FFFFFF', k.lw * 0.6)
            tip = k.P(*pts[-1])
            cv.fill(VPath().rect(tip[0] - k.lw * 0.7, tip[1], tip[0] + k.lw * 0.7, tip[1] + k.lw * 2.6, r=k.lw * 0.3),
                    '#B9BCC4')
        pocket = [(-wx * 0.78, p.waist_y - 0.02 * hh), (wx * 0.78, p.waist_y - 0.02 * hh),
                  (wx * 0.95, hem + 0.10 * hh), (-wx * 0.95, hem + 0.10 * hh)]
        cv.stroke(k.path(pocket, smooth=False), ink, k.lw * 0.6)
        k.detail(cv, [(-hx, hem + 0.07 * hh), (hx, hem + 0.07 * hh)], sh, 0.5, smooth=False)
    if top in ('shirt', 'school_uniform', 'suit', 'kurta'):
        collar_y = p.shoulder_y + 0.05 * hh
        v_bottom = p.shoulder_y - (0.22 if top != 'kurta' else 0.30) * hh
        cv.fill(k.path([(-nw * 1.15, collar_y), (0, v_bottom), (nw * 1.15, collar_y)], smooth=False),
                pal.cel_shadow(k.skin, 'skin') if top != 'suit' else '#F4F4F8')
        if top == 'kurta':
            cv.stroke(k.path([(-nw * 1.15, collar_y), (0, v_bottom), (nw * 1.15, collar_y)], closed=False,
                             smooth=False), ink, k.lw * 0.8)
            k.detail(cv, [(0, v_bottom), (0, p.chest_y - 0.12 * hh)], ink, 0.5, smooth=False)
            for yy in (0.0, 0.1):
                k.detail(cv, [(-hx * flare * 0.98, hem + (0.10 + yy) * hh), (hx * flare * 0.98, hem + (0.10 + yy) * hh)],
                         accent, 0.9, smooth=False)
            for s in (-1, 1):
                k.detail(cv, [(s * hx * 1.18, hem + 0.02 * hh), (s * hx * 1.04, p.crotch_y - 0.05 * hh)], ink, 0.45,
                         smooth=False)
        else:
            for s in (-1, 1):
                flap = [(s * nw * 1.25, collar_y), (s * nw * 0.15, p.shoulder_y - 0.17 * hh),
                        (s * nw * 2.1, p.shoulder_y - 0.09 * hh)]
                k.part(cv, flap, '#F7F7F8' if top != 'suit' else '#F7F7F8', smooth=False, shade=None, lw_mul=0.7)
            if top in ('school_uniform', 'suit') or 'tie' in d.accessories:
                tie = [(-0.045 * hh, p.shoulder_y - 0.15 * hh), (0.045 * hh, p.shoulder_y - 0.15 * hh),
                       (0.075 * hh, p.waist_y + 0.10 * hh), (0, p.waist_y + 0.0 * hh), (-0.075 * hh, p.waist_y + 0.10 * hh)]
                k.part(cv, tie, accent, smooth=False, shade=(-0.05, 0), lw_mul=0.7)
            else:
                for i in range(4):
                    x, y = k.P(0.0, p.shoulder_y - (0.30 + i * 0.26) * hh)
                    cv.fill_stroke(VPath().ellipse(x, y, k.lw * 1.1, k.lw * 1.1), '#FFFFFF', ink, k.lw * 0.35)
                pocket = [(-cx * 0.72, p.chest_y + 0.10 * hh), (-cx * 0.30, p.chest_y + 0.10 * hh),
                          (-cx * 0.30, p.chest_y - 0.10 * hh), (-cx * 0.72, p.chest_y - 0.10 * hh)]
                cv.stroke(k.path(pocket, smooth=False), ink, k.lw * 0.5)
            if top == 'suit':
                for s in (-1, 1):
                    lapel = [(s * nw * 1.35, p.shoulder_y + 0.03 * hh), (s * 0.08 * hh, p.waist_y + 0.04 * hh),
                             (s * 0.30 * hh, p.chest_y + 0.06 * hh)]
                    k.part(cv, lapel, pal.cel_shadow(tc), smooth=False, shade=None, lw_mul=0.7)
                x, y = k.P(0.10 * hh, p.waist_y - 0.1 * hh)
                cv.fill_stroke(VPath().ellipse(x, y, k.lw * 1.2, k.lw * 1.2), '#2A2A30', ink, k.lw * 0.3)
    if top == 'dress':
        belt = [(-wx * 1.05, p.waist_y + 0.05 * hh), (wx * 1.05, p.waist_y + 0.05 * hh),
                (wx * 1.05, p.waist_y - 0.05 * hh), (-wx * 1.05, p.waist_y - 0.05 * hh)]
        k.part(cv, belt, accent, smooth=False, shade=None, lw_mul=0.6)
    if top == 'sweater':
        for yy in (0.0, 0.05, 0.10):
            k.detail(cv, [(-hx * 0.98, hem + (0.04 + yy) * hh), (hx * 0.98, hem + (0.04 + yy) * hh)], sh, 0.4,
                     smooth=False)
    # armpit / under-chest ambient occlusion
    for s in (-1, 1):
        ao = [(s * sx * 0.98, p.shoulder_y - 0.18 * hh), (s * cx * 0.9, p.chest_y - 0.05 * hh),
              (s * cx * 0.80, p.shoulder_y - 0.20 * hh)]
        cv.fill(k.path(ao, smooth=False), pal.with_alpha(sh, 140))


# --------------------------------------------------------------------------
# Limbs: organic silhouettes merged from several shapes
# --------------------------------------------------------------------------


class Sculpt:
    """Several shapes merged into one silhouette.

    Every outline is stroked first at double width, then all fills go on top:
    only the outer contour keeps a line (exactly ``lw`` wide), so a hand made
    of palm + fingers + thumb, or a leg made of segment + joint disc, reads as
    one drawn shape. Interior lines (folds, finger gaps, hems) are added after
    with ``detail``.
    """

    def __init__(self, k: Kit, cv: Canvas) -> None:
        self.k, self.cv = k, cv
        self.items: list = []
        self.lines: list = []
        self.after: list = []

    def add(self, shape, color: str, kind: str = 'skin', shade=(-0.06, 0.0), outline: bool = True,
            smooth: bool = True, tension: float = 0.5) -> VPath:
        path = shape if isinstance(shape, VPath) else self.k.path(shape, smooth=smooth, tension=tension)
        self.items.append((path, color, kind, shade, outline))
        return path

    def edge(self, pts, color: str | None = None, smooth: bool = True) -> None:
        """Outline-only polyline (e.g. the sides of a parent limb segment)."""
        self.lines.append((pts, color, smooth))

    def detail(self, pts, color=None, w=0.45, smooth=True) -> None:
        self.after.append((pts, color, w, smooth))

    def finish(self) -> None:
        k, cv = self.k, self.cv
        width = k.lw * 2.0
        for path, color, kind, shade, outline in self.items:
            if outline:
                cv.stroke(path, k.ink(color), width)
        for pts, color, smooth in self.lines:
            cv.stroke(k.path(pts, smooth=smooth and len(pts) > 2, closed=False),
                      k.ink(color or k.skin), width)
        hh = k.p.hh
        for path, color, kind, shade, outline in self.items:
            if shade is None:
                cv.fill(path, color)
            else:
                off = (shade[0] * hh * k.dpi, shade[1] * hh * k.dpi)
                cv.shaded(path, color, pal.cel_shadow(color, kind), off)
        for pts, color, w, smooth in self.after:
            k.detail(cv, pts, color, w, smooth)


def _side_pts(x: float, y0: float, y1: float, keys, side: int) -> list:
    """Points along one side of a vertical limb; keys = (t, half_left, half_right)."""
    out = []
    for t, hl, hr in keys:
        y = y0 + (y1 - y0) * t
        out.append((x - hl, y) if side < 0 else (x + hr, y))
    return out


def _arc(cx, cy, r, a0, a1, n=14):
    return [(cx + math.cos(a0 + (a1 - a0) * i / n) * r, cy + math.sin(a0 + (a1 - a0) * i / n) * r)
            for i in range(n + 1)]


def limb_shape(k: Kit, x: float, y0: float, y1: float, keys, cap_top: float | None = None,
               cap_bottom: float | None = None) -> tuple[VPath, list, list]:
    """Outline of a limb hanging from y0 down to y1 (y0 > y1) with smooth sides.

    ``cap_top``/``cap_bottom`` add round joint ends of that radius centred on
    the end points (the half widths there should equal the radius).
    Returns (closed path, left side points, right side points) in inches."""
    left = _side_pts(x, y0, y1, keys, -1)
    right = _side_pts(x, y0, y1, keys, 1)
    lp = [k.P(*q) for q in left]
    rp = [k.P(*q) for q in right]
    ls = VPath().smooth(lp, tension=0.55).subpaths[0]
    rs = VPath().smooth(rp, tension=0.55).subpaths[0]
    poly = list(ls)
    if cap_bottom:
        poly += [k.P(*q) for q in _arc(x, y1, cap_bottom, math.pi, 2 * math.pi)]
    poly += list(reversed(rs))
    if cap_top:
        poly += [k.P(*q) for q in _arc(x, y0, cap_top, 0.0, math.pi)]
    return VPath().poly(poly), left, right


def _covered(d) -> tuple[bool, float]:
    """(legs in trousers, fraction of thigh covered by shorts)."""
    if d.top == 'kurta' or d.bottom in ('pants', 'jeans'):
        return True, 1.0
    if d.bottom == 'shorts':
        return False, 0.55
    return False, 0.0


def _leg_keys(d, p, segment: str, view: str):
    """Half-width keys (t, left, right) for thigh or shin, in inches."""
    w = p.thigh_w / 2
    covered, _ = _covered(d)
    slim = d.bottom == 'jeans' or d.gender == 'female'
    back = 1.0 if view == 'front' else 1.08    # calf/thigh-back fullness on -x in 3/4
    front = 1.0 if view == 'front' else 0.94
    if covered:
        rk = w * (0.80 if not slim else 0.74)
        if segment == 'thigh':
            return [(0.0, w * 1.06, w * 1.06), (0.35, w * 1.0 * back, w * 0.98 * front),
                    (0.72, w * 0.90, w * 0.86), (1.0, rk, rk)], rk
        hem = w * (0.86 if not slim else 0.72)
        return [(0.0, rk, rk), (0.3, rk * 0.98 * back, rk * 0.96), (0.72, rk * 0.94, rk * 0.92),
                (1.0, hem, hem)], rk
    rk = w * 0.62
    if segment == 'thigh':
        return [(0.0, w * 1.0, w * 1.0), (0.35, w * 0.96 * back, w * 0.90 * front),
                (0.75, w * 0.76, w * 0.72), (1.0, rk, rk)], rk
    return [(0.0, rk, rk), (0.26, rk * 1.18 * back, rk * 1.06), (0.62, rk * 0.92, rk * 0.86),
            (1.0, rk * 0.66, rk * 0.66)], rk


def leg_bounds(p, side: int, segment: str) -> tuple[float, float, float, float]:
    hx = side * p.hip_jx
    if segment == 'thigh':
        return (hx - 0.45 * p.hh, p.knee_y - 0.3 * p.hh, hx + 0.45 * p.hh, p.hip_jy + 0.3 * p.hh)
    return (hx - 0.6 * p.hh, -0.15 * p.hh, hx + 0.75 * p.hh, p.knee_y + 0.3 * p.hh)


def draw_thigh(k: Kit, cv: Canvas, side: int, view: str = 'front') -> None:
    if k.toon:
        return stick_thigh(k, cv, side, view)
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x, y0, y1 = side * p.hip_jx, p.hip_jy + 0.14 * hh, p.knee_y
    keys, rk = _leg_keys(d, p, 'thigh', view)
    covered, frac = _covered(d)
    color = c['bottom'] if covered else k.skin
    sc = Sculpt(k, cv)
    path, left, right = limb_shape(k, x, y0, y1, keys, cap_bottom=rk)
    sc.add(path, color, 'cloth' if covered else 'skin', shade=(-0.06, 0.0), outline=False)
    sc.edge(left, color)
    sc.edge(right, color)
    if frac and not covered:  # shorts over the top of the thigh
        yb = y0 + (y1 - y0) * frac
        sk = [(t * frac, hl * 1.12, hr * 1.12) for t, hl, hr in keys if t <= frac] + \
             [(frac, keys[1][1] * 1.08, keys[1][2] * 1.08)]
        spath, sl, sr = limb_shape(k, x, y0, yb, [(t / frac, a, b) for t, a, b in sk])
        sc.add(spath, c['bottom'], 'cloth', shade=(-0.06, 0.0), outline=False)
        sc.edge(sl, c['bottom'])
        sc.edge(sr, c['bottom'])
        sc.edge([sl[-1], sr[-1]], c['bottom'], smooth=False)
        sc.detail([(x - keys[1][1], yb + 0.05 * hh), (x + keys[1][2], yb + 0.05 * hh)],
                  pal.cel_shadow(c['bottom']), 0.4, smooth=False)
    if covered:
        # fabric: a fold where the thigh meets the knee, jeans seam
        ky = y1 + 0.16 * hh
        o = -1 if side < 0 else 1
        sc.detail([(x + o * rk * 0.95, ky + 0.02 * hh), (x + o * rk * 0.35, ky - 0.03 * hh)], None, 0.5)
        sc.detail([(x - o * rk * 0.9, ky - 0.08 * hh), (x - o * rk * 0.45, ky - 0.11 * hh)], None, 0.4)
        if d.bottom == 'jeans':
            sc.detail([(x + side * keys[1][2] * 0.85, y0 - 0.1 * hh), (x + side * rk * 0.85, y1 + 0.05 * hh)],
                      '#E8C25A', 0.3)
    sc.finish()


def draw_shin(k: Kit, cv: Canvas, side: int, view: str) -> None:
    if k.toon:
        return stick_shin(k, cv, side, view)
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x = side * p.hip_jx
    covered, _ = _covered(d)
    keys, rk = _leg_keys(d, p, 'shin', view)
    color = c['bottom'] if covered else k.skin
    sc = Sculpt(k, cv)
    shoe_x = x + side * 0.02 * hh
    draw_shoe(k, sc, shoe_x, view, side)
    sandals = d.top == 'kurta' or 'sandals' in d.accessories
    # trousers break over shoes, but stop at the ankle above bare feet in sandals
    hem_y = p.shoe_h * (0.62 if covered and not sandals else 0.95)
    path, left, right = limb_shape(k, x, p.knee_y, hem_y, keys, cap_top=rk)
    sc.add(path, color, 'cloth' if covered else 'skin', shade=(-0.06, 0.0), outline=True)
    if covered:
        hw = keys[-1][1]
        sc.detail([(x - hw, hem_y + 0.01 * hh), (x, hem_y - 0.02 * hh), (x + hw, hem_y + 0.01 * hh)], None, 0.9)
        o = -1 if side < 0 else 1
        sc.detail([(x - o * rk * 0.85, hem_y + 0.16 * hh), (x - o * rk * 0.2, hem_y + 0.11 * hh)], None, 0.4)
        sc.detail([(x + o * rk * 0.8, p.knee_y - 0.12 * hh), (x + o * rk * 0.25, p.knee_y - 0.07 * hh)], None, 0.4)
        if d.bottom == 'jeans':
            sc.detail([(x + side * rk * 0.8, p.knee_y - 0.05 * hh), (x + side * hw * 0.8, hem_y + 0.08 * hh)],
                      '#E8C25A', 0.3)
    else:
        if d.bottom == 'skirt' or d.top in ('school_uniform', 'dress'):
            sy0 = p.knee_y + (hem_y - p.knee_y) * 0.62
            spath, _, _ = limb_shape(k, x, sy0, hem_y, [(0.0, rk * 0.86, rk * 0.84), (1.0, rk * 0.72, rk * 0.72)])
            sc.add(spath, '#F4F4F8', 'cloth', shade=(-0.06, 0.0), outline=False)
            sc.detail([(x - rk * 0.86, sy0), (x + rk * 0.84, sy0)], None, 0.6, smooth=False)
        if view == 'front':
            sc.detail([(x - rk * 0.35, p.knee_y - 0.02 * hh), (x, p.knee_y - 0.05 * hh),
                       (x + rk * 0.3, p.knee_y - 0.02 * hh)], None, 0.35)
    sc.finish()


def draw_shoe(k: Kit, sc: Sculpt, x: float, view: str, side: int) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    L, H = p.shoe_len, p.shoe_h
    formal = d.top in ('suit',) or (d.top == 'school_uniform' and d.shoe_color in ('white', '', None))
    base = '#26232A' if formal else c['shoe']
    sole_c = '#F2F2F4' if not formal else '#3A3640'
    if base.upper() in ('#F4F4F2', '#FFFFFF', '#F2F2F4'):
        sole_c = '#D9D9E2'
    accent = c['accent']
    if d.top == 'kurta' or 'sandals' in d.accessories:
        _sandal(k, sc, x, view, side)
        return
    if view == 'front':
        w = L * 0.70
        o = side * 0.04 * hh  # toes turned slightly out
        upper = [(x - w / 2 + o, 0.05 * hh), (x - w * 0.54 + o, H * 0.45), (x - w * 0.40 + o, H * 0.86),
                 (x - w * 0.12, H * 1.02), (x + w * 0.12, H * 1.02), (x + w * 0.40 + o, H * 0.86),
                 (x + w * 0.54 + o, H * 0.45), (x + w / 2 + o, 0.05 * hh)]
        sole = [(x - w * 0.56 + o, 0.0), (x + w * 0.56 + o, 0.0), (x + w * 0.58 + o, 0.075 * hh),
                (x - w * 0.58 + o, 0.075 * hh)]
        sc.add(upper, base, 'cloth', shade=(-0.05, -0.03), tension=0.45)
        sc.add(sole, sole_c, 'cloth', shade=None, smooth=False)
        sc.detail([(x - w * 0.56 + o, 0.075 * hh), (x + w * 0.56 + o, 0.075 * hh)], None, 0.6, smooth=False)
        if not formal:
            sc.detail([(x - w * 0.36 + o, H * 0.35), (x, H * 0.22), (x + w * 0.36 + o, H * 0.35)], None, 0.45)
            for i in range(3):
                yy = H * (0.66 + i * 0.1)
                sc.detail([(x - w * 0.14, yy), (x + w * 0.14, yy + 0.008 * hh)], '#FFFFFF' if base != '#FFFFFF' else
                          '#9A9AA8', 0.55, smooth=False)
    else:
        back, toe = x - L * 0.34, x + L * 0.68
        upper = [(back, 0.05 * hh), (back - 0.03 * L, H * 0.55), (back + 0.04 * L, H * 1.0),
                 (x - 0.04 * L, H * 1.12), (x + 0.10 * L, H * 1.02), (x + 0.32 * L, H * 0.80),
                 (toe - 0.10 * L, H * 0.58), (toe + 0.02 * L, H * 0.30), (toe - 0.02 * L, 0.05 * hh)]
        sole = [(back - 0.02 * L, 0.0), (toe - 0.06 * L, 0.0), (toe + 0.03 * L, 0.06 * hh),
                (toe + 0.04 * L, 0.09 * hh), (back - 0.03 * L, 0.085 * hh)]
        sc.add(upper, base, 'cloth', shade=(-0.04, -0.03), tension=0.45)
        sc.add(sole, sole_c, 'cloth', shade=None, tension=0.3)
        sc.detail([(back - 0.02 * L, 0.085 * hh), (toe + 0.03 * L, 0.09 * hh)], None, 0.6)
        if not formal:
            sc.detail([(back + 0.10 * L, H * 0.35), (x + 0.10 * L, H * 0.55), (x + 0.45 * L, H * 0.30)],
                      accent, 1.3)
            for i in range(3):
                lx = x + (0.06 + i * 0.09) * L
                ly = H * (1.0 - i * 0.08)
                sc.detail([(lx, ly), (lx + 0.07 * L, ly - 0.05 * H)], '#FFFFFF' if base != '#FFFFFF' else '#9A9AA8',
                          0.55, smooth=False)
        sc.detail([(toe - 0.30 * L, H * 0.22), (toe - 0.05 * L, H * 0.32)], None, 0.4, smooth=False)


def _sandal(k: Kit, sc: Sculpt, x: float, view: str, side: int) -> None:
    """Flat chappal: bare foot with toes on a thin sole and a strap."""
    p, c = k.p, k.col
    hh = p.hh
    L, H = p.shoe_len, p.shoe_h
    strap = c['shoe'] if c['shoe'].upper() not in ('#F4F4F2', '#FFFFFF') else '#8A5A3B'
    skin = k.skin
    if view == 'front':
        w = L * 0.56
        o = side * 0.03 * hh
        foot = [(x - w / 2 + o, 0.04 * hh), (x - w * 0.52 + o, H * 0.40), (x - w * 0.30, H * 0.80),
                (x + w * 0.30, H * 0.80), (x + w * 0.52 + o, H * 0.40), (x + w / 2 + o, 0.04 * hh)]
        sole = [(x - w * 0.62 + o, 0.0), (x + w * 0.62 + o, 0.0), (x + w * 0.62 + o, 0.045 * hh),
                (x - w * 0.62 + o, 0.045 * hh)]
        sc.add(foot, skin, 'skin', shade=(-0.04, -0.02), tension=0.45)
        sc.add(sole, '#7A5238', 'cloth', shade=None, smooth=False)
        for i in range(4):
            tx = x + o + (-0.30 + i * 0.2) * w
            sc.detail([(tx, 0.05 * hh), (tx, H * 0.22)], None, 0.35, smooth=False)
        sc.add([(x - w * 0.50, H * 0.30), (x + w * 0.50, H * 0.30), (x + w * 0.46, H * 0.48),
                (x - w * 0.46, H * 0.48)], strap, 'cloth', shade=None, smooth=False)
    else:
        back, toe = x - L * 0.30, x + L * 0.66
        foot = [(back, 0.04 * hh), (back - 0.02 * L, H * 0.45), (x - 0.02 * L, H * 0.95),
                (x + 0.25 * L, H * 0.62), (toe - 0.04 * L, H * 0.35), (toe, 0.04 * hh)]
        sc.add(foot, skin, 'skin', shade=(-0.03, -0.02), tension=0.45)
        sc.add([(back - 0.04 * L, 0.0), (toe + 0.02 * L, 0.0), (toe + 0.02 * L, 0.045 * hh),
                (back - 0.04 * L, 0.045 * hh)], '#7A5238', 'cloth', shade=None, smooth=False)
        sc.add([(x + 0.02 * L, H * 0.30), (x + 0.30 * L, H * 0.30), (x + 0.26 * L, H * 0.62),
                (x + 0.04 * L, H * 0.80)], strap, 'cloth', shade=None, tension=0.4)
        sc.detail([(toe - 0.18 * L, 0.05 * hh), (toe - 0.16 * L, H * 0.22)], None, 0.35, smooth=False)


def arm_bounds(p, side: int, segment: str) -> tuple[float, float, float, float]:
    sx = side * p.arm_x
    if segment == 'upper':
        return (sx - 0.45 * p.hh, p.shoulder_y - p.upper_len - 0.3 * p.hh, sx + 0.45 * p.hh, p.shoulder_y + 0.25 * p.hh)
    ey = p.shoulder_y - p.upper_len
    return (sx - 0.5 * p.hh, ey - p.fore_len - p.hand_len * 1.5, sx + 0.5 * p.hh, ey + 0.25 * p.hh)


def _sleeves(d) -> tuple[str, str]:
    """(upper arm covering, forearm covering): 'long', 'short', 'three_quarter' or 'none'."""
    if d.top in ('tshirt', 'dress') or (d.top == 'school_uniform' and d.gender == 'female'):
        return 'short', 'none'
    if d.top == 'kurta':
        return 'long', 'three_quarter'
    return 'long', 'long'


def _elbow_radius(d, p) -> float:
    up, _ = _sleeves(d)
    return p.upper_w / 2 * (0.95 if up == 'long' else 0.74)


def draw_upper_arm(k: Kit, cv: Canvas, side: int, length_mul: float = 1.0) -> None:
    if k.toon:
        return stick_upper(k, cv, side, length_mul)
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x, y0 = side * p.arm_x, p.shoulder_y
    L = p.upper_len * length_mul
    y1 = y0 - L
    w = p.upper_w / 2
    up, _ = _sleeves(d)
    re = _elbow_radius(d, p)
    tc = c['top']
    sc = Sculpt(k, cv)
    o = side  # outer side
    if up == 'long':
        keys = [(0.0, w * 1.16, w * 1.16), (0.18, w * 1.14, w * 1.10), (0.5, w * 1.04, w * 0.98),
                (0.82, w * 1.00, w * 0.97), (1.0, re, re)]
        path, left, right = limb_shape(k, x, y0, y1, keys, cap_top=w * 1.12, cap_bottom=re)
        sc.add(path, tc, 'cloth', shade=(-0.06, 0.0), outline=False)
        top = _arc(x, y0, w * 1.12, 0.0, math.pi)
        sc.edge(top, tc)
        sc.edge(left, tc)
        sc.edge(right, tc)
        if length_mul > 0.8:
            ey = y1 + 0.12 * hh
            sc.detail([(x - o * re * 0.9, ey), (x - o * re * 0.25, ey + 0.04 * hh)], None, 0.45)
            sc.detail([(x - o * re * 0.85, ey + 0.10 * hh), (x - o * re * 0.40, ey + 0.12 * hh)], None, 0.35)
    else:
        keys = [(0.0, w * 1.0, w * 1.0), (0.3, w * 1.0, w * 0.94), (0.72, w * 0.84, w * 0.80), (1.0, re, re)]
        path, left, right = limb_shape(k, x, y0, y1, keys, cap_top=w, cap_bottom=re)
        sc.add(path, k.skin, 'skin', shade=(-0.06, 0.0), outline=False)
        sc.edge(left, k.skin)
        sc.edge(right, k.skin)
        # short sleeve: flared opening with a hem
        cut = y0 - p.upper_len * 0.50
        sk = [(0.0, w * 1.18, w * 1.18), (0.6, w * 1.30, w * 1.26), (1.0, w * 1.42, w * 1.36)]
        spath, sl, sr = limb_shape(k, x, y0, cut, sk, cap_top=w * 1.18)
        sc.add(spath, tc, 'cloth', shade=(-0.06, 0.0), outline=True)
        sc.detail([(x - w * 1.38, cut + 0.05 * hh), (x + w * 1.32, cut + 0.05 * hh)], pal.cel_shadow(tc), 0.5)
        sc.detail([(x + o * w * 1.2, cut + 0.28 * hh), (x + o * w * 0.5, cut + 0.12 * hh)], None, 0.35)
    sc.finish()


def draw_forearm(k: Kit, cv: Canvas, side: int, hand: str) -> None:
    if k.toon:
        return stick_fore(k, cv, side, hand)
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x = side * p.arm_x
    y0 = p.shoulder_y - p.upper_len
    L = p.fore_len
    y1 = y0 - L
    re = _elbow_radius(d, p)
    wf = p.fore_w / 2
    _, cover = _sleeves(d)
    tc = c['top']
    sc = Sculpt(k, cv)
    o = side
    wrist = wf * 0.72
    draw_hand(k, sc, x, y1 + 0.02 * hh, -side, hand, wrist)
    if cover == 'long':
        keys = [(0.0, re, re), (0.22, re * 1.04, re * 0.98), (0.55, re * 0.94, re * 0.90),
                (0.80, re * 0.97, re * 0.95), (1.0, re * 0.90, re * 0.90)]
        path, _, _ = limb_shape(k, x, y0, y1 + 0.06 * hh, keys, cap_top=re)
        sc.add(path, tc, 'cloth', shade=(-0.06, 0.0))
        # fabric bunching above the cuff
        for j, fy in enumerate((0.62, 0.74)):
            yy = y0 - L * fy
            s1 = 1 if j % 2 == 0 else -1
            sc.detail([(x + s1 * re * 0.92, yy), (x + s1 * re * 0.35, yy - 0.03 * hh)], None, 0.42)
        cuff_top = y1 + 0.20 * hh
        cuff = [(0.0, re * 0.82, re * 0.82), (1.0, re * 0.80, re * 0.80)]
        cpath, _, _ = limb_shape(k, x, cuff_top, y1 + 0.03 * hh, cuff)
        sc.add(cpath, pal.cel_shadow(tc) if d.top == 'hoodie' else tc, 'cloth', shade=None)
        sc.detail([(x - re * 0.82, cuff_top), (x + re * 0.82, cuff_top)], None, 0.5, smooth=False)
        if d.top in ('hoodie', 'sweater'):
            for i in range(1, 4):
                xx = x - re * 0.8 + i * re * 0.4
                sc.detail([(xx, cuff_top - 0.02 * hh), (xx, y1 + 0.05 * hh)], pal.darken(tc, 0.35), 0.3, smooth=False)
        sc.detail([(x + o * re * 0.9, y0 - 0.20 * hh), (x + o * re * 0.3, y0 - 0.26 * hh)], None, 0.4)
    else:
        keys = [(0.0, re, re), (0.25, re * 1.12, re * 1.0), (0.7, wf * 0.86, wf * 0.82), (1.0, wrist, wrist)]
        path, _, _ = limb_shape(k, x, y0, y1, keys, cap_top=re)
        sc.add(path, k.skin, 'skin', shade=(-0.06, 0.0))
        if cover == 'three_quarter':
            sk = [(0.0, re * 1.08, re * 1.08), (1.0, re * 1.3, re * 1.3)]
            spath, _, _ = limb_shape(k, x, y0 + 0.02 * hh, y0 - L * 0.45, sk, cap_top=re * 1.08)
            sc.add(spath, tc, 'cloth', shade=(-0.06, 0.0))
            sc.detail([(x - re * 1.28, y0 - L * 0.45 + 0.04 * hh), (x + re * 1.28, y0 - L * 0.45 + 0.04 * hh)],
                      c['accent'], 0.8)
    sc.finish()


def draw_hand(k: Kit, sc: Sculpt, x: float, y: float, thumb: int, kind: str, wrist: float) -> None:
    """Cartoon hand hanging from the wrist at (x, y), fingers pointing down.
    ``thumb`` (+1/-1) is the side the thumb is on (towards the body)."""
    p = k.p
    hl = p.hand_len
    pw = max(hl * 0.66, wrist * 2.3)
    skin = k.skin
    sh = (-0.04, -0.02)
    palm_h = hl * 0.50

    def finger(x0, y0, ang, length, width):
        ax, ay = math.sin(ang), -math.cos(ang)
        tip = (x0 + ax * length, y0 + ay * length)
        nx, ny = -ay, ax
        w0, w1 = width / 2, width * 0.46
        pts = [(x0 + nx * w0, y0 + ny * w0), (tip[0] + nx * w1, tip[1] + ny * w1)]
        pts += _arc(tip[0], tip[1], w1, math.atan2(ny, nx), math.atan2(ny, nx) - math.pi, 8)
        pts += [(x0 - nx * w0, y0 - ny * w0)]
        return pts, tip

    # wrist stub so the hand joins the forearm
    sc.add([(x - wrist, y + 0.06 * p.hh), (x + wrist, y + 0.06 * p.hh), (x + wrist * 1.05, y - 0.02 * p.hh),
            (x - wrist * 1.05, y - 0.02 * p.hh)], skin, 'skin', shade=sh, smooth=False)
    palm = [(x - pw * 0.42, y), (x + pw * 0.42, y), (x + pw * 0.54, y - palm_h * 0.55),
            (x + pw * 0.46, y - palm_h), (x - pw * 0.46, y - palm_h), (x - pw * 0.54, y - palm_h * 0.55)]
    if kind in ('open', 'palm'):
        fw = pw / 3.6
        lens = [0.38, 0.47, 0.48, 0.44] if kind == 'open' else [0.44, 0.52, 0.54, 0.50]
        spread = [0.10, 0.03, -0.03, -0.09] if kind == 'open' else [0.42, 0.14, -0.12, -0.36]
        tips = []
        for i in range(4):
            # i = 0 pinky (away from the thumb) ... 3 index (thumb side)
            fx = x + (-0.36 + i * 0.24) * pw * thumb
            fy = y - palm_h * 0.88
            pts, tip = finger(fx, fy, spread[i] * thumb * -1, hl * lens[i], fw)
            sc.add(pts, skin, 'skin', shade=sh, smooth=False)
            tips.append((fx, fy, tip))
        tpts, _ = finger(x + thumb * pw * 0.44, y - palm_h * 0.25, thumb * (0.75 if kind == 'open' else 1.15),
                         hl * 0.40, fw * 1.15)
        sc.add(tpts, skin, 'skin', shade=sh, smooth=False)
        sc.add(palm, skin, 'skin', shade=sh, tension=0.4)
        for i in range(3):
            ax, ay, _ = tips[i]
            bx, by, _ = tips[i + 1]
            mx = (ax + bx) / 2
            sc.detail([(mx, y - palm_h * 0.80), (mx + (tips[i][2][0] - ax) * 0.15, y - palm_h - hl * 0.12)], None, 0.45,
                      smooth=False)
        if kind == 'palm':
            sc.detail([(x - pw * 0.25 * thumb, y - palm_h * 0.35), (x + pw * 0.1 * thumb, y - palm_h * 0.6)], None, 0.35)
    else:
        fist = [(x - pw * 0.48, y), (x + pw * 0.48, y), (x + pw * 0.58, y - hl * 0.32),
                (x + pw * 0.50, y - hl * 0.58), (x - pw * 0.50, y - hl * 0.58), (x - pw * 0.58, y - hl * 0.32)]
        sc.add(fist, skin, 'skin', shade=sh, tension=0.45)
        # knuckle bumps along the bottom
        for i in range(4):
            bx = x + (-0.36 + i * 0.24) * pw
            sc.add(_arc(bx, y - hl * 0.56, pw * 0.13, math.pi * 0.05, math.pi * 0.95, 8), skin, 'skin',
                   shade=None, smooth=False)
        for i in range(3):
            bx = x + (-0.24 + i * 0.24) * pw
            sc.detail([(bx, y - hl * 0.42), (bx, y - hl * 0.62)], None, 0.4, smooth=False)
        if kind == 'point':
            pts, _ = finger(x + thumb * pw * 0.30, y - hl * 0.50, 0.0, hl * 0.55, pw / 3.4)
            sc.add(pts, skin, 'skin', shade=sh, smooth=False)
        # thumb wrapped across the front
        sc.add([(x + thumb * pw * 0.58, y - hl * 0.12), (x + thumb * pw * 0.30, y - hl * 0.38),
                (x - thumb * pw * 0.05, y - hl * 0.42), (x - thumb * pw * 0.02, y - hl * 0.30),
                (x + thumb * pw * 0.30, y - hl * 0.24)], skin, 'skin', shade=None, tension=0.5)


# --------------------------------------------------------------------------
# Stick ("noodle") limbs for the web-cartoon style
# --------------------------------------------------------------------------
# Web cartoons draw a full character for head and torso but keep arms and
# legs as thin sticks of constant width. Every segment is a capsule with the
# same radius, so joints are perfect circles: the parent segment leaves its
# lower end unoutlined and the child outlines its upper end, which makes a
# straight limb seamless and a bent one show a clean round elbow or knee.


def _capsule(k: Kit, x: float, y0: float, y1: float, r: float, top_line: bool = True,
             bottom_line: bool = True):
    """Vertical capsule from (x, y0) down to (x, y1). Returns (fill path,
    outline polylines) honouring which round ends get a line."""
    left = [(x - r, y0), (x - r, y1)]
    right = [(x + r, y1), (x + r, y0)]
    bottom = _arc(x, y1, r, math.pi, 2 * math.pi, 16)
    top = _arc(x, y0, r, 0.0, math.pi, 16)
    pts = left + bottom[1:-1] + right + top[1:-1]
    path = VPath().poly([k.P(*q) for q in pts])
    lines = [left, right]
    if bottom_line:
        lines.append(bottom)
    if top_line:
        lines.append(top)
    return path, lines


def _stick(sc: 'Sculpt', k: Kit, x, y0, y1, r, color, kind, top_line=True, bottom_line=True,
           shade=(-0.035, 0.0)):
    path, lines = _capsule(k, x, y0, y1, r, top_line, bottom_line)
    sc.add(path, color, kind, shade=shade, outline=False)
    for ln in lines:
        sc.edge(ln, color, smooth=False)
    return path


def stick_thigh(k: Kit, cv: Canvas, side: int, view: str) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x, y0, y1 = side * p.hip_jx, p.hip_jy + 0.10 * hh, p.knee_y
    r = p.thigh_w / 2
    covered, frac = _covered(d)
    sc = Sculpt(k, cv)
    _stick(sc, k, x, y0, y1, r, c['bottom'] if covered else k.skin, 'cloth' if covered else 'skin',
           top_line=False, bottom_line=False)
    if frac and not covered:  # shorts: a flared leg opening around the top of the thigh
        yb = y0 + (y1 - y0) * frac
        sc.add([(x - r * 1.6, y0), (x + r * 1.6, y0), (x + r * 2.1, yb), (x - r * 2.1, yb)],
               c['bottom'], 'cloth', shade=(-0.04, 0.0), smooth=False)
    sc.finish()


def stick_shin(k: Kit, cv: Canvas, side: int, view: str) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x = side * p.hip_jx
    r = p.shin_w / 2
    covered, _ = _covered(d)
    sandals = d.top == 'kurta' or 'sandals' in d.accessories
    sc = Sculpt(k, cv)
    draw_shoe(k, sc, x + side * 0.01 * hh, view, side)
    ankle = p.shoe_h * 0.75
    color = c['bottom'] if covered else k.skin
    _stick(sc, k, x, p.knee_y, ankle, r, color, 'cloth' if covered else 'skin', bottom_line=False)
    if covered and not sandals:
        hem = p.shoe_h * 0.55
        sc.add([(x - r * 1.05, hem + 0.16 * hh), (x + r * 1.05, hem + 0.16 * hh), (x + r * 1.45, hem),
                (x - r * 1.45, hem)], color, 'cloth', shade=(-0.035, 0.0), smooth=False)
    elif not covered and (d.bottom == 'skirt' or d.top in ('school_uniform', 'dress')):
        top = p.knee_y - (p.knee_y - ankle) * 0.55
        sc.add([(x - r * 1.15, top), (x + r * 1.15, top), (x + r * 1.15, ankle - 0.02 * hh),
                (x - r * 1.15, ankle - 0.02 * hh)], '#F4F4F8', 'cloth', shade=(-0.035, 0.0), smooth=False)
    sc.finish()


def stick_upper(k: Kit, cv: Canvas, side: int, length_mul: float = 1.0) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x, y0 = side * p.arm_x, p.shoulder_y - 0.02 * hh
    y1 = p.shoulder_y - p.upper_len * length_mul
    r = p.upper_w / 2
    up, _ = _sleeves(d)
    tc = c['top']
    sc = Sculpt(k, cv)
    # shoulder end without a line: it tucks into the torso of the same colour
    _stick(sc, k, x, y0, y1, r, tc if up == 'long' else k.skin, 'cloth' if up == 'long' else 'skin',
           top_line=False, bottom_line=False)
    if up == 'short':
        # rounded sleeve that grows out of the shoulder and flares a little
        cut = y0 - p.upper_len * 0.38
        sleeve = [(x - r * 1.35, y0 + 0.07 * hh), (x, y0 + 0.11 * hh), (x + r * 1.35, y0 + 0.07 * hh),
                  (x + r * 2.05, cut + 0.02 * hh), (x, cut - 0.015 * hh), (x - r * 2.05, cut + 0.02 * hh)]
        sc.add(sleeve, tc, 'cloth', shade=(-0.04, 0.0), tension=0.42)
        sc.detail([(x - r * 1.85, cut + 0.05 * hh), (x, cut + 0.02 * hh), (x + r * 1.85, cut + 0.05 * hh)],
                  pal.cel_shadow(tc), 0.45)
    sc.finish()


def stick_fore(k: Kit, cv: Canvas, side: int, hand: str) -> None:
    d, p, c = k.d, k.p, k.col
    hh = p.hh
    x = side * p.arm_x
    y0 = p.shoulder_y - p.upper_len
    y1 = y0 - p.fore_len
    r = p.fore_w / 2
    _, cover = _sleeves(d)
    tc = c['top']
    sc = Sculpt(k, cv)
    draw_hand(k, sc, x, y1 + 0.01 * hh, -side, hand, r * 1.05)
    color = tc if cover == 'long' else k.skin
    _stick(sc, k, x, y0, y1 + 0.03 * hh, r, color, 'cloth' if cover == 'long' else 'skin', bottom_line=False)
    if cover == 'long':
        sc.add([(x - r * 1.25, y1 + 0.13 * hh), (x + r * 1.25, y1 + 0.13 * hh), (x + r * 1.3, y1 + 0.02 * hh),
                (x - r * 1.3, y1 + 0.02 * hh)], pal.cel_shadow(tc) if d.top == 'hoodie' else tc, 'cloth',
               shade=None, smooth=False)
    elif cover == 'three_quarter':
        cut = y0 - p.fore_len * 0.45
        sc.add([(x - r * 1.5, y0 + 0.02 * hh), (x + r * 1.5, y0 + 0.02 * hh), (x + r * 2.0, cut),
                (x - r * 2.0, cut)], tc, 'cloth', shade=(-0.04, 0.0), smooth=False)
        sc.detail([(x - r * 1.9, cut + 0.03 * hh), (x + r * 1.9, cut + 0.03 * hh)], c['accent'], 0.7, smooth=False)
    sc.finish()


# --------------------------------------------------------------------------
# Ground shadow
# --------------------------------------------------------------------------


def shadow_bounds(p) -> tuple[float, float, float, float]:
    return (-1.4 * p.hh, -0.3 * p.hh, 1.4 * p.hh, 0.3 * p.hh)


def draw_shadow(k: Kit, cv: Canvas) -> None:
    p = k.p
    w = max(p.shoulder_x, p.hip_x) * 1.25 + 0.25 * p.hh
    x, y = k.P(0.0, 0.0)
    cv.fill(VPath().ellipse(x, y, w * k.dpi, w * 0.16 * k.dpi), '#3A2C4A55')
