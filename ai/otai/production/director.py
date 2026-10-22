"""Compiles a Shot into an OpenToonz Scene with full cutout acting.

Transforms are animated on ones from layered procedural motion (see
motion.py): idle breathing/sway, speech-driven acting (head bobs on stressed
syllables, brow raises, gestures landing on stresses, listener nods), actions
with anticipation/overshoot/settle, squash & stretch with planted feet, 2-bone
walk cycles, and spring-driven secondary motion (hair, forearms, symbols).
Drawing swaps (mouth, eyes, hands) follow the classic cutout rules: lip sync
on twos one frame ahead of the audio, blinks every few seconds, eye darts.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..art.background import FLOOR_Y, PLATE_H, PLATE_W
from ..art.character import drawing_id, eye_name
from ..art.text import chunk_caption, render_caption
from ..audio.lipsync import loudness, mouth_track
from ..audio.tts import Speech
from ..tnz.model import Scene
from .motion import (Motion, ease_in_out, ease_out, lag, noise, pose_weight, sine_in_out,
                     spring_follow)
from .rigging import REST_ROT, CharacterRig, add_character_to_scene
from .schema import Beat, Production, Shot

STAGE_HALF = 6.2
NAMED_POS = {'far_left': -0.78, 'left': -0.42, 'center': 0.0, 'right': 0.42, 'far_right': 0.78}
AUTO_POS = {1: [0.0], 2: [-0.36, 0.36], 3: [-0.6, 0.0, 0.6], 4: [-0.72, -0.24, 0.24, 0.72],
            5: [-0.8, -0.4, 0.0, 0.4, 0.8]}

# emotion -> (eyes, brows, mouth at rest, symbol, blush)
EMOTIONS = {
    'neutral': ('open', 'neutral', 'rest', None, None),
    'happy': ('open', 'raised', 'smile', None, None),
    'laugh': ('happy', 'raised', 'grin', None, None),
    'excited': ('wide', 'raised', 'grin', 'sparkle', 'soft'),
    'sad': ('sad', 'sad', 'frown', 'gloom', None),
    'crying': ('squeeze', 'sad', 'wavy', 'tears', None),
    'angry': ('angry', 'angry', 'clench', 'vein', None),
    'furious': ('angry', 'angry', 'shout', 'steam', None),
    'surprised': ('wide', 'raised', 'O', 'exclaim', None),
    'shocked': ('blank', 'raised', 'shout', 'exclaim', None),
    'scared': ('wide', 'sad', 'wavy', 'sweat', None),
    'nervous': ('open', 'sad', 'wavy', 'sweat', None),
    'embarrassed': ('open', 'sad', 'wavy', 'sweat', 'lines'),
    'annoyed': ('half', 'flat', 'flat', 'dots', None),
    'confused': ('open', 'skeptic', 'flat', 'question', None),
    'thinking': ('open', 'skeptic', 'flat', 'dots', None),
    'love': ('heart', 'raised', 'smile', 'heart', 'soft'),
    'smug': ('half', 'raised', 'smirk', None, None),
    'determined': ('sharp', 'angry', 'flat', 'sparkle', None),
    'tired': ('half', 'sad', 'flat', None, None),
    'sleepy': ('closed', 'neutral', 'rest', 'zzz', None),
    'idea': ('wide', 'raised', 'smile', 'idea', None),
    'disgusted': ('sharp', 'angry', 'wavy', None, None),
    'hypnotized': ('hypno', 'raised', 'smile', None, None),
}
EMOTION_LOOK = {'embarrassed': 'd', 'thinking': 'u', 'annoyed': 'away', 'smug': 'away', 'tired': 'd'}
EMOTION_ACTION = {
    'surprised': 'take', 'shocked': 'big_take', 'excited': 'bounce', 'laugh': 'laugh',
    'nervous': 'shiver', 'scared': 'shiver', 'furious': 'shiver', 'sad': 'slump',
    'crying': 'slump', 'confused': 'head_tilt', 'idea': 'hop', 'thinking': 'think',
    'hypnotized': 'head_tilt',
}
LOUD = {'angry', 'furious', 'shocked'}
HAPPY = {'happy', 'laugh', 'excited', 'love'}
BLINKABLE = {'open', 'wide', 'sad', 'angry', 'sharp', 'half', 'heart'}

# arm poses: (upper angle, forearm angle, hand, foreshortened upper arm);
# degrees from hanging straight down, positive = away from the body
ARM_REST = (7.0, 2.0)
ARM_POSES = {
    'wave': (85.0, 172.0, 'open', False),
    'point': (78.0, 86.0, 'point', False),
    'hip': (40.0, -38.0, 'fist', False),
    'think': (14.0, -146.0, 'fist', True),
    'facepalm': (8.0, -165.0, 'open', True),
    'cross': (-4.0, -104.0, 'fist', False),
    'cheer': (158.0, 172.0, 'fist', False),
    'fist_pump': (22.0, 168.0, 'fist', False),
    'shrug': (28.0, 104.0, 'palm', False),
    'gesture': (18.0, 72.0, 'palm', False),
    'explain': (52.0, 96.0, 'palm', False),
    'chest': (6.0, -118.0, 'open', True),
    'clap': (10.0, -72.0, 'open', False),
    'flare': (38.0, 60.0, 'palm', False),
}
TALK_GESTURES = ['gesture', 'explain', 'chest', 'gesture', 'explain']
# sound effect played when an emotion symbol pops in
FX_SFX = {'exclaim': 'boing', 'question': 'pop', 'sparkle': 'twinkle', 'heart': 'pop', 'gloom': 'slide_down',
          'tears': 'drip', 'sweat': 'drip', 'steam': 'whoosh', 'notes': 'twinkle', 'idea': 'ding',
          'dots': 'pop', 'vein': 'pop'}


@dataclass
class CharState:
    rig: CharacterRig
    name: str
    x: float
    facing: str
    view: list
    flip: list
    eyes: list
    look: list
    brows: list
    mouth_rest: list
    mouth: list
    fx: list
    blush: list
    emotion: list
    hand: dict
    short: dict
    arm_busy: dict = field(default_factory=lambda: {'l': -1, 'r': -1})
    talk_count: int = 0
    walking: np.ndarray | None = None
    look_lock: list | None = None

    def oid(self, part: str) -> str:
        return self.rig.peg if part == 'peg' else self.rig.col_id(part)


class ShotCompiler:
    def __init__(self, prod: Production, shot: Shot, manifests: dict[str, dict],
                 speeches: dict[int, Speech], scenes_dir: Path) -> None:
        self.prod, self.shot = prod, shot
        self.manifests = manifests
        self.speeches = speeches
        self.scenes_dir = Path(scenes_dir)
        self.fps = prod.settings.fps
        seed = sum(map(ord, shot.id)) * 7919 + sum(map(ord, prod.id))
        self.rnd = random.Random(seed)
        self.rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    def timeline(self) -> tuple[list[tuple[int, int]], int]:
        fps = self.fps
        pad_in, pad_out, gap = round(0.25 * fps), round(0.4 * fps), round(0.3 * fps)
        f = pad_in
        beats = []
        for i, b in enumerate(self.shot.beats):
            if b.kind in ('dialogue', 'narration') and b.text.strip():
                sp = self.speeches.get(i)
                dur = sp.duration if sp else 2.0
                n = math.ceil(dur * fps) + gap
                if b.duration:
                    n = max(n, round(b.duration * fps))
            else:
                default = {'pause': 0.6, 'reaction': 1.4, 'action': 1.6}.get(b.kind, 1.2)
                n = round((b.duration or default) * fps)
            beats.append((f, max(n, 8)))
            f += max(n, 8)
        total = max(f + pad_out, round(1.2 * fps))
        return beats, total

    def build(self) -> tuple[Scene, dict]:
        shot, prod = self.shot, self.prod
        beats, total = self.timeline()
        self.total = total
        self.shakes: list[tuple[int, float]] = []
        self.sfx: list[tuple[int, str]] = []
        self.freezes: list[tuple[int, int]] = []
        scene = Scene(res=prod.settings.size, fps=self.fps)
        scene.output_path = '$scenefolder/render/%s..png' % shot.id
        self.scene = scene
        bg = prod.backgrounds[shot.background]
        bg_level = 'bg_' + _slug(bg.name)
        scene.add_level(bg_level, '$scenefolder/assets/backgrounds/%s..png' % bg_level, 120)
        _, col = scene.add_column('background')
        col.hold(0, total, bg_level, 1)
        self.motion = Motion(scene, total, self.fps)
        # tighter shots need smaller body moves or heads leave the frame
        self.k = {'closeup': 0.35, 'extreme_closeup': 0.2}.get(shot.shot_type, 1.0)
        self.place_characters()
        self.cam_base = self.frame_camera()
        self.apply_entrances()
        captions = []
        for i, (b, (s, ln)) in enumerate(zip(shot.beats, beats)):
            self.apply_beat(i, b, s, ln)
            if b.kind in ('dialogue', 'narration') and b.text.strip() and prod.settings.subtitles:
                captions.append((i, b, s, ln))
        for st in self.chars.values():
            self.idle(st)
            self.eye_life(st)
            self.secondary(st)
            self.keep_legs(st)
        self.add_text_pops([(s, ln, b.text_pop) for b, (s, ln) in zip(shot.beats, beats) if b.text_pop])
        self.camera(beats)
        for st in self.chars.values():
            self.motion.copy(st.oid('upper_r'), st.oid('upper_r_back'))
            self.motion.copy(st.oid('fore_r'), st.oid('fore_r_back'))
        n_keys = self.motion.bake()
        for st in self.chars.values():
            self.write_cells(st)
        self.add_captions(captions)
        if shot.title:
            self.add_title(shot.title)
        audio = [[self.speeches[i].path, s] for i, (s, ln) in enumerate(beats)
                 if self.speeches.get(i) and self.speeches[i].path]
        if shot.transition == 'whip':
            self.sfx.append((0, 'whoosh'))
        if shot.camera == 'zoom_snap':
            self.sfx.append((0, 'swish'))
        timing = {'frames': total, 'fps': self.fps, 'beats': [list(x) for x in beats],
                  'audio': audio, 'transition': shot.transition,
                  'sfx': sorted([int(f), n] for f, n in self.sfx if 0 <= f < total),
                  'freezes': [list(x) for x in self.freezes],
                  'seconds': round(total / self.fps, 2), 'keys': n_keys}
        return scene, timing

    # ------------------------------------------------------------------
    # characters
    # ------------------------------------------------------------------
    def place_characters(self) -> None:
        shot, total = self.shot, self.total
        self.chars: dict[str, CharState] = {}
        n = len(shot.characters)
        auto = AUTO_POS.get(n, [(-0.8 + 1.6 * i / max(1, n - 1)) for i in range(n)])
        xs = []
        for i, sc in enumerate(shot.characters):
            if isinstance(sc.position, (int, float)):
                pos = max(-1.0, min(1.0, float(sc.position)))
            elif isinstance(sc.position, str):
                pos = NAMED_POS[sc.position]
            else:
                pos = auto[i]
            xs.append(pos * STAGE_HALF)
        for i, sc in enumerate(shot.characters):
            x = xs[i]
            facing = sc.facing
            if facing == 'auto':
                others = [xs[j] for j in range(n) if j != i]
                facing = 'front' if not others else ('right' if sum(others) / len(others) > x else 'left')
            view = 'front' if facing == 'front' else 'three_quarter'
            flip = facing == 'left'
            m = self.manifests[sc.name]
            rig = add_character_to_scene(self.scene, m, 'assets/characters/%s' % m['prefix'],
                                         x=x, y=FLOOR_Y, scale=sc.scale, flip=flip)
            e, b, mo, fx, bl = EMOTIONS[sc.emotion]
            st = CharState(rig, sc.name, x, facing, [view] * total, [flip] * total, [e] * total,
                           ['c'] * total, [b] * total, [mo] * total, [None] * total, [None] * total,
                           [bl] * total, [sc.emotion] * total,
                           {'l': ['open'] * total, 'r': ['open'] * total},
                           {'l': [False] * total, 'r': [False] * total},
                           walking=np.zeros(total), look_lock=[False] * total)
            self.chars[sc.name] = st
            self.set_emotion(st, sc.emotion, 0, round(1.6 * self.fps))

    def rig_dir_to(self, st: CharState, x: float, f: int) -> int:
        screen = 1 if x > st.x else -1
        return -screen if st.flip[min(f, self.total - 1)] else screen

    def facing_dir(self, st: CharState, f: int = 0) -> int:
        """+1 when the rig faces +x in its own space (always, in three-quarter)."""
        return 1 if st.view[min(f, self.total - 1)] != 'front' else 0

    def set_emotion(self, st: CharState, emotion: str, start: int, fx_len: int, pop: bool = True) -> None:
        e, b, mo, fx, bl = EMOTIONS[emotion]
        for f in range(start, self.total):
            st.eyes[f], st.brows[f], st.mouth_rest[f], st.blush[f], st.emotion[f] = e, b, mo, bl, emotion
            st.fx[f] = None
        if fx and pop:
            for f in range(start, min(self.total, start + fx_len)):
                st.fx[f] = fx
            sound = FX_SFX.get(fx)
            if sound:
                self.sfx.append((start + 1, sound))
            # symbol pops in with a springy overshoot
            n = min(fx_len, self.total - start)
            target = np.ones(n)
            pop_curve = spring_follow(target, 4.0, 0.3, self.fps, x0=0.35)
            self.motion.add(st.oid('fx'), 'sc', start, pop_curve - 1.0)
        look = EMOTION_LOOK.get(emotion)
        if look:
            for f in range(start, min(self.total, start + round(1.8 * self.fps))):
                if look == 'away':
                    others = [c for c in self.chars.values() if c is not st]
                    st.look[f] = ('l' if self.rig_dir_to(st, others[0].x, f) > 0 else 'r') if others else 'd'
                else:
                    st.look[f] = look
                st.look_lock[f] = True

    # ------------------------------------------------------------------
    # beats
    # ------------------------------------------------------------------
    def apply_beat(self, idx: int, b: Beat, s: int, ln: int) -> None:
        st = self.chars.get(b.character) if b.character else None
        emotion = b.emotion
        if st and emotion:
            self.set_emotion(st, emotion, s, max(ln, round(1.6 * self.fps)))
        sp = self.speeches.get(idx)
        if st and b.kind == 'dialogue' and sp:
            self.speak(st, sp, s, ln, explicit_action=b.action != 'none')
        elif b.kind == 'narration' and sp:
            for other in self.chars.values():  # characters react softly under narration
                self.listen(other, None, s, ln, None)
        action = b.action
        if st and action == 'none' and emotion in EMOTION_ACTION:
            action = EMOTION_ACTION[emotion]
        if st and action != 'none':
            self.do_action(st, action, s, ln, b.target)
        if b.camera_shake or (st is not None and emotion in ('shocked', 'furious')):
            self.shakes.append((s + 3, 1.0 if emotion != 'furious' else 0.6))
            self.sfx.append((s + 3, 'boom' if emotion != 'furious' else 'thud'))
        for name in b.sfx:
            self.sfx.append((s, name))
        if b.camera == 'freeze':
            self.freezes.append((s, ln))
            self.sfx.append((s, 'scratch'))

    def speak(self, st: CharState, sp: Speech, s: int, ln: int, explicit_action: bool) -> None:
        fps = self.fps
        emo = st.emotion[min(s, self.total - 1)]
        track = mouth_track(sp.text, sp.words, sp.duration, fps, sp.path, hold=2)
        lead = 1
        for k, shape in enumerate(track):
            f = s + k - lead
            if 0 <= f < self.total:
                st.mouth[f] = self.talk_shape(shape, emo) if shape else None
        n = len(track)
        env = loudness(sp.path, n, fps)
        if env is None:
            env = np.array([0.0 if m is None else 0.8 for m in track], dtype=float)
        env = np.convolve(env, np.ones(3) / 3, mode='same')
        stresses = _stress_events(env, fps)
        hh = st.rig.manifest['head_height']
        head, body = st.oid('head'), st.oid('body')
        fd = self.facing_dir(st, s)
        # head bobs land on stressed syllables (start 2 frames early)
        for e in stresses:
            k = np.arange(10)
            bump = np.sin(np.pi * k / 9) * (0.7 + 0.6 * env[min(e, n - 1)])
            self.motion.add(head, 'rot', s + e - 3, -2.2 * bump * (fd if fd else 0.6))
            self.motion.add(head, 'y', s + e - 3, -0.012 * hh * bump)
            self.motion.add(head, 'sy', s + e - 3, -0.012 * bump)
        # brow raises on the strongest stress of each ~1.6 s window
        last = -999
        for e in sorted(stresses, key=lambda e: -env[min(e, n - 1)]):
            if abs(e - last) < 1.6 * fps:
                continue
            last = e
            for f in range(s + e - 2, min(self.total, s + e + 9)):
                if 0 <= f < self.total and st.brows[f] == 'neutral':
                    st.brows[f] = 'raised'
        # lean towards whoever listens
        others = [c for c in self.chars.values() if c is not st]
        if others:
            tx = min(others, key=lambda c: abs(c.x - st.x)).x
            d = self.rig_dir_to(st, tx, s)
            self.motion.add(body, 'rot', s, -1.6 * d * pose_weight(ln, 10, 12, 0.05, 0.0, 0.2))
            for f in range(s, min(self.total, s + ln)):
                if not st.look_lock[f]:
                    st.look[f] = 'r' if d > 0 else 'l'
        # gestures: one per ~2.2 s of speech, apex on a stressed word
        if not explicit_action and n > 1.1 * fps:
            count = max(1, int(n / (2.4 * fps)))
            picks = sorted(sorted(stresses, key=lambda e: -env[min(e, n - 1)])[:count]) or [n // 3]
            for j, e in enumerate(picks):
                start = s + max(0, e - 9)
                dur = int(min(max(1.3 * fps, n - e + 6), 2.4 * fps))
                pose = TALK_GESTURES[(st.talk_count + j) % len(TALK_GESTURES)]
                side = 'r' if (st.talk_count + j) % 2 == 0 else 'l'
                if others and pose in ('explain',):
                    side = 'r' if self.rig_dir_to(st, others[0].x, s) > 0 else 'l'
                self.arm(st, side, pose, start, dur)
        st.talk_count += 1
        for other in others:
            self.listen(other, st, s, ln, stresses)

    def listen(self, st: CharState, speaker: CharState | None, s: int, ln: int, stresses) -> None:
        if speaker is not None:
            d = self.rig_dir_to(st, speaker.x, s)
            for f in range(s, min(self.total, s + ln)):
                if not st.look_lock[f]:
                    st.look[f] = 'r' if d > 0 else 'l'
        # small acknowledging nods every 2-4 s, a few frames after a stress
        head = st.oid('head')
        hh = st.rig.manifest['head_height']
        f = s + int(self.rnd.uniform(1.2, 2.2) * self.fps)
        while f < s + ln - 10:
            k = np.arange(10)
            bump = np.sin(np.pi * k / 9)
            self.motion.add(head, 'y', f, -0.010 * hh * bump)
            self.motion.add(head, 'rot', f, -1.4 * bump * (self.facing_dir(st, f) or 0.5))
            f += int(self.rnd.uniform(2.2, 4.0) * self.fps)

    def talk_shape(self, vowel: str, emotion: str) -> str:
        if vowel == 'M':
            return 'M'
        if emotion in LOUD and vowel in ('A', 'O', 'E'):
            return 'shout'
        if emotion in HAPPY and vowel in ('A', 'E'):
            return 'grin'
        return vowel

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def do_action(self, st: CharState, action: str, s: int, ln: int, target: str | None) -> None:
        fps = self.fps
        e = min(s + ln, self.total)
        n = e - s
        hh = st.rig.manifest['head_height']
        tgt = self.chars.get(target) if target else None
        if tgt is not None:
            rig_dir = self.rig_dir_to(st, tgt.x, s)
        else:
            rig_dir = 1
        near = 'r' if rig_dir > 0 else 'l'
        head, body, peg = st.oid('head'), st.oid('body'), st.oid('peg')
        M = self.motion
        if action in ('wave', 'point', 'gesture', 'fist_pump'):
            side = near if action in ('point', 'wave') else 'r'
            self.arm(st, side, action if action != 'gesture' else 'gesture', s, n, wave=(action == 'wave'))
            if action == 'fist_pump':
                self.bounce(st, s, min(n, 18), 0.07 * hh)
            if tgt is not None and action == 'point':
                for f in range(s, e):
                    st.look[f] = 'r' if rig_dir > 0 else 'l'
                    st.look_lock[f] = True
        elif action in ('cross_arms', 'hands_on_hips', 'cheer', 'shrug', 'clap'):
            pose = {'cross_arms': 'cross', 'hands_on_hips': 'hip', 'cheer': 'cheer',
                    'shrug': 'shrug', 'clap': 'clap'}[action]
            self.arm(st, 'l', pose, s, n, wave=(action == 'clap'))
            self.arm(st, 'r', pose, s + 2, n - 2, wave=(action == 'clap'))
            if action == 'cheer':
                self.bounce(st, s + 4, n - 8, 0.10 * hh)
            if action == 'shrug':
                w = pose_weight(n, 6, 8, 0.1, 0.1)
                M.add(body, 'y', s, 0.025 * hh * w)
                M.add(head, 'rot', s + 2, 6.0 * w)
        elif action == 'think':
            self.arm(st, 'r', 'think', s, n)
            M.add(head, 'rot', s + 3, 5.0 * pose_weight(n - 3, 10, 10))
            for f in range(s + 4, e):
                if not st.look_lock[f]:
                    st.look[f] = 'u'
        elif action == 'facepalm':
            self.arm(st, 'r', 'facepalm', s, n, t_in=7)
            self.sfx.append((s + 7, 'thud'))
            w = pose_weight(n - 6, 3, 10, 0.2, 0.0)
            M.add(head, 'y', s + 6, -0.04 * hh * w)
            M.add(head, 'rot', s + 6, -4.0 * w)
            for f in range(s + 7, max(s + 7, e - 8)):
                st.eyes[f] = 'closed'
        elif action == 'nod':
            k = np.arange(20)
            bump = np.abs(np.sin(np.pi * k / 10)) * np.where(k < 10, 1.0, 0.7)
            M.add(head, 'y', s, -0.03 * hh * bump)
            M.add(head, 'sy', s, -0.03 * bump)
            M.add(head, 'rot', s, -3.0 * bump * (self.facing_dir(st, s) or 0.4))
        elif action == 'shake_head':
            k = np.arange(min(n, 26))
            env = np.sin(np.pi * k / len(k))
            osc = np.sin(2 * np.pi * k / 8.5)
            M.add(head, 'rot', s, 7.0 * osc * env)
            M.add(head, 'x', s, -0.02 * hh * osc * env)
        elif action == 'head_tilt':
            M.add(head, 'rot', s, 8.0 * pose_weight(n, 8, 10, 0.12, 0.08))
        elif action in ('jump', 'hop'):
            self.jump(st, s, (0.55 if action == 'jump' else 0.28) * hh * self.k)
        elif action in ('take', 'big_take'):
            self.take(st, s, big=(action == 'big_take'))
        elif action == 'bounce':
            self.bounce(st, s, n, 0.08 * hh)
        elif action == 'laugh':
            self.bounce(st, s, n, 0.035 * hh, period=5)
            M.add(head, 'rot', s, 6.0 * pose_weight(n, 6, 8) * (-(self.facing_dir(st, s) or 0.5)))
            k = np.arange(n)
            M.add(st.oid('upper_l'), 'rot', s, -2.5 * np.sin(2 * np.pi * k / 4) * pose_weight(n, 4, 6, 0, 0))
            M.add(st.oid('upper_r'), 'rot', s, 2.5 * np.sin(2 * np.pi * k / 4) * pose_weight(n, 4, 6, 0, 0))
        elif action == 'shiver':
            k = np.arange(min(n, int(1.2 * fps)))
            env = pose_weight(len(k), 3, 6, 0, 0, 0)
            M.add(body, 'x', s, 0.018 * hh * np.where(k % 2 == 0, 1, -1) * env)
        elif action == 'slump':
            w = pose_weight(n, 12, 12, 0.04, 0.0)
            M.add(head, 'y', s, -0.05 * hh * w)
            M.add(head, 'rot', s, -4.0 * w * (self.facing_dir(st, s) or 0.5))
            M.add(body, 'sy', s, -0.03 * w)
            M.add(st.oid('upper_l'), 'rot', s, 3.0 * w)
            M.add(st.oid('upper_r'), 'rot', s, -3.0 * w)
        elif action == 'bow':
            w = pose_weight(n, 10, 12, 0.05, 0.05)
            fd = self.facing_dir(st, s)
            if fd:
                M.add(body, 'rot', s, -14.0 * w)
            M.add(head, 'y', s + 2, -0.10 * hh * w)
            M.add(body, 'sy', s, -0.05 * w)
        elif action == 'lean_in':
            M.add(body, 'rot', s, -6.0 * rig_dir * pose_weight(n, 10, 12, 0.08, 0.1))
        elif action == 'turn_around':
            self.turn(st, s, tgt)
        elif action in ('walk_in', 'walk_out'):
            side = 'left' if st.x < 0 else 'right'
            if action == 'walk_in':
                self.walk(st, side, s, entering=True)
            else:
                self.walk(st, side, max(0, e - round(1.4 * fps)), entering=False)

    # -- building blocks ---------------------------------------------------
    def arm(self, st: CharState, side: str, pose: str, s: int, n: int, wave: bool = False,
            t_in: int = 9, t_out: int = 11) -> None:
        if st.arm_busy[side] >= s:
            shift = st.arm_busy[side] + 1 - s
            s, n = s + shift, n - shift
        s = max(0, s)
        n = min(n, self.total - s)
        if n < 12:
            return
        st.arm_busy[side] = s + n
        sgn = 1 if side == 'r' else -1
        a_u, a_f, hand, short = ARM_POSES[pose]
        rest_u = sgn * ARM_REST[0]
        rest_f = sgn * (ARM_REST[1] - ARM_REST[0])
        d_u = sgn * a_u - rest_u
        d_f = sgn * (a_f - a_u) - rest_f
        w = pose_weight(n, t_in, t_out, overshoot=0.12, anticip=0.10, drift=0.05,
                        phase=self.rnd.uniform(0, 6))
        M = self.motion
        M.add(st.oid('upper_' + side), 'rot', s, d_u * w)
        M.add(st.oid('fore_' + side), 'rot', s, d_f * lag(w, 2))
        if wave:
            k = np.arange(n)
            hold = np.clip((k - t_in) / 4, 0, 1) * np.clip((n - t_out - k) / 4, 0, 1)
            M.add(st.oid('fore_' + side), 'rot', s, sgn * 22.0 * np.sin(2 * np.pi * k / 13) * hold)
        a, b = s + t_in // 2, s + n - t_out // 2
        for f in range(a, min(b, self.total)):
            st.hand[side][f] = hand
            st.short[side][f] = short
        if short:
            lift = st.rig.manifest['proportions']['upper_len'] * 0.45
            step = np.zeros(n)
            step[t_in // 2:n - t_out // 2] = lift
            M.add(st.oid('fore_' + side), 'y', s, step)

    def bounce(self, st: CharState, s: int, n: int, amp: float, period: int = 7) -> None:
        if n <= 2:
            return
        k = np.arange(n)
        amp *= max(self.k, 0.4)
        env = pose_weight(n, 4, 6, 0, 0, 0)
        hop = np.abs(np.sin(np.pi * k / period)) * env
        self.motion.add(st.oid('body'), 'y', s, amp * hop)
        squash = np.where(hop < 0.15, -0.04, 0.02) * env
        self.motion.add(st.oid('body'), 'sy', s, squash)

    def jump(self, st: CharState, s: int, height: float) -> None:
        crouch, launch, air, land, rec = 6, 3, 12, 3, 8
        hh = st.rig.manifest['head_height']
        y = np.concatenate([
            -0.10 * hh * ease_out(np.arange(crouch) / (crouch - 1)),
            -0.10 * hh + (0.10 * hh + height * 0.35) * np.arange(1, launch + 1) / launch,
            height * (0.35 + 0.65 * np.sin(np.pi * np.arange(air) / (air - 1)) * 0.95),
            -0.08 * hh * np.sin(np.pi * np.arange(land) / land * 0.5),
            -0.08 * hh * (1 - ease_out(np.arange(rec) / (rec - 1))),
        ])
        sy = np.concatenate([1 - 0.12 * ease_out(np.arange(crouch) / (crouch - 1)), np.full(launch, 1.12),
                             1.04 - 0.04 * np.arange(air) / air, np.full(land, 0.88),
                             0.88 + 0.12 * ease_out(np.arange(rec) / (rec - 1))])
        self.motion.add(st.oid('body'), 'y', s, y)
        self.motion.add(st.oid('body'), 'sy', s, sy - 1)
        self.motion.add(st.oid('body'), 'sx', s, 1 / np.sqrt(sy) - 1)
        self.motion.add(st.oid('shadow'), 'sc', s, -0.45 * np.clip(y / max(height, 1e-6), 0, 1))
        self.sfx.append((s + crouch, 'slide_up'))
        self.sfx.append((s + crouch + launch + air, 'thud'))
        for side in ('l', 'r'):
            sg = 1 if side == 'r' else -1
            w = np.zeros(len(y))
            w[crouch + launch:crouch + launch + air] = np.sin(np.pi * np.arange(air) / (air - 1))
            self.motion.add(st.oid('upper_' + side), 'rot', s, sg * 35 * w)

    def take(self, st: CharState, s: int, big: bool) -> None:
        hh = st.rig.manifest['head_height']
        n = int(1.4 * self.fps)
        # tighter shots need smaller moves or the head leaves the frame
        k = self.k
        target = np.ones(n)
        target[:3] = 1 - 0.12 * k
        target[3:7] = 1 + (0.16 if big else 0.10) * k
        sy = spring_follow(target, 5.0, 0.32, self.fps, x0=1.0)
        ty = np.zeros(n)
        ty[3:8] = (0.30 if big else 0.16) * hh * k
        y = spring_follow(ty, 4.0, 0.5, self.fps, x0=0.0)
        y[:3] = -0.04 * hh * np.arange(1, 4) / 3
        self.motion.add(st.oid('body'), 'sy', s, sy - 1)
        self.motion.add(st.oid('body'), 'sx', s, 1 / np.sqrt(sy) - 1)
        self.motion.add(st.oid('body'), 'y', s, y)
        self.motion.add(st.oid('head'), 'sy', s, (sy - 1) * 0.6)
        self.sfx.append((s + 2, 'scratch' if big else 'boing'))
        if big:
            self.arm(st, 'l', 'flare', s + 2, n)
            self.arm(st, 'r', 'flare', s + 3, n - 1)

    def turn(self, st: CharState, s: int, tgt: CharState | None) -> None:
        new_flip = (tgt.x < st.x) if tgt is not None else (not st.flip[s])
        for f in range(s, self.total):
            st.flip[f] = new_flip
            st.view[f] = 'three_quarter'
        sx = self.motion.track(st.oid('peg'), 'sx')
        sx[s:] = -1.0 if new_flip else 1.0
        k = np.arange(8)
        self.motion.add(st.oid('head'), 'sx', s - 4, -0.15 * np.sin(np.pi * k / 7))
        for f in range(max(0, s - 1), min(self.total, s + 2)):
            st.eyes[f] = 'closed'

    def walk(self, st: CharState, side: str, s: int, entering: bool) -> None:
        """Walks in from / out to the given screen side with a 2-bone leg cycle."""
        fps = self.fps
        rig = st.rig
        pr = rig.manifest['proportions']
        leg_len = pr['hip_jy']
        cx, cy, sc = self.cam_base
        off = cx + (-1 if side == 'left' else 1) * (8.0 * sc + 1.8 * rig.scale)
        x0 = st.x
        a, b = (off, x0) if entering else (x0, off)
        dist = abs(b - a)
        period = 24
        stride = 2 * 2 * leg_len * math.sin(math.radians(22)) * rig.scale  # per cycle (2 steps)
        n = int(max(0.8 * fps, min(3.2 * fps, dist / stride * period)))
        s = max(0, min(s, self.total - 2))
        n = min(n, self.total - s) if not entering else n
        M = self.motion
        # travel with eased start/stop (trapezoid velocity)
        k = np.arange(n) / max(1, n - 1)
        acc = 0.18
        prog = np.where(k < acc, k * k / (2 * acc * (1 - acc)),
                        np.where(k > 1 - acc, 1 - (1 - k) ** 2 / (2 * acc * (1 - acc)),
                                 (k - acc / 2) / (1 - acc)))
        xs = a + (b - a) * prog
        xt = M.track(st.oid('peg'), 'x')
        if entering:
            xt[:s] = a
        seg = xs[:max(0, min(n, self.total - s))]
        xt[s:s + len(seg)] = seg
        if not entering:
            xt[s + len(seg):] = b
        going_right = b > a
        flip_walk = not going_right
        sxt = M.track(st.oid('peg'), 'sx')
        if entering:
            sxt[:s + n] = -1.0 if flip_walk else 1.0
            for f in range(0, min(self.total, s + n)):
                st.view[f], st.flip[f] = 'three_quarter', flip_walk
        else:
            sxt[s:] = -1.0 if flip_walk else 1.0
            for f in range(s, self.total):
                st.view[f], st.flip[f] = 'three_quarter', flip_walk
        # leg / arm / body cycle
        m = len(seg)
        f = np.arange(m)
        ph = 2 * np.pi * f / period
        ramp = np.clip(np.minimum(f / 6, (m - 1 - f) / 6), 0, 1)
        A, B = 24.0, 52.0
        M.add(st.oid('thigh_l'), 'rot', s, A * np.sin(ph) * ramp)
        M.add(st.oid('thigh_r'), 'rot', s, -A * np.sin(ph) * ramp)
        M.add(st.oid('shin_l'), 'rot', s, -B * np.maximum(0, np.cos(ph)) ** 1.5 * ramp - 6 * ramp)
        M.add(st.oid('shin_r'), 'rot', s, -B * np.maximum(0, -np.cos(ph)) ** 1.5 * ramp - 6 * ramp)
        bob = 0.05 * leg_len
        M.add(st.oid('body'), 'y', s, -bob * (0.5 + 0.5 * np.cos(2 * ph + 0.5)) * ramp)
        M.add(st.oid('body'), 'rot', s, -3.0 * ramp + 1.5 * np.sin(ph) * ramp)
        M.add(st.oid('head'), 'rot', s, lag(-1.0 * np.sin(ph) * ramp, 2))
        M.add(st.oid('upper_l'), 'rot', s, -18.0 * np.sin(ph) * ramp)
        M.add(st.oid('upper_r'), 'rot', s, 18.0 * np.sin(ph) * ramp)
        M.add(st.oid('fore_l'), 'rot', s, lag(-10.0 * np.maximum(0, -np.sin(ph)) * ramp, 3))
        M.add(st.oid('fore_r'), 'rot', s, lag(-10.0 * np.maximum(0, np.sin(ph)) * ramp, 3))
        st.walking[s:s + m] = np.maximum(st.walking[s:s + m], ramp)
        for c in range(6, m - 3, period // 2):
            self.sfx.append((s + c, 'tap'))

    def apply_entrances(self) -> None:
        for sc in self.shot.characters:
            st = self.chars[sc.name]
            if sc.enter != 'none':
                self.walk(st, sc.enter, 0, entering=True)
            if sc.exit != 'none':
                self.walk(st, sc.exit, self.total - round(1.6 * self.fps), entering=False)

    # ------------------------------------------------------------------
    # always-alive layers
    # ------------------------------------------------------------------
    def idle(self, st: CharState) -> None:
        T = self.total
        t = np.arange(T) / self.fps
        rng = np.random.default_rng(_seed(self.shot.id, st.name, 'idle'))
        calm = 1.0 - 0.7 * st.walking
        hh = st.rig.manifest['head_height']
        M = self.motion
        body, head = st.oid('body'), st.oid('head')
        br_T = rng.uniform(3.6, 4.4)
        ph = rng.uniform(0, 2 * np.pi)
        breath = np.sin(2 * np.pi * t / br_T + ph)
        M.add_all(body, 'sy', 0.012 * breath * calm)
        M.add_all(body, 'sx', -0.004 * breath * calm)
        M.add_all(head, 'y', lag(0.006 * hh * breath, 4) * calm)
        sway = 0.7 * noise(T, rng, 70) + 0.35 * np.sin(2 * np.pi * t / 5.3 + ph)
        M.add_all(body, 'rot', sway * calm)
        M.add_all(body, 'x', 0.03 * hh * noise(T, rng, 110) * calm)
        M.add_all(head, 'rot', (0.9 * noise(T, rng, 55) + 0.45 * np.sin(2 * np.pi * t / 3.1 + ph * 0.7)) * calm)
        for side in ('l', 'r'):
            sg = 1 if side == 'r' else -1
            M.add_all(st.oid('upper_' + side), 'rot', (sg * 0.8 * breath + 1.1 * noise(T, rng, 80)) * calm)
            M.add_all(st.oid('fore_' + side), 'rot', 1.4 * noise(T, rng, 60) * calm)

    def eye_life(self, st: CharState) -> None:
        """Blinks every 2.5-5.5 s (sometimes double) and idle eye darts."""
        fps, T = self.fps, self.total
        rnd = random.Random(_seed(self.shot.id, st.name, 'eyes'))
        f = rnd.randint(int(0.6 * fps), int(2.2 * fps))
        while f < T - 6:
            base = st.eyes[f]
            if base in BLINKABLE and st.eyes[min(f + 5, T - 1)] == base:
                seq = ['blink', 'closed', 'closed', 'blink']
                if rnd.random() < 0.12:
                    seq += [base, 'blink', 'closed', 'blink']
                for k, e in enumerate(seq):
                    if f + k < T and st.eyes[f + k] in BLINKABLE:
                        st.eyes[f + k] = e
            f += rnd.randint(int(2.5 * fps), int(5.5 * fps))
        # darts while nobody holds the gaze
        f = rnd.randint(int(1.0 * fps), int(2.5 * fps))
        while f < T - 8:
            if not st.look_lock[f]:
                choice = rnd.choice(['u', 'd', 'l', 'r', 'c'])
                hold = rnd.randint(int(0.4 * fps), int(1.0 * fps))
                base = st.look[f]
                for g in range(f, min(T, f + hold)):
                    if not st.look_lock[g] and st.look[g] == base:
                        st.look[g] = choice
            f += rnd.randint(int(1.4 * fps), int(3.2 * fps))

    def secondary(self, st: CharState) -> None:
        """Hair lags the head on a loose spring; forearms drag behind upper arms."""
        M, fps = self.motion, self.fps
        body, head = st.oid('body'), st.oid('head')
        world = M.track(body, 'rot') + M.track(head, 'rot')
        follow = spring_follow(world, 3.0, 0.28, fps)
        swing = np.clip((follow - world) * 0.9, -12, 12)
        yb = M.track(body, 'y') + M.track(head, 'y')
        bounce = spring_follow(yb, 3.4, 0.3, fps) - yb
        for part, k in (('hair_front', 0.6), ('hair_back', 1.0)):
            M.add_all(st.oid(part), 'rot', swing * k)
            M.add_all(st.oid(part), 'y', bounce * 0.5 * k)
        for side in ('l', 'r'):
            up = M.track(st.oid('upper_' + side), 'rot')
            drag = spring_follow(up, 3.0, 0.45, fps) - up
            M.add_all(st.oid('fore_' + side), 'rot', drag * 0.55)

    def keep_legs(self, st: CharState) -> None:
        """Legs ignore torso squash/stretch, and bend to keep the feet planted
        whenever the body dips below its rest height."""
        M = self.motion
        body = st.oid('body')
        bsx, bsy, by = M.track(body, 'sx'), M.track(body, 'sy'), M.track(body, 'y')
        base_y = self.scene.object(body).curve('y').default
        for side in ('l', 'r'):
            thigh = st.oid('thigh_' + side)
            M.track(thigh, 'sx')[:] = 1.0 / np.maximum(bsx, 0.3)
            M.track(thigh, 'sy')[:] = 1.0 / np.maximum(bsy, 0.3)
        pr = st.rig.manifest['proportions']
        leg = pr['hip_jy']
        drop = np.clip(base_y - by, 0, leg * 0.6) * (1 - st.walking)
        theta = np.degrees(np.arccos(np.clip(1 - drop / leg, -1, 1)))
        front = np.array([1.0 if v == 'front' else 0.0 for v in st.view])
        for side, sg in (('l', -1), ('r', 1)):
            out = sg * theta * front + theta * (1 - front)
            M.add_all(st.oid('thigh_' + side), 'rot', out)
            M.add_all(st.oid('shin_' + side), 'rot', -2 * out)

    # ------------------------------------------------------------------
    # cells
    # ------------------------------------------------------------------
    def write_cells(self, st: CharState) -> None:
        rig, scene, m = st.rig, self.scene, st.rig.manifest
        T = self.total

        def put(part: str, fids: list):
            col = scene.columns[rig.cols[part]]
            lvl = rig.info(part)['level']
            for f in range(T):
                if fids[f] is None:
                    col.cells.pop(f, None)
                else:
                    col.cells[f] = (lvl, fids[f])

        views = st.view
        for part in ('hair_back', 'head', 'acc', 'hair_front', 'body', 'shin_l', 'shin_r', 'thigh_l', 'thigh_r'):
            put(part, [drawing_id(m, part, '', views[f]) for f in range(T)])
        put('shadow', [1] * T)
        put('eyes', [drawing_id(m, 'eyes', eye_name(st.eyes[f], st.look[f]), views[f]) for f in range(T)])
        put('brows', [drawing_id(m, 'brows', st.brows[f], views[f]) for f in range(T)])
        put('mouth', [drawing_id(m, 'mouth', st.mouth[f] or st.mouth_rest[f], views[f]) for f in range(T)])
        put('fx', [drawing_id(m, 'fx', st.fx[f], views[f]) if st.fx[f] else None for f in range(T)])
        put('blush', [drawing_id(m, 'blush', st.blush[f], views[f]) if st.blush[f] else None for f in range(T)])
        put('upper_l', [2 if st.short['l'][f] else 1 for f in range(T)])
        put('fore_l', [drawing_id(m, 'fore_l', st.hand['l'][f]) for f in range(T)])
        upper_r = [2 if st.short['r'][f] else 1 for f in range(T)]
        fore_r = [drawing_id(m, 'fore_r', st.hand['r'][f]) for f in range(T)]
        front = [views[f] == 'front' for f in range(T)]
        put('upper_r', [upper_r[f] if front[f] else None for f in range(T)])
        put('fore_r', [fore_r[f] if front[f] else None for f in range(T)])
        put('upper_r_back', [None if front[f] else upper_r[f] for f in range(T)])
        put('fore_r_back', [None if front[f] else fore_r[f] for f in range(T)])

    # ------------------------------------------------------------------
    # camera
    # ------------------------------------------------------------------
    def frame_camera(self) -> tuple[float, float, float]:
        shot = self.shot
        chars = list(self.chars.values())
        if not chars or shot.shot_type == 'wide':
            return self.clamp(0.0, 0.0, 1.0)
        focus = self.chars.get(shot.focus) if shot.focus else None
        if focus is None:
            focus = chars[0]
        rig = focus.rig
        hh = rig.head_height
        fx, fy = rig.face_world()
        t = shot.shot_type
        group = chars if t in ('two_shot', 'full', 'medium') and len(chars) > 1 else [focus]
        xs = [c.x for c in group]
        H = max(c.rig.height for c in group)
        span = (max(xs) - min(xs)) + 2.6 * max(c.rig.head_height for c in group)
        look = 0.0
        if len(group) == 1 and focus.view[0] != 'front':
            look = -1.0 if focus.flip[0] else 1.0
        if t == 'full':
            sc = max(H * 1.25 / 9.0, span * 1.1 / 16.0)
            cy = FLOOR_Y - 0.08 * H + 4.5 * sc
            cx = (max(xs) + min(xs)) / 2
        elif t in ('medium', 'two_shot'):
            top = FLOOR_Y + H + 0.55 * hh
            low = min(c.rig.face_world()[1] - 1.6 * c.rig.head_height for c in group)
            sc = max(H * 0.66 / 9.0, span * 1.12 / 16.0, (top - low) / 9.0)
            cy = top - 4.5 * sc
            cx = (max(xs) + min(xs)) / 2
        elif t == 'closeup':
            sc = 2.4 * hh / 9.0
            cy = fy - 0.30 * hh
            cx = fx
        else:  # extreme_closeup
            sc = 1.35 * hh / 9.0
            cy = fy - 0.02 * hh
            cx = fx
        cx += look * 0.16 * 16.0 * sc
        return self.clamp(cx, cy, sc)

    def clamp(self, cx: float, cy: float, sc: float) -> tuple[float, float, float]:
        sc = min(max(sc, 0.08), 1.3)
        mx = PLATE_W / 2 - 8.0 * sc * 1.12
        my = PLATE_H / 2 - 4.5 * sc * 1.12
        return (max(-mx, min(mx, cx)), max(-my, min(my, cy)), sc)

    def camera(self, beats) -> None:
        M, T, fps = self.motion, self.total, self.fps
        cam = 'Camera1'
        cx, cy, sc = self.cam_base
        obj = self.scene.object(cam)
        obj.curve('x').default, obj.curve('y').default, obj.curve('sc').default = cx, cy, sc
        x, y, s = M.track(cam, 'x'), M.track(cam, 'y'), M.track(cam, 'sc')
        k = np.arange(T) / max(1, T - 1)
        move = self.shot.camera
        if move == 'push_in':
            s[:] = sc * (1 - 0.09 * sine_in_out(k))
        elif move == 'pull_out':
            s[:] = sc * (0.91 + 0.09 * sine_in_out(k))
        elif move in ('pan_left', 'pan_right'):
            d = 0.12 * 16.0 * sc * (1 if move == 'pan_right' else -1)
            a, b = self.clamp(cx - d, cy, sc)[0], self.clamp(cx + d, cy, sc)[0]
            x[:] = a + (b - a) * ease_in_out(k)
        elif move == 'tilt_up':
            d = 0.15 * 9.0 * sc
            a = self.clamp(cx, cy - d, sc)[1]
            y[:] = a + (cy - a) * ease_in_out(k)
        elif move == 'zoom_snap':
            n = 8
            st = self.clamp(cx, cy, sc * 1.7)
            r = ease_out(np.arange(n) / (n - 1))
            s[:n] = st[2] + (sc - st[2]) * r
            x[:n] = st[0] + (cx - st[0]) * r
            y[:n] = st[1] + (cy - st[1]) * r
        else:  # static: a slow 'breathing' push keeps the frame alive
            s[:] = sc * (1 - 0.025 * sine_in_out(k))
            self.jump_cuts(beats, x, y, s)
        self.punch_ins(beats, x, y, s)
        t = np.arange(T) / fps
        x += 0.0025 * 16 * sc * np.sin(2 * np.pi * t / 8.0)
        y += 0.0018 * 9 * sc * np.sin(2 * np.pi * t / 6.5 + 1.0)
        shakes = list(self.shakes) + ([(2, 1.0)] if move == 'shake' else [])
        rot = M.track(cam, 'rot')
        for f0, strength in shakes:
            n = min(14, T - f0)
            if n <= 0:
                continue
            kk = np.arange(n)
            amp = 0.014 * 9.0 * sc * strength * np.exp(-kk / 4.5)
            x[f0:f0 + n] += amp * self.rng.uniform(-1, 1, n)
            y[f0:f0 + n] += amp * self.rng.uniform(-1, 1, n)
            rot[f0:f0 + n] += 0.6 * strength * np.exp(-kk / 4.5) * self.rng.uniform(-1, 1, n)

    def _speaker_face(self, b: Beat):
        st = self.chars.get(b.character) if b.character else None
        if st is None and self.shot.focus:
            st = self.chars.get(self.shot.focus)
        return (st.rig.face_world(), st.rig.head_height) if st else None

    def jump_cuts(self, beats, x, y, s) -> None:
        """Editor-style punch-ins: on alternate beats of a long static shot,
        hard-cut to a tighter framing on whoever is talking, so the picture
        changes every few seconds without needing a new shot."""
        if self.shot.shot_type not in ('medium', 'two_shot', 'full', 'wide') or len(beats) < 2:
            return
        cx, cy, sc = self.cam_base
        for i, ((b0, n), beat) in enumerate(zip(beats, self.shot.beats)):
            if i % 2 == 0 or beat.camera == 'punch_in':
                continue
            got = self._speaker_face(beat)
            if got is None:
                continue
            (fx, fy), hh = got
            px, py, ps = self.clamp(cx + (fx - cx) * 0.7, cy + (fy - 0.9 * hh - cy) * 0.6, sc * 0.74)
            e = min(self.total, b0 + n)
            x[b0:e] += px - cx
            y[b0:e] += py - cy
            s[b0:e] *= ps / sc

    def punch_ins(self, beats, x, y, s) -> None:
        """Per-beat 'punch_in' for punchlines: snap about 120% onto the speaker."""
        for (b0, n), beat in zip(beats, self.shot.beats):
            if beat.camera != 'punch_in':
                continue
            got = self._speaker_face(beat)
            if got is None:
                continue
            (fx, fy), hh = got
            e = min(self.total, b0 + n)
            w = np.ones(e - b0)
            w[:4] = ease_out(np.arange(4) / 3)[:len(w[:4])]
            bx, by, bs = x[b0:e].copy(), y[b0:e].copy(), s[b0:e].copy()
            tx, ty, ts = self.clamp(fx, fy - 0.25 * hh, float(bs.mean()) / 1.2)
            x[b0:e] = bx + (tx - bx) * w * 0.8
            y[b0:e] = by + (ty - by) * w * 0.8
            s[b0:e] = bs + (ts - bs) * w
            self.sfx.append((b0, 'swish'))

    def add_text_pops(self, items) -> None:
        """Kinetic words: camera-attached text that springs in, wobbles, holds."""
        if not items:
            return
        scene = self.scene
        w, h = scene.camera.res
        level = 'pop_' + self.shot.id
        folder = self.scenes_dir / 'assets' / 'captions' / self.shot.id
        scene.add_level(level, '$scenefolder/assets/captions/%s/%s..png' % (self.shot.id, level),
                        scene.camera.dpi)
        idx, col = scene.add_column('text_pops', parent='Camera1')
        oid = 'Col%d' % (idx + 1)
        obj = scene.column_object(idx)
        obj.curve('y').default = scene.camera.size[1] * 0.27
        for fid, (s, n, text) in enumerate(items, start=1):
            render_caption(text.upper(), (int(w * 0.9), int(h * 0.26)), folder / ('%s.%04d.png' % (level, fid)), 'pop')
            hold = min(n, int(1.6 * self.fps))
            col.hold(s, hold, level, fid)
            pop = spring_follow(np.ones(hold), 4.5, 0.32, self.fps, x0=0.25)
            self.motion.add(oid, 'sc', s, pop - 1.0)
            self.motion.add(oid, 'rot', s, -4.0 + 3.0 * np.exp(-np.arange(hold) / 6.0) * np.sin(np.arange(hold) / 1.6))
            self.sfx.append((s, 'pop'))

    # ------------------------------------------------------------------
    # captions and titles
    # ------------------------------------------------------------------
    def add_captions(self, items) -> None:
        if not items:
            return
        scene = self.scene
        w, h = scene.camera.res
        cap_h = int(h * 0.2)
        level = 'cap_' + self.shot.id
        folder = self.scenes_dir / 'assets' / 'captions' / self.shot.id
        # only this level's frames: text pops and titles share the folder
        for old in folder.glob(level + '.*.png') if folder.exists() else []:
            old.unlink()
        scene.add_level(level, '$scenefolder/assets/captions/%s/%s..png' % (self.shot.id, level),
                        scene.camera.dpi)
        _, col = scene.add_column('captions', parent='Camera1')
        obj = scene.column_object(len(scene.columns) - 1)
        cam_h_in = scene.camera.size[1]
        obj.curve('y').default = -cam_h_in / 2 + (cap_h / scene.camera.dpi) / 2 + 0.12 * cam_h_in / 9
        fid = 0
        for i, b, s, ln in items:
            sp = self.speeches.get(i)
            dur = (sp.duration if sp else ln / self.fps)
            chunks = chunk_caption(b.text)
            total_chars = sum(len(c) for c in chunks) or 1
            f = s
            for c in chunks:
                fid += 1
                render_caption(c, (w, cap_h), folder / ('%s.%04d.png' % (level, fid)),
                               'narration' if b.kind == 'narration' else 'dialogue')
                n = max(int(round(dur * self.fps * len(c) / total_chars)), 12)
                if c is chunks[-1]:
                    n = max(n, s + ln - f - 2)
                col.hold(f, min(n, self.total - f), level, fid)
                f += n

    def add_title(self, text: str) -> None:
        scene = self.scene
        w, h = scene.camera.res
        level = 'title_' + self.shot.id
        folder = self.scenes_dir / 'assets' / 'captions' / self.shot.id
        render_caption(text, (w, int(h * 0.3)), folder / ('%s.0001.png' % level), 'title')
        scene.add_level(level, '$scenefolder/assets/captions/%s/%s..png' % (self.shot.id, level),
                        scene.camera.dpi)
        idx, col = scene.add_column('title', parent='Camera1')
        # upper third, on screen for the first ~2.4 s only
        scene.column_object(idx).curve('y').default = scene.camera.size[1] * 0.30
        col.hold(0, min(self.total, int(2.4 * self.fps)), level, 1)


def _stress_events(env: np.ndarray, fps: float) -> list[int]:
    """Frames of stressed syllables: local loudness peaks clearly above the
    surrounding average, at least ~0.35 s apart."""
    n = len(env)
    out = []
    min_gap = int(0.35 * fps)
    for f in range(2, n - 2):
        a, b = max(0, f - 4), min(n, f + 5)
        if env[f] < 0.5 or env[f] < env[a:b].max():
            continue
        ma, mb = max(0, f - 12), min(n, f + 12)
        if env[f] < 1.15 * env[ma:mb].mean():
            continue
        if out and f - out[-1] < min_gap:
            continue
        out.append(f)
    return out


def _seed(*parts) -> int:
    return zlib.crc32(':'.join(map(str, parts)).encode('utf-8'))


def _slug(s: str) -> str:
    out = ''.join(ch.lower() if ch.isalnum() else '_' for ch in s).strip('_')
    return out or 'x'
