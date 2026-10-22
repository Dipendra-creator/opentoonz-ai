"""MCP server exposing OpenToonz scene authoring + an anime production studio.

Run:  python -m otai.mcp_server        (stdio transport)

Two layers of tools:
* production tools - cast characters, build sets, write shots (dialogue,
  emotions, actions, camera), preview and render a narrated anime video;
  every shot is also saved as a native OpenToonz scene (.tnz).
* tnz_* tools - direct, low-level access to OpenToonz scenes on disk:
  inspect, create, add image levels, set xsheet cells, keyframe pegbars,
  columns and the camera, and render (built-in renderer or tcomposer).
"""

from __future__ import annotations

import io
import subprocess
import threading
from pathlib import Path
from typing import Literal, Optional, get_args

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from PIL import Image as PILImage
from pydantic import BaseModel, Field

from . import config
from .art.background import ABSTRACT, EXTERIORS, INTERIORS, TIMES
from .production import director
from .production.render import render_production
from .production.schema import Action, BackgroundSpec, CharacterSpec, Shot
from .production.studio import Studio
from .render.compositor import Compositor
from .tnz.model import Scene

INSTRUCTIONS = """\
OpenToonz AI layer. Make 2D anime / cartoon animations without opening the OpenToonz app.

Production workflow (preferred):
1. studio_capabilities  -> vocabulary (locations, emotions, actions, shot types...).
2. create_production    -> returns production_id.
3. add_character for each recurring character (one call each, ~10 s). Look at the returned preview.
4. add_background for each location (reuse locations, 3-8 per video).
5. add_shots in batches of 5-15 shots. Each shot = background + characters + beats
   (dialogue / narration / reaction / action / pause). Speech duration comes from TTS, so the
   result reports real seconds; keep adding until total_seconds reaches the target.
6. preview_shot / contact_sheet to check framing, then fix with update_shot.
7. render_production (async) + render_status.
Every shot is also written as an OpenToonz scene (scenes/<shot>.tnz) that opens in OpenToonz.

Low-level tools (tnz_*) edit any .tnz scene directly: levels, xsheet cells, pegbar keyframes, camera.
Units: stage inches (camera is 16 x 9 in), degrees, frames are 0-based.
"""

mcp = MCPServer('opentoonz', instructions=INSTRUCTIONS)
_studio: Studio | None = None
_renders: dict[str, dict] = {}


def studio() -> Studio:
    global _studio
    if _studio is None:
        _studio = Studio()
    return _studio


async def _bg(fn, *args, **kw):
    return await anyio.to_thread.run_sync(lambda: fn(*args, **kw))


def _image(path: Path, max_w: int = 960) -> Image:
    img = PILImage.open(path).convert('RGB')
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=82)
    return Image(data=buf.getvalue(), format='jpeg')


# ==========================================================================
# Production tools
# ==========================================================================


@mcp.tool()
def studio_capabilities() -> dict:
    """Vocabulary accepted by the production tools, plus environment info."""
    from .art.character import BROW_DRAWINGS, EYE_DRAWINGS, FX_DRAWINGS, MOUTH_DRAWINGS
    return {
        'styles': {'anime': 'Japanese anime look: detailed irises, coloured line art, cel shading, ~6 heads tall',
                   'cartoon': 'Desi web-cartoon look (Indian comedy storytelling channels): ~3 heads tall, '
                              'big googly eyes with eyelid caps, thick ink outlines, cloud-curl or swoop hair, '
                              'hard cel shadows, 4-finger hands'},
        'locations': {'interiors': INTERIORS, 'exteriors': EXTERIORS,
                      'reaction_backdrops': ABSTRACT},
        'times_of_day': TIMES,
        'emotions': sorted(director.EMOTIONS),
        'emotion_auto_actions': director.EMOTION_ACTION,
        'actions': list(get_args(Action)),
        'shot_types': ['wide', 'full', 'medium', 'two_shot', 'closeup', 'extreme_closeup'],
        'camera_moves': ['static', 'push_in', 'pull_out', 'pan_left', 'pan_right', 'shake', 'zoom_snap', 'tilt_up'],
        'transitions': ['cut', 'fade', 'fade_white', 'dissolve', 'flash'],
        'positions': 'float -1..1 (stage left..right) or far_left/left/center/right/far_right',
        'character_options': {
            'hair_style': ['short', 'spiky', 'curly', 'messy', 'undercut', 'long', 'ponytail', 'bob',
                           'twintails', 'bun', 'buzz', 'bald'],
            'top': ['tshirt', 'shirt', 'hoodie', 'school_uniform', 'dress', 'kurta', 'suit', 'sweater'],
            'bottom': ['pants', 'jeans', 'skirt', 'shorts'],
            'age': ['child', 'teen', 'adult', 'elder'],
            'accessories': ['glasses', 'beard', 'mustache', 'bindi', 'earrings', 'cap', 'bow', 'headband',
                            'freckles', 'tie', 'mask', 'stripe (coloured band on a tshirt, uses accent_color)'],
            'skin_tone': ['fair', 'light', 'peach', 'medium', 'wheat', 'tan', 'brown', 'dark', 'deep', '#hex'],
            'colors': 'named (navy, maroon, saffron, denim, mint, ...) or #RRGGBB',
        },
        'drawings': {'eyes': EYE_DRAWINGS, 'brows': BROW_DRAWINGS, 'mouth': MOUTH_DRAWINGS,
                     'symbols': FX_DRAWINGS},
        'languages': ['en', 'en-IN', 'hi', 'ja'],
        'environment': {
            'productions_dir': str(studio().root),
            'tcomposer': str(config.tcomposer_exe()) if config.tcomposer_exe() else None,
            'opentoonz_repo': str(config.REPO_DIR),
        },
    }


