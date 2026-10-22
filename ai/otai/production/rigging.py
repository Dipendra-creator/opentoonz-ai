"""Turns a character rig manifest into OpenToonz columns and pegbars.

Hierarchy (cutout skeleton)::

    Peg (feet on the ground) -> shadow
                             -> body (pivot hips) -> thigh -> shin
                                                  -> head (pivot neck) -> face parts
                                                  -> upper arm -> forearm

The far arm in three-quarter view must sit behind the torso, so the right arm
also has a "back" pair of columns using the same levels; the director shows
the arm in one pair or the other depending on the view.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..art.character import VIEWS, drawing_id, eye_name
from ..tnz.model import Scene, StageObject

# upper segments sit above lower ones so joints stay hidden on straight limbs
PART_ORDER = ['shadow', 'hair_back', 'fore_r_back', 'upper_r_back', 'shin_r', 'thigh_r',
              'shin_l', 'thigh_l', 'body', 'head', 'blush', 'eyes', 'mouth', 'acc',
              'hair_front', 'brows', 'fx', 'fore_l', 'upper_l', 'fore_r', 'upper_r']
ALIAS = {'upper_r_back': 'upper_r', 'fore_r_back': 'fore_r'}
PARENT = {
    'shadow': None, 'body': None, 'head': 'body', 'hair_back': 'head', 'blush': 'head',
    'eyes': 'head', 'mouth': 'head', 'acc': 'head', 'hair_front': 'head', 'brows': 'head',
    'fx': 'head', 'upper_l': 'body', 'fore_l': 'upper_l', 'upper_r': 'body', 'fore_r': 'upper_r',
    'upper_r_back': 'body', 'fore_r_back': 'upper_r_back', 'thigh_l': 'body', 'shin_l': 'thigh_l',
    'thigh_r': 'body', 'shin_r': 'thigh_r',
}
HEAD_PARTS = ('hair_back', 'head', 'acc', 'hair_front')
# Rest pose: arms slightly away from the body (degrees, OpenToonz is CCW+)
REST_ROT = {'upper_l': -7.0, 'upper_r': 7.0, 'upper_r_back': 7.0,
            'fore_l': 5.0, 'fore_r': -5.0, 'fore_r_back': -5.0,
            # relaxed stance: feet a little apart, knees soft
            'thigh_l': -2.5, 'thigh_r': 2.5, 'shin_l': 1.5, 'shin_r': -1.5}


@dataclass
class CharacterRig:
    name: str
    manifest: dict
    peg: str
    cols: dict[str, int] = field(default_factory=dict)
    base: dict[str, tuple[float, float]] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    flip: bool = False

    def obj(self, scene: Scene, part: str) -> StageObject:
        return scene.column_object(self.cols[part])

    def col_id(self, part: str) -> str:
        return 'Col%d' % (self.cols[part] + 1)

    def info(self, part: str) -> dict:
        return self.manifest['parts'][ALIAS.get(part, part)]

    @property
    def height(self) -> float:
        return self.manifest['height'] * self.scale

    @property
    def head_height(self) -> float:
        return self.manifest['head_height'] * self.scale

    @property
    def props(self) -> dict:
        return self.manifest['proportions']

    def face_world(self) -> tuple[float, float]:
        fx, fy = self.manifest['face_center']
        return (self.x + (-fx if self.flip else fx) * self.scale, self.y + fy * self.scale)


def add_character_to_scene(scene: Scene, manifest: dict, rel_dir: str,
                           x: float = 0.0, y: float = 0.0, scale: float = 1.0,
                           flip: bool = False, **_) -> CharacterRig:
    """Adds pegbar + columns for a character. ``rel_dir`` is the folder of the
    part PNGs relative to the scene folder ('.' when next to the .tnz)."""
    if manifest.get('rig_version', 1) < 2:
        raise ValueError('character %r was built with an old rig; add it again' % manifest['name'])
    name = manifest['name']
    peg = scene.new_pegbar(name)
    peg.curve('x').default = x
    peg.curve('y').default = y
    peg.curve('sc').default = scale
    if flip:
        peg.curve('sx').default = -1.0
    rig = CharacterRig(name, manifest, peg.id, x=x, y=y, scale=scale, flip=flip)
    rel = rel_dir.strip('/').replace('\\', '/')
    for part in PART_ORDER:
        info = rig.info(part)
        if info['level'] not in scene.levels:
            path = '$scenefolder/%s%s..png' % ('' if rel in ('', '.') else rel + '/', info['level'])
            scene.add_level(info['level'], path, info['dpi'])
        idx, _ = scene.add_column('%s_%s' % (name, part))
        rig.cols[part] = idx
    for part in PART_ORDER:
        info = rig.info(part)
        parent_part = PARENT[part]
        obj = scene.column_object(rig.cols[part])
        obj.parent = peg.id if parent_part is None else rig.col_id(parent_part)
        cx, cy = info['center']
        px, py = (0.0, 0.0) if parent_part is None else rig.info(parent_part)['center']
        pos = (cx - px, cy - py)
        rig.base[part] = pos
        obj.curve('x').default = pos[0]
        obj.curve('y').default = pos[1]
        pvx, pvy = info['pivot']
        obj.set_pivot(pvx - cx, pvy - cy)
        if part in REST_ROT:
            obj.curve('rot').default = REST_ROT[part]
    return rig


def set_drawing(scene: Scene, rig: CharacterRig, part: str, start: int,
                length: int, fid: int) -> None:
    scene.columns[rig.cols[part]].hold(start, length, rig.info(part)['level'], fid)


def clear_part(scene: Scene, rig: CharacterRig, part: str, start: int, length: int) -> None:
    col = scene.columns[rig.cols[part]]
    for r in range(start, start + length):
        col.cells.pop(r, None)


def pose_rest(scene: Scene, rig: CharacterRig, start: int, length: int,
              view: str = 'front', eyes: str = 'open', brows: str = 'neutral',
              mouth: str = 'rest', look: str = 'c') -> None:
    m = rig.manifest
    for part in HEAD_PARTS + ('body', 'shin_l', 'shin_r', 'thigh_l', 'thigh_r'):
        set_drawing(scene, rig, part, start, length, drawing_id(m, part, '', view))
    for part in ('shadow', 'upper_l'):
        set_drawing(scene, rig, part, start, length, 1)
    set_drawing(scene, rig, 'fore_l', start, length, drawing_id(m, 'fore_l', 'open'))
    front_r = view == 'front'
    for part in ('upper_r', 'fore_r', 'upper_r_back', 'fore_r_back'):
        clear_part(scene, rig, part, start, length)
    up, fo = ('upper_r', 'fore_r') if front_r else ('upper_r_back', 'fore_r_back')
    set_drawing(scene, rig, up, start, length, 1)
    set_drawing(scene, rig, fo, start, length, drawing_id(m, 'fore_r', 'open'))
    set_drawing(scene, rig, 'eyes', start, length, drawing_id(m, 'eyes', eye_name(eyes, look), view))
    set_drawing(scene, rig, 'brows', start, length, drawing_id(m, 'brows', brows, view))
    set_drawing(scene, rig, 'mouth', start, length, drawing_id(m, 'mouth', mouth, view))


__all__ = ['CharacterRig', 'PART_ORDER', 'PARENT', 'ALIAS', 'REST_ROT', 'VIEWS',
           'add_character_to_scene', 'set_drawing', 'clear_part', 'pose_rest']
