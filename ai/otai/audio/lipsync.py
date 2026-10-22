"""Mouth shape timing from text + word timings (+ audio loudness)."""

from __future__ import annotations

import math
import unicodedata

import numpy as np

from ..render.video import SAMPLE_RATE, decode_audio

LATIN = {'a': 'A', 'e': 'E', 'i': 'I', 'o': 'O', 'u': 'U', 'y': 'I'}
DEVANAGARI = {
    'ा': 'A', 'ि': 'I', 'ी': 'I', 'ु': 'U', 'ू': 'U',
    'े': 'E', 'ै': 'E', 'ो': 'O', 'ौ': 'O',
    'अ': 'A', 'आ': 'A', 'इ': 'I', 'ई': 'I', 'उ': 'U',
    'ऊ': 'U', 'ए': 'E', 'ऐ': 'E', 'ओ': 'O', 'औ': 'O',
}


def vowel_shapes(word: str) -> list[str]:
    shapes = []
    for ch in word:
        low = ch.lower()
        if low in LATIN:
            shapes.append(LATIN[low])
            continue
        if ch in DEVANAGARI:
            if shapes and shapes[-1] == 'A' and 'ा' <= ch <= 'ौ':
                shapes[-1] = DEVANAGARI[ch]  # vowel sign replaces the inherent 'a'
            else:
                shapes.append(DEVANAGARI[ch])
            continue
        if 'क' <= ch <= 'ह':  # consonant with inherent vowel
            shapes.append('A')
            continue
        name = unicodedata.name(ch, '')
        if 'HIRAGANA' in name or 'KATAKANA' in name:
            last = name.split()[-1]
            if last and last[-1] in 'AIUEO' and 'SMALL' not in name:
                shapes.append(last[-1])
            continue
        if 'CJK UNIFIED' in name:
            shapes.append('AEIO'[len(shapes) % 4])
    # collapse runs of the same vowel
    out = []
    for s in shapes:
        if not out or out[-1] != s:
            out.append(s)
    return out or ['E']


def loudness(path: str | None, n_frames: int, fps: float) -> np.ndarray | None:
    if not path:
        return None
    try:
        pcm = decode_audio(path)
    except Exception:
        return None
    hop = SAMPLE_RATE / fps
    out = np.zeros(n_frames, dtype=np.float32)
    for f in range(n_frames):
        a, b = int(f * hop), int((f + 1) * hop)
        seg = pcm[a:b]
        out[f] = float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0
    peak = out.max() or 1.0
    return out / peak


def mouth_track(text: str, words: list, duration: float, fps: float,
                audio_path: str | None = None, hold: int = 3) -> list[str | None]:
    """Per-frame mouth shape ('A','I','U','E','O') or None (closed) for a
    spoken line lasting ``duration`` seconds."""
    n = max(1, int(math.ceil(duration * fps)))
    track: list[str | None] = [None] * n
    if not words:
        toks = text.split() or [text]
        if len(toks) == 1 and len(text) > 12:  # no spaces: chunk the characters
            toks = [text[i:i + 3] for i in range(0, len(text), 3)]
        total = sum(len(t) for t in toks) or 1
        t = 0.05
        speak = max(duration - 0.15, 0.2)
        words = []
        for tok in toks:
            d = speak * len(tok) / total
            words.append((t, t + d * 0.9, tok))
            t += d
    for start, end, w in words:
        f0 = int(start * fps)
        f1 = max(f0 + 1, int(end * fps))
        shapes = vowel_shapes(w)
        if w[:1].lower() in ('m', 'b', 'p'):
            shapes = ['M'] + shapes  # lips pressed on m/b/p
        span = max(1, f1 - f0)
        k = 0
        f = f0
        while f < f1 and f < n:
            idx = min(len(shapes) - 1, int((f - f0) / span * len(shapes)))
            shape = shapes[idx]
            for g in range(f, min(f + hold, f1, n)):
                track[g] = shape
            f += hold
            k += 1
    env = loudness(audio_path, n, fps)
    if env is not None:
        for f in range(n):
            if track[f] is not None and env[f] < 0.06:
                track[f] = None
    # avoid single-frame closures (flicker): fill gaps shorter than 2 frames
    for f in range(1, n - 1):
        if track[f] is None and track[f - 1] is not None and track[f + 1] is not None:
            track[f] = track[f - 1]
    return track
