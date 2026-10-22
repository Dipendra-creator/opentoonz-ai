"""In-memory model of an OpenToonz scene that round-trips to .tnz files.

Covers the subset needed for cutout animation: raster image levels, level
columns, pegbars/columns/camera stage objects with keyframed transforms, and
the fx DAG plumbing that makes columns renderable. Semantics follow toonzlib:

* TStageObject::computeLocalPlacement (tstageobject.cpp)
    local = T(offset*inch + pos) * R(rot) * Shear * S(sx*sc, sy*sc) * T(-center*inch)
* TDoubleParam::getValue (tdoubleparam.cpp) for Linear / Constant / EaseInOut
  keyframes, including the per-keyframe ``step`` (animating "on 2s/3s").

Units: positions/centers in inches (as stored in the file), angles in degrees,
scales as factors, frames 0-based (frame 0 is "1" in the OpenToonz UI).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .stream import Node, TnzWriter, parse_file

INCH = 53.33333  # Stage::inch
SCENE_VERSION = '71.1'
GENERATOR = 'OpenToonz AI layer (otai)'

PARAM_DEFAULTS = {
    'x': 0.0, 'y': 0.0, 'z': 0.0, 'so': 0.0, 'rot': 0.0,
    'sx': 1.0, 'sy': 1.0, 'sc': 1.0, 'shx': 0.0, 'shy': 0.0,
}
PARAM_ORDER = ['x', 'y', 'z', 'so', 'sx', 'sy', 'sc', 'rot', 'shx', 'shy']

_TYPE_TO_CODE = {'constant': 'C', 'linear': 'L', 'ease': 'E', 'speed': 'S',
                 'ease_pct': 'Ep', 'exp': 'Exp'}
_CODE_TO_TYPE = {v: k for k, v in _TYPE_TO_CODE.items()}


# --------------------------------------------------------------------------
# Animation curves
# --------------------------------------------------------------------------


@dataclass
class Key:
    frame: int
    value: float
    interp: str = 'linear'  # interpolation of the segment that starts here
    ease_in: float = 0.0    # frames (EaseInOut handle coming into this key)
    ease_out: float = 0.0   # frames (EaseInOut handle leaving this key)
    step: int = 1


class Curve:
    """A TDoubleParam: a default value plus optional keyframes."""

    def __init__(self, default: float = 0.0) -> None:
        self.default = float(default)
        self.keys: list[Key] = []

    def set_key(self, frame: int, value: float, interp: str = 'linear',
                step: int = 1, ease_in: float = 0.0,
                ease_out: float = 0.0) -> Key:
        if interp not in _TYPE_TO_CODE:
            raise ValueError('unknown interpolation %r' % interp)
        frame = int(frame)
        for k in self.keys:
            if k.frame == frame:
                k.value, k.interp, k.step = float(value), interp, int(step)
                k.ease_in, k.ease_out = float(ease_in), float(ease_out)
                return k
        k = Key(frame, float(value), interp, float(ease_in), float(ease_out),
                int(step))
        self.keys.append(k)
        self.keys.sort(key=lambda q: q.frame)
        return k

    def clear(self) -> None:
        self.keys.clear()

    def is_default(self, base: float) -> bool:
        return not self.keys and abs(self.default - base) < 1e-12

    def value(self, frame: float) -> float:
        ks = self.keys
        if not ks:
            return self.default
        if frame <= ks[0].frame:
            return ks[0].value
        if frame >= ks[-1].frame:
            return ks[-1].value
        # segment (a, b) containing frame
        lo, hi = 0, len(ks) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ks[mid].frame <= frame:
                lo = mid
            else:
                hi = mid
        a, b = ks[lo], ks[hi]
        b_frame = b.frame
        if a.step > 1:
            rel = math.floor(b.frame - a.frame)
            step = min(a.step, rel)
            b_frame = a.frame + (rel // step) * step
            if frame > b_frame:
                frame = b_frame
            frame = a.frame + (math.floor(frame - a.frame) // step) * step
        span = b_frame - a.frame
        if a.interp == 'constant':
            return a.value if frame < b_frame else b.value
        if span <= 0:
            return a.value
        if a.interp == 'ease':
            return _ease_in_out(a.value, b.value, a.frame, b_frame, frame,
                                a.ease_out, b.ease_in)
        if a.interp == 'ease_pct':
            return _ease_in_out(a.value, b.value, a.frame, b_frame, frame,
                                a.ease_out * span * 0.01,
                                b.ease_in * span * 0.01)
        t = (frame - a.frame) / span
        return a.value + (b.value - a.value) * t  # linear (and approximations)


def _ease_in_out(v0, v1, f0, f1, frame, e0, e1) -> float:
    x3 = f1 - f0
    if x3 <= 0:
        return v0
    x = frame - f0
    if x <= 0:
        return v0
    if x >= x3:
        return v1
    e0, e1 = max(e0, 0.0), max(e1, 0.0)
    if e0 + e1 >= x3:
        m = min(max((e0 + x3 - e1) / 2, 0.0), x3)
        e0, e1 = m, x3 - m
    x1, x2 = e0, x3 - e1
    v = 2 / (x3 + x2 - x1)
    if x < x1:
        val = 0.5 * (v / e0) * x * x
    elif x > x2:
        val = 1 - 0.5 * (v / e1) * (x3 - x) * (x3 - x)
    else:
        val = x * v - 0.5 * v * e0
    return (1 - val) * v0 + val * v1


def _write_curve(w: TnzWriter, curve: Curve) -> None:
    w.child('default', curve.default)
    if not curve.keys:
        return
    w.open('keyframes')
    prev: Key | None = None
    for k in curve.keys:
        attrs = {'step': str(k.step)} if k.step > 1 else None
        w.open(_TYPE_TO_CODE[k.interp], attrs)
        if prev is not None:
            if prev.interp in ('linear',):
                w.child('prev', k.value)
            elif prev.interp in ('ease', 'ease_pct'):
                w.child('prev', k.value, -k.ease_in)
            elif prev.interp == 'speed':
                w.child('prev', k.value, 0.0, 0.0)
        if k.interp in ('ease', 'ease_pct'):
            w.values(k.frame, k.value, k.ease_out)
        elif k.interp == 'speed':
            w.values(k.frame, k.value, 0.0, 0.0)
        else:
            w.values(k.frame, k.value)
        w.close()
        prev = k
    w.close()


def _read_curve(node: Node, base: float) -> Curve:
    c = Curve(base)
    d = node.find('default')
    if d is not None and d.tokens():
        c.default = float(d.tokens()[0])
    kfs = node.find('keyframes')
    if kfs is None:
        return c
    for kn in kfs.nodes():
        interp = _CODE_TO_TYPE.get(kn.tag)
        if interp is None:  # expressions/files: keep the value only
            interp = 'linear'
        toks = kn.tokens()
        if len(toks) < 2:
            continue
        frame = int(float(toks[0]))
        try:
            value = float(toks[1])
        except ValueError:
            value = c.default
        ease_in = 0.0
        prev = kn.find('prev')
        if prev is not None and len(prev.tokens()) >= 2:
            ease_in = -float(prev.tokens()[1])
        ease_out = float(toks[2]) if interp in ('ease', 'ease_pct') and len(toks) > 2 else 0.0
        step = int(kn.attrs.get('step', '1'))
        c.keys.append(Key(frame, value, interp, ease_in, ease_out, step))
    c.keys.sort(key=lambda q: q.frame)
    return c


# --------------------------------------------------------------------------
# Stage objects
# --------------------------------------------------------------------------


def _affine(a, b, c, d, e, f) -> np.ndarray:
    return np.array([[a, b, c], [d, e, f], [0.0, 0.0, 1.0]])


@dataclass
class StageObject:
    id: str                        # 'Table', 'Camera1', 'Peg3', 'Col7'
    parent: str | None = 'Table'
    name: str = ''
    center: tuple[float, float] = (0.0, 0.0)
    offset: tuple[float, float] = (0.0, 0.0)
    curves: dict[str, Curve] = field(default_factory=dict)

    def curve(self, param: str) -> Curve:
        if param not in PARAM_DEFAULTS:
            raise KeyError('unknown stage object param %r' % param)
        if param not in self.curves:
            self.curves[param] = Curve(PARAM_DEFAULTS[param])
        return self.curves[param]

    def get(self, param: str, frame: float) -> float:
        c = self.curves.get(param)
        return c.value(frame) if c else PARAM_DEFAULTS[param]

    def set_pivot(self, cx: float, cy: float) -> None:
        """Sets the rotation/scale centre (inches, object-local) without
        moving the object at rest (TStageObject::setCenter on identity)."""
        self.center = (cx, cy)
        self.offset = (cx, cy)

    def local_affine(self, frame: float) -> np.ndarray:
        sc = self.get('sc', frame)
        sx = sc * self.get('sx', frame)
        sy = sc * self.get('sy', frame)
        ang = math.radians(self.get('rot', frame))
        shx, shy = self.get('shx', frame), self.get('shy', frame)
        px = (self.offset[0] + self.get('x', frame)) * INCH
        py = (self.offset[1] + self.get('y', frame)) * INCH
        cx, cy = self.center[0] * INCH, self.center[1] * INCH
        cs, sn = math.cos(ang), math.sin(ang)
        return (_affine(1, 0, px, 0, 1, py) @ _affine(cs, -sn, 0, sn, cs, 0) @
                _affine(1, shx, 0, shy, 1, 0) @ _affine(sx, 0, 0, 0, sy, 0) @
                _affine(1, 0, -cx, 0, 1, -cy))

    @property
    def is_camera(self) -> bool:
        return self.id.startswith('Camera')

    @property
    def is_column(self) -> bool:
        return self.id.startswith('Col')

    def write(self, w: TnzWriter, camera: 'CameraSpec | None') -> None:
        w.open_close('parent', {'id': self.parent or 'None', 'handle': 'B',
                                'parentHandle': 'B'})
        if self.name:
            w.child('name', self.name)
        w.child('isOpened', 0)
        w.child('center', self.center[0], self.center[1],
                -self.offset[0], -self.offset[1])
        w.child('status', 0)
        for p in PARAM_ORDER:
            c = self.curves.get(p)
            if c is not None and not c.is_default(PARAM_DEFAULTS[p]):
                w.open(p)
                _write_curve(w, c)
                w.close()
        if self.is_camera and camera is not None:
            w.open('camera')
            camera.write(w)
            w.close()


# --------------------------------------------------------------------------
# Camera, levels, columns
# --------------------------------------------------------------------------


@dataclass
class CameraSpec:
    res: tuple[int, int] = (1920, 1080)
    size: tuple[float, float] = (16.0, 9.0)  # inches

    @property
    def dpi(self) -> float:
        return self.res[0] / self.size[0]

    def write(self, w: TnzWriter) -> None:
        w.child('cameraSize', float(self.size[0]), float(self.size[1]))
        w.child('cameraRes', int(self.res[0]), int(self.res[1]))
        w.child('cameraXPrevalence', 1)
        w.child('interestRect', 0.0, 0.0, -1.0, -1.0)


@dataclass
class Level:
    """A raster image-sequence level (OVL_XSHLEVEL), e.g. ``hero_mouth..png``.

    ``path`` is the path as stored in the scene; '$scenefolder/...' paths are
    resolved against the scene's folder. Frame N lives in ``name.000N.png``.
    """
    name: str
    path: str
    dpi: float = 120.0

    def frame_path(self, scene_dir: Path, fid: int) -> Path:
        p = self.path.replace('\\', '/')
        if p.startswith('$scenefolder'):
            p = str(scene_dir) + p[len('$scenefolder'):]
        if '..' in os.path.basename(p):
            head, ext = p.rsplit('..', 1)
            return Path('%s.%04d.%s' % (head, fid, ext))
        return Path(p)  # single image file


@dataclass
class Column:
    name: str = ''
    cells: dict[int, tuple[str, int]] = field(default_factory=dict)
    opacity: int = 255

    def set_cells(self, start: int, level: str, fids) -> None:
        for i, fid in enumerate(fids):
            if fid is None or fid == 0:
                self.cells.pop(start + i, None)
            else:
                self.cells[start + i] = (level, int(fid))

    def hold(self, start: int, length: int, level: str, fid: int) -> None:
        self.set_cells(start, level, [fid] * length)

    def row_count(self) -> int:
        return max(self.cells) + 1 if self.cells else 0


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------


class Scene:
    def __init__(self, res=(1920, 1080), fps: float = 24.0) -> None:
        aspect = res[0] / res[1]
        self.camera = CameraSpec(tuple(res), (16.0, 16.0 / aspect))
        self.fps = float(fps)
        self.bg_color = (255, 255, 255, 0)
        self.levels: dict[str, Level] = {}
        self.columns: list[Column] = []
        self.objects: dict[str, StageObject] = {}
        self.output_path = '$scenefolder/render/output..png'
        self.path: Path | None = None
        self.warnings: list[str] = []
        self.object('Table').parent = None
        self.object('Camera1')

    # -- construction -------------------------------------------------------
    def object(self, oid: str) -> StageObject:
        if oid not in self.objects:
            parent = None if oid == 'Table' else 'Table'
            self.objects[oid] = StageObject(oid, parent)
        return self.objects[oid]

    def add_level(self, name: str, path: str, dpi: float) -> Level:
        if name in self.levels:
            raise ValueError('level %r already exists' % name)
        lv = Level(name, path, float(dpi))
        self.levels[name] = lv
        return lv

    def add_column(self, name: str = '', parent: str = 'Table') -> tuple[int, Column]:
        col = Column(name)
        self.columns.append(col)
        idx = len(self.columns) - 1
        obj = self.object('Col%d' % (idx + 1))
        obj.parent = parent
        obj.name = name
        return idx, col

    def column_object(self, idx: int) -> StageObject:
        return self.object('Col%d' % (idx + 1))

    def new_pegbar(self, name: str = '', parent: str = 'Table') -> StageObject:
        n = 1
        while 'Peg%d' % n in self.objects:
            n += 1
        peg = self.object('Peg%d' % n)
        peg.parent, peg.name = parent, name
        return peg

    @property
    def frame_count(self) -> int:
        return max([c.row_count() for c in self.columns] or [0])

    # -- placement ---------------------------------------------------------
    def placement(self, oid: str, frame: float, _cache=None) -> np.ndarray:
        cache = _cache if _cache is not None else {}
        if oid in cache:
            return cache[oid]
        obj = self.objects.get(oid) or StageObject(oid)
        m = obj.local_affine(frame)
        if obj.parent and obj.parent != oid:
            m = self.placement(obj.parent, frame, cache) @ m
        cache[oid] = m
        return m

    # -- saving --------------------------------------------------------------
    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self.to_text()
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(text, encoding='utf-8', newline='\n')
        os.replace(tmp, path)
        self.path = path
        return path

    def to_text(self) -> str:
        w = TnzWriter()
        n_frames = self.frame_count
        w.open('tnz', {'framecount': str(n_frames), 'version': SCENE_VERSION})
        w.child('generator', GENERATOR)
        self._write_properties(w, n_frames)
        level_ids = self._write_level_set(w)
        w.open('xsheet')
        column_fx_ids = self._write_columns(w, level_ids)
        self._write_pegbars(w)
        self._write_fx_nodes(w, column_fx_ids)
        w.close()  # xsheet
        w.close()  # tnz
        return w.text()

    def _write_properties(self, w: TnzWriter, n_frames: int) -> None:
        w.open('properties')
        w.open('cameras')
        w.open('camera')
        self.camera.write(w)
        w.close()
        w.close()
        w.open('outputs')
        for name in ('main', 'preview'):
            w.open('output', {'name': name})
            w.child('range', 0, max(n_frames - 1, 0))
            w.child('step', 1)
            w.child('shrink', 1)
            w.child('applyShrinkToViewer', 0)
            w.child('fps', self.fps)
            w.child('path', self.output_path)
            w.child('bpp', 32)
            if name == 'preview':
                w.child('syncColorSettings', 1)
            w.child('multimedia', 0)
            w.child('threadsIndex', 2)
            w.child('maxTileSizeIndex', 0)
            w.child('subcameraPrev', 0)
            w.child('stereoscopic', 0, 0.05)
            w.child('resquality', 0)
            w.child('fieldprevalence', 0)
            w.child('gamma', 1.0)
            w.child('timestretch', 25.0, 25.0)
            w.open('formatsProperties')
            w.close()
            w.close()
        w.close()
        w.child('bgColor', *self.bg_color)
        w.child('markers', 6, 0)
        w.child('subsampling', 1, 1)
        w.child('fieldguide', 16, 1.77778)
        w.close()

    def _write_level_set(self, w: TnzWriter) -> dict[str, int]:
        ids: dict[str, int] = {}
        w.open('levelSet')
        w.open('levels')
        for lv in self.levels.values():
            pid = w.persist_open('level')
            ids[lv.name] = pid
            w.values(lv.name)
            dpi = '%f' % lv.dpi
            w.open_close('info', {'dpix': dpi, 'dpiy': dpi})
            w.child('path', lv.path)
            w.persist_close()
        w.close()
        w.open('folder', {'name': 'Cast', 'type': 'default'})
        if self.levels:
            w.open('levels')
            for lv in self.levels.values():
                w.persist_ref('level', ids[lv.name])
            w.close()
        w.close()
        w.close()
        return ids

    def _write_columns(self, w: TnzWriter, level_ids: dict[str, int]) -> list[int]:
        fx_ids = []
        w.open('columns')
        for col in self.columns:
            w.persist_open('levelColumn')
            w.child('status', 0)
            if col.opacity < 255:
                w.child('camerastand_opacity', int(col.opacity))
            if col.cells:
                w.open('cells')
                rows = sorted(col.cells)
                i = 0
                while i < len(rows):
                    r = rows[i]
                    level, fid = col.cells[r]
                    n, inc = 1, 0
                    if i + 1 < len(rows) and rows[i + 1] == r + 1 and col.cells[rows[i + 1]][0] == level:
                        inc = col.cells[rows[i + 1]][1] - fid
                        while (i + n < len(rows) and rows[i + n] == r + n and
                               col.cells[rows[i + n]][0] == level and
                               col.cells[rows[i + n]][1] == fid + n * inc):
                            n += 1
                    if n == 1:
                        inc = 0
                    w.open('cell')
                    w.values(r, n)
                    w.persist_ref('level', level_ids[level])
                    w.values(str(fid), inc)
                    w.close()
                    i += n
                w.close()
            w.open('fx')
            fx_ids.append(w.persist_open('Toonz_columnFx'))
            _write_fx_common(w)
            w.persist_close()
            w.close()
            w.persist_close()
        w.close()
        return fx_ids

    def _write_pegbars(self, w: TnzWriter) -> None:
        w.open('pegbars')
        n_cols = len(self.columns)

        def order(oid: str):
            kind = {'Table': 0, 'Cam': 1, 'Peg': 2, 'Col': 3}[oid[:3] if oid != 'Table' else 'Table']
            num = int(''.join(ch for ch in oid if ch.isdigit()) or 0)
            return kind, num

        for oid in sorted(self.objects, key=order):
            obj = self.objects[oid]
            if obj.is_column and int(oid[3:]) > n_cols:
                continue
            attrs = {'id': oid}
            if oid == 'Camera1':
                attrs['activeboth'] = 'yes'
            w.open('pegbar', attrs)
            obj.write(w, self.camera)
            w.close()
        w.child('grid_dimension', 0)
        w.close()

    def _write_fx_nodes(self, w: TnzWriter, column_fx_ids: list[int]) -> None:
        w.open('fxnodes')
        if column_fx_ids:
            w.open('terminal')
            for pid in column_fx_ids:
                w.open('fxnode')
                w.persist_ref('Toonz_columnFx', pid)
                w.close()
            w.close()
        w.open('xsheet')
        xsheet_id = w.persist_open('Toonz_xsheetFx')
        _write_fx_common(w)
        w.persist_close()
        w.close()
        w.open('output')
        w.persist_open('Toonz_outputFx')
        w.open('params')
        w.close()
        w.open('ports')
        w.open('source')
        w.persist_ref('Toonz_xsheetFx', xsheet_id)
        w.close()
        w.close()
        w.child('numberId', 0)
        w.child('fxId', '')
        w.child('opened', 1)
        w.persist_close()
        w.close()
        w.child('grid_dimension', 0)
        w.close()

    # -- loading ------------------------------------------------------------
    @classmethod
    def load(cls, path) -> 'Scene':
        path = Path(path)
        root = parse_file(path).find('tnz')
        if root is None:
            raise ValueError('%s is not a .tnz scene' % path)
        scene = cls()
        scene.path = path
        props = root.find('properties')
        if props is not None:
            cams = props.find('cameras')
            cam = cams.find('camera') if cams is not None else None
            if cam is not None:
                size, res = cam.find('cameraSize'), cam.find('cameraRes')
                if size is not None:
                    scene.camera.size = tuple(size.floats()[:2])
                if res is not None:
                    scene.camera.res = tuple(res.ints()[:2])
            outs = props.find('outputs')
            if outs is not None:
                for o in outs.nodes('output'):
                    if o.attrs.get('name') == 'main':
                        fps = o.find('fps')
                        if fps is not None:
                            scene.fps = fps.floats()[0]
                        p = o.find('path')
                        if p is not None and p.tokens():
                            scene.output_path = p.tokens()[0]
            bg = props.find('bgColor')
            if bg is not None and len(bg.ints()) == 4:
                scene.bg_color = tuple(bg.ints())

        persist: dict[str, str] = {}  # level persist id -> level name
        lset = root.find('levelSet')
        if lset is not None:
            for levels in lset.nodes('levels'):
                for ln in levels.nodes():
                    scene._load_level(ln, persist)

        xsh = root.find('xsheet')
        if xsh is not None:
            cols = xsh.find('columns')
            if cols is not None:
                for cn in cols.nodes():
                    col = Column()
                    if cn.tag == 'levelColumn':
                        op = cn.find('camerastand_opacity')
                        if op is not None:
                            col.opacity = op.ints()[0]
                        cells = cn.find('cells')
                        if cells is not None:
                            for cell in cells.nodes('cell'):
                                toks = cell.tokens()
                                lref = next(cell.nodes(), None)
                                if lref is None or len(toks) < 4:
                                    continue
                                row, n = int(toks[0]), int(toks[1])
                                fid_str, inc = toks[2], int(toks[3])
                                level = persist.get(lref.attrs.get('id', ''))
                                if level is None:
                                    level = scene._load_level(lref, persist)
                                if level is None:
                                    continue
                                digits = ''.join(ch for ch in fid_str if ch.isdigit())
                                fid = int(digits or 1)
                                for i in range(n):
                                    col.cells[row + i] = (level, fid + i * inc)
                    else:
                        scene.warnings.append(
                            'column %d (%s) is not a level column; kept empty'
                            % (len(scene.columns) + 1, cn.tag))
                    scene.columns.append(col)
            pegs = xsh.find('pegbars')
            if pegs is not None:
                for pn in pegs.nodes('pegbar'):
                    scene._load_pegbar(pn)
            if xsh.find('fxnodes') is not None:
                fxn = xsh.find('fxnodes')
                internal = fxn.find('internal')
                if internal is not None and any(True for _ in internal.nodes()):
                    scene.warnings.append('fx nodes (effects) are not imported')
        for i, col in enumerate(scene.columns):
            col.name = scene.column_object(i).name
        return scene

    def _load_level(self, ln: Node, persist: dict) -> str | None:
        pid = ln.attrs.get('id', '')
        if ln.self_closing:
            return persist.get(pid)
        if ln.tag != 'level':
            self.warnings.append('level type <%s> is not supported' % ln.tag)
            return None
        toks = ln.tokens()
        name = toks[0] if toks else 'level%s' % pid
        pathn = ln.find('path')
        path = pathn.tokens()[0] if pathn is not None and pathn.tokens() else ''
        info = ln.find('info')
        dpi = 120.0
        if info is not None and 'dpix' in info.attrs:
            dpi = float(info.attrs['dpix'])
        ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
        if ext in ('pli', 'tlv', 'tzp', 'tzl', 'svg', 'mesh'):
            self.warnings.append(
                'level %r is a %s level; only raster image levels can be '
                'rendered by the built-in renderer' % (name, ext))
        self.levels[name] = Level(name, path, dpi)
        persist[pid] = name
        return name

    def _load_pegbar(self, pn: Node) -> None:
        oid = pn.attrs.get('id') or (pn.tokens()[0] if pn.tokens() else '')
        if not oid:
            return
        obj = self.object(oid)
        parent = pn.find('parent')
        if parent is not None:
            pid = parent.attrs.get('id', 'None')
            obj.parent = None if pid == 'None' else pid
        name = pn.find('name')
        if name is not None:
            obj.name = name.text()
        center = pn.find('center')
        if center is not None and len(center.floats()) >= 4:
            v = center.floats()
            obj.center = (v[0], v[1])
            obj.offset = (-v[2], -v[3])
        for p in PARAM_ORDER:
            cn = pn.find(p)
            if cn is not None:
                obj.curves[p] = _read_curve(cn, PARAM_DEFAULTS[p])
        if oid == 'Camera1':
            cam = pn.find('camera')
            if cam is not None:
                size, res = cam.find('cameraSize'), cam.find('cameraRes')
                if size is not None:
                    self.camera.size = tuple(size.floats()[:2])
                if res is not None:
                    self.camera.res = tuple(res.ints()[:2])

    # -- inspection -------------------------------------------------------
    def summary(self) -> dict:
        cols = []
        for i, c in enumerate(self.columns):
            rows = sorted(c.cells)
            obj = self.column_object(i)
            cols.append({
                'index': i + 1, 'name': c.name, 'parent': obj.parent,
                'rows': [rows[0], rows[-1]] if rows else None,
                'levels': sorted({lv for lv, _ in c.cells.values()}),
                'opacity': c.opacity,
                'animated': sorted(p for p, cv in obj.curves.items() if cv.keys),
            })
        objs = {}
        for oid, o in self.objects.items():
            if o.is_column:
                continue
            objs[oid] = {
                'name': o.name, 'parent': o.parent,
                'params': {p: {'default': cv.default,
                               'keys': [[k.frame, k.value, k.interp] for k in cv.keys]}
                           for p, cv in o.curves.items()},
            }
        return {
            'path': str(self.path) if self.path else None,
            'camera': {'res': list(self.camera.res), 'size_in': list(self.camera.size)},
            'fps': self.fps, 'frame_count': self.frame_count,
            'levels': [{'name': lv.name, 'path': lv.path, 'dpi': lv.dpi}
                       for lv in self.levels.values()],
            'columns': cols, 'stage_objects': objs, 'warnings': self.warnings,
        }


def _write_fx_common(w: TnzWriter) -> None:
    w.open('params')
    w.close()
    w.open('ports')
    w.close()
    w.child('numberId', 0)
    w.child('fxId', '')
    w.child('opened', 1)
