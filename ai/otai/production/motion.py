"""Procedural motion layers baked into OpenToonz keyframes.

Every animated transform is a per-frame channel (numpy array) built by adding
layers: rest pose, idle breathing/sway, talking acting, actions with
anticipation and overshoot, walk cycles, and spring-driven secondary motion.
Channels are evaluated on ones and baked into linear keyframes, dropping
keys a straight line can reproduce within a small tolerance, so the .tnz stays
compact while every frame moves.
"""

from __future__ import annotations

import math

import numpy as np

from ..tnz.model import Scene

# per-parameter bake tolerances (value units)
TOL = {'x': 0.0015, 'y': 0.0015, 'rot': 0.04, 'sx': 0.0008, 'sy': 0.0008, 'sc': 0.0008}


# --------------------------------------------------------------------------
# easing
# --------------------------------------------------------------------------


def ease_in_out(t):
    t = np.clip(t, 0.0, 1.0)
    return np.where(t < 0.5, 4 * t ** 3, 1 - (-2 * t + 2) ** 3 / 2)


def ease_out(t):
    t = np.clip(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_out_back(t, overshoot: float = 0.1):
    """Cubic back-out; ``overshoot`` is the peak fraction above 1 (approx)."""
    t = np.clip(t, 0.0, 1.0)
    s = 1.70158 * (overshoot / 0.1) ** 0.75 if overshoot > 0 else 0.0
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def sine_in_out(t):
    t = np.clip(t, 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * t)


def pose_weight(n: int, t_in: int = 8, t_out: int = 10, overshoot: float = 0.10,
                anticip: float = 0.12, drift: float = 0.04, phase: float = 0.0) -> np.ndarray:
    """Weight curve 0 -> 1 -> 0 over ``n`` frames for a pose: a small dip
    (anticipation), a back-out rise that overshoots and settles, a moving
    hold that never freezes, and an eased return."""
    n = max(int(n), 2)
    t_in = max(2, min(t_in, n // 2))
    t_out = max(2, min(t_out, n - t_in))
    w = np.zeros(n)
    a = max(1, min(4, t_in // 2)) if anticip > 0 else 0
    if a:
        w[:a] = -anticip * np.sin(np.linspace(0, np.pi / 2, a, endpoint=False))
    rise = np.arange(t_in - a) / max(1, t_in - a - 1)
    start = w[a - 1] if a else 0.0
    w[a:t_in] = start + (1 - start) * ease_out_back(rise, overshoot)
    hold_n = n - t_in - t_out
    if hold_n > 0:
        k = np.arange(hold_n)
        w[t_in:t_in + hold_n] = 1 + drift * np.sin(2 * np.pi * k / 46 + phase) * np.minimum(1, k / 10)
    last = w[t_in + hold_n - 1] if t_in + hold_n > 0 else 1.0
    r = np.arange(1, t_out + 1) / t_out
    w[n - t_out:] = last * (1 - ease_in_out(r))
    return w


# --------------------------------------------------------------------------
# springs
# --------------------------------------------------------------------------


def spring_follow(target: np.ndarray, f_hz: float, zeta: float, fps: float,
                  x0: float | None = None) -> np.ndarray:
    """Damped spring chasing a target signal (semi-implicit Euler, substeps)."""
    w = 2 * math.pi * f_hz
    out = np.empty_like(target, dtype=float)
    x = float(target[0] if x0 is None else x0)
    v = 0.0
    sub = 4
    dt = 1.0 / fps / sub
    for i, tg in enumerate(target):
        for _ in range(sub):
            a = -w * w * (x - tg) - 2 * zeta * w * v
            v += a * dt
            x += v * dt
        out[i] = x
    return out


def lag(signal: np.ndarray, frames: int) -> np.ndarray:
    if frames <= 0:
        return signal.copy()
    return np.concatenate([np.full(frames, signal[0]), signal[:-frames]])


# --------------------------------------------------------------------------
# channels
# --------------------------------------------------------------------------


class Motion:
    def __init__(self, scene: Scene, total: int, fps: float) -> None:
        self.scene, self.total, self.fps = scene, total, fps
        self.tracks: dict[tuple[str, str], np.ndarray] = {}

    def track(self, oid: str, param: str) -> np.ndarray:
        key = (oid, param)
        if key not in self.tracks:
            base = self.scene.object(oid).curve(param).default
            self.tracks[key] = np.full(self.total, base, dtype=float)
        return self.tracks[key]

    def add(self, oid: str, param: str, start: int, values) -> None:
        tr = self.track(oid, param)
        values = np.asarray(values, dtype=float)
        a = max(0, start)
        b = min(self.total, start + len(values))
        if b > a:
            tr[a:b] += values[a - start:b - start]

    def add_all(self, oid: str, param: str, values: np.ndarray) -> None:
        self.track(oid, param)[:] += values[:self.total]

    def mul(self, oid: str, param: str, start: int, values) -> None:
        tr = self.track(oid, param)
        values = np.asarray(values, dtype=float)
        a, b = max(0, start), min(self.total, start + len(values))
        if b > a:
            tr[a:b] *= values[a - start:b - start]

    def set(self, oid: str, param: str, start: int, values) -> None:
        tr = self.track(oid, param)
        values = np.asarray(values, dtype=float)
        a, b = max(0, start), min(self.total, start + len(values))
        if b > a:
            tr[a:b] = values[a - start:b - start]

    def copy(self, src: str, dst: str) -> None:
        for (oid, param), tr in list(self.tracks.items()):
            if oid == src:
                self.tracks[(dst, param)] = tr.copy()

    def bake(self) -> int:
        """Writes every channel into its stage object curve; returns key count."""
        n_keys = 0
        for (oid, param), tr in self.tracks.items():
            curve = self.scene.object(oid).curve(param)
            curve.clear()
            if np.ptp(tr) < TOL.get(param, 0.001) * 0.5:
                curve.default = float(tr[0])
                continue
            for f in reduce_keys(tr, TOL.get(param, 0.001)):
                curve.set_key(int(f), float(tr[f]), 'linear')
                n_keys += 1
        return n_keys


def reduce_keys(values: np.ndarray, tol: float) -> list[int]:
    """Ramer-Douglas-Peucker on (frame, value): frames whose linear
    interpolation reproduces the curve within ``tol``."""
    n = len(values)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        xs = np.arange(a + 1, b)
        line = values[a] + (values[b] - values[a]) * (xs - a) / (b - a)
        err = np.abs(values[a + 1:b] - line)
        i = int(np.argmax(err))
        if err[i] > tol:
            m = a + 1 + i
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return list(np.nonzero(keep)[0])


def noise(n: int, rng: np.random.Generator, period: float) -> np.ndarray:
    """Smooth value noise in [-1, 1] with features every ``period`` frames."""
    k = max(2, int(n / period) + 3)
    pts = rng.uniform(-1, 1, k)
    xs = np.arange(n) / period
    i = np.floor(xs).astype(int)
    t = xs - i
    t = t * t * (3 - 2 * t)
    return pts[i] * (1 - t) + pts[i + 1] * t
