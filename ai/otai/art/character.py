"""Parametric character generator producing a cutout-animation rig.

Every part is an image-sequence level (PNG frames) plus rig data telling the
scene compiler where the part sits and where it pivots, so a character maps to
OpenToonz columns parented the way cutout animators build them:

    Peg (root, feet) -> body -> head -> {hair_back, blush, eyes, mouth, acc,
                                         hair_front, brows, fx}
                             -> upper_l -> fore_l
                             -> upper_r -> fore_r

Head-attached parts share one canvas so they stay pixel aligned. Each head
part has drawings for two views: front and three-quarter (facing +x; the
other side is obtained by mirroring the root pegbar).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from . import palette as pal
from .vec import Canvas, Path as VPath, bezier_points, taper_stroke

HEAD_DPI = 480
BODY_DPI = 240

# Drawing vocabularies. Eye expressions with pupils exist once per look
# direction (c centre, l/r left/right in rig space, u up, d down).
EYE_LOOK_EXPRS = ['open', 'half', 'wide', 'angry', 'sad', 'sharp']
EYE_STATIC_EXPRS = ['closed', 'happy', 'squeeze', 'blank', 'heart', 'blink']
EYE_LOOKS = ['c', 'l', 'r', 'u', 'd']
EYE_DRAWINGS = ['%s_%s' % (e, l) for e in EYE_LOOK_EXPRS for l in EYE_LOOKS] + EYE_STATIC_EXPRS
BROW_DRAWINGS = ['neutral', 'raised', 'angry', 'sad', 'flat', 'skeptic']
MOUTH_DRAWINGS = ['rest', 'M', 'smile', 'grin', 'frown', 'flat', 'A', 'I', 'U',
                  'E', 'O', 'shout', 'wavy', 'cat', 'smirk', 'clench', 'buck']
FX_DRAWINGS = ['sweat', 'vein', 'question', 'exclaim', 'sparkle', 'heart',
               'gloom', 'tears', 'steam', 'notes', 'zzz', 'idea', 'dots']
BLUSH_DRAWINGS = ['soft', 'lines']
HAND_DRAWINGS = ['open', 'fist', 'point', 'palm']
VIEWS = ['front', 'three_quarter']
VIEW_TURN = {'front': 0.0, 'three_quarter': 0.55}


def eye_name(expr: str, look: str = 'c') -> str:
    return '%s_%s' % (expr, look) if expr in EYE_LOOK_EXPRS else expr


@dataclass
class CharacterDesign:
    name: str
    style: str = 'anime'            # 'anime' | 'cartoon' (web cartoon)
    gender: str = 'female'          # 'female' | 'male'
    age: str = 'teen'               # 'child' | 'teen' | 'adult' | 'elder'
    skin_tone: str = 'light'
    hair_style: str = 'long'        # short spiky long ponytail bob twintails bun buzz bald curly messy undercut
    hair_color: str = 'black'
    eye_color: str = 'brown'
    top: str = 'tshirt'             # tshirt shirt hoodie school_uniform dress kurta suit sweater
    top_color: str = 'blue'
    bottom: str = 'pants'           # pants jeans skirt shorts
    bottom_color: str = 'navy'
    shoe_color: str = 'white'
    accent_color: str = 'red'
    accessories: list[str] = field(default_factory=list)
    height: float = 1.0
    build: str = 'average'          # slim | average | broad

    def resolved(self) -> dict:
        return {
            'skin': pal.resolve(self.skin_tone, pal.SKIN, pal.SKIN['light']),
            'hair': pal.resolve(self.hair_color, pal.HAIR, pal.HAIR['black']),
            'eye': pal.resolve(self.eye_color, pal.EYES, pal.EYES['brown']),
            'top': pal.resolve(self.top_color, pal.CLOTH, pal.CLOTH['blue']),
            'bottom': pal.resolve(self.bottom_color, pal.CLOTH, pal.CLOTH['navy']),
            'shoe': pal.resolve(self.shoe_color, pal.CLOTH, pal.CLOTH['white']),
            'accent': pal.resolve(self.accent_color, pal.CLOTH, pal.CLOTH['red']),
        }


# --------------------------------------------------------------------------
# Proportions (inches; root at the feet, y up)
# --------------------------------------------------------------------------


@dataclass
class Proportions:
    H: float
    hh: float
    u: float
    chin: float
    face_cy: float
    shoulder_y: float
    chest_y: float
    waist_y: float
    crotch_y: float
    knee_y: float
    ankle_y: float
    shoulder_x: float
    chest_x: float
    waist_x: float
    hip_x: float
    neck_w: float
    arm_x: float      # shoulder joint
    hip_jx: float     # hip joint
    hip_jy: float
    upper_w: float
    fore_w: float
    thigh_w: float
    shin_w: float
    upper_len: float
    fore_len: float
    hand_len: float
    shoe_len: float
    shoe_h: float
    lw: float         # outline width (inches)


def proportions(d: CharacterDesign) -> Proportions:
    toon = d.style == 'cartoon'
    male = d.gender == 'male'
    child = d.age == 'child'
    build = {'slim': 0.9, 'average': 1.0, 'broad': 1.15}[d.build]
    if toon:
        # web cartoon: big heads, short torso, noodle limbs
        heads = {'child': 2.7, 'teen': 3.1, 'adult': 3.4, 'elder': 3.3}[d.age]
        total = {'child': 3.9, 'teen': 5.1, 'adult': 5.5, 'elder': 5.3}[d.age]
    else:
        heads = {'child': 4.4, 'teen': 6.0, 'adult': 6.7, 'elder': 6.4}[d.age]
        total = {'child': 4.3, 'teen': 6.1, 'adult': 6.5, 'elder': 6.2}[d.age]
    if male and not child:
        total += 0.35 if not toon else 0.3
    H = total * d.height
    hh = H / heads
    u = hh / 1.24
    chin = H - hh
    body = chin
    if toon:
        f = {'shoulder': 0.07, 'chest': 0.22, 'waist': 0.38, 'crotch': 0.50, 'knee': 0.76}
        sx = (0.40 if child else (0.50 if male else 0.43)) * build
        wx = (0.40 if male else 0.33) * build
        hx = (0.40 if male else 0.40) * build
        limb = min(hh, H / 3.0)
        dims = dict(upper_w=0.15 * limb, fore_w=0.13 * limb, thigh_w=0.23 * limb, shin_w=0.19 * limb,
                    hand_len=0.26 * limb, shoe_len=0.50 * limb, shoe_h=0.20 * limb, neck_w=0.11 * limb)
        lw = 0.030 * u
    else:
        f = {'shoulder': 0.05, 'chest': 0.20, 'waist': 0.34, 'crotch': 0.44, 'knee': 0.71}
        sx = (0.55 if child else (0.78 if male else 0.62)) * build
        wx = (0.46 if male else 0.36) * build
        hx = (0.47 if male else 0.52) * build
        limb = min(hh, H / 6.0)
        dims = dict(upper_w=(0.25 if male else 0.21) * limb, fore_w=(0.20 if male else 0.17) * limb,
                    thigh_w=(0.34 if male else 0.32) * limb, shin_w=0.24 * limb,
                    hand_len=min(0.36 * hh, 0.065 * H), shoe_len=0.45 * limb, shoe_h=0.18 * limb,
                    neck_w=(0.17 if male else 0.13) * hh)
        lw = 0.018 * u
    shoulder_y = chin - f['shoulder'] * body - (0.04 if toon else 0.07) * hh
    crotch_y = chin - f['crotch'] * body
    knee_y = chin - f['knee'] * body
    arm_x = sx * hh - dims['upper_w'] * 0.45
    return Proportions(
        H=H, hh=hh, u=u, chin=chin, face_cy=chin + 0.62 * u,
        shoulder_y=shoulder_y, chest_y=chin - f['chest'] * body, waist_y=chin - f['waist'] * body,
        crotch_y=crotch_y, knee_y=knee_y, ankle_y=0.05 * hh,
        shoulder_x=sx * hh, chest_x=sx * hh * 0.92, waist_x=wx * hh, hip_x=hx * hh,
        arm_x=arm_x, hip_jx=hx * hh * 0.48, hip_jy=crotch_y + 0.06 * hh,
        upper_len=(shoulder_y - (chin - f['waist'] * body)) * (0.62 if toon else 0.95) + 0.02 * hh,
        fore_len=((shoulder_y - (chin - f['waist'] * body)) * 0.48 + 0.02 * hh) if toon
        else (crotch_y - knee_y) * 0.78 + 0.1 * hh,
        lw=lw, **dims)


# --------------------------------------------------------------------------
# Head painter (face units: x right, y down, face centre at 0,0, width 1)
# --------------------------------------------------------------------------

HEAD_X0, HEAD_X1, HEAD_Y0, HEAD_Y1 = -1.5, 1.5, -1.6, 2.3


class HeadPainter:
    def __init__(self, d: CharacterDesign, p: Proportions, view: str) -> None:
        self.d, self.p, self.view = d, p, view
        self.t = VIEW_TURN[view]
        self.U = p.u * HEAD_DPI  # px per face unit
        self.W = int(round((HEAD_X1 - HEAD_X0) * self.U))
        self.Hpx = int(round((HEAD_Y1 - HEAD_Y0) * self.U))
        self.col = d.resolved()
        self.cartoon = d.style == 'cartoon'
        self.male = d.gender == 'male'
        self.lw = p.lw * HEAD_DPI
        self.skin = self.col['skin']
        self.skin_sh = pal.shade(self.skin)
        self.skin_line = pal.mix(pal.line_color(self.skin), '#2B1B1B', 0.4)
        self.hair = self.col['hair']
        self.hair_sh = pal.shade(self.hair, (0.72, 0.68, 0.86))
        self.hair_hi = pal.lighten(self.hair, 0.35)
        self.hair_line = pal.line_color(self.hair) if not self.cartoon else '#1E1A22'
        if self.cartoon:
            self.skin_line = '#2A2024'

    # coordinate helpers --------------------------------------------------
    def P(self, x: float, y: float) -> tuple[float, float]:
        return ((x - HEAD_X0) * self.U, (y - HEAD_Y0) * self.U)

    def warp(self, x: float, y: float = 0.0) -> float:
        """Horizontal shift of head features for the three-quarter view."""
        t = self.t
        if t == 0:
            return x
        k = max(0.0, 1 - (x / 0.78) ** 2)
        return x * (1 - 0.12 * t) + t * 0.22 * k

    def W2(self, x: float, y: float) -> tuple[float, float]:
        return self.P(self.warp(x, y), y)

    def path(self, pts, closed=True, smooth=True, warp=True) -> VPath:
        conv = [(self.W2(x, y) if warp else self.P(x, y)) for x, y in pts]
        if smooth:
            return VPath().smooth(conv, closed=closed)
        return VPath().poly(conv, closed=closed)

    def canvas(self, x0=HEAD_X0, y0=HEAD_Y0, x1=HEAD_X1, y1=HEAD_Y1, ss=2) -> Canvas:
        px0, py0 = self.P(x0, y0)
        px1, py1 = self.P(x1, y1)
        px0, py0 = max(0, int(px0)), max(0, int(py0))
        px1, py1 = min(self.W, int(math.ceil(px1))), min(self.Hpx, int(math.ceil(py1)))
        return Canvas(px1 - px0, py1 - py0, ss=ss, origin=(px0, py0))

    def blank(self) -> Image.Image:
        return Image.new('RGBA', (self.W, self.Hpx), (0, 0, 0, 0))

    # geometry ----------------------------------------------------------
    def face_outline(self) -> list[tuple[float, float]]:
        t = self.t
        child = self.d.age == 'child'
        if self.cartoon:
            cheek, jaw, chin = (0.52, 0.28), (0.40, 0.55), (0.0, 0.66)
        elif self.male:
            cheek, jaw, chin = (0.48, 0.25), (0.36, 0.50), (0.0, 0.63)
        elif child:
            cheek, jaw, chin = (0.50, 0.30), (0.36, 0.53), (0.0, 0.62)
        else:
            cheek, jaw, chin = (0.47, 0.27), (0.29, 0.52), (0.0, 0.64)
        if t == 0:
            right = [(0.50, -0.35), (0.50, 0.02), cheek, jaw]
            pts = [(0.0, -0.68), (0.36, -0.60)] + right + [chin]
            pts += [(-x, y) for x, y in reversed(right)] + [(-0.36, -0.60)]
            return [(x, y) for x, y in pts]
        # three-quarter: far side (+x) narrow, chin moved towards facing side
        far = [(0.46, -0.35), (0.45, 0.0), (0.43, 0.16), (cheek[0] * 0.78, cheek[1] + 0.06),
               (jaw[0] * 0.7 + 0.08, jaw[1] + 0.03)]
        chin_pt = (0.20 * t + chin[0], chin[1] - 0.01)
        near = [(-0.52, -0.35), (-0.52, 0.02), (-cheek[0] - 0.02, cheek[1]),
                (-jaw[0] - 0.04, jaw[1])]
        pts = [(0.02, -0.68), (0.36, -0.60)] + far + [chin_pt] + list(reversed(near)) + [(-0.38, -0.60)]
        return pts  # already in view space

    def eye_geom(self, side: int) -> tuple[float, float, float, float, float]:
        """(cx, cy, w, h, scale) for the eye on screen side -1 or +1."""
        if self.cartoon:
            w, h, ex, ey = 0.13, 0.20, 0.20, 0.10
        else:
            w = 0.27 if not self.male else 0.25
            h = 0.30 if not self.male else 0.22
            ex, ey = 0.215, 0.12
            if self.d.age == 'child':
                h *= 1.08
        cx = self.warp(side * ex)
        sc = 1.0
        if self.t:
            sc = 0.82 if side > 0 else 1.0  # far eye foreshortened
        return cx, ey, w * sc, h, sc


def _eye_shape(hp: HeadPainter, side: int, top_in: float, top_peak: float,
               top_out: float, bottom: float = 0.45, look: float = 0.0):
    cx, cy, w, h, _ = hp.eye_geom(side)
    inner = cx - side * w / 2
    outer = cx + side * w / 2
    up = [(inner, cy + top_in * h), (cx - side * 0.05 * w, cy + top_peak * h),
          (outer, cy + top_out * h)]
    low = [(outer - side * 0.08 * w, cy + 0.2 * h), (cx, cy + bottom * h),
           (inner + side * 0.06 * w, cy + 0.25 * h)]
    return up, low


ANIME_LOOK = {'c': (0.0, 0.0), 'l': (-0.22, 0.0), 'r': (0.22, 0.0), 'u': (0.0, -0.14), 'd': (0.0, 0.12)}


def draw_eye(hp: HeadPainter, cv: Canvas, side: int, variant: str, look: str = 'c') -> None:
    """Anime eye. ``variant`` is an expression from EYE_LOOK_EXPRS or
    EYE_STATIC_EXPRS; ``look`` a key of ANIME_LOOK."""
    cx, cy, w, h, sc = hp.eye_geom(side)
    lash = '#2A1E24' if not hp.cartoon else '#1A1418'
    lw = hp.lw
    U = hp.U
    iris_c = hp.col['eye']
    if hp.cartoon:
        _draw_dot_eye(hp, cv, side, variant)
        return

    def lid_line(pts, width_mul=1.0, flick=True):
        conv = [hp.P(x, y) for x, y in pts]
        smooth = bezier_points(conv[0], conv[1], conv[1], conv[2], 20)
        if flick and not hp.male:
            ox, oy = smooth[-1]
            smooth.append((ox + side * 0.035 * U, oy - 0.012 * U))
        cv.fill(taper_stroke(smooth, lw * 0.6, lw * 0.9, lw * 2.4 * width_mul), lash)

    if variant in ('closed', 'happy', 'squeeze'):
        if variant == 'closed':
            pts = [(cx - side * w / 2, cy + 0.10 * h), (cx, cy + 0.32 * h), (cx + side * w / 2, cy + 0.06 * h)]
        elif variant == 'happy':
            pts = [(cx - side * w / 2, cy + 0.20 * h), (cx, cy - 0.22 * h), (cx + side * w / 2, cy + 0.20 * h)]
        else:  # squeeze  > <
            a = (cx - side * w * 0.45, cy - 0.25 * h)
            b = (cx + side * w * 0.35, cy + 0.08 * h)
            c = (cx - side * w * 0.45, cy + 0.38 * h)
            cv.fill(taper_stroke([hp.P(*a), hp.P(*b)], lw * 1.6, lw * 1.8), lash)
            cv.fill(taper_stroke([hp.P(*b), hp.P(*c)], lw * 1.8, lw * 1.6), lash)
            return
        lid_line(pts, 0.85, flick=(variant == 'closed'))
        return

    if variant == 'blank':
        up, low = _eye_shape(hp, side, -0.25, -0.62, -0.30, 0.55)
        shape = VPath().smooth([hp.P(*q) for q in up + low], closed=True)
        cv.fill_stroke(shape, '#FFFFFF', lash, lw * 1.2)
        return

    lids = {
        'open': (-0.18, -0.52, -0.30), 'half': (-0.02, -0.08, -0.06),
        'angry': (-0.02, -0.30, -0.48), 'sad': (-0.46, -0.40, -0.12),
        'wide': (-0.30, -0.66, -0.40), 'heart': (-0.18, -0.52, -0.30),
        'annoyed': (0.02, 0.0, 0.0), 'sharp': (-0.08, -0.30, -0.36),
        'look_side': (-0.18, -0.52, -0.30), 'blink': (0.10, 0.16, 0.12),
    }
    top_in, top_peak, top_out = lids.get(variant, lids['open'])
    up, low = _eye_shape(hp, side, top_in, top_peak, top_out,
                         0.55 if variant == 'wide' else 0.45)
    sclera_pts = [hp.P(*q) for q in up] + [hp.P(*q) for q in low]
    sclera = VPath().smooth(sclera_pts, closed=True, tension=0.6)
    clip = cv.mask(sclera)
    cv.fill(sclera, '#FFFFFF')
    # iris
    look_dx, look_dy = ANIME_LOOK.get(look, (0.0, 0.0))
    look_dx += hp.t * 0.12
    ir_x = cx + look_dx * w
    ir_y = cy + 0.04 * h + look_dy * h
    rx, ry = 0.36 * w, 0.47 * h
    if variant == 'wide':
        rx, ry = rx * 0.62, ry * 0.62
    if variant in ('angry', 'sharp'):
        rx, ry = rx * 0.85, ry * 0.85
    iris_canvas = Canvas(cv.w, cv.h, cv.ss, (cv.ox, cv.oy))
    if variant == 'heart':
        hx, hy = hp.P(ir_x, ir_y)
        iris_canvas.fill(_heart_path(hx, hy, rx * U * 1.1), '#F05A8C')
        iris_canvas.fill(_heart_path(hx - rx * U * 0.25, hy - ry * U * 0.25, rx * U * 0.3), '#FFC2D6')
    else:
        ipath = VPath().ellipse(*hp.P(ir_x, ir_y), rx * U, ry * U)
        iris_canvas.gradient(ipath, pal.darken(iris_c, 0.45), pal.lighten(iris_c, 0.25))
        iris_canvas.stroke(ipath, pal.darken(iris_c, 0.6), lw * 0.6)
        iris_canvas.fill(VPath().ellipse(*hp.P(ir_x, ir_y + 0.02 * h), rx * U * 0.42, ry * U * 0.45),
                         pal.darken(iris_c, 0.7))
        # highlights
        hl = 0.55 if variant != 'sad' else 0.8
        iris_canvas.fill(VPath().ellipse(*hp.P(ir_x - side * 0.10 * w - 0.06 * w, ir_y - 0.16 * h),
                                         rx * U * 0.38 * hl * 1.4, ry * U * 0.30 * hl * 1.4), '#FFFFFF')
        iris_canvas.fill(VPath().ellipse(*hp.P(ir_x + 0.12 * w, ir_y + 0.20 * h),
                                         rx * U * 0.16, ry * U * 0.12), '#FFFFFFDD')
        if variant == 'sad':
            iris_canvas.fill(VPath().ellipse(*hp.P(ir_x, ir_y + 0.32 * h), rx * U * 0.7, ry * U * 0.12),
                             '#FFFFFFAA')
    # lid shadow on the sclera
    shadow = VPath().smooth([hp.P(*q) for q in up] +
                            [hp.P(up[2][0], up[2][1] + 0.18 * h), hp.P(up[1][0], up[1][1] + 0.22 * h),
                             hp.P(up[0][0], up[0][1] + 0.16 * h)], closed=True)
    iris_canvas.fill(shadow, pal.with_alpha('#5A4A7A', 70))
    from PIL import ImageChops
    iris_img = iris_canvas.img
    iris_img.putalpha(ImageChops.multiply(iris_img.getchannel('A'), clip))
    cv.img.alpha_composite(iris_img)
    # lashes
    lid_line(up, 1.0)
    # lower lash, outer half
    lo = [hp.P(*low[0]), hp.P(low[0][0] - side * 0.25 * w, low[0][1] + 0.18 * h)]
    cv.fill(taper_stroke(lo, lw * 0.9, lw * 0.3), lash)
    if variant in ('open', 'wide', 'sad', 'heart', 'look_side') and not hp.male:
        crease = [hp.P(cx - side * 0.25 * w, cy + (top_peak - 0.20) * h),
                  hp.P(cx + side * 0.25 * w, cy + (top_peak - 0.18) * h)]
        cv.fill(taper_stroke(crease, lw * 0.2, lw * 0.2, lw * 0.6), pal.with_alpha(hp.skin_line, 150))


def _draw_dot_eye(hp: HeadPainter, cv: Canvas, side: int, variant: str) -> None:
    cx, cy, w, h, sc = hp.eye_geom(side)
    U, lw = hp.U, hp.lw
    ink = '#1A1418'
    x, y = hp.P(cx + hp.t * 0.04, cy)
    if variant in ('closed', 'half', 'annoyed'):
        yy = cy + (0.1 if variant == 'closed' else -0.05) * h
        pts = [hp.P(cx - w * 0.6, yy), hp.P(cx, yy + (0.15 if variant == 'closed' else 0) * h),
               hp.P(cx + w * 0.6, yy)]
        cv.fill(taper_stroke(bezier_points(pts[0], pts[1], pts[1], pts[2], 12), lw * 0.8, lw * 0.8, lw * 1.3), ink)
        if variant == 'half':
            cv.fill(VPath().ellipse(x, y + 0.18 * h * U, w * 0.4 * U * sc, h * 0.25 * U), ink)
        return
    if variant in ('happy', 'squeeze'):
        pts = [hp.P(cx - w * 0.6, cy + 0.2 * h), hp.P(cx, cy - 0.3 * h), hp.P(cx + w * 0.6, cy + 0.2 * h)]
        if variant == 'squeeze':
            pts = [hp.P(cx - side * w * 0.6, cy - 0.3 * h), hp.P(cx + side * w * 0.5, cy), hp.P(cx - side * w * 0.6, cy + 0.3 * h)]
            cv.fill(taper_stroke(pts, lw * 1.2, lw * 1.2), ink)
            return
        cv.fill(taper_stroke(bezier_points(pts[0], pts[1], pts[1], pts[2], 14), lw * 1.1, lw * 1.1), ink)
        return
    if variant in ('wide', 'blank'):
        cv.fill_stroke(VPath().ellipse(x, y, w * 0.85 * U * sc, h * 0.75 * U), '#FFFFFF', ink, lw)
        if variant == 'wide':
            cv.fill(VPath().ellipse(x, y, w * 0.18 * U, h * 0.16 * U), ink)
        return
    if variant == 'heart':
        cv.fill(_heart_path(x, y, w * 0.9 * U), '#E8457A')
        return
    rx, ry = w * 0.5 * U * sc, h * 0.5 * U
    cv.fill(VPath().ellipse(x, y, rx, ry), ink)
    cv.fill(VPath().ellipse(x - rx * 0.3, y - ry * 0.35, rx * 0.32, ry * 0.25), '#FFFFFF')
    if variant in ('angry', 'sharp'):
        lid = [hp.P(cx - side * w * 0.9, cy - 0.15 * h), hp.P(cx + side * w * 0.9, cy - 0.65 * h),
               hp.P(cx + side * w * 0.9, cy - 1.0 * h), hp.P(cx - side * w * 0.9, cy - 1.0 * h)]
        cv.fill(VPath().poly(lid), hp.skin)
        cv.fill(taper_stroke(lid[:2], lw * 1.2, lw * 1.2), ink)
    if variant == 'sad':
        lid = [hp.P(cx - side * w * 0.9, cy - 0.65 * h), hp.P(cx + side * w * 0.9, cy - 0.2 * h),
               hp.P(cx + side * w * 0.9, cy - 1.0 * h), hp.P(cx - side * w * 0.9, cy - 1.0 * h)]
        cv.fill(VPath().poly(lid), hp.skin)


def _heart_path(cx: float, cy: float, s: float) -> VPath:
    p = VPath().move(cx, cy + s * 0.55)
    p.cubic((cx - s * 0.9, cy - s * 0.05), (cx - s * 0.45, cy - s * 0.75), (cx, cy - s * 0.25))
    p.cubic((cx + s * 0.45, cy - s * 0.75), (cx + s * 0.9, cy - s * 0.05), (cx, cy + s * 0.55))
    return p.close()


def draw_brows(hp: HeadPainter, cv: Canvas, variant: str) -> None:
    color = pal.darken(hp.hair, 0.35) if not hp.cartoon else '#1E1A22'
    width = hp.lw * (2.6 if hp.cartoon else (1.9 if hp.male else 1.3))
    for side in (-1, 1):
        cx, cy, w, h, sc = hp.eye_geom(side)
        by = cy - (0.62 if not hp.cartoon else 0.95) * h - 0.035
        inner_dy, outer_dy, arch = {
            'neutral': (0.0, 0.01, 0.03), 'raised': (-0.07, -0.05, 0.05),
            'angry': (0.06, -0.05, 0.0), 'sad': (-0.06, 0.04, 0.02),
            'flat': (0.03, 0.03, 0.0),
        }.get(variant, (0.0, 0.0, 0.03))
        if variant == 'skeptic':
            inner_dy, outer_dy, arch = ((-0.08, -0.07, 0.05) if side > 0 else (0.03, 0.04, 0.0))
        inner = (cx - side * w * 0.55, by + inner_dy)
        outer = (cx + side * w * 0.65 * sc, by + outer_dy + 0.02)
        mid = ((inner[0] + outer[0]) / 2, min(inner[1], outer[1]) - arch)
        pts = bezier_points(hp.P(*inner), hp.P(*mid), hp.P(*mid), hp.P(*outer), 16)
        cv.fill(taper_stroke(pts, width * 1.0, width * 0.35, width), color)


def draw_mouth(hp: HeadPainter, cv: Canvas, variant: str) -> None:
    mx = hp.warp(0.0) + hp.t * 0.02
    my = 0.43 if not hp.cartoon else 0.40
    mw = (0.15 if not hp.male else 0.17) * (1.3 if hp.cartoon else 1.0) * (1 - 0.15 * hp.t)
    U, lw = hp.U, hp.lw
    line = '#5A2A2A' if not hp.cartoon else '#2A1A1A'
    inside, tongue, teeth = '#7A2433', '#E06A78', '#FFFFFF'

    def P(dx, dy):
        return hp.P(mx + dx * mw, my + dy * mw)

    def curve(a, c, b, wmul=1.0):
        pts = bezier_points(P(*a), P(*c), P(*c), P(*b), 16)
        cv.fill(taper_stroke(pts, lw * 0.5 * wmul, lw * 0.5 * wmul, lw * 1.1 * wmul), line)

    def open_mouth(pts, teeth_top=0.0, tongue_on=True):
        shape = VPath().smooth([P(*q) for q in pts], closed=True, tension=0.55)
        m = cv.mask(shape)
        cv.fill(shape, inside)
        bx0, by0, bx1, by1 = shape.bbox()
        sub = Canvas(cv.w, cv.h, cv.ss, (cv.ox, cv.oy))
        if tongue_on:
            sub.fill(VPath().ellipse((bx0 + bx1) / 2 + (bx1 - bx0) * 0.12, by1, (bx1 - bx0) * 0.38,
                                     (by1 - by0) * 0.45), tongue)
        if teeth_top > 0:
            sub.fill(VPath().rect(bx0, by0, bx1, by0 + (by1 - by0) * teeth_top), teeth)
        from PIL import ImageChops
        sub.img.putalpha(ImageChops.multiply(sub.img.getchannel('A'), m))
        cv.img.alpha_composite(sub.img)
        cv.stroke(shape, line, lw * 0.9)

    v = variant
    if v == 'rest':
        curve((-0.38, 0.02), (0, 0.10), (0.38, 0.0))
    elif v == 'smile':
        curve((-0.55, -0.08), (0, 0.32), (0.55, -0.08), 1.1)
    elif v == 'frown':
        curve((-0.45, 0.12), (0, -0.12), (0.45, 0.12))
    elif v == 'flat':
        curve((-0.42, 0.04), (0, 0.04), (0.42, 0.04))
    elif v == 'smirk':
        curve((-0.40, 0.08), (0.05, 0.12), (0.50, -0.10))
    elif v == 'wavy':
        pts = [P(-0.5 + i * 0.125, 0.05 + (0.06 if i % 2 else -0.06)) for i in range(9)]
        cv.fill(taper_stroke(pts, lw * 0.6, lw * 0.6, lw * 0.9), line)
    elif v == 'cat':
        pts = [P(-0.55, -0.02), P(-0.28, 0.20), P(0.0, 0.0), P(0.28, 0.20), P(0.55, -0.02)]
        cv.fill(taper_stroke(VPath().smooth(pts).subpaths[0], lw * 0.7, lw * 0.7, lw * 1.0), line)
    elif v == 'grin':
        open_mouth([(-0.6, -0.05), (0, -0.02), (0.6, -0.05), (0.35, 0.40), (0, 0.52), (-0.35, 0.40)], teeth_top=0.28)
    elif v == 'A':
        open_mouth([(-0.35, -0.05), (0, -0.10), (0.35, -0.05), (0.30, 0.45), (0, 0.65), (-0.30, 0.45)])
    elif v == 'I':
        open_mouth([(-0.5, 0.0), (0, -0.04), (0.5, 0.0), (0.3, 0.18), (0, 0.22), (-0.3, 0.18)], teeth_top=0.45, tongue_on=False)
    elif v == 'U':
        open_mouth([(-0.16, 0.05), (0, -0.04), (0.16, 0.05), (0.14, 0.22), (0, 0.28), (-0.14, 0.22)], tongue_on=False)
    elif v == 'E':
        open_mouth([(-0.42, -0.02), (0, -0.06), (0.42, -0.02), (0.30, 0.28), (0, 0.34), (-0.30, 0.28)], teeth_top=0.25)
    elif v == 'O':
        open_mouth([(-0.25, 0.05), (0, -0.12), (0.25, 0.05), (0.22, 0.38), (0, 0.50), (-0.22, 0.38)])
    elif v == 'shout':
        open_mouth([(-0.55, -0.12), (0, -0.16), (0.55, -0.12), (0.45, 0.55), (0, 0.80), (-0.45, 0.55)], teeth_top=0.15)
    elif v == 'M':
        curve((-0.32, 0.04), (0, 0.06), (0.32, 0.04), 1.3)
    elif v == 'buck':
        open_mouth([(-0.3, 0.0), (0, -0.03), (0.3, 0.0), (0.25, 0.25), (0, 0.32), (-0.25, 0.25)], teeth_top=0.45)
    elif v == 'clench':
        shape = VPath().rect(*P(-0.45, -0.06), *P(0.45, 0.24), r=0.05 * mw * U)
        cv.fill(shape, teeth)
        for i in range(1, 5):
            x = -0.45 + i * 0.18
            cv.stroke(VPath().poly([P(x, -0.06), P(x, 0.24)], closed=False), '#B9A8A8', lw * 0.4)
        cv.stroke(VPath().poly([P(-0.45, 0.09), P(0.45, 0.09)], closed=False), '#B9A8A8', lw * 0.4)
        cv.stroke(shape, line, lw * 0.9)


def draw_fx(hp: HeadPainter, cv: Canvas, variant: str) -> None:
    U, lw = hp.U, hp.lw
    ink = '#2A2030'

    def P(x, y):
        return hp.P(x, y)

    if variant == 'sweat':
        x, y = P(0.62, -0.45)
        s = 0.16 * U
        drop = VPath().move(x, y - s)
        drop.cubic((x + s * 0.2, y - s * 0.3), (x + s * 0.6, y + s * 0.2), (x, y + s * 0.6))
        drop.cubic((x - s * 0.6, y + s * 0.2), (x - s * 0.2, y - s * 0.3), (x, y - s)).close()
        cv.fill_stroke(drop, '#9FD8F5', '#3A7FB5', lw * 0.8)
        cv.fill(VPath().ellipse(x - s * 0.15, y + s * 0.15, s * 0.12, s * 0.2), '#FFFFFF')
    elif variant == 'vein':
        cx, cy = P(-0.38, -0.62)
        s = 0.13 * U
        for ang in (0, 90, 180, 270):
            a = math.radians(ang + 45)
            p0 = (cx + math.cos(a) * s * 0.25, cy + math.sin(a) * s * 0.25)
            p1 = (cx + math.cos(a) * s, cy + math.sin(a) * s)
            c = (cx + math.cos(a + 0.6) * s * 0.8, cy + math.sin(a + 0.6) * s * 0.8)
            pts = bezier_points(p0, c, c, p1, 10)
            cv.fill(taper_stroke(pts, lw * 1.6, lw * 0.8, lw * 2.2), '#E0303A')
    elif variant in ('question', 'exclaim'):
        x, y = P(0.55, -1.15)
        s = 0.42 * U
        _text_glyph(cv, '?' if variant == 'question' else '!', x, y, s,
                    '#FFD23F' if variant == 'exclaim' else '#7FC8F8', ink, lw * 1.2)
    elif variant == 'sparkle':
        for (fx, fy, fs) in ((-0.75, -0.75, 0.16), (0.78, -0.55, 0.12), (0.62, -1.05, 0.09), (-0.55, -1.15, 0.08)):
            _star(cv, *P(fx, fy), fs * U, '#FFE36E', '#E0A800', lw * 0.6)
    elif variant == 'heart':
        for (fx, fy, fs) in ((0.6, -0.95, 0.20), (0.85, -0.65, 0.12), (-0.7, -0.9, 0.14)):
            cv.fill_stroke(_heart_path(*P(fx, fy), fs * U), '#FF6F9C', '#B02A5A', lw * 0.7)
    elif variant == 'gloom':
        for i in range(7):
            x = -0.40 + i * 0.13
            cv.stroke(VPath().poly([P(x, -0.62), P(x, -0.12 - 0.06 * (i % 2))], closed=False),
                      '#5B4C9A88', lw * 1.3)
    elif variant == 'tears':
        for side in (-1, 1):
            cx, cy, w, h, _ = hp.eye_geom(side)
            x0 = cx + side * 0.05 * w
            stream = VPath().smooth([P(x0 - 0.02, cy + 0.3 * h), P(x0 + 0.02 * side, cy + 0.55),
                                     P(x0 - 0.01, cy + 0.85), P(x0 + 0.01, cy + 1.05),
                                     P(x0 + 0.09, cy + 1.05), P(x0 + 0.08, cy + 0.80),
                                     P(x0 + 0.08 + 0.02 * side, cy + 0.50), P(x0 + 0.06, cy + 0.3 * h)], closed=True)
            cv.fill_stroke(stream, '#AEE3FA', '#4A9BCF', lw * 0.6)
    elif variant == 'steam':
        for (fx, fy, fs) in ((-0.55, -1.0, 0.18), (0.55, -1.05, 0.2), (0.0, -1.25, 0.15)):
            x, y = P(fx, fy)
            puff = VPath()
            for k in range(5):
                a = k * 2 * math.pi / 5
                puff.ellipse(x + math.cos(a) * fs * U * 0.6, y + math.sin(a) * fs * U * 0.5,
                             fs * U * 0.55, fs * U * 0.45)
            cv.fill(puff, '#F2F2F2')
            cv.stroke(puff, '#9A9AA8', lw * 0.5)
    elif variant == 'notes':
        for (fx, fy, fs) in ((0.62, -0.9, 0.22), (0.9, -0.55, 0.16)):
            _note(cv, *P(fx, fy), fs * U, '#3A3A5A', lw)
    elif variant == 'zzz':
        for i, (fx, fy, fs) in enumerate(((0.55, -0.85, 0.16), (0.78, -1.1, 0.2), (1.0, -1.38, 0.24))):
            _text_glyph(cv, 'z', *P(fx, fy), fs * U * 1.4, '#9AD0F5', ink, lw * 0.9)
    elif variant == 'idea':
        x, y = P(0.0, -1.25)
        s = 0.22 * U
        bulb = VPath().ellipse(x, y, s, s * 1.05)
        cv.fill_stroke(bulb, '#FFE66B', ink, lw)
        cv.fill_stroke(VPath().rect(x - s * 0.45, y + s * 0.9, x + s * 0.45, y + s * 1.35), '#B0B0B8', ink, lw * 0.8)
        for k in range(7):
            a = math.radians(-160 + k * 23)
            cv.stroke(VPath().poly([(x + math.cos(a) * s * 1.35, y + math.sin(a) * s * 1.35),
                                    (x + math.cos(a) * s * 1.75, y + math.sin(a) * s * 1.75)], closed=False),
                      '#F2B705', lw * 1.1)
    elif variant == 'dots':
        for k in range(3):
            cv.circle(*P(0.35 + k * 0.17, -1.05), 0.05 * U, ink)


def _text_glyph(cv: Canvas, ch: str, x: float, y: float, size: float, fill, outline, width) -> None:
    from PIL import ImageDraw, ImageFont
    from ..config import font_path
    font = ImageFont.truetype(font_path('title'), int(size * cv.ss))
    d = ImageDraw.Draw(cv.img)
    d.text(((x - cv.ox) * cv.ss, (y - cv.oy) * cv.ss), ch, font=font, fill=pal_rgba(fill),
           anchor='mm', stroke_width=int(width * cv.ss), stroke_fill=pal_rgba(outline))


def pal_rgba(c):
    from .vec import rgba
    return rgba(c)


def _star(cv: Canvas, x, y, s, fill, line, width) -> None:
    pts = []
    for k in range(8):
        r = s if k % 2 == 0 else s * 0.32
        a = math.pi / 4 * k - math.pi / 2
        pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
    cv.fill_stroke(VPath().poly(pts), fill, line, width)


def _note(cv: Canvas, x, y, s, ink, lw) -> None:
    cv.fill(VPath().ellipse(x, y, s * 0.32, s * 0.24, rot=-0.4), ink)
    cv.stroke(VPath().poly([(x + s * 0.28, y), (x + s * 0.28, y - s * 1.0)], closed=False), ink, lw)
    cv.fill(VPath().poly([(x + s * 0.28, y - s * 1.0), (x + s * 0.7, y - s * 0.75), (x + s * 0.28, y - s * 0.7)]), ink)


# --------------------------------------------------------------------------
# Hair
# --------------------------------------------------------------------------


def _hair_front_outline(hp: HeadPainter) -> list[tuple[float, float]]:
    d = hp.d
    style = d.hair_style
    female = d.gender == 'female'
    t = hp.t
    if style in ('bald',):
        return []
    if style == 'buzz':
        return [(-0.53, -0.20), (-0.56, -0.55), (0.0, -0.78), (0.56, -0.55), (0.53, -0.20),
                (0.42, -0.40), (0.0, -0.46), (-0.42, -0.40)]
    vol = 0.04
    # smooth dome: elliptical arc over the skull, from the left temple to the right
    outer_l, outer_r = [(-0.56, 0.0)], []
    for k in range(13):
        a = math.pi * (1.0 + k / 12.0)
        x = math.cos(a) * (0.63 + vol)
        y = -0.30 + math.sin(a) * (0.60 + vol)
        (outer_l if k <= 6 else outer_r).append((x, y))
    outer_r.append((0.56, 0.0))
    if style == 'spiky':
        outer_l = [(-0.56, -0.05), (-0.78, -0.30), (-0.62, -0.48), (-0.82, -0.72), (-0.45, -0.75),
                   (-0.52, -1.08), (-0.18, -0.90), (0.0, -1.18)]
        outer_r = [(0.18, -0.92), (0.50, -1.10), (0.46, -0.78), (0.84, -0.74), (0.62, -0.50),
                   (0.80, -0.30), (0.56, -0.05)]
    # side locks
    lock_len = 0.52 if female and style not in ('short',) else (0.18 if style != 'spiky' else 0.10)
    if d.age == 'child' and not female:
        lock_len = 0.12
    right_lock = [(0.56, 0.0), (0.54, lock_len), (0.45, lock_len - 0.18), (0.44, -0.12)]
    left_lock = [(-0.44, -0.12), (-0.45, lock_len - 0.18), (-0.54, lock_len), (-0.56, 0.0)]
    # bangs: zigzag of tips along the hairline
    n = 7 if female else 6
    tips = []
    part = 0.12 if female else -0.05
    for i in range(n + 1):
        x = 0.44 - i * (0.88 / n)
        if i == 0 or i == n:
            y_tip, y_gap = -0.10, -0.25
        else:
            longer = 0.06 if abs(x - part) > 0.15 else -0.06
            y_tip = (-0.02 if female else -0.10) + longer + 0.04 * math.sin(i * 1.7)
            y_gap = -0.30 + 0.05 * math.cos(i * 2.3)
        tips.append((x, y_tip))
        if i < n:
            tips.append((x - 0.44 / n, y_gap))
    if style == 'bob' or (style == 'long' and female):
        pass
    pts = outer_l + outer_r + right_lock + tips + left_lock
    return pts


def draw_hair_front(hp: HeadPainter, cv: Canvas) -> None:
    pts = _hair_front_outline(hp)
    d = hp.d
    if not pts:
        return
    shape = hp.path(pts, closed=True, smooth=False)
    # soften with a smooth pass on the outer contour only: rebuild smooth outer
    hair_mask_shape = shape
    off = (-0.05 * hp.U, -0.06 * hp.U)
    if hp.cartoon:
        cv.fill_stroke(hair_mask_shape, hp.hair, hp.hair_line, hp.lw)
    else:
        cv.shaded(hair_mask_shape, hp.hair, hp.hair_sh, off, hp.hair_line, hp.lw)
        # angel-ring highlight: thin slivers following the curve of the skull
        for k in range(6):
            x = -0.42 + k * 0.17
            def yy(xv):
                return -0.66 + 0.30 * (xv / 0.62) ** 2
            seg = [(x - 0.06, yy(x - 0.06)), (x + 0.06, yy(x + 0.06)),
                   (x + 0.02, yy(x + 0.02) + 0.05 + 0.02 * (k % 2)), (x - 0.03, yy(x - 0.03) + 0.03)]
            cv.fill(hp.path(seg, smooth=False), pal.with_alpha(hp.hair_hi, 170))
        # strand lines
        for x in (-0.28, 0.02, 0.30):
            pts2 = [hp.W2(x * 0.5, -0.74), hp.W2(x * 0.9, -0.48), hp.W2(x * 1.05, -0.24)]
            cv.fill(taper_stroke(bezier_points(pts2[0], pts2[1], pts2[1], pts2[2], 10),
                                 hp.lw * 0.15, hp.lw * 0.15, hp.lw * 0.55), pal.with_alpha(hp.hair_line, 200))
    acc = set(d.accessories)
    if 'headband' in acc:
        band = [(-0.6, -0.45), (0.0, -0.80), (0.6, -0.45), (0.62, -0.36), (0.0, -0.70), (-0.62, -0.36)]
        cv.fill_stroke(hp.path(band, smooth=False), hp.col['accent'], pal.line_color(hp.col['accent']), hp.lw * 0.8)
    if 'bow' in acc:
        bx, by = hp.W2(0.42, -0.62)
        s = 0.16 * hp.U
        for sgn in (-1, 1):
            wing = VPath().poly([(bx, by), (bx + sgn * s, by - s * 0.6), (bx + sgn * s, by + s * 0.6)])
            cv.fill_stroke(wing, hp.col['accent'], pal.line_color(hp.col['accent']), hp.lw * 0.7)
        cv.circle(bx, by, s * 0.25, pal.darken(hp.col['accent'], 0.2))
    if 'cap' in acc:
        cap = [(-0.62, -0.30), (-0.60, -0.70), (0.0, -0.95), (0.60, -0.70), (0.62, -0.30)]
        cv.fill_stroke(hp.path(cap + [(0.0, -0.36)], closed=True), hp.col['accent'],
                       pal.line_color(hp.col['accent']), hp.lw)
        brim = [(-0.25 + 0.4 * hp.t, -0.38), (0.75, -0.30), (0.70, -0.20), (-0.25 + 0.4 * hp.t, -0.27)]
        cv.fill_stroke(hp.path(brim, smooth=False), pal.darken(hp.col['accent'], 0.15),
                       pal.line_color(hp.col['accent']), hp.lw)


def draw_hair_back(hp: HeadPainter, cv: Canvas) -> None:
    d = hp.d
    style = d.hair_style
    if style == 'bald':
        if d.age == 'elder':
            for sgn in (-1, 1):
                patch = [(sgn * 0.48, -0.30), (sgn * 0.60, -0.20), (sgn * 0.58, 0.05), (sgn * 0.48, 0.02)]
                cv.fill_stroke(hp.path(patch), hp.hair, hp.hair_line, hp.lw * 0.7)
        return
    shapes = []
    if style in ('long',):
        shapes.append([(-0.62, -0.40), (-0.42, -0.84), (0.0, -0.92), (0.42, -0.84), (0.62, -0.40),
                       (0.72, 0.4), (0.82, 1.2), (0.86, 1.9), (0.55, 1.75), (0.3, 1.95), (0.0, 1.8),
                       (-0.3, 1.95), (-0.55, 1.75), (-0.86, 1.9), (-0.82, 1.2), (-0.72, 0.4)])
    elif style == 'bob':
        shapes.append([(-0.62, -0.40), (-0.42, -0.84), (0.0, -0.92), (0.42, -0.84), (0.62, -0.40),
                       (0.72, 0.30), (0.70, 0.72), (0.40, 0.66), (0.0, 0.70), (-0.40, 0.66),
                       (-0.70, 0.72), (-0.72, 0.30)])
    else:
        shapes.append([(-0.60, -0.40), (-0.42, -0.84), (0.0, -0.92), (0.42, -0.84), (0.60, -0.40),
                       (0.58, 0.10), (0.40, 0.30), (-0.40, 0.30), (-0.58, 0.10)])
    if style == 'ponytail':
        shapes.append([(0.30, -0.70), (0.62, -0.55), (0.80, 0.0), (0.78, 0.7), (0.62, 1.3),
                       (0.50, 0.80), (0.50, 0.10), (0.35, -0.40)])
    if style == 'twintails':
        for sgn in (-1, 1):
            shapes.append([(sgn * 0.55, -0.55), (sgn * 0.85, -0.40), (sgn * 1.05, 0.2), (sgn * 1.00, 0.9),
                           (sgn * 0.85, 1.45), (sgn * 0.75, 0.9), (sgn * 0.72, 0.2), (sgn * 0.60, -0.30)])
    if style == 'bun':
        shapes.append(None)
    for s in shapes:
        if s is None:
            x, y = hp.W2(0.0, -0.98)
            bun = VPath().ellipse(x, y, 0.26 * hp.U, 0.22 * hp.U)
            if hp.cartoon:
                cv.fill_stroke(bun, hp.hair, hp.hair_line, hp.lw)
            else:
                cv.shaded(bun, hp.hair, hp.hair_sh, (-0.04 * hp.U, -0.04 * hp.U), hp.hair_line, hp.lw)
            continue
        path = hp.path(s, closed=True, smooth=True)
        if hp.cartoon:
            cv.fill_stroke(path, hp.hair_sh, hp.hair_line, hp.lw)
        else:
            cv.shaded(path, pal.darken(hp.hair, 0.08), hp.hair_sh, (0.06 * hp.U, -0.05 * hp.U), hp.hair_line, hp.lw)
    if style == 'twintails':
        for sgn in (-1, 1):
            x, y = hp.W2(sgn * 0.70, -0.48)
            cv.fill_stroke(VPath().ellipse(x, y, 0.08 * hp.U, 0.08 * hp.U), hp.col['accent'], '#2A2030', hp.lw * 0.6)


# --------------------------------------------------------------------------
# Face (base head layer)
# --------------------------------------------------------------------------


def draw_face(hp: HeadPainter, cv: Canvas) -> None:
    outline = hp.face_outline()
    face = VPath().smooth([hp.P(x, y) for x, y in outline], closed=True, tension=0.55)
    # ears (behind the face outline)
    ears = [-1, 1] if hp.t == 0 else [-1]
    for sgn in ears:
        ex = -0.51 if sgn < 0 else 0.51
        if hp.t and sgn < 0:
            ex = -0.53
        x, y = hp.P(ex, 0.08)
        ear = VPath().ellipse(x + sgn * 0.02 * hp.U, y, 0.09 * hp.U, 0.15 * hp.U)
        cv.fill_stroke(ear, hp.skin, hp.skin_line, hp.lw * 0.8)
        cv.stroke(VPath().poly([(x + sgn * 0.0 * hp.U, y - 0.06 * hp.U), (x + sgn * 0.04 * hp.U, y + 0.05 * hp.U)],
                               closed=False), hp.skin_sh, hp.lw * 0.6)
    off = (0.045 * hp.U * (1 if hp.t else 0) - 0.01 * hp.U, -0.05 * hp.U)
    cv.shaded(face, hp.skin, hp.skin_sh if not hp.cartoon else pal.mix(hp.skin, hp.skin_sh, 0.4),
              off, hp.skin_line, hp.lw)
    # nose
    if not hp.cartoon:
        nx = hp.warp(0.0) + 0.05 * hp.t
        if hp.t:
            pts = [hp.P(nx + 0.02, 0.18), hp.P(nx + 0.07, 0.30), hp.P(nx + 0.01, 0.32)]
            cv.fill(taper_stroke(pts, hp.lw * 0.3, hp.lw * 0.5, hp.lw * 0.8), hp.skin_line)
        else:
            cv.fill(taper_stroke([hp.P(nx + 0.01, 0.27), hp.P(nx - 0.02, 0.31)], hp.lw * 0.5, hp.lw * 0.8),
                    pal.with_alpha(hp.skin_line, 180))
    else:
        nx = hp.warp(0.0) + 0.04 * hp.t
        x, y = hp.P(nx, 0.27)
        cv.fill_stroke(VPath().ellipse(x, y, 0.05 * hp.U, 0.04 * hp.U), pal.shade(hp.skin), hp.skin_line, hp.lw * 0.6)


def draw_blush(hp: HeadPainter, cv: Canvas, variant: str) -> None:
    for side in (-1, 1):
        cx, cy, w, h, sc = hp.eye_geom(side)
        x, y = hp.P(cx + side * 0.03, cy + 0.27)
        if variant == 'soft':
            cv.fill(VPath().ellipse(x, y, 0.11 * hp.U * sc, 0.05 * hp.U), '#FF8A9A70')
        else:
            cv.fill(VPath().ellipse(x, y, 0.12 * hp.U * sc, 0.06 * hp.U), '#FF7A8A60')
            for k in range(3):
                dx = (-0.06 + k * 0.06) * hp.U * sc
                cv.stroke(VPath().poly([(x + dx + 0.02 * hp.U, y - 0.035 * hp.U),
                                        (x + dx - 0.02 * hp.U, y + 0.035 * hp.U)], closed=False),
                          '#E0506A', hp.lw * 0.6)


def draw_accessories(hp: HeadPainter, cv: Canvas) -> None:
    acc = set(hp.d.accessories)
    ink = '#2A2030'
    if 'glasses' in acc:
        for side in (-1, 1):
            cx, cy, w, h, sc = hp.eye_geom(side)
            x, y = hp.P(cx, cy + 0.02)
            rim = VPath().rect(x - 0.62 * w * hp.U * sc, y - 0.42 * h * hp.U * 1.1,
                               x + 0.62 * w * hp.U * sc, y + 0.42 * h * hp.U * 1.1, r=0.06 * hp.U)
            cv.fill(rim, '#E8F4FF30')
            cv.stroke(rim, ink, hp.lw * 0.9)
            cv.stroke(VPath().poly([(x - 0.3 * w * hp.U, y - 0.2 * h * hp.U),
                                    (x - 0.05 * w * hp.U, y - 0.38 * h * hp.U)], closed=False), '#FFFFFFB0', hp.lw * 0.8)
        l, _, _, _, _ = hp.eye_geom(-1)
        r, cy, w, _, _ = hp.eye_geom(1)
        cv.stroke(VPath().poly([hp.P(l + 0.6 * w, cy - 0.02), hp.P(r - 0.6 * w, cy - 0.02)], closed=False), ink, hp.lw * 0.8)
    if 'bindi' in acc:
        cv.circle(*hp.W2(0.0, -0.02), 0.025 * hp.U, '#C81E3A')
    if 'mustache' in acc or 'beard' in acc:
        mx = hp.warp(0.0)
        must = [(mx - 0.17, 0.38), (mx, 0.34), (mx + 0.17, 0.38), (mx + 0.12, 0.40), (mx, 0.37), (mx - 0.12, 0.40)]
        cv.fill(hp.path(must, warp=False), pal.darken(hp.hair, 0.1))
    if 'beard' in acc:
        mx = hp.warp(0.0)
        beard = [(mx - 0.36, 0.32), (mx - 0.22, 0.56), (mx + 0.05 * hp.t, 0.70), (mx + 0.22, 0.56),
                 (mx + 0.36, 0.32), (mx + 0.20, 0.50), (mx, 0.54), (mx - 0.20, 0.50)]
        cv.fill(hp.path(beard, warp=False), pal.with_alpha(pal.darken(hp.hair, 0.1), 235))
    if 'earrings' in acc:
        cv.circle(*hp.P(-0.52, 0.24), 0.03 * hp.U, '#F2C94C')
        if hp.t == 0:
            cv.circle(*hp.P(0.52, 0.24), 0.03 * hp.U, '#F2C94C')
    if 'freckles' in acc:
        for side in (-1, 1):
            cx, cy, w, h, sc = hp.eye_geom(side)
            for k in range(3):
                cv.circle(*hp.P(cx + (k - 1) * 0.05, cy + 0.24 + 0.02 * (k % 2)), 0.008 * hp.U, '#B5765A')


# --------------------------------------------------------------------------
# Building the rig (v2: separate legs, look-direction eyes, ground shadow)
# --------------------------------------------------------------------------


def _save_level(frames: list[Image.Image], folder: Path, level: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(frames, start=1):
        img.save(folder / ('%s.%04d.png' % (level, i)), compress_level=1)


def _painters(design: CharacterDesign, p: Proportions, view: str):
    """Head painter + drawing functions for the design's style."""
    hp = HeadPainter(design, p, view)
    if design.style == 'cartoon':
        from . import toonhead as tk
        th = tk.ToonHead(hp)
        return th, dict(hair_back=tk.draw_hair_back, face=tk.draw_face, blush=tk.draw_blush,
                        eye=tk.draw_eye, mouth=tk.draw_mouth, acc=tk.draw_accessories,
                        hair_front=tk.draw_hair_front, brows=tk.draw_brows, fx=draw_fx)
    return hp, dict(hair_back=draw_hair_back, face=draw_face, blush=draw_blush, eye=draw_eye,
                    mouth=draw_mouth, acc=draw_accessories, hair_front=draw_hair_front,
                    brows=draw_brows, fx=draw_fx)