@mcp.tool()
def create_production(title: str, story: str = '', style: Literal['anime', 'cartoon'] = 'anime',
                      resolution: Literal['480p', '720p', '1080p'] = '720p',
                      language: str = 'en', target_minutes: float = 2.0,
                      tts_engine: Literal['edge', 'sapi', 'none'] = 'edge',
                      subtitles: bool = True, narrator_voice: Optional[str] = None) -> dict:
    """Creates a production folder. target_minutes is 0.2-10. Returns production_id."""
    p = studio().create(title, story=story, style=style, resolution=resolution, language=language,
                        target_minutes=target_minutes, tts_engine=tts_engine, subtitles=subtitles,
                        narrator_voice=narrator_voice)
    return {'production_id': p.id, 'folder': str(studio().dir(p.id))}


@mcp.tool()
def list_productions() -> list[dict]:
    """Lists productions, newest first."""
    return studio().list()


@mcp.tool()
def get_production(production_id: str, include_story: bool = False) -> dict:
    """Cast, sets, shots with durations, total vs target seconds."""
    s = studio().summary(production_id)
    if include_story:
        s['story'] = studio().load(production_id).story
    return s


@mcp.tool()
async def add_character(production_id: str, character: CharacterSpec) -> list:
    """Designs a character and builds its cutout rig (all parts, expressions, mouth shapes,
    front + 3/4 views). Re-adding the same name replaces it. Returns info + a preview image."""
    info = await _bg(studio().add_character, production_id, character)
    return [info, _image(Path(info['preview']), 800)]


@mcp.tool()
async def add_background(production_id: str, background: BackgroundSpec) -> list:
    """Builds a background plate for a location. Re-adding the same name replaces it."""
    info = await _bg(studio().add_background, production_id, background)
    plate = studio().dir(production_id) / 'scenes' / 'assets' / 'backgrounds' / ('%s.0001.png' % info['level'])
    return [info, _image(plate, 640)]


@mcp.tool()
async def add_shots(production_id: str, shots: list[Shot], replace_all: bool = False) -> dict:
    """Appends shots (auto ids s001, s002...). Synthesizes speech, compiles each shot into an
    OpenToonz scene, and reports real durations. Invalid shots are rejected with reasons."""
    return await _bg(studio().add_shots, production_id, shots, replace_all)


@mcp.tool()
async def update_shot(production_id: str, shot_id: str, shot: Shot) -> dict:
    """Replaces one shot (keeps its id and position)."""
    return await _bg(studio().update_shot, production_id, shot_id, shot)


@mcp.tool()
def delete_shot(production_id: str, shot_id: str) -> dict:
    """Removes a shot."""
    return studio().delete_shot(production_id, shot_id)


@mcp.tool()
def reorder_shots(production_id: str, shot_ids: list[str]) -> dict:
    """Puts the given shots first, in this order (others keep their order after them)."""
    return studio().reorder(production_id, shot_ids)


