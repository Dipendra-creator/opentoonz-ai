"""Production storage and operations (used by the MCP server and web app).

Layout of a production folder::

    <id>/production.json            settings, cast, sets, shots, timings
    <id>/scenes/<shot>.tnz          one OpenToonz scene per shot
    <id>/scenes/assets/characters/  cutout rig levels (PNG sequences)
    <id>/scenes/assets/backgrounds/ background plates
    <id>/scenes/assets/captions/    subtitle / title levels
    <id>/audio/                     cached speech
    <id>/render/                    previews, segments, final.mp4
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..art.background import BackgroundDesign, build_background
from ..art.character import CharacterDesign, build_character, preview_sheet
from ..audio.tts import Speech, narrator_voice, pick_voice, synthesize
from ..config import font_path, productions_dir
from ..render.compositor import Compositor
from .director import ShotCompiler
from .schema import BackgroundSpec, CharacterSpec, Production, Settings, Shot

_LOCK = threading.RLock()


def _locked(fn):
    """Serialises read-modify-write of production.json (MCP tools can run concurrently)."""
    def wrapper(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


def slugify(s: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s[:40] or 'production'


class Studio:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else productions_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- persistence ----------------------------------------------------------
    def dir(self, pid: str) -> Path:
        d = self.root / pid
        if not d.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('bad production id')
        return d

    def create(self, title: str, story: str = '', **settings) -> Production:
        base = slugify(title)
        pid = base
        n = 2
        while (self.root / pid).exists():
            pid = '%s-%d' % (base, n)
            n += 1
        prod = Production(id=pid, settings=Settings(title=title, **settings), story=story)
        for sub in ('scenes/assets/characters', 'scenes/assets/backgrounds', 'audio', 'render'):
            (self.dir(pid) / sub).mkdir(parents=True, exist_ok=True)
        self.save(prod)
        return prod

    def load(self, pid: str) -> Production:
        path = self.dir(pid) / 'production.json'
        if not path.exists():
            raise FileNotFoundError('production %r not found' % pid)
        return Production.model_validate_json(path.read_text(encoding='utf-8'))

    def save(self, prod: Production) -> None:
        with _LOCK:
            path = self.dir(prod.id) / 'production.json'
            tmp = path.with_suffix('.tmp')
            tmp.write_text(prod.model_dump_json(indent=1), encoding='utf-8')
            tmp.replace(path)

    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if (d / 'production.json').exists():
                try:
                    p = self.load(d.name)
                except Exception:
                    continue
                out.append({'id': p.id, 'title': p.settings.title, 'shots': len(p.shots),
                            'seconds': self.runtime(p),
                            'final': (d / 'render' / 'final.mp4').exists()})
        return out

    # -- cast and sets ---------------------------------------------------
    def add_character(self, pid: str, spec: CharacterSpec) -> dict:
        prod = self.load(pid)
        design = CharacterDesign(
            name=spec.name, style=prod.settings.style, gender=spec.gender, age=spec.age,
            skin_tone=spec.skin_tone, hair_style=spec.hair_style, hair_color=spec.hair_color,
            eye_color=spec.eye_color, top=spec.top, top_color=spec.top_color, bottom=spec.bottom,
            bottom_color=spec.bottom_color, shoe_color=spec.shoe_color,
            accent_color=spec.accent_color, accessories=list(spec.accessories),
            height=spec.height, build=spec.build)
        folder = self.char_dir(pid, spec.name)
        for old in folder.glob('*.png') if folder.exists() else []:
            old.unlink()
        manifest = build_character(design, folder, prefix=_slug(spec.name))
        prev = preview_sheet(manifest, folder, self.dir(pid) / 'render' / ('cast_%s.png' % _slug(spec.name)))
        with _LOCK:  # tools may run concurrently: re-read and update atomically
            prod = self.load(pid)
            prod.characters[spec.name] = spec
            if spec.voice:
                prod.voices[spec.name] = [spec.voice, spec.voice_pitch or '+0Hz']
            else:
                same = [n for n, c in prod.characters.items()
                        if n != spec.name and c.gender == spec.gender and (c.age == 'child') == (spec.age == 'child')]
                voice, pitch = pick_voice(prod.settings.language, spec.gender, spec.age, len(same))
                prod.voices[spec.name] = [voice, spec.voice_pitch or pitch]
            self.save(prod)
        return {'name': spec.name, 'voice': prod.voices[spec.name], 'preview': str(prev),
                'height_in': round(manifest['height'], 2)}

    def char_dir(self, pid: str, name: str) -> Path:
        return self.dir(pid) / 'scenes' / 'assets' / 'characters' / _slug(name)

    def manifest(self, pid: str, name: str) -> dict:
        return json.loads((self.char_dir(pid, name) / 'rig.json').read_text(encoding='utf-8'))

    def add_background(self, pid: str, spec: BackgroundSpec) -> dict:
        self.load(pid)  # fail early on a bad id
        info = build_background(
            BackgroundDesign(spec.name, spec.location, spec.time_of_day, spec.wall_color,
                             spec.accent_color),
            self.dir(pid) / 'scenes' / 'assets' / 'backgrounds', 'bg_' + _slug(spec.name))
        with _LOCK:
            prod = self.load(pid)
            prod.backgrounds[spec.name] = spec
            self.save(prod)
        return {'name': spec.name, **info}

    # -- shots ------------------------------------------------------------
    def validate_shot(self, prod: Production, shot: Shot) -> list[str]:
        errors = []
        if shot.background not in prod.backgrounds:
            errors.append('unknown background %r (add it first; have %s)'
                          % (shot.background, sorted(prod.backgrounds)))
        names = [c.name for c in shot.characters]
        for n in names:
            if n not in prod.characters:
                errors.append('unknown character %r (have %s)' % (n, sorted(prod.characters)))
        if len(set(names)) != len(names):
            errors.append('a character appears twice in the same shot')
        if shot.focus and shot.focus not in names:
            errors.append('focus %r is not in the shot' % shot.focus)
        for i, b in enumerate(shot.beats):
            if b.kind == 'dialogue' and not b.character:
                errors.append('beat %d: dialogue needs a character' % i)
            if b.character and b.character not in prod.characters:
                errors.append('beat %d: unknown character %r' % (i, b.character))
            if b.kind in ('dialogue', 'narration') and not b.text.strip():
                errors.append('beat %d: %s needs text' % (i, b.kind))
            if b.target and b.target not in names:
                errors.append('beat %d: target %r is not in the shot' % (i, b.target))
        return errors

    def speech_for_beat(self, prod: Production, b) -> tuple[str, str, str] | None:
        if b.kind == 'dialogue' and b.text.strip():
            voice, pitch = prod.voices.get(b.character, [narrator_voice(prod.settings.language), '+0Hz'])
            rate = prod.characters[b.character].voice_rate if b.character in prod.characters else '+0%'
            if b.emotion in ('excited', 'furious', 'shocked', 'scared'):
                rate = _add_pct(rate, 8)
            elif b.emotion in ('sad', 'tired', 'sleepy', 'crying'):
                rate = _add_pct(rate, -10)
            return voice, pitch, rate
        if b.kind == 'narration' and b.text.strip():
            return (prod.settings.narrator_voice or narrator_voice(prod.settings.language)), '+0Hz', '-4%'
        return None

    def synthesize_shots(self, prod: Production, shots: list[Shot]) -> dict[tuple[str, int], Speech]:
        jobs = {}
        for shot in shots:
            for i, b in enumerate(shot.beats):
                v = self.speech_for_beat(prod, b)
                if v:
                    jobs[(shot.id, i)] = (b.text, *v)
        audio_dir = self.dir(prod.id) / 'audio'
        engine = prod.settings.tts_engine

        def run(item):
            k, (text, voice, pitch, rate) = item
            return k, synthesize(text, voice, audio_dir, engine, rate=rate, pitch=pitch)

        with ThreadPoolExecutor(6) as ex:
            return dict(ex.map(run, jobs.items()))

    @_locked
    def add_shots(self, pid: str, shots: list[Shot], replace: bool = False) -> dict:
        prod = self.load(pid)
        if replace:
            for s in prod.shots:
                (self.dir(pid) / 'scenes' / ('%s.tnz' % s.id)).unlink(missing_ok=True)
            prod.shots = []
            prod.timings = {}
        existing = {s.id for s in prod.shots}
        n = len(prod.shots)
        errors = {}
        accepted = []
        for k, shot in enumerate(shots):
            if not shot.id or shot.id in existing:
                n += 1
                while 's%03d' % n in existing:
                    n += 1
                shot.id = 's%03d' % n
            existing.add(shot.id)
            errs = self.validate_shot(prod, shot)
            if errs:
                errors['#%d' % k] = errs
            else:
                accepted.append(shot)
        speech = self.synthesize_shots(prod, accepted)
        report = []
        for shot in accepted:
            timing = self.compile(prod, shot, {i: speech[(shot.id, i)] for i in range(len(shot.beats))
                                               if (shot.id, i) in speech})
            prod.shots.append(shot)
            prod.timings[shot.id] = timing
            report.append({'id': shot.id, 'seconds': timing['seconds']})
        self.save(prod)
        return {'added': report, 'rejected': errors, 'total_seconds': self.runtime(prod),
                'shot_count': len(prod.shots)}

    @_locked
    def update_shot(self, pid: str, shot_id: str, shot: Shot) -> dict:
        prod = self.load(pid)
        idx = next((i for i, s in enumerate(prod.shots) if s.id == shot_id), None)
        if idx is None:
            raise KeyError('no shot %r' % shot_id)
        shot.id = shot_id
        errs = self.validate_shot(prod, shot)
        if errs:
            return {'rejected': errs}
        speech = self.synthesize_shots(prod, [shot])
        timing = self.compile(prod, shot, {i: speech[(shot.id, i)] for i in range(len(shot.beats))
                                           if (shot.id, i) in speech})
        prod.shots[idx] = shot
        prod.timings[shot.id] = timing
        self.save(prod)
        return {'updated': shot_id, 'seconds': timing['seconds'], 'total_seconds': self.runtime(prod)}

    @_locked
    def delete_shot(self, pid: str, shot_id: str) -> dict:
        prod = self.load(pid)
        prod.shots = [s for s in prod.shots if s.id != shot_id]
        prod.timings.pop(shot_id, None)
        tnz = self.dir(pid) / 'scenes' / ('%s.tnz' % shot_id)
        tnz.unlink(missing_ok=True)
        self.save(prod)
        return {'deleted': shot_id, 'total_seconds': self.runtime(prod)}

    @_locked
    def reorder(self, pid: str, ids: list[str]) -> dict:
        prod = self.load(pid)
        by_id = {s.id: s for s in prod.shots}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise KeyError('unknown shots %s' % missing)
        rest = [s for s in prod.shots if s.id not in ids]
        prod.shots = [by_id[i] for i in ids] + rest
        self.save(prod)
        return {'order': [s.id for s in prod.shots]}

    # -- compiling ---------------------------------------------------------
    def compile(self, prod: Production, shot: Shot, speeches: dict[int, Speech] | None = None,
                save: bool = True):
        if speeches is None:
            speeches = self.cached_speeches(prod, shot)
        manifests = {c.name: self.manifest(prod.id, c.name) for c in shot.characters}
        scenes = self.dir(prod.id) / 'scenes'
        compiler = ShotCompiler(prod, shot, manifests, speeches, scenes)
        scene, timing = compiler.build()
        scene.path = scenes / ('%s.tnz' % shot.id)
        if save:
            scene.save(scene.path)
        timing['tnz'] = str(scene.path)
        return (scene, timing) if not save else timing

    def scene_for(self, prod: Production, shot: Shot):
        speeches = self.cached_speeches(prod, shot)
        manifests = {c.name: self.manifest(prod.id, c.name) for c in shot.characters}
        scenes = self.dir(prod.id) / 'scenes'
        scene, timing = ShotCompiler(prod, shot, manifests, speeches, scenes).build()
        scene.path = scenes / ('%s.tnz' % shot.id)
        return scene, timing

    def cached_speeches(self, prod: Production, shot: Shot) -> dict[int, Speech]:
        audio_dir = self.dir(prod.id) / 'audio'
        out = {}
        for i, b in enumerate(shot.beats):
            v = self.speech_for_beat(prod, b)
            if v:
                out[i] = synthesize(b.text, v[0], audio_dir, prod.settings.tts_engine, rate=v[2], pitch=v[1])
        return out

    def runtime(self, prod: Production) -> float:
        return round(sum(prod.timings.get(s.id, {}).get('seconds', 0) for s in prod.shots), 2)

    # -- previews ----------------------------------------------------------------
    def preview(self, pid: str, shot_id: str, at: float = 0.5, size=(960, 540)) -> Path:
        prod = self.load(pid)
        shot = next((s for s in prod.shots if s.id == shot_id), None)
        if shot is None:
            raise KeyError('no shot %r' % shot_id)
        scene, timing = self.scene_for(prod, shot)
        frame = int(min(max(at, 0.0), 1.0) * (timing['frames'] - 1)) if at <= 1.0 else int(at * prod.settings.fps)
        frame = min(frame, timing['frames'] - 1)
        out = self.dir(pid) / 'render' / ('preview_%s_%04d.png' % (shot_id, frame))
        Compositor(scene, scene.path.parent, size=size, vignette=0.22).render_png(frame, out)
        return out

    def contact_sheet(self, pid: str, cols: int = 4, tile=(384, 216)) -> Path:
        prod = self.load(pid)
        shots = prod.shots
        rows = max(1, math.ceil(len(shots) / cols))
        sheet = Image.new('RGB', (cols * tile[0], rows * (tile[1] + 28)), (24, 24, 30))
        font = ImageFont.truetype(font_path('latin'), 16)
        d = ImageDraw.Draw(sheet)
        for i, shot in enumerate(shots):
            scene, timing = self.scene_for(prod, shot)
            mid = timing['frames'] // 2
            img = Compositor(scene, scene.path.parent, size=tile, vignette=0.22).render(mid).convert('RGB')
            x, y = (i % cols) * tile[0], (i // cols) * (tile[1] + 28)
            sheet.paste(img, (x, y))
            label = '%s  %.1fs  %s' % (shot.id, timing['seconds'], shot.shot_type)
            d.text((x + 6, y + tile[1] + 5), label, fill=(230, 230, 240), font=font)
        out = self.dir(pid) / 'render' / 'contact_sheet.png'
        sheet.save(out)
        return out

    def thumbnail(self, pid: str, shot_id: str | None = None, text: str = '', at: float = 0.55) -> Path:
        """YouTube thumbnail: the most extreme reaction close-up, boosted colour,
        and up to 3 huge words."""
        from PIL import ImageEnhance
        from ..art.text import render_caption
        prod = self.load(pid)
        if not prod.shots:
            raise ValueError('production has no shots')
        strong = {'shocked': 5, 'surprised': 4, 'scared': 4, 'furious': 4, 'crying': 4, 'angry': 3,
                  'love': 3, 'embarrassed': 3, 'laugh': 2, 'excited': 2}
        close = {'extreme_closeup': 3, 'closeup': 2, 'medium': 1}

        def score(s):
            emo = max([strong.get(b.emotion or '', 0) for b in s.beats] +
                      [strong.get(c.emotion, 0) for c in s.characters])
            return emo * 2 + close.get(s.shot_type, 0) + (1 if s.characters else -5)

        shot = next((s for s in prod.shots if s.id == shot_id), None) if shot_id else max(prod.shots, key=score)
        scene, timing = self.scene_for(prod, shot)
        for col in scene.columns:  # no subtitles or titles on a thumbnail
            if col.name in ('captions', 'title', 'text_pops'):
                col.cells.clear()
        frame = min(timing['frames'] - 1, int(at * (timing['frames'] - 1)))
        img = Compositor(scene, scene.path.parent, size=(1280, 720), vignette=0.35).render(frame).convert('RGB')
        img = ImageEnhance.Color(img).enhance(1.3)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        words = ' '.join((text or prod.settings.title).split()[:3]).upper()
        if words:
            tmp = self.dir(pid) / 'render' / '_thumb_text.png'
            render_caption(words, (1180, 300), tmp, 'pop')
            label = Image.open(tmp).convert('RGBA').rotate(4, expand=True, resample=Image.Resampling.BICUBIC)
            base = img.convert('RGBA')
            base.alpha_composite(label, (int((1280 - label.width) / 2), 720 - label.height + 20))
            img = base.convert('RGB')
            tmp.unlink(missing_ok=True)
        out = self.dir(pid) / 'render' / 'thumbnail.png'
        img.save(out)
        return out

    def summary(self, pid: str) -> dict:
        prod = self.load(pid)
        return {
            'id': prod.id, 'settings': prod.settings.model_dump(),
            'characters': {n: {'voice': prod.voices.get(n), 'gender': c.gender, 'age': c.age,
                               'look': '%s %s hair, %s %s, %s %s' % (c.hair_color, c.hair_style, c.top_color,
                                                                  c.top, c.bottom_color, c.bottom)}
                           for n, c in prod.characters.items()},
            'backgrounds': {n: '%s (%s)' % (b.location, b.time_of_day) for n, b in prod.backgrounds.items()},
            'shots': [{'id': s.id, 'seconds': prod.timings.get(s.id, {}).get('seconds'),
                       'background': s.background, 'type': s.shot_type,
                       'characters': [c.name for c in s.characters], 'beats': len(s.beats)}
                      for s in prod.shots],
            'total_seconds': self.runtime(prod),
            'target_seconds': prod.settings.target_minutes * 60,
            'folder': str(self.dir(pid)),
        }


def _slug(s: str) -> str:
    out = ''.join(ch.lower() if ch.isalnum() else '_' for ch in s).strip('_')
    return out or 'x'


def _add_pct(rate: str, delta: int) -> str:
    try:
        v = int(rate.strip('%').replace('+', ''))
    except ValueError:
        v = 0
    v += delta
    return ('+%d%%' % v) if v >= 0 else ('%d%%' % v)
