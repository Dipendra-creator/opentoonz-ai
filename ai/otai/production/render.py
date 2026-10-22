"""Renders a whole production to MP4.

1. every shot is compiled and saved as its OpenToonz scene (.tnz), in parallel;
2. the saved scenes are loaded back and rendered in fixed-size frame chunks
   spread over all CPU cores (so the video is rendered from the real .tnz
   files, and long shots do not serialise the render);
3. chunks are concatenated and muxed with the mixed dialogue track.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..render.compositor import Compositor
from ..render.video import SAMPLE_RATE, concat_videos, decode_audio, mux, write_wav
from ..tnz.model import Scene
from .studio import Studio

FADE_FRAMES = 12
CHUNK = 144


def _transition_post(transition: str, total: int, last: bool):
    def post(frame: int, img: Image.Image) -> Image.Image:
        a = 0.0
        color = (0, 0, 0)
        if transition in ('fade', 'dissolve') and frame < FADE_FRAMES:
            a = 1 - frame / FADE_FRAMES
        elif transition == 'fade_white' and frame < FADE_FRAMES:
            a, color = 1 - frame / FADE_FRAMES, (255, 255, 255)
        elif transition == 'flash' and frame < 3:
            a, color = 0.9 - 0.3 * frame, (255, 255, 255)
        if last and frame >= total - FADE_FRAMES:
            a = max(a, (frame - (total - FADE_FRAMES)) / FADE_FRAMES)
            color = (0, 0, 0)
        if a <= 0:
            return img
        over = Image.new('RGBA', img.size, color + (int(255 * min(a, 1.0)),))
        out = img.copy()
        out.alpha_composite(over)
        return out
    return post


def compile_shot(root: str, pid: str, shot_id: str) -> tuple[str, dict]:
    """Worker: build one shot and save its .tnz."""
    studio = Studio(Path(root))
    prod = studio.load(pid)
    shot = next(s for s in prod.shots if s.id == shot_id)
    scene, timing = studio.scene_for(prod, shot)
    scene.save(scene.path)
    timing['tnz'] = str(scene.path)
    return shot_id, timing


@lru_cache(maxsize=4)
def _scene(path: str, mtime: float) -> Scene:
    return Scene.load(path)


def render_chunk(tnz: str, out: str, start: int, end: int, size: tuple[int, int],
                 transition: str, total: int, last: bool, crf: int) -> str:
    """Worker: render frames [start, end) of a saved scene to an MP4 chunk."""
    scene = _scene(tnz, os.path.getmtime(tnz))
    comp = Compositor(scene, Path(tnz).parent, size=size, vignette=0.22)
    comp.render_to_video(Path(out), frames=range(start, end),
                         post=_transition_post(transition, total, last), crf=crf)
    return out


def mix_audio(studio: Studio, pid: str, shot_frames: dict[str, int]) -> Path | None:
    prod = studio.load(pid)
    fps = prod.settings.fps
    total_frames = sum(shot_frames[s.id] for s in prod.shots)
    n = int(total_frames / fps * SAMPLE_RATE) + SAMPLE_RATE
    mixbuf = np.zeros(n, dtype=np.float32)
    offset = 0
    any_audio = False
    for shot in prod.shots:
        timing = prod.timings.get(shot.id, {})
        for path, start in timing.get('audio', []):
            if not path or not Path(path).exists():
                continue
            pcm = decode_audio(Path(path))
            a = int((offset + start) / fps * SAMPLE_RATE)
            b = min(n, a + len(pcm))
            mixbuf[a:b] += pcm[:b - a]
            any_audio = True
        offset += shot_frames[shot.id]
    if not any_audio:
        return None
    peak = float(np.abs(mixbuf).max()) or 1.0
    if peak > 0.98:
        mixbuf *= 0.98 / peak
    out = studio.dir(pid) / 'render' / 'audio.wav'
    write_wav(out, mixbuf[:int(total_frames / fps * SAMPLE_RATE)])
    return out


def render_production(studio: Studio, pid: str, progress: Callable[[dict], None] | None = None,
                      workers: int | None = None, crf: int = 20) -> Path:
    prod = studio.load(pid)
    if not prod.shots:
        raise ValueError('production has no shots')
    status_path = studio.dir(pid) / 'render' / 'status.json'
    seg_dir = studio.dir(pid) / 'render' / 'segments'
    seg_dir.mkdir(parents=True, exist_ok=True)
    for old in seg_dir.glob('*.mp4'):
        old.unlink()
    t0 = time.time()
    workers = workers or max(1, (os.cpu_count() or 2) - 1)

    def report(**kw):
        state = {'production': pid, 'elapsed': round(time.time() - t0, 1), **kw}
        status_path.write_text(json.dumps(state), encoding='utf-8')
        if progress:
            progress(state)

    timings: dict[str, dict] = {}
    report(phase='compiling', done=0, total=len(prod.shots))
    with ProcessPoolExecutor(workers) as ex:
        futs = [ex.submit(compile_shot, str(studio.root), pid, s.id) for s in prod.shots]
        for fut in as_completed(futs):
            sid, timing = fut.result()
            timings[sid] = timing
            report(phase='compiling', done=len(timings), total=len(prod.shots))
    prod = studio.load(pid)
    prod.timings.update(timings)
    studio.save(prod)

    size = prod.settings.size
    last_id = prod.shots[-1].id
    jobs = []
    for s in prod.shots:
        n = timings[s.id]['frames']
        for a in range(0, n, CHUNK):
            out = seg_dir / ('%s_%05d.mp4' % (s.id, a))
            jobs.append((timings[s.id]['tnz'], str(out), a, min(n, a + CHUNK), size, s.transition, n,
                         s.id == last_id, crf))
    total_frames = sum(timings[s.id]['frames'] for s in prod.shots)
    frames_done = 0
    report(phase='rendering', done=0, total=len(prod.shots), frames=0, total_frames=total_frames)
    with ProcessPoolExecutor(workers) as ex:
        futs = {ex.submit(render_chunk, *j): j for j in jobs}
        for fut in as_completed(futs):
            fut.result()
            j = futs[fut]
            frames_done += j[3] - j[2]
            report(phase='rendering', done=round(len(prod.shots) * frames_done / total_frames, 1),
                   total=len(prod.shots), frames=frames_done, total_frames=total_frames)
    report(phase='audio', done=len(prod.shots), total=len(prod.shots))
    video = studio.dir(pid) / 'render' / 'video.mp4'
    concat_videos([Path(j[1]) for j in jobs], video)
    audio = mix_audio(studio, pid, {s.id: timings[s.id]['frames'] for s in prod.shots})
    final = studio.dir(pid) / 'render' / 'final.mp4'
    mux(video, audio, final)
    report(phase='done', done=len(prod.shots), total=len(prod.shots), output=str(final),
           frames=total_frames, total_frames=total_frames)
    return final
