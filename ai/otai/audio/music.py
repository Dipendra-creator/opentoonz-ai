"""Procedural background music beds (royalty-free by construction).

Each mood is an 8-bar loop built from a chord progression with a
Karplus-Strong plucked arpeggio, a soft bass, a warm pad and light drums,
cached as a WAV. ``bed`` tiles a loop to any length; ``duck`` lowers it under
dialogue (side-chain style) so the voice always stays on top.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..render.video import SAMPLE_RATE, decode_audio, write_wav

SR = SAMPLE_RATE
MAJOR = {0: (0, 4, 7), 2: (0, 3, 7), 4: (0, 3, 7), 5: (0, 4, 7), 7: (0, 4, 7), 9: (0, 3, 7)}
MINOR = {0: (0, 3, 7), 3: (0, 4, 7), 5: (0, 3, 7), 7: (0, 4, 7), 8: (0, 4, 7), 10: (0, 4, 7)}

MOODS = {
    'comedy': dict(bpm=112, key=60, minor=False, prog=[0, 9, 5, 7], arp=[0, 1, 2, 3, 2, 1, 2, 1],
                   drums='bouncy', arp_div=2),
    'upbeat': dict(bpm=124, key=67, minor=False, prog=[0, 7, 9, 5], arp=[0, 2, 1, 3, 0, 2, 1, 2],
                   drums='pop', arp_div=2),
    'warm': dict(bpm=86, key=65, minor=False, prog=[0, 5, 9, 7], arp=[0, 1, 2, 1], drums='soft', arp_div=1),
    'emotional': dict(bpm=70, key=57, minor=True, prog=[0, 8, 3, 10], arp=[0, 2, 3, 2], drums=None, arp_div=1),
    'tense': dict(bpm=96, key=50, minor=True, prog=[0, 0, 8, 7], arp=[0, 3, 0, 3, 0, 3, 0, 1],
                  drums='pulse', arp_div=2),
}


def _f(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _pluck(freq: float, dur: float, decay: float = 0.996, seed: int = 0) -> np.ndarray:
    """Karplus-Strong plucked string, processed one period at a time."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    buf = np.random.default_rng(seed).uniform(-1, 1, period)
    blocks = []
    for _ in range(n // period + 1):
        blocks.append(buf)
        buf = decay * 0.5 * (buf + np.roll(buf, -1))
    out = np.concatenate(blocks)[:n]
    fade = np.minimum(1, (n - np.arange(n)) / (0.02 * SR))
    return out * fade


def _tone(freq: float, dur: float, harmonics=((1, 1.0),), attack=0.01, release=0.2) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    x = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in harmonics)
    env = np.clip(t / attack, 0, 1) * np.clip((dur - t) / release, 0, 1)
    return x * env


def _kick(dur=0.22):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-t * 30)) / SR) * np.exp(-t * 14)


def _hat(dur=0.05, seed=3):
    t = np.arange(int(dur * SR)) / SR
    n = np.random.default_rng(seed).uniform(-1, 1, len(t))
    n = n - np.concatenate([[0], n[:-1]])  # crude high-pass
    return n * np.exp(-t * 80) * 0.5


def _snare(dur=0.16, seed=5):
    t = np.arange(int(dur * SR)) / SR
    n = np.random.default_rng(seed).uniform(-1, 1, len(t))
    return (0.7 * n + 0.5 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 26)


def _add(dst: np.ndarray, src: np.ndarray, at: int, gain: float) -> None:
    if at >= len(dst):
        return
    m = min(len(src), len(dst) - at)
    dst[at:at + m] += src[:m] * gain


