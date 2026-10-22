"""Text to speech with word timings (for lip sync and captions).

Engines:
* ``edge``  Microsoft Edge online voices via edge-tts (needs internet; the
            text is sent to Microsoft's speech service).
* ``sapi``  Windows built-in voices through PowerShell (offline).
* ``none``  silence with an estimated duration (captions only).

Results are cached by (engine, voice, rate, pitch, text).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..render.video import SAMPLE_RATE, audio_duration, write_wav

import numpy as np

WORDS_PER_SECOND = 2.6

# voice pools per language: (female adult, male adult, child)
VOICES = {
    'en': {'female': ['en-US-AriaNeural', 'en-US-JennyNeural', 'en-US-MichelleNeural', 'en-GB-SoniaNeural'],
           'male': ['en-US-GuyNeural', 'en-US-ChristopherNeural', 'en-US-EricNeural', 'en-GB-RyanNeural'],
           'child': ['en-US-AnaNeural'],
           'narrator': 'en-US-ChristopherNeural'},
    'en-in': {'female': ['en-IN-NeerjaNeural', 'en-IN-NeerjaExpressiveNeural'],
              'male': ['en-IN-PrabhatNeural'],
              'child': ['en-US-AnaNeural'],
              'narrator': 'en-IN-PrabhatNeural'},
    'hi': {'female': ['hi-IN-SwaraNeural'], 'male': ['hi-IN-MadhurNeural'],
           'child': ['hi-IN-SwaraNeural'], 'narrator': 'hi-IN-MadhurNeural'},
    'ja': {'female': ['ja-JP-NanamiNeural'], 'male': ['ja-JP-KeitaNeural'],
           'child': ['ja-JP-NanamiNeural'], 'narrator': 'ja-JP-KeitaNeural'},
}
# pitch offsets used to tell apart characters that share a voice
PITCH_STEPS = ['+0Hz', '+12Hz', '-10Hz', '+22Hz', '-18Hz', '+6Hz']


@dataclass
class Speech:
    path: str | None
    duration: float
    words: list[tuple[float, float, str]] = field(default_factory=list)
    engine: str = 'none'
    text: str = ''

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> 'Speech':
        d = dict(d)
        d['words'] = [tuple(w) for w in d.get('words', [])]
        return cls(**d)


def lang_key(language: str) -> str:
    lang = (language or 'en').lower()
    if lang in VOICES:
        return lang
    if lang.startswith('hi'):
        return 'hi'
    if lang.startswith('ja'):
        return 'ja'
    if lang in ('en-in', 'hinglish', 'in'):
        return 'en-in'
    return 'en'


def pick_voice(language: str, gender: str, age: str, index: int) -> tuple[str, str]:
    pool = VOICES[lang_key(language)]
    if age == 'child':
        voices = pool['child']
        pitch = '+8Hz' if gender == 'female' else '-6Hz'
        return voices[index % len(voices)], pitch
    voices = pool['male' if gender == 'male' else 'female']
    voice = voices[index % len(voices)]
    pitch = PITCH_STEPS[(index // len(voices)) % len(PITCH_STEPS)]
    if age == 'elder':
        pitch = '-14Hz'
    return voice, pitch


def narrator_voice(language: str) -> str:
    return VOICES[lang_key(language)]['narrator']


def _cache_key(*parts) -> str:
    return hashlib.sha1('\x1f'.join(map(str, parts)).encode('utf-8')).hexdigest()[:16]


def estimate_duration(text: str) -> float:
    words = max(1, len(text.split()))
    # scripts without spaces (Japanese): count characters instead
    if len(text.split()) <= 2 and len(text) > 12:
        words = len(text) / 3.5
    return words / WORDS_PER_SECOND + 0.3


def synthesize(text: str, voice: str, cache_dir: Path, engine: str = 'edge',
               rate: str = '+0%', pitch: str = '+0Hz') -> Speech:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = ' '.join(text.split())
    key = _cache_key(engine, voice, rate, pitch, text)
    meta = cache_dir / (key + '.json')
    if meta.exists():
        return Speech.from_json(json.loads(meta.read_text(encoding='utf-8')))
    speech = None
    errors = []
    for eng in _engine_chain(engine):
        try:
            if eng == 'edge':
                speech = _edge(text, voice, rate, pitch, cache_dir / (key + '.mp3'))
            elif eng == 'sapi':
                speech = _sapi(text, voice, rate, cache_dir / (key + '.wav'))
            else:
                speech = Speech(None, estimate_duration(text), [], 'none', text)
            break
        except Exception as e:  # fall through to the next engine
            errors.append('%s: %s' % (eng, e))
    if speech is None:
        raise RuntimeError('; '.join(errors))
    speech.text = text
    meta.write_text(json.dumps(speech.to_json(), ensure_ascii=False), encoding='utf-8')
    return speech


def _engine_chain(engine: str) -> list[str]:
    if engine == 'edge':
        return ['edge', 'sapi', 'none'] if os.name == 'nt' else ['edge', 'none']
    if engine == 'sapi':
        return ['sapi', 'none']
    return ['none']


def _edge(text: str, voice: str, rate: str, pitch: str, out: Path) -> Speech:
    import edge_tts

    async def run():
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                    boundary='WordBoundary')
        words, audio = [], bytearray()
        async for chunk in comm.stream():
            if chunk['type'] == 'audio':
                audio.extend(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                start = chunk['offset'] / 1e7
                words.append((start, start + chunk['duration'] / 1e7, chunk['text']))
        return words, bytes(audio)

    words, audio = _run_async(run())
    if not audio:
        raise RuntimeError('no audio received')
    out.write_bytes(audio)
    return Speech(str(out), audio_duration(out), words, 'edge')


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # called from inside an event loop (e.g. an async MCP tool): use a thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _sapi(text: str, voice: str, rate: str, out: Path) -> Speech:
    if os.name != 'nt':
        raise RuntimeError('SAPI is only available on Windows')
    female = any(k in voice for k in ('Aria', 'Jenny', 'Michelle', 'Sonia', 'Ana', 'Neerja', 'Swara', 'Nanami'))
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        txt = f.name
    script = (
        'Add-Type -AssemblyName System.Speech;'
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;'
        "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::%s) } catch {};"
        '$s.Rate = %d;'
        "$s.SetOutputToWaveFile('%s');"
        "$s.Speak([IO.File]::ReadAllText('%s'));$s.Dispose()"
    ) % ('Female' if female else 'Male', _sapi_rate(rate), str(out).replace("'", "''"),
         txt.replace("'", "''"))
    try:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        os.unlink(txt)
    return Speech(str(out), audio_duration(out), [], 'sapi')


def _sapi_rate(rate: str) -> int:
    try:
        pct = int(rate.strip('%+')) * (-1 if rate.startswith('-') else 1)
    except ValueError:
        pct = 0
    return max(-10, min(10, pct // 10))


def silence(path: Path, seconds: float) -> None:
    write_wav(path, np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32))
