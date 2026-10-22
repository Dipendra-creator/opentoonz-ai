"""ffmpeg helpers: encoding frames, probing/decoding audio, concat, mux."""

from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from ..config import ffmpeg_exe

SAMPLE_RATE = 44100
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run([ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                           '-y'] + args, capture_output=True,
                          creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError('ffmpeg failed: %s' %
                           proc.stderr.decode(errors='replace')[-2000:])
    return proc


class FrameWriter:
    """Streams RGB frames into an H.264 mp4."""

    def __init__(self, path: Path, size: tuple[int, int], fps: float,
                 crf: int = 20, preset: str = 'veryfast') -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        w, h = size
        self._proc = subprocess.Popen(
            [ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (w, h),
             '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264',
             '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', str(self.path)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW)

    def write(self, rgb_bytes: bytes) -> None:
        self._proc.stdin.write(rgb_bytes)

    def close(self) -> None:
        self._proc.stdin.close()
        err = self._proc.stderr.read()
        if self._proc.wait() != 0:
            raise RuntimeError('ffmpeg encode failed: %s' %
                               err.decode(errors='replace')[-2000:])


def decode_audio(path: Path) -> np.ndarray:
    """Decodes any audio file to mono float32 at SAMPLE_RATE."""
    proc = _run(['-i', str(path), '-f', 's16le', '-ac', '1', '-ar',
                 str(SAMPLE_RATE), '-'])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def audio_duration(path: Path) -> float:
    return len(decode_audio(path)) / SAMPLE_RATE


def write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(samples, -1.0, 1.0)
    pcm = (data * 32767).astype('<i2').tobytes()
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def concat_videos(parts: list[Path], out: Path) -> Path:
    lst = out.with_suffix('.concat.txt')
    lst.write_text(''.join("file '%s'\n" % p.resolve().as_posix() for p in parts),
                   encoding='utf-8')
    _run(['-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', str(out)])
    lst.unlink(missing_ok=True)
    return out


def mux(video: Path, audio: Path | None, out: Path, loudnorm: bool = True) -> Path:
    """Joins video and audio; normalises loudness to -14 LUFS / -1.5 dBTP
    (the level YouTube plays back at)."""
    if audio is None:
        _run(['-i', str(video), '-c', 'copy', str(out)])
    else:
        af = ['-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', str(SAMPLE_RATE)] if loudnorm else []
        _run(['-i', str(video), '-i', str(audio), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k'] + af +
             ['-shortest', '-movflags', '+faststart', str(out)])
    return out


def video_duration(path: Path) -> float:
    proc = subprocess.run([ffmpeg_exe(), '-hide_banner', '-i', str(path)],
                          capture_output=True, creationflags=_NO_WINDOW)
    m = re.search(rb'Duration: (\d+):(\d+):([\d.]+)', proc.stderr)
    if not m:
        return 0.0
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)
