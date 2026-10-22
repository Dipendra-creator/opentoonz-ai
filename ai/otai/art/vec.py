"""Tiny vector drawing toolkit on top of Pillow (no native deps).

Paths are built from lines and bezier curves, flattened to polygons and
rasterised on a supersampled canvas, then reduced with a box filter for
antialiasing. Coordinates are canvas pixels (y down).
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

Point = tuple[float, float]


class Path:
    def __init__(self) -> None:
        self.subpaths: list[list[Point]] = []
        self.closed: list[bool] = []
        self._cur: list[Point] | None = None

    # -- building -----------------------------------------------------------
    def move(self, x: float, y: float) -> 'Path':
        self._cur = [(x, y)]
        self.subpaths.append(self._cur)
        self.closed.append(False)
        return self

    def line(self, x: float, y: float) -> 'Path':
        self._cur.append((x, y))
        return self

    def cubic(self, c1: Point, c2: Point, p: Point, steps: int = 0) -> 'Path':
        p0 = self._cur[-1]
        n = steps or _steps(p0, c1, c2, p)
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            x = u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p[0]
            y = u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p[1]
            self._cur.append((x, y))
        return self

    def quad(self, c: Point, p: Point) -> 'Path':
        p0 = self._cur[-1]
        c1 = (p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1]))
        c2 = (p[0] + 2 / 3 * (c[0] - p[0]), p[1] + 2 / 3 * (c[1] - p[1]))
        return self.cubic(c1, c2, p)

    def smooth(self, pts: Sequence[Point], closed: bool = False,
               tension: float = 0.5) -> 'Path':
        """Catmull-Rom spline through points (starts a new subpath)."""
        pts = list(pts)
        if closed:
            ext = [pts[-1]] + pts + [pts[0], pts[1]]
        else:
            ext = [pts[0]] + pts + [pts[-1]]
        self.move(*pts[0])
        n = len(pts) if closed else len(pts) - 1
        for i in range(n):
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
            c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
            self.cubic(c1, c2, p2)
        if closed:
            self.close()
        return self

    def close(self) -> 'Path':
        if self._cur is not None:
            self.closed[-1] = True
        return self

    def ellipse(self, cx: float, cy: float, rx: float, ry: float,
                rot: float = 0.0) -> 'Path':
        n = max(24, int((rx + ry) / 3))
        cs, sn = math.cos(rot), math.sin(rot)
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            x, y = rx * math.cos(a), ry * math.sin(a)
            pts.append((cx + x * cs - y * sn, cy + x * sn + y * cs))
        self.move(*pts[0])
        for p in pts[1:]:
            self.line(*p)
        return self.close()

    def rect(self, x0, y0, x1, y1, r: float = 0.0) -> 'Path':
        if r <= 0:
            return self.move(x0, y0).line(x1, y0).line(x1, y1).line(x0, y1).close()
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        k = 0.5523 * r
        self.move(x0 + r, y0).line(x1 - r, y0)
        self.cubic((x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r)).line(x1, y1 - r)
        self.cubic((x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1)).line(x0 + r, y1)
        self.cubic((x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r)).line(x0, y0 + r)
        self.cubic((x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))
        return self.close()

    def poly(self, pts: Iterable[Point], closed: bool = True) -> 'Path':
        pts = list(pts)
        self.move(*pts[0])
        for p in pts[1:]:
            self.line(*p)
        if closed:
            self.close()
        return self

    # -- transforms -----------------------------------------------------
    def mapped(self, fn) -> 'Path':
        out = Path()
        for sp, cl in zip(self.subpaths, self.closed):
            out.subpaths.append([fn(p) for p in sp])
            out.closed.append(cl)
        out._cur = out.subpaths[-1] if out.subpaths else None
        return out

    def translated(self, dx: float, dy: float) -> 'Path':
        return self.mapped(lambda p: (p[0] + dx, p[1] + dy))

    def mirrored_x(self, cx: float) -> 'Path':
        return self.mapped(lambda p: (2 * cx - p[0], p[1]))

    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for sp in self.subpaths for p in sp]
        ys = [p[1] for sp in self.subpaths for p in sp]
        return min(xs), min(ys), max(xs), max(ys)


def _steps(*pts: Point) -> int:
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    return max(6, min(80, int(length / 6)))


def rgba(color) -> tuple[int, int, int, int]:
    if isinstance(color, str):
        c = color.lstrip('#')
        if len(c) == 6:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255
        if len(c) == 8:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4, 6))
        raise ValueError('bad color %r' % color)
    if len(color) == 3:
        return (int(color[0]), int(color[1]), int(color[2]), 255)
    return tuple(int(v) for v in color)


class Canvas:
    """Supersampled RGBA drawing surface covering a region of a bigger image.

    ``origin`` lets several small canvases share one coordinate system (e.g.
    an eye drawn on a 300px canvas placed inside a 1200px head image).
    """

    def __init__(self, w: int, h: int, ss: int = 3,
                 origin: tuple[int, int] = (0, 0)) -> None:
        self.w, self.h, self.ss = int(w), int(h), ss
        self.ox, self.oy = origin
        self.img = Image.new('RGBA', (self.w * ss, self.h * ss), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)

    def _pts(self, sp: Sequence[Point]) -> list[Point]:
        s, ox, oy = self.ss, self.ox, self.oy
        return [((x - ox) * s, (y - oy) * s) for x, y in sp]

    # -- masks ------------------------------------------------------------
    def mask(self, path: Path) -> Image.Image:
        m = Image.new('L', self.img.size, 0)
        d = ImageDraw.Draw(m)
        for sp in path.subpaths:
            if len(sp) >= 3:
                d.polygon(self._pts(sp), fill=255)
        return m

    def stroke_mask(self, path: Path, width: float) -> Image.Image:
        m = Image.new('L', self.img.size, 0)
        _stroke(ImageDraw.Draw(m), path, self, width, 255)
        return m

    def paint(self, mask: Image.Image, color) -> None:
        layer = Image.new('RGBA', self.img.size, rgba(color))
        a = mask
        if rgba(color)[3] < 255:
            a = mask.point(lambda v: v * rgba(color)[3] // 255)
        layer.putalpha(a)
        self.img.alpha_composite(layer)

    def erase(self, mask: Image.Image) -> None:
        alpha = self.img.getchannel('A')
        self.img.putalpha(ImageChops.subtract(alpha, mask))

    # -- drawing ------------------------------------------------------------
    def fill(self, path: Path, color) -> None:
        if rgba(color)[3] == 255:
            for sp in path.subpaths:
                if len(sp) >= 3:
                    self.draw.polygon(self._pts(sp), fill=rgba(color))
        else:
            self.paint(self.mask(path), color)

    def stroke(self, path: Path, color, width: float) -> None:
        if rgba(color)[3] == 255:
            _stroke(self.draw, path, self, width, rgba(color))
        else:
            self.paint(self.stroke_mask(path, width), color)

    def fill_stroke(self, path: Path, fill, stroke, width: float) -> None:
        self.fill(path, fill)
        if width > 0:
            self.stroke(path, stroke, width)

    def shaded(self, path: Path, base, shadow, offset: tuple[float, float],
               line=None, width: float = 0.0, clip: Image.Image | None = None) -> None:
        """Cel shading: base colour where the shape overlaps itself shifted by
        ``offset`` (towards the light), shadow colour on the remaining rim."""
        m = self.mask(path)
        if clip is not None:
            m = ImageChops.multiply(m, clip)
        dx, dy = int(offset[0] * self.ss), int(offset[1] * self.ss)
        shifted = ImageChops.offset(m, dx, dy)
        lit = ImageChops.multiply(m, shifted)
        self.paint(m, shadow)
        self.paint(lit, base)
        if width > 0 and line is not None:
            self.stroke(path, line, width)

    def gradient(self, path: Path, top, bottom, y0: float | None = None,
                 y1: float | None = None) -> None:
        m = self.mask(path)
        bx0, by0, bx1, by1 = path.bbox()
        y0 = by0 if y0 is None else y0
        y1 = by1 if y1 is None else y1
        grad = _vgradient(self.img.size, rgba(top), rgba(bottom),
                          (y0 - self.oy) * self.ss, (y1 - self.oy) * self.ss)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), m))
        self.img.alpha_composite(grad)

    def circle(self, cx, cy, r, color) -> None:
        self.fill(Path().ellipse(cx, cy, r, r), color)

    def blur(self, radius: float) -> None:
        self.img = self.img.filter(ImageFilter.GaussianBlur(radius * self.ss))
        self.draw = ImageDraw.Draw(self.img)

    def result(self) -> Image.Image:
        if self.ss == 1:
            return self.img
        return self.img.reduce(self.ss)

    def paste_into(self, target: Image.Image) -> Image.Image:
        """Places the result into ``target`` (assumed transparent there)."""
        target.paste(self.result(), (int(self.ox), int(self.oy)))
        return target


def _stroke(draw: ImageDraw.ImageDraw, path: Path, cv: Canvas, width: float,
            fill) -> None:
    wpx = max(1, int(round(width * cv.ss)))
    r = wpx / 2
    for sp, closed in zip(path.subpaths, path.closed):
        pts = cv._pts(sp)
        if closed:
            pts = pts + [pts[0]]
        if len(pts) >= 2:
            draw.line(pts, fill=fill, width=wpx, joint='curve')
        for x, y in (pts[0], pts[-1]):
            draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _vgradient(size, top, bottom, y0, y1) -> Image.Image:
    w, h = size
    col = Image.new('RGBA', (1, h))
    span = max(1.0, y1 - y0)
    px = col.load()
    for y in range(h):
        t = min(max((y - y0) / span, 0.0), 1.0)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4))
    return col.resize((w, h))


def taper_stroke(pts: Sequence[Point], w0: float, w1: float, w_mid: float | None = None) -> Path:
    """A filled outline around a polyline whose width varies along it
    (brush-like strokes for lashes, brows, hair strands)."""
    n = len(pts)
    if w_mid is None:
        w_mid = max(w0, w1)
    left, right = [], []
    for i, p in enumerate(pts):
        t = i / (n - 1)
        wv = (w0 + (w_mid - w0) * (t / 0.5)) if t < 0.5 else (w_mid + (w1 - w_mid) * ((t - 0.5) / 0.5))
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        left.append((p[0] + nx * wv / 2, p[1] + ny * wv / 2))
        right.append((p[0] - nx * wv / 2, p[1] - ny * wv / 2))
    return Path().poly(left + right[::-1])


def bezier_points(p0: Point, c1: Point, c2: Point, p3: Point, n: int = 24) -> list[Point]:
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
    return out
