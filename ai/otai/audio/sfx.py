"""Synthesised cartoon sound effects (no sample library needed).

Every effect is generated with numpy at SAMPLE_RATE, mono float32 in [-1, 1].
Placement rules from the retention playbook live in ``plan_sfx``: one effect
every few seconds at most, no repeat of the same effect within 20 s (except
footsteps), and at most two "boom" hits per video.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from ..render.video import SAMPLE_RATE

SR = SAMPLE_RATE


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _env(n: int, attack: float = 0.004, decay: float = 0.2) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def _sweep(f0: float, f1: float, seconds: float, curve: str = 'exp') -> np.ndarray:
    t = _t(seconds)
    k = t / seconds
    f = f0 * (f1 / f0) ** k if curve == 'exp' else f0 + (f1 - f0) * k
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """One-pole low-pass; ``cutoff`` may be a per-sample array (Hz)."""
    cut = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = np.exp(-2 * np.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def _noise(seconds: float, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1, 1, int(seconds * SR))


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.abs(x).max() or 1.0
    return (x / m * peak).astype(np.float32)


@lru_cache(maxsize=None)
def make(name: str) -> np.ndarray:
    if name == 'pop':
        x = _sweep(1100, 280, 0.09) * _env(int(0.09 * SR), 0.001, 0.03)
        return _norm(x, 0.8)
    if name == 'boing':
        t = _t(0.55)
        f = 170 + 230 * (1 - np.exp(-t * 6)) + 40 * np.sin(2 * np.pi * 16 * t) * np.exp(-t * 4)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.003, 0.22)
        return _norm(x, 0.8)
    if name in ('whoosh', 'swish'):
        dur = 0.45 if name == 'whoosh' else 0.18
        n = _noise(dur, 3)
        t = _t(dur)
        bell = np.sin(np.pi * t / dur) ** 2
        cut = 300 + 2600 * bell
        x = _lowpass(n, cut) * bell
        return _norm(x, 0.7 if name == 'whoosh' else 0.45)
    if name == 'boom':
        t = _t(1.1)
        body = np.sin(2 * np.pi * np.cumsum(55 + 40 * np.exp(-t * 10)) / SR)
        x = np.tanh(2.2 * body * np.exp(-t * 2.4)) + 0.3 * _lowpass(_noise(1.1, 7), 400) * np.exp(-t * 18)
        return _norm(x, 0.95)
    if name == 'thud':
        t = _t(0.25)
        x = np.sin(2 * np.pi * np.cumsum(110 * np.exp(-t * 6) + 50) / SR) * _env(len(t), 0.002, 0.07)
        return _norm(x + 0.2 * _lowpass(_noise(0.25, 5), 600) * np.exp(-t * 30), 0.8)
    if name == 'ding':
        t = _t(1.0)
        x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
                for f, a, d in ((1320, 1.0, 3.5), (2640, 0.45, 5), (3960, 0.2, 7), (1980, 0.25, 4)))
        return _norm(x * _env(len(t), 0.002, 10), 0.6)
    if name == 'twinkle':
        out = np.zeros(int(0.6 * SR))
        for i, f in enumerate((1568, 1976, 2349, 3136)):
            s = int(i * 0.09 * SR)
            b = np.sin(2 * np.pi * f * _t(0.25)) * _env(int(0.25 * SR), 0.002, 0.07)
            out[s:s + len(b)] += b[:len(out) - s]
        return _norm(out, 0.5)
    if name == 'scratch':
        t = _t(0.42)
        mod = np.sin(2 * np.pi * 9 * t)
        n = _lowpass(_noise(0.42, 11), 1800 + 1500 * mod)
        saw = 2 * ((np.cumsum(300 + 250 * mod) / SR) % 1.0) - 1
        x = (0.7 * n + 0.4 * saw) * np.abs(mod) * _env(len(t), 0.003, 0.3)
        return _norm(x, 0.75)
    if name in ('slide_up', 'slide_down'):
        f0, f1 = (420, 1500) if name == 'slide_up' else (1300, 360)
        x = _sweep(f0, f1, 0.5) * np.sin(np.pi * _t(0.5) / 0.5) ** 0.5
        return _norm(x, 0.45)
    if name == 'drip':
        a = _sweep(1600, 700, 0.07) * _env(int(0.07 * SR), 0.001, 0.03)
        b = _sweep(1300, 650, 0.06) * _env(int(0.06 * SR), 0.001, 0.025) * 0.6
        out = np.zeros(int(0.2 * SR))
        out[:len(a)] += a
        out[int(0.1 * SR):int(0.1 * SR) + len(b)] += b
        return _norm(out, 0.55)
    if name == 'tap':
        t = _t(0.06)
        x = _lowpass(_noise(0.06, 13), 900) * np.exp(-t * 70)
        return _norm(x, 0.35)
    raise KeyError('unknown sfx %r' % name)


NAMES = ['pop', 'boing', 'whoosh', 'swish', 'boom', 'thud', 'ding', 'twinkle', 'scratch',
         'slide_up', 'slide_down', 'drip', 'tap']
GAIN = {'tap': 0.35, 'swish': 0.45, 'boom': 0.75, 'twinkle': 0.55, 'pop': 0.55, 'ding': 0.5,
        'boing': 0.55, 'whoosh': 0.5, 'scratch': 0.6, 'thud': 0.6, 'drip': 0.5,
        'slide_up': 0.45, 'slide_down': 0.45}


def plan_sfx(events: list[tuple[float, str]], min_gap_same: float = 20.0, max_boom: int = 2,
             min_gap_any: float = 0.9) -> list[tuple[float, str]]:
    """Thins a list of (seconds, name) events following the playbook."""
    out: list[tuple[float, str]] = []
    last_by_name: dict[str, float] = {}
    last_any = -99.0
    booms = 0
    for t, name in sorted(events):
        if name not in NAMES:
            continue
        if name != 'tap':
            if t - last_by_name.get(name, -99.0) < min_gap_same:
                continue
            if t - last_any < min_gap_any:
                continue
            if name == 'boom':
                if booms >= max_boom:
                    continue
                booms += 1
            last_any = t
        last_by_name[name] = t
        out.append((t, name))
    return out
