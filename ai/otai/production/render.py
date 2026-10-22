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
from PIL import Image, ImageChops

from ..render.compositor import Compositor
from ..render.video import SAMPLE_RATE, concat_videos, decode_audio, mux, write_wav
from ..tnz.model import Scene
from .studio import Studio

FADE_FRAMES = 12
CHUNK = 144


@lru_cache(maxsize=4)
def _watermark(text: str, size: tuple[int, int]) -> Image.Image:
    from PIL import ImageDraw, ImageFont
    from ..config import font_path
    px = max(12, size[1] // 40)
    font = ImageFont.truetype(font_path('latin'), px)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size[0] - px, size[1] - px), text, font=font, anchor='rs',
                             fill=(255, 255, 255, 120), stroke_width=max(1, px // 10), stroke_fill=(0, 0, 0, 90))
    return img


def _transition_post(transition: str, total: int, last: bool, watermark: str | None = None):
    def post(frame: int, img: Image.Image) -> Image.Image:
        if watermark:
            img = img.copy()
            img.alpha_composite(_watermark(watermark, img.size))
        a = 0.0
        color = (0, 0, 0)
        if transition in ('fade', 'dissolve') and frame < FADE_FRAMES:
            a = 1 - frame / FADE_FRAMES
        elif transition == 'fade_white' and frame < FADE_FRAMES:
            a, color = 1 - frame / FADE_FRAMES, (255, 255, 255)
        elif transition == 'flash' and frame < 3:
            a, color = 0.9 - 0.3 * frame, (255, 255, 255)
        elif transition == 'whip' and frame < 6:
            # fast horizontal slide-in with motion blur
            off = int(img.width * 0.35 * (1 - frame / 6) ** 2)
            acc = None
            for k in range(5):
                shifted = ImageChops.offset(img, off + k * max(1, off // 6), 0)
                acc = shifted if acc is None else Image.blend(acc, shifted, 1 / (k + 1))
            img = acc
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
                 transition: str, total: int, last: bool, crf: int, freezes=(), grade: str = 'none',
                 watermark: str | None = None) -> str:
    """Worker: render frames [start, end) of a saved scene to an MP4 chunk.
    Frames inside a freeze window repeat the window's first frame."""
    scene = _scene(tnz, os.path.getmtime(tnz))
    comp = Compositor(scene, Path(tnz).parent, size=size, vignette=0.22, grade=grade)
    frames = []
    for f in range(start, end):
        src = f
        for a, n in freezes:
            if a <= f < a + n:
                src = a
        frames.append(src)
    comp.render_to_video(Path(out), frames=frames,
                         post=_transition_post(transition, total, last, watermark), crf=crf)
    return out


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def write_srt(prod, timings: dict, out: Path) -> Path:
    """Subtitles for YouTube (upload alongside the video)."""
    from ..art.text import chunk_caption
    fps = prod.settings.fps
    lines, offset, k = [], 0, 0
    for shot in prod.shots:
        t = timings[shot.id]
        for beat, (s, n) in zip(shot.beats, t['beats']):
            if beat.kind not in ('dialogue', 'narration') or not beat.text.strip():
                continue
            chunks = chunk_caption(beat.text)
            total_chars = sum(len(c) for c in chunks) or 1
            a = (offset + s) / fps
            span = n / fps
            for c in chunks:
                d = span * len(c) / total_chars
                k += 1
                speaker = ('%s: ' % beat.character) if beat.kind == 'dialogue' and beat.character else ''
                lines.append('%d\n%s --> %s\n%s%s\n' % (k, _srt_time(a), _srt_time(a + d), speaker,
                                                         c.replace('\n', ' ')))
                a += d
        offset += t['frames']
    out.write_text('\n'.join(lines), encoding='utf-8')
    return out


def _mood(prod, shot) -> str:
    mood = shot.music or prod.settings.music
    if mood == 'auto':
        mood = 'comedy' if prod.settings.style == 'cartoon' else 'warm'
    return mood


def mix_audio(studio: Studio, pid: str, shot_frames: dict[str, int]) -> Path | None:
    """Dialogue + planned sound effects + a mood music bed ducked under the
    voices. Loudness normalisation happens when muxing (-14 LUFS)."""
    from ..audio import music, sfx
    prod = studio.load(pid)
    fps = prod.settings.fps
    total_frames = sum(shot_frames[s.id] for s in prod.shots)
    n = int(total_frames / fps * SAMPLE_RATE) + SAMPLE_RATE
    voice = np.zeros(n, dtype=np.float32)
    effects = np.zeros(n, dtype=np.float32)
    bed = np.zeros(n, dtype=np.float32)
    events = []
    offset = 0
    runs: list[list] = []  # [mood, start_frame, end_frame]
    for shot in prod.shots:
        timing = prod.timings.get(shot.id, {})
        for path, start in timing.get('audio', []):
            if not path or not Path(path).exists():
                continue
            pcm = decode_audio(Path(path))
            a = int((offset + start) / fps * SAMPLE_RATE)
            b = min(n, a + len(pcm))
            voice[a:b] += pcm[:b - a]
        for f, name in timing.get('sfx', []):
            events.append(((offset + f) / fps, name))
        mood = _mood(prod, shot)
        if runs and runs[-1][0] == mood:
            runs[-1][2] = offset + shot_frames[shot.id]
        else:
            runs.append([mood, offset, offset + shot_frames[shot.id]])
        offset += shot_frames[shot.id]
    if prod.settings.sfx:
        for t, name in sfx.plan_sfx(events):
            clip = sfx.make(name) * sfx.GAIN.get(name, 0.5) * 0.55
            a = int(t * SAMPLE_RATE)
            b = min(n, a + len(clip))
            if a < n:
                effects[a:b] += clip[:b - a]
    cache = studio.root.parent / 'audio_cache'
    for mood, f0, f1 in runs:
        if mood == 'none':
            continue
        seg = music.bed(mood, (f1 - f0) / fps + 0.5, cache, fade=1.2)
        a = int(f0 / fps * SAMPLE_RATE)
        b = min(n, a + len(seg))
        bed[a:b] += seg[:b - a]
    if np.any(bed):
        bed = music.duck(bed * 0.26, voice + 0.5 * effects)
    mixbuf = voice + effects + bed
    if not np.any(mixbuf):
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
                         s.id == last_id, crf, [tuple(x) for x in timings[s.id].get('freezes', [])],
                         s.grade, prod.settings.watermark))
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
    write_srt(studio.load(pid), timings, studio.dir(pid) / 'render' / 'subtitles.srt')
    report(phase='done', done=len(prod.shots), total=len(prod.shots), output=str(final),
           frames=total_frames, total_frames=total_frames)
    return final