def make_loop(mood: str) -> np.ndarray:
    m = MOODS[mood]
    beat = 60.0 / m['bpm']
    bars = 8
    n = int(bars * 4 * beat * SR)
    out = np.zeros(n)
    qual = MINOR if m['minor'] else MAJOR
    seed = 0
    for bar in range(bars):
        root_off = m['prog'][bar % len(m['prog'])]
        chord = [m['key'] + root_off + iv for iv in qual.get(root_off % 12, (0, 4, 7))]
        tones = chord + [chord[0] + 12]
        bar_start = int(bar * 4 * beat * SR)
        # pad
        pad = sum(_tone(_f(nn - 12), 4 * beat, ((1, 1.0), (2, 0.25)), attack=0.35, release=0.5) for nn in chord)
        _add(out, pad, bar_start, 0.05)
        # bass
        for b in range(0, 4, 2 if m['drums'] in (None, 'soft') else 1):
            bn = _tone(_f(chord[0] - 24), beat * (2 if m['drums'] in (None, 'soft') else 0.9),
                       ((1, 1.0), (2, 0.35)), attack=0.005, release=0.12)
            _add(out, np.tanh(1.5 * bn), bar_start + int(b * beat * SR), 0.22)
        # plucked arpeggio
        step = beat / m['arp_div']
        for i in range(4 * m['arp_div']):
            k = m['arp'][i % len(m['arp'])]
            if mood == 'comedy' and i % 8 == 7:
                continue  # a breath at the end of the bar
            seed += 1
            note = _pluck(_f(tones[k % len(tones)]), min(1.2, step * 3), 0.994, seed)
            _add(out, note, bar_start + int(i * step * SR), 0.16 if mood != 'emotional' else 0.2)
        # drums
        d = m['drums']
        for b in range(4):
            at = bar_start + int(b * beat * SR)
            if d in ('bouncy', 'pop'):
                if b in (0, 2):
                    _add(out, _kick(), at, 0.5)
                if b in (1, 3):
                    _add(out, _snare(), at, 0.16 if d == 'bouncy' else 0.22)
                for h in range(2):
                    _add(out, _hat(), at + int(h * beat / 2 * SR), 0.12)
            elif d == 'soft':
                if b == 0:
                    _add(out, _kick(), at, 0.3)
                _add(out, _hat(), at + int(beat / 2 * SR), 0.06)
            elif d == 'pulse':
                for h in range(2):
                    _add(out, _kick(0.15), at + int(h * beat / 2 * SR), 0.28 if h == 0 else 0.15)
    out /= np.abs(out).max() or 1.0
    return (out * 0.6).astype(np.float32)


def loop(mood: str, cache_dir: Path) -> np.ndarray:
    path = Path(cache_dir) / ('music_%s.wav' % mood)
    if path.exists():
        return decode_audio(path)
    x = make_loop(mood)
    write_wav(path, x)
    return x


def bed(mood: str, seconds: float, cache_dir: Path, fade: float = 1.5) -> np.ndarray:
    """Music of ``seconds`` length, looped with short crossfades."""
    lp = loop(mood, cache_dir)
    n = int(seconds * SR)
    xf = int(0.05 * SR)
    out = np.zeros(n, dtype=np.float32)
    pos = 0
    while pos < n:
        seg = lp[:min(len(lp), n - pos)].copy()
        if pos > 0:
            seg[:xf] *= np.linspace(0, 1, min(xf, len(seg)))
        out[pos:pos + len(seg)] += seg
        pos += len(lp) - xf
    f = int(min(fade, seconds / 4) * SR)
    if f:
        out[:f] *= np.linspace(0, 1, f)
        out[-f:] *= np.linspace(1, 0, f)
    return out


def _moving_average(x: np.ndarray, win: int) -> np.ndarray:
    """Centred moving average in O(n) (np.convolve is O(n * win))."""
    c = np.cumsum(np.concatenate([[0.0], x.astype(np.float64)]))
    half = win // 2
    idx = np.arange(len(x))
    a = np.clip(idx - half, 0, len(x))
    b = np.clip(idx + half + 1, 0, len(x))
    return ((c[b] - c[a]) / np.maximum(b - a, 1)).astype(np.float32)


def duck(music: np.ndarray, voice: np.ndarray, depth: float = 0.78) -> np.ndarray:
    """Side-chain style ducking: lower the music while the voice is active."""
    v = np.abs(voice[:len(music)])
    if len(v) < len(music):
        v = np.concatenate([v, np.zeros(len(music) - len(v))])
    env = _moving_average(v, int(0.05 * SR))
    thr = max(1e-4, np.percentile(env[env > 1e-4], 60) if np.any(env > 1e-4) else 1e-4)
    active = _moving_average(np.clip(env / thr, 0, 1), int(0.25 * SR))
    return music * (1 - depth * active)