def build_character(design: CharacterDesign, out_dir: Path, prefix: str | None = None) -> dict:
    """Renders all part levels into ``out_dir`` and returns the rig manifest.

    Drawing ids are 1-based. Head parts and view-dependent body parts store
    the front view first, then the three-quarter view (see drawing_id)."""
    from . import body as bk
    out_dir = Path(out_dir)
    p = proportions(design)
    prefix = prefix or _slug(design.name)
    parts: dict[str, dict] = {}

    head_layers: dict[str, list[Image.Image]] = {k: [] for k in
                                                 ('hair_back', 'head', 'blush', 'eyes', 'mouth', 'acc',
                                                  'hair_front', 'brows', 'fx')}
    for view in VIEWS:
        hp, fn = _painters(design, p, view)
        cv = hp.canvas()
        fn['hair_back'](hp, cv)
        head_layers['hair_back'].append(cv.paste_into(hp.blank()))
        cv = hp.canvas(-1.0, -1.0, 1.0, 1.0)
        fn['face'](hp, cv)
        head_layers['head'].append(cv.paste_into(hp.blank()))
        for v in BLUSH_DRAWINGS:
            cv = hp.canvas(-0.8, -0.2, 0.8, 0.7)
            fn['blush'](hp, cv, v)
            head_layers['blush'].append(cv.paste_into(hp.blank()))
        for name in EYE_DRAWINGS:
            expr, _, look = name.partition('_')
            cv = hp.canvas(-0.75, -0.45, 0.85, 0.5)
            for side in (-1, 1):
                fn['eye'](hp, cv, side, expr, look or 'c')
            head_layers['eyes'].append(cv.paste_into(hp.blank()))
        for v in MOUTH_DRAWINGS:
            cv = hp.canvas(-0.5, 0.1, 0.65, 0.85)
            fn['mouth'](hp, cv, v)
            head_layers['mouth'].append(cv.paste_into(hp.blank()))
        cv = hp.canvas(-1.0, -0.7, 1.0, 0.9)
        fn['acc'](hp, cv)
        head_layers['acc'].append(cv.paste_into(hp.blank()))
        cv = hp.canvas(-1.25, -1.45, 1.25, 0.9)
        fn['hair_front'](hp, cv)
        head_layers['hair_front'].append(cv.paste_into(hp.blank()))
        for v in BROW_DRAWINGS:
            cv = hp.canvas(-0.8, -0.6, 0.85, 0.2)
            fn['brows'](hp, cv, v)
            head_layers['brows'].append(cv.paste_into(hp.blank()))
        for v in FX_DRAWINGS:
            cv = hp.canvas(-1.35, -1.6, 1.35, 1.3)
            fn['fx'](hp, cv, v)
            head_layers['fx'].append(cv.paste_into(hp.blank()))

    img_cy = p.face_cy - ((HEAD_Y0 + HEAD_Y1) / 2) * p.u
    neck_pivot = [0.0, p.chin + 0.02 * p.hh]
    for name, frames in head_layers.items():
        level = '%s_%s' % (prefix, name)
        _save_level(frames, out_dir, level)
        parts[name] = {'level': level, 'dpi': HEAD_DPI, 'center': [0.0, img_cy],
                       'pivot': list(neck_pivot), 'count': len(frames)}

    def body_part(name, bounds, draw, variants, pivot, warp=False):
        frames, kit = [], None
        for v in variants:
            kit = bk.Kit(design, p, *bounds, view=v[0], warp=warp)
            cv = kit.canvas()
            draw(kit, cv, *v[1:])
            frames.append(cv.result())
        level = '%s_%s' % (prefix, name)
        _save_level(frames, out_dir, level)
        parts[name] = {'level': level, 'dpi': BODY_DPI, 'center': list(kit.center),
                       'pivot': list(pivot), 'count': len(frames)}

    body_part('shadow', bk.shadow_bounds(p), bk.draw_shadow, [('front',)], (0.0, 0.0))
    body_part('body', bk.torso_bounds(p), bk.draw_torso, [('front',), ('three_quarter',)],
              (0.0, p.crotch_y), warp=True)
    for side_name, side in (('l', -1), ('r', 1)):
        body_part('thigh_' + side_name, bk.leg_bounds(p, side, 'thigh'), bk.draw_thigh,
                  [('front', side, 'front'), ('three_quarter', side, 'three_quarter')],
                  (side * p.hip_jx, p.hip_jy))
        body_part('shin_' + side_name, bk.leg_bounds(p, side, 'shin'), bk.draw_shin,
                  [('front', side, 'front'), ('three_quarter', side, 'three_quarter')],
                  (side * p.hip_jx, p.knee_y))
        body_part('upper_' + side_name, bk.arm_bounds(p, side, 'upper'), bk.draw_upper_arm,
                  [('front', side, 1.0), ('front', side, 0.55)], (side * p.arm_x, p.shoulder_y))
        body_part('fore_' + side_name, bk.arm_bounds(p, side, 'fore'), bk.draw_forearm,
                  [('front', side, h) for h in HAND_DRAWINGS],
                  (side * p.arm_x, p.shoulder_y - p.upper_len))

    manifest = {
        'name': design.name,
        'prefix': prefix,
        'rig_version': 2,
        'design': asdict(design),
        'proportions': asdict(p),
        'parts': parts,
        'drawings': {
            'eyes': EYE_DRAWINGS, 'brows': BROW_DRAWINGS, 'mouth': MOUTH_DRAWINGS,
            'fx': FX_DRAWINGS, 'blush': BLUSH_DRAWINGS, 'hands': HAND_DRAWINGS, 'views': VIEWS,
        },
        'face_center': [0.0, p.face_cy],
        'height': p.H,
        'head_height': p.hh,
    }
    (out_dir / 'rig.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    return manifest


_LISTS = {'eyes': EYE_DRAWINGS, 'brows': BROW_DRAWINGS, 'mouth': MOUTH_DRAWINGS,
          'fx': FX_DRAWINGS, 'blush': BLUSH_DRAWINGS}
_VIEW_PARTS = {'hair_back', 'head', 'acc', 'hair_front', 'body', 'shin_l', 'shin_r', 'thigh_l', 'thigh_r'}


def drawing_id(manifest: dict, part: str, name: str = '', view: str = 'front') -> int:
    """1-based frame id of a named drawing of a part."""
    vi = VIEWS.index(view)
    if part in _LISTS:
        names = _LISTS[part]
        return vi * len(names) + names.index(name) + 1
    if part in _VIEW_PARTS:
        return vi + 1
    if part.startswith('fore_'):
        return HAND_DRAWINGS.index(name or 'open') + 1
    if part.startswith('upper_'):
        return 2 if name == 'short' else 1
    return 1


def _slug(s: str) -> str:
    out = ''.join(ch.lower() if ch.isalnum() else '_' for ch in s).strip('_')
    return out or 'char'


def preview_sheet(manifest: dict, folder: Path, out: Path) -> Path:
    """Rig at rest, front and three-quarter, for a quick look."""
    from ..tnz.model import Scene
    from ..render.compositor import Compositor
    from ..production.rigging import add_character_to_scene, pose_rest
    scene = Scene(res=(1280, 720))
    scene.path = folder / '_preview.tnz'
    H = manifest['height']
    scale = min(1.35, 7.6 / H)
    for view, x in (('front', -3.2), ('three_quarter', 3.2)):
        rig = add_character_to_scene(scene, manifest, '.', x=x, y=-4.2, scale=scale)
        pose_rest(scene, rig, 0, 1, view=view, mouth='smile')
    Compositor(scene, folder, background=(236, 234, 242)).render_png(0, out)
    return out
