"""Paths and environment discovery for the AI layer."""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
AI_DIR = PACKAGE_DIR.parent
REPO_DIR = AI_DIR.parent


def home() -> Path:
    """Root for productions and jobs (override with OTAI_HOME)."""
    p = Path(os.environ.get('OTAI_HOME', AI_DIR / 'workspace'))
    p.mkdir(parents=True, exist_ok=True)
    return p


def productions_dir() -> Path:
    p = home() / 'productions'
    p.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    exe = os.environ.get('OTAI_FFMPEG') or shutil.which('ffmpeg')
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def tcomposer_exe() -> Path | None:
    """OpenToonz's command line renderer, if installed or built."""
    candidates = []
    if os.environ.get('OPENTOONZ_DIR'):
        candidates.append(Path(os.environ['OPENTOONZ_DIR']))
    candidates += [
        Path(r'C:\Program Files\OpenToonz'),
        REPO_DIR / 'toonz' / 'build' / 'Release',
        REPO_DIR / 'toonz' / 'build' / 'RelWithDebInfo',
        Path('/Applications/OpenToonz.app/Contents/MacOS'),
        Path('/usr/bin'), Path('/usr/local/bin'),
    ]
    for d in candidates:
        for name in ('tcomposer.exe', 'tcomposer'):
            if (d / name).is_file():
                return d / name
    return None


def stuff_dir() -> Path | None:
    """The OpenToonz 'stuff' folder tcomposer needs (TOONZROOT)."""
    for p in (os.environ.get('TOONZROOT'), r'C:\OpenToonz stuff',
              str(Path.home() / 'Documents' / 'OpenToonz stuff'),
              str(REPO_DIR / 'stuff')):
        if p and Path(p).is_dir():
            return Path(p)
    return None


_FONT_DIRS = [Path(r'C:\Windows\Fonts'), Path('/usr/share/fonts'),
              Path('/Library/Fonts'), Path('/System/Library/Fonts')]

_FONTS = {
    'latin': ['arialbd.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf'],
    'latin_regular': ['arial.ttf', 'DejaVuSans.ttf', 'Arial.ttf'],
    'comic': ['comicbd.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'],
    'title': ['impact.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'],
    'devanagari': ['NirmalaB.ttf', 'Nirmala.ttc', 'Nirmala.ttf',
                   'NotoSansDevanagari-Bold.ttf', 'Mangal.ttf'],
    'cjk': ['YuGothB.ttc', 'meiryob.ttc', 'msgothic.ttc',
            'NotoSansCJK-Bold.ttc'],
}


@lru_cache(maxsize=None)
def font_path(kind: str = 'latin') -> str | None:
    for name in _FONTS.get(kind, []) + _FONTS['latin']:
        for d in _FONT_DIRS:
            if (d / name).is_file():
                return str(d / name)
            if d.is_dir():
                hits = list(d.rglob(name))
                if hits:
                    return str(hits[0])
    return None
