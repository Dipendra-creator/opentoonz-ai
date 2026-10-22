"""Style-match benchmark: how close a rendered video's look and rhythm are to a
reference, measured on frames sampled once per second.

The metrics describe style only (light, colour, palette, line density, cut
rhythm), never content, so an original story can be scored against any
reference look.

    python -m otai.render.style_bench REFERENCE CANDIDATE [--json out.json]

REFERENCE and CANDIDATE are each a video file or a folder of frame images
(sorted by name, one frame per second).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SIZE = (320, 180)
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp'}

# metric -> (label, scale): the score drops linearly to 0 at a difference of ``scale``
METRICS = {
    'brightness': ('mean brightness', 0.25),
    'saturation': ('mean saturation', 0.25),
    'contrast': ('luminance contrast', 0.12),
    'warmth': ('warmth (red minus blue)', 0.15),
    'dark_frames': ('share of dark frames', 0.35),
    'edge_density': ('line / detail density', 0.06),
    'cuts_per_min': ('cuts per minute', 15.0),
}


def load_frames(src: Path) -> list[np.ndarray]:
    """RGB float frames at SIZE, one per second."""
    if src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXT)
        return [np.asarray(Image.open(p).convert('RGB').resize(SIZE, Image.Resampling.BILINEAR),
                           dtype=np.float32) / 255 for p in files]
    import imageio_ffmpeg
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-loglevel', 'error', '-i', str(src),
                        '-vf', 'fps=1,scale=%d:%d' % SIZE, str(Path(tmp) / 'f%05d.png')], check=True)
        return load_frames(Path(tmp))


def _hsv(frame: np.ndarray) -> np.ndarray:
    img = Image.fromarray((frame * 255).astype(np.uint8), 'RGB').convert('HSV')
    return np.asarray(img, dtype=np.float32) / 255


def measure(frames: list[np.ndarray]) -> dict:
    if not frames:
        raise ValueError('no frames')
    lum = [f @ np.array([0.299, 0.587, 0.114], dtype=np.float32) for f in frames]
    hsv = [_hsv(f) for f in frames]
    edges = []
    for l in lum:
        e = Image.fromarray((l * 255).astype(np.uint8), 'L').filter(ImageFilter.FIND_EDGES)
        edges.append(float((np.asarray(e) > 40).mean()))
    diffs = [float(np.abs(a - b).mean()) for a, b in zip(frames, frames[1:])]
    cuts = sum(d > 0.10 for d in diffs)
    hist = np.zeros((12, 4, 4))
    for h in hsv:
        q = np.minimum((h * [12, 4, 4]).astype(int), [11, 3, 3]).reshape(-1, 3)
        np.add.at(hist, (q[:, 0], q[:, 1], q[:, 2]), 1)
    return {
        'frames': len(frames),
        'brightness': float(np.mean([h[..., 2].mean() for h in hsv])),
        'saturation': float(np.mean([h[..., 1].mean() for h in hsv])),
        'contrast': float(np.mean([l.std() for l in lum])),
        'warmth': float(np.mean([(f[..., 0] - f[..., 2]).mean() for f in frames])),
        'dark_frames': float(np.mean([l.mean() < 0.15 for l in lum])),
        'edge_density': float(np.mean(edges)),
        'cuts_per_min': cuts / max(1, len(frames) - 1) * 60,
        'palette': (hist / hist.sum()).ravel().tolist(),
    }


def compare(ref: dict, cand: dict) -> dict:
    rows = {}
    for key, (label, scale) in METRICS.items():
        a, b = ref[key], cand[key]
        rows[key] = {'label': label, 'reference': round(a, 3), 'candidate': round(b, 3),
                     'score': round(100 * max(0.0, 1 - abs(a - b) / scale), 1)}
    palette = float(np.minimum(np.array(ref['palette']), np.array(cand['palette'])).sum())
    rows['palette'] = {'label': 'palette overlap (HSV histogram)', 'reference': '-', 'candidate': '-',
                       'score': round(100 * palette, 1)}
    overall = round(float(np.mean([r['score'] for r in rows.values()])), 1)
    return {'overall': overall, 'metrics': rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('reference', type=Path)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--json', type=Path)
    args = ap.parse_args()
    result = compare(measure(load_frames(args.reference)), measure(load_frames(args.candidate)))
    print('%-34s %10s %10s %6s' % ('metric', 'reference', 'candidate', 'score'))
    for r in result['metrics'].values():
        print('%-34s %10s %10s %6.1f' % (r['label'], r['reference'], r['candidate'], r['score']))
    print('%-34s %28.1f' % ('OVERALL', result['overall']))
    if args.json:
        args.json.write_text(json.dumps(result, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