@mcp.tool()
def get_shot(production_id: str, shot_id: str) -> dict:
    """Full JSON of one shot (useful before update_shot)."""
    prod = studio().load(production_id)
    for s in prod.shots:
        if s.id == shot_id:
            return {'shot': s.model_dump(), 'timing': prod.timings.get(shot_id)}
    raise ValueError('no shot %r' % shot_id)


@mcp.tool()
async def preview_shot(production_id: str, shot_id: str, at: float = 0.5) -> list:
    """Renders one frame of a shot. at: 0..1 fraction of the shot (or seconds if > 1)."""
    path = await _bg(studio().preview, production_id, shot_id, at)
    return [str(path), _image(path, 960)]


@mcp.tool()
async def contact_sheet(production_id: str) -> list:
    """Thumbnail grid of the middle frame of every shot."""
    path = await _bg(studio().contact_sheet, production_id)
    return [str(path), _image(path, 1280)]


@mcp.tool()
def render_production_video(production_id: str) -> dict:
    """Starts rendering the final MP4 in the background. Poll render_status."""
    job = _renders.get(production_id)
    if job and job.get('phase') not in ('done', 'error'):
        return {'status': 'already rendering', **job}
    _renders[production_id] = {'phase': 'starting'}

    def run():
        try:
            out = render_production(studio(), production_id,
                                    progress=lambda st: _renders[production_id].update(st))
            _renders[production_id].update({'phase': 'done', 'output': str(out)})
        except Exception as e:  # report to the poller
            _renders[production_id].update({'phase': 'error', 'error': repr(e)})

    threading.Thread(target=run, daemon=True).start()
    return {'status': 'started', 'poll': 'render_status'}


@mcp.tool()
def render_status(production_id: str) -> dict:
    """Progress of render_production_video (phase, done/total shots, output path)."""
    job = _renders.get(production_id)
    if job:
        return job
    status = studio().dir(production_id) / 'render' / 'status.json'
    if status.exists():
        import json
        return json.loads(status.read_text(encoding='utf-8'))
    return {'phase': 'not started'}


@mcp.tool()
def opentoonz_scenes(production_id: str) -> dict:
    """Paths of the OpenToonz scenes (.tnz) of a production, in shot order."""
    prod = studio().load(production_id)
    scenes = studio().dir(production_id) / 'scenes'
    return {'scenes': [str(scenes / ('%s.tnz' % s.id)) for s in prod.shots],
            'how_to_open': 'OpenToonz > File > Load Scene. Assets live in scenes/assets '
                           '(paths use $scenefolder so the folder can be moved).'}


# ==========================================================================
# Low-level OpenToonz scene tools
# ==========================================================================


class KeySpec(BaseModel):
    frame: int = Field(..., ge=0, description='0-based frame')
    value: float
    interp: Literal['linear', 'constant', 'ease'] = 'linear'
    step: int = Field(1, ge=1, le=8, description='hold each value N frames (animate on 2s/3s)')
    ease: float = Field(0.0, ge=0, description='ease in/out length in frames (interp=ease)')


def _load(path: str) -> Scene:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return Scene.load(p)


@mcp.tool()
def tnz_inspect(path: str) -> dict:
    """Reads an OpenToonz scene: camera, fps, levels, columns (cells, parents), pegbars and keyframes."""
    return _load(path).summary()


@mcp.tool()
def tnz_create(path: str, width: int = 1920, height: int = 1080, fps: float = 24.0) -> dict:
    """Creates an empty OpenToonz scene file (camera 16 in wide at the given resolution)."""
    s = Scene(res=(width, height), fps=fps)
    s.save(path)
    return s.summary()


@mcp.tool()
def tnz_add_level(path: str, name: str, images: list[str], dpi: float = 0.0) -> dict:
    """Adds a raster level made of the given image files (frame 1..N in order). Images are
    copied next to the scene (extras/<name>/). dpi 0 = full-frame at camera resolution."""
    scene = _load(path)
    folder = Path(path).parent / 'extras' / name
    folder.mkdir(parents=True, exist_ok=True)
    w0 = None
    for i, src in enumerate(images, start=1):
        img = PILImage.open(src)
        w0 = w0 or img.width
        img.convert('RGBA').save(folder / ('%s.%04d.png' % (name, i)))
    if dpi <= 0:
        dpi = (w0 or scene.camera.res[0]) / scene.camera.size[0]
    scene.add_level(name, '$scenefolder/extras/%s/%s..png' % (name, name), dpi)
    scene.save(path)
    return {'level': name, 'frames': len(images), 'dpi': dpi}


