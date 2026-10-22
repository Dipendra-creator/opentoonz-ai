"""Subtitle / title-card images.

Pillow lays out Latin and CJK text itself. Complex scripts (Devanagari etc.)
need text shaping; when Pillow is built without libraqm we fall back to
Windows GDI+ through PowerShell, which shapes them correctly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from ..config import font_path

COMPLEX = re.compile('[ऀ-෿؀-ۿ฀-๿]')
CJK = re.compile('[぀-ヿ一-鿿가-힯]')


def script_of(text: str) -> str:
    if COMPLEX.search(text):
        return 'devanagari'
    if CJK.search(text):
        return 'cjk'
    return 'latin'


def wrap(text: str, width: int = 42) -> list[str]:
    if CJK.search(text) and ' ' not in text.strip():
        width = max(10, width // 2)
        return [text[i:i + width] for i in range(0, len(text), width)]
    return textwrap.wrap(text, width) or ['']


def chunk_caption(text: str, width: int = 42, max_lines: int = 2) -> list[str]:
    lines = wrap(text, width)
    return ['\n'.join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]


def render_caption(text: str, size: tuple[int, int], out: Path, style: str = 'dialogue') -> Path:
    """Draws text centred in an image of ``size`` (transparent)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    fill, outline = {'dialogue': ('#FFFFFF', '#1B1B24'), 'narration': ('#FFE9A8', '#1B1B24'),
                     'title': ('#FFFFFF', '#1B1B24')}[style]
    px = int(h * (0.25 if style != 'title' else 0.32))
    script = script_of(text)
    if script == 'devanagari' and not features.check('raqm') and os.name == 'nt':
        render_gdi([(text, w, h, px, fill, outline, str(out))])
        return out
    kind = {'latin': 'latin' if style != 'title' else 'title', 'cjk': 'cjk', 'devanagari': 'devanagari'}[script]
    font = ImageFont.truetype(font_path(kind), px)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.multiline_text((w / 2, h / 2), text, font=font, fill=fill, anchor='mm', align='center',
                     spacing=int(px * 0.2), stroke_width=max(2, px // 9), stroke_fill=outline)
    img.save(out)
    return out


_GDI_SCRIPT = r'''
Add-Type -AssemblyName System.Drawing
$items = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
foreach ($it in $items) {
  $bmp = New-Object System.Drawing.Bitmap([int]$it.w, [int]$it.h, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAlias'
  $fam = New-Object System.Drawing.FontFamily('Nirmala UI')
  $fmt = New-Object System.Drawing.StringFormat
  $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $rect = New-Object System.Drawing.RectangleF(0, 0, [single]$it.w, [single]$it.h)
  $path.AddString($it.text, $fam, 1, [single]$it.px, $rect, $fmt)
  $pen = New-Object System.Drawing.Pen([System.Drawing.ColorTranslator]::FromHtml($it.outline), [single]([math]::Max(3, $it.px / 5)))
  $pen.LineJoin = 'Round'
  $g.DrawPath($pen, $path)
  $brush = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml($it.fill))
  $g.FillPath($brush, $path)
  $bmp.Save($it.out, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
'''


def render_gdi(items: list[tuple]) -> None:
    payload = [{'text': t, 'w': w, 'h': h, 'px': px, 'fill': f, 'outline': o, 'out': out}
               for t, w, h, px, f, o, out in items]
    with tempfile.TemporaryDirectory() as tmp:
        js = Path(tmp) / 'items.json'
        js.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        ps1 = Path(tmp) / 'render.ps1'
        ps1.write_text(_GDI_SCRIPT, encoding='utf-8-sig')
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ps1), str(js)], check=True, capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
