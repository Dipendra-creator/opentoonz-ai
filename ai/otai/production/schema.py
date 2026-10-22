"""Data model of an animated production (what the AI fills in)."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ..art.background import LOCATIONS, TIMES

Style = Literal['anime', 'cartoon']
Emotion = Literal[
    'neutral', 'happy', 'laugh', 'excited', 'sad', 'crying', 'angry', 'furious',
    'surprised', 'shocked', 'scared', 'nervous', 'embarrassed', 'annoyed',
    'confused', 'thinking', 'love', 'smug', 'determined', 'tired', 'sleepy',
    'idea', 'disgusted']
Action = Literal[
    'none', 'wave', 'point', 'nod', 'shake_head', 'jump', 'shrug', 'facepalm',
    'cross_arms', 'think', 'hands_on_hips', 'cheer', 'fist_pump', 'bow', 'shiver',
    'gesture', 'clap', 'slump', 'lean_in', 'bounce', 'head_tilt', 'turn_around',
    'walk_in', 'walk_out']
ShotType = Literal['wide', 'full', 'medium', 'two_shot', 'closeup', 'extreme_closeup']
CameraMove = Literal['static', 'push_in', 'pull_out', 'pan_left', 'pan_right',
                     'shake', 'zoom_snap', 'tilt_up']
Transition = Literal['cut', 'fade', 'fade_white', 'dissolve', 'flash']


class Settings(BaseModel):
    title: str = 'Untitled'
    style: Style = 'anime'
    resolution: Literal['480p', '720p', '1080p'] = '720p'
    fps: int = Field(24, ge=12, le=30)
    language: str = Field('en', description="Dialogue language: 'en', 'en-IN', 'hi', 'ja'")
    tts_engine: Literal['edge', 'sapi', 'none'] = 'edge'
    narrator_voice: Optional[str] = None
    subtitles: bool = True
    target_minutes: float = Field(2.0, ge=0.2, le=10.0)

    @property
    def size(self) -> tuple[int, int]:
        return {'480p': (854, 480), '720p': (1280, 720), '1080p': (1920, 1080)}[self.resolution]


class CharacterSpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    description: str = ''
    gender: Literal['female', 'male'] = 'female'
    age: Literal['child', 'teen', 'adult', 'elder'] = 'teen'
    skin_tone: str = Field('light', description='fair, light, medium, wheat, tan, brown, dark, deep or #hex')
    hair_style: Literal['short', 'spiky', 'curly', 'messy', 'undercut', 'long', 'ponytail', 'bob',
                        'twintails', 'bun', 'buzz', 'bald'] = 'short'
    hair_color: str = 'black'
    eye_color: str = 'brown'
    top: Literal['tshirt', 'shirt', 'hoodie', 'school_uniform', 'dress', 'kurta',
                 'suit', 'sweater'] = 'tshirt'
    top_color: str = 'blue'
    bottom: Literal['pants', 'jeans', 'skirt', 'shorts'] = 'pants'
    bottom_color: str = 'navy'
    shoe_color: str = 'white'
    accent_color: str = 'red'
    accessories: list[Literal['glasses', 'beard', 'mustache', 'bindi', 'earrings', 'cap',
                              'bow', 'headband', 'freckles', 'tie', 'mask', 'stripe']] = []
    height: float = Field(1.0, ge=0.7, le=1.3)
    build: Literal['slim', 'average', 'broad'] = 'average'
    voice: Optional[str] = Field(None, description='edge-tts voice name; auto if empty')
    voice_pitch: Optional[str] = Field(None, description="e.g. '+10Hz'")
    voice_rate: str = '+0%'


class BackgroundSpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    location: str = 'living_room'
    time_of_day: Literal['day', 'evening', 'night'] = 'day'
    wall_color: Optional[str] = None
    accent_color: Optional[str] = None
    description: str = ''

    @field_validator('location')
    @classmethod
    def _loc(cls, v: str) -> str:
        if v not in LOCATIONS:
            raise ValueError('location must be one of %s' % LOCATIONS)
        return v


class ShotCharacter(BaseModel):
    name: str
    position: Union[float, Literal['far_left', 'left', 'center', 'right', 'far_right'], None] = None
    facing: Literal['auto', 'front', 'left', 'right'] = 'auto'
    emotion: Emotion = 'neutral'
    enter: Literal['none', 'left', 'right'] = 'none'
    exit: Literal['none', 'left', 'right'] = 'none'
    scale: float = Field(1.0, ge=0.5, le=1.5, description='depth scale')


class Beat(BaseModel):
    kind: Literal['dialogue', 'narration', 'reaction', 'action', 'pause'] = 'dialogue'
    character: Optional[str] = Field(None, description='speaker (dialogue) or actor (reaction/action)')
    text: str = ''
    emotion: Optional[Emotion] = None
    action: Action = 'none'
    target: Optional[str] = Field(None, description='character to point at / turn to')
    duration: Optional[float] = Field(None, ge=0.2, le=12.0, description='seconds; dialogue/narration use the audio length')
    camera_shake: bool = False


class Shot(BaseModel):
    id: str = ''
    background: str
    shot_type: ShotType = 'medium'
    focus: Optional[str] = None
    camera: CameraMove = 'static'
    characters: list[ShotCharacter] = []
    beats: list[Beat] = Field(..., min_length=1)
    transition: Transition = 'cut'
    title: Optional[str] = Field(None, description='on-screen title card text (e.g. "The next day...")')
    notes: str = ''


class Production(BaseModel):
    id: str
    settings: Settings
    story: str = ''
    characters: dict[str, CharacterSpec] = {}
    backgrounds: dict[str, BackgroundSpec] = {}
    shots: list[Shot] = []
    timings: dict[str, dict] = {}     # shot id -> compiled timing info
    voices: dict[str, list[str]] = {}  # character -> [voice, pitch]