@mcp.tool()
def tnz_set_cells(path: str, level: str, frames: list[int], column: int = 0, start_row: int = 0,
                  column_name: str = '', parent: str = '') -> dict:
    """Writes xsheet cells: frames[i] (level drawing number, 0 = empty) goes to row start_row+i.
    column is 1-based; 0 appends a new column. parent: 'Table', 'Peg1', 'Col2', 'Camera1'."""
    scene = _load(path)
    if level not in scene.levels:
        raise ValueError('unknown level %r' % level)
    if column <= 0:
        idx, col = scene.add_column(column_name or level)
    else:
        while len(scene.columns) < column:
            scene.add_column()
        idx, col = column - 1, scene.columns[column - 1]
        if column_name:
            col.name = column_name
            scene.column_object(idx).name = column_name
    col.set_cells(start_row, level, frames)
    if parent:
        scene.column_object(idx).parent = parent
    scene.save(path)
    return {'column': idx + 1, 'rows': [start_row, start_row + len(frames) - 1],
            'frame_count': scene.frame_count}


@mcp.tool()
def tnz_set_keyframes(path: str, object_id: str,
                      param: Literal['x', 'y', 'z', 'so', 'rot', 'sx', 'sy', 'sc', 'shx', 'shy'],
                      keys: list[KeySpec], clear: bool = False) -> dict:
    """Keyframes a stage object ('Col3', 'Peg1', 'Camera1', 'Table'). x/y in inches, rot in
    degrees (counter-clockwise), scales as factors (1 = 100%)."""
    scene = _load(path)
    obj = scene.object(object_id)
    c = obj.curve(param)
    if clear:
        c.clear()
    for k in keys:
        c.set_key(k.frame, k.value, k.interp, step=k.step, ease_in=k.ease, ease_out=k.ease)
    scene.save(path)
    return {'object': object_id, 'param': param, 'keys': [[k.frame, k.value, k.interp] for k in c.keys]}


@mcp.tool()
def tnz_set_object(path: str, object_id: str, parent: str = '', name: str = '',
                   pivot: Optional[list[float]] = None,
                   defaults: Optional[dict[str, float]] = None) -> dict:
    """Sets a stage object's parent, name, pivot [x, y] (inches, object-local) and static
    (non-animated) values, e.g. defaults={'x': 2, 'sc': 1.5}. Use 'PegN' ids to create pegbars."""
    scene = _load(path)
    obj = scene.object(object_id)
    if parent:
        obj.parent = parent
    if name:
        obj.name = name
    if pivot:
        obj.set_pivot(float(pivot[0]), float(pivot[1]))
    for p, v in (defaults or {}).items():
        obj.curve(p).default = float(v)
    scene.save(path)
    return {'object': object_id, 'parent': obj.parent, 'center': obj.center}


@mcp.tool()
async def tnz_render(path: str, output: str = '', frame: Optional[int] = None,
                     engine: Literal['builtin', 'tcomposer'] = 'builtin',
                     width: int = 0, height: int = 0) -> list:
    """Renders a scene. With frame set: one PNG (also returned as an image). Otherwise the whole
    scene to MP4 (builtin) or PNG sequence (tcomposer, OpenToonz's own renderer if installed)."""
    scene = _load(path)
    size = (width, height) if width and height else None
    if engine == 'tcomposer':
        exe = config.tcomposer_exe()
        if exe is None:
            raise RuntimeError('tcomposer not found: install OpenToonz or set OPENTOONZ_DIR')
        out = output or str(Path(path).with_suffix('')) + '..png'
        cmd = [str(exe), path, '-o', out]
        if frame is not None:
            cmd += ['-range', str(frame + 1), str(frame + 1)]
        proc = await _bg(subprocess.run, cmd, capture_output=True, text=True, timeout=3600)
        return [{'output': out, 'returncode': proc.returncode, 'log': (proc.stdout + proc.stderr)[-3000:]}]
    comp = Compositor(scene, Path(path).parent, size=size)
    if frame is not None:
        out = Path(output or str(Path(path).with_suffix('')) + '_%04d.png' % frame)
        await _bg(comp.render_png, frame, out)
        return [str(out), _image(out)]
    out = Path(output or str(Path(path).with_suffix('.mp4')))
    await _bg(comp.render_to_video, out)
    return [{'output': str(out), 'frames': scene.frame_count, 'fps': scene.fps}]


def main() -> None:
    mcp.run()


if __name__ == '__main__':
    main()
