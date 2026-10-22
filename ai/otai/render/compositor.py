"""Built-in renderer for Scene models (no OpenToonz binaries required).

Matches the placement math tcomposer uses for raster levels:

    screen <- camera_dpi * inverse(camera placement) * column placement
              * level_dpi (image pixels -> stage units, image centred, y up)

Supported: raster image levels, column hierarchy (pegbars, parented columns,
camera-parented columns), keyframed x/y/rot/scale/shear, column opacity.
Not supported: z-depth perspective, fxs, vector (pli) and toonz raster (tlv)
levels. For those, render the saved .tnz with tcomposer instead.
"""

from __future__ import annotations

import math
import os
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..tnz.model import INCH, Scene


class _ImageCache:
    """Loads level frames, trims them to their alpha bbox, builds mipmaps."""

    def __init__(self, max_items: int = 600) -> None:
        self._items: OrderedDict = OrderedDict()
        self._max = max_items

    def get(self, path: Path, mip: int):
        # the modification time keeps long-lived caches correct after a rebuild
        key = (str(path), mip, os.path.getmtime(path))
        hit = self._items.get(key)
        if hit is not None:
            self._items.move_to_end(key)
            return hit
        if mip == 0:
            img = Image.open(path).convert('RGBA')
            full_w, full_h = img.size
            bbox = img.getbbox()
            if bbox is None:
                entry = (None, (0, 0), (full_w, full_h))
            else:
                # premultiplied: Pillow would otherwise convert on every transform
                entry = (img.crop(bbox).convert('RGBa'), (bbox[0], bbox[1]), (full_w, full_h))
        else:
            base, off, full = self.get(path, mip - 1)
            if base is None:
                entry = (None, off, full)
            else:
                w, h = base.size
                img = base.resize((max(1, w // 2), max(1, h // 2)),
                                  Image.Resampling.BOX)
                entry = (img, off, full)
        self._items[key] = entry
        if len(self._items) > self._max:
            self._items.popitem(last=False)
        return entry


# shared by every Compositor in a process, so render chunks reuse decoded levels
_PROCESS_CACHE = _ImageCache(max_items=1500)


def _vignette(size: tuple[int, int], strength: float) -> Image.Image:
    """Soft dark corners (screen space), like a lens; strength 0..1."""
    w, h = size
    sw, sh = max(2, w // 8), max(2, h // 8)
    y, x = np.mgrid[0:sh, 0:sw]
    d = np.sqrt(((x - sw / 2) / (sw / 2)) ** 2 + ((y - sh / 2) / (sh / 2)) ** 2) / math.sqrt(2)
    a = np.clip((d - 0.55) / 0.45, 0, 1) ** 1.6 * 255 * strength
    alpha = Image.fromarray(a.astype(np.uint8), 'L').resize((w, h), Image.Resampling.BILINEAR)
    img = Image.new('RGBA', (w, h), (28, 18, 36, 0))
    img.putalpha(alpha)
    return img


class Compositor:
    def __init__(self, scene: Scene, scene_dir: Path | None = None,
                 size: tuple[int, int] | None = None,
                 background=(255, 255, 255), vignette: float = 0.0) -> None:
        self.scene = scene
        self.scene_dir = Path(scene_dir or (scene.path.parent if scene.path else '.'))
        self.size = size or tuple(scene.camera.res)
        self.background = background
        self.cache = _PROCESS_CACHE
        self._vignette = _vignette(self.size, vignette) if vignette > 0 else None
        self._last_sig = None
        self._last_frame: Image.Image | None = None

    # ------------------------------------------------------------------
    def _screen_matrix(self) -> np.ndarray:
        w, h = self.size
        cam = self.scene.camera
        s = w / (cam.size[0] * INCH)
        return np.array([[s, 0, w / 2], [0, -s, h / 2], [0, 0, 1.0]])

    def layers(self, frame: int):
        """Yields (path, matrix_from_image_px_to_screen, opacity) bottom-up."""
        scene = self.scene
        cache: dict = {}
        cam = scene.placement('Camera1', frame, cache)
        view = self._screen_matrix() @ np.linalg.inv(cam)
        order = []
        for i, col in enumerate(scene.columns):
            obj = scene.column_object(i)
            order.append((obj.get('z', frame), obj.get('so', frame), i))
        order.sort()
        for _, _, i in order:
            col = scene.columns[i]
            cell = col.cells.get(frame)
            if cell is None or col.opacity <= 0:
                continue
            level = scene.levels.get(cell[0])
            if level is None:
                continue
            path = level.frame_path(self.scene_dir, cell[1])
            world = scene.placement('Col%d' % (i + 1), frame, cache)
            yield path, view @ world, level.dpi, col.opacity

    def render(self, frame: int) -> Image.Image:
        items = []
        for path, m, dpi, opacity in self.layers(frame):
            k = INCH / dpi
            # determinant -> pixel scale on screen, used to pick a mipmap
            scale = math.sqrt(abs(np.linalg.det(m[:2, :2]))) * k
            mip = 0
            while scale * (2 ** (mip + 1)) <= 1.0 and mip < 5:
                mip += 1
            items.append((path, m, k, mip, opacity))
        sig = tuple((str(p), np.round(m, 4).tobytes(), mip, op)
                    for p, m, k, mip, op in items)
        if sig == self._last_sig and self._last_frame is not None:
            return self._last_frame
        canvas = Image.new('RGBA', self.size, self.background + (255,))
        for path, m, k, mip, opacity in items:
            self._draw(canvas, path, m, k, mip, opacity)
        if self._vignette is not None:
            canvas.alpha_composite(self._vignette)
        self._last_sig, self._last_frame = sig, canvas
        return canvas

    def _draw(self, canvas: Image.Image, path: Path, m: np.ndarray, k: float,
              mip: int, opacity: int) -> None:
        try:
            img, off, full = self.cache.get(path, mip)
        except FileNotFoundError:
            return
        if img is None:
            return
        f = 2 ** mip
        fw, fh = full
        # image pixel (i, j) of the mip image -> stage units of the level
        img_m = np.array([[k * f, 0, (off[0] - fw / 2) * k],
                          [0, -k * f, (fh / 2 - off[1]) * k],
                          [0, 0, 1.0]])
        mm = m @ img_m
        w, h = img.size
        corners = mm @ np.array([[0, w, 0, w], [0, 0, h, h], [1, 1, 1, 1.0]])
        x0 = max(int(math.floor(corners[0].min())), 0)
        y0 = max(int(math.floor(corners[1].min())), 0)
        x1 = min(int(math.ceil(corners[0].max())), canvas.width)
        y1 = min(int(math.ceil(corners[1].max())), canvas.height)
        if x1 <= x0 or y1 <= y0:
            return
        inv = np.linalg.inv(mm)
        a, b, c = inv[0]
        d, e, g = inv[1]
        data = (a, b, a * x0 + b * y0 + c, d, e, d * x0 + e * y0 + g)
        part = img.transform((x1 - x0, y1 - y0), Image.Transform.AFFINE, data,
                             resample=Image.Resampling.BILINEAR).convert('RGBA')
        if opacity < 255:
            alpha = part.getchannel('A').point(lambda v: v * opacity // 255)
            part.putalpha(alpha)
        canvas.alpha_composite(part, (x0, y0))

    # ------------------------------------------------------------------
    def render_to_video(self, out: Path, frames: range | None = None,
                        post: Callable[[int, Image.Image], Image.Image] | None = None,
                        progress: Callable[[int, int], None] | None = None,
                        crf: int = 20) -> Path:
        from .video import FrameWriter
        frames = frames if frames is not None else range(self.scene.frame_count)
        writer = FrameWriter(out, self.size, self.scene.fps, crf=crf)
        last_key, last_bytes = None, None
        try:
            for n, fr in enumerate(frames):
                img = self.render(fr)
                if post is not None:
                    img = post(fr, img)
                key = id(img) if post is None else None
                if key is not None and key == last_key:
                    data = last_bytes
                else:
                    data = img.convert('RGB').tobytes()
                    last_key, last_bytes = key, data
                writer.write(data)
                if progress and n % 12 == 0:
                    progress(n, len(frames))
        finally:
            writer.close()
        return out

    def render_png(self, frame: int, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        self.render(frame).convert('RGB').save(out)
        return out
