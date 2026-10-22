"""Colour grades for finished frames (MP4 only, like shot transitions).

A grade sets the lighting of a whole shot after compositing: the frame is
desaturated, tinted and has its shadows lifted towards a colour, while bright
saturated pixels (glowing eyes, phone screens, lamps, neon) keep their colour
and bloom, so they read as light sources in the dark. Some grades also float
soft light motes across the frame.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class Grade:
    mult: tuple[float, float, float]   # per-channel gain
    lift: tuple[int, int, int]         # colour the shadows lift towards
    lift_amount: float                 # 0..1
    sat: float                         # saturation of the non-glowing pixels
    glow: float                        # bloom strength of the glowing pixels
    motes: int = 0                     # number of drifting light motes
    mote_color: tuple[int, int, int] = (230, 236, 255)


GRADES: dict[str, Grade | None] = {
    'none': None,
    # moonlit room: cool and dim, screens and eyes glow
    'night': Grade((0.50, 0.60, 0.92), (18, 22, 52), 0.22, 0.75, 0.9),
    # trance / daydream: violet light, strong glow, floating motes
    'dream': Grade((0.70, 0.52, 0.98), (40, 14, 70), 0.30, 0.85, 1.3, motes=24),
    # golden hour / nostalgia
    'warm': Grade((1.04, 0.90, 0.72), (60, 30, 10), 0.10, 1.05, 0.5, motes=10, mote_color=(255, 232, 180)),
    # sad / lonely: grey-blue and flat
    'gloom': Grade((0.66, 0.70, 0.84), (26, 28, 40), 0.25, 0.40, 0.0),
    # party / hype: dark magenta, saturated, heavy bloom
    'neon': Grade((0.60, 0.42, 0.86), (30, 0, 46), 0.25, 1.25, 1.7),
}


def _smoothstep(a: float, b: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _blur(rgb: np.ndarray, factor: int, radius: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), 'RGB')
    small = img.resize((max(1, w // factor), max(1, h // factor)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(small.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32) / 255


@lru_cache(maxsize=16)
def _mote_sprite(r: int, color: tuple[int, int, int]) -> Image.Image:
    size = r * 4 + 1
    y, x = np.mgrid[0:size, 0:size]
    d = np.sqrt((x - size // 2) ** 2 + (y - size // 2) ** 2) / r
    a = np.clip(1.15 - d, 0, 1) ** 1.6 * 0.85 + np.exp(-d * d * 0.6) * 0.25
    sprite = np.zeros((size, size, 4), dtype=np.uint8)
    sprite[..., :3] = color
    sprite[..., 3] = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(sprite, 'RGBA')


def _motes(img: Image.Image, g: Grade, frame: int) -> None:
    w, h = img.size
    rnd = random.Random(7)
    for _ in range(g.motes):
        r = max(2, int(h * rnd.uniform(0.004, 0.012)))
        x0, y0 = rnd.uniform(0, w), rnd.uniform(0, h)
        vx, vy = rnd.uniform(-0.5, 0.5) * h / 720, -rnd.uniform(0.2, 0.9) * h / 720
        phase, speed = rnd.uniform(0, 6.28), rnd.uniform(0.04, 0.12)
        span_x, span_y = w + 8 * r, h + 8 * r
        x = (x0 + vx * frame) % span_x - 4 * r
        y = (y0 + vy * frame) % span_y - 4 * r
        twinkle = 0.55 + 0.45 * np.sin(phase + speed * frame)
        sprite = _mote_sprite(r, g.mote_color)
        if twinkle < 0.98:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel('A').point(lambda v, k=twinkle: int(v * k)))
        # paste (not alpha_composite) accepts sprites hanging off the frame edge
        img.paste(sprite, (int(x) - 2 * r, int(y) - 2 * r), sprite)


def animated(name: str) -> bool:
    """True when the grade changes from frame to frame (motes)."""
    g = GRADES.get(name)
    return bool(g and g.motes)


def apply(img: Image.Image, name: str, frame: int = 0) -> Image.Image:
    """Returns ``img`` graded (a new RGBA image), or ``img`` itself for 'none'."""
    g = GRADES.get(name)
    if g is None:
        return img
    a = np.asarray(img.convert('RGB'), dtype=np.float32) / 255
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    emit = (_smoothstep(0.80, 0.96, mx) * _smoothstep(0.42, 0.68, sat))[..., None]
    lum = (a @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
    out = lum + (a - lum) * g.sat
    out = out * np.array(g.mult, dtype=np.float32)
    lift = np.array(g.lift, dtype=np.float32) / 255
    out = out + (lift - out) * g.lift_amount * (1 - lum)
    out = out * (1 - emit) + a * emit
    if g.glow > 0:
        src = a * emit
        bloom = _blur(src, 4, max(1.0, img.height / 240)) * 0.6 + _blur(src, 8, max(1.0, img.height / 200)) * 0.8
        out = 1 - (1 - out) * (1 - np.clip(bloom * g.glow, 0, 1))
    res = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), 'RGB').convert('RGBA')
    if g.motes:
        _motes(res, g, frame)
    return res
