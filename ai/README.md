# OpenToonz AI layer

Paste a story and get a narrated 2D animation (Japanese anime or Indian web-cartoon style),
with every shot also saved as a native OpenToonz scene. The OpenToonz app does not need to be
running or even installed: the layer reads and writes OpenToonz's scene format directly and ships
its own renderer.

```
story ──► web screen ──► Claude CLI (director) ──MCP──► otai studio ──► .tnz scenes + PNG levels
                                                                  └──► built-in renderer ─► final.mp4
                                                                  └──► tcomposer (optional, OpenToonz's renderer)
```

## Quick start (Windows)

```powershell
cd ai
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m otai.web          # opens on http://127.0.0.1:8765
```

Requirements: Python 3.11+, the Claude Code CLI (`claude`) on PATH and logged in. ffmpeg is
bundled through `imageio-ffmpeg`. The default voices use Microsoft Edge neural TTS, which sends the
dialogue text to Microsoft's speech service; pick "Windows voices (offline)" or "No voice" in the
form to keep everything local.

In the web screen: paste the story, choose the style, the length (0.5 to 10 minutes), the language
and the resolution, then press **Create animation**. The page shows the director's log while Claude
works, then the render progress, then the video, a contact sheet and a download button.

Outputs go to `ai/workspace/productions/<id>/` (change it with `OTAI_HOME`):

| Path | What |
|---|---|
| `render/final.mp4` | the finished video |
| `scenes/s001.tnz`, ... | one OpenToonz scene per shot (File > Load Scene) |
| `scenes/assets/` | character rigs, backgrounds and captions as PNG levels |
| `production.json` | the full script: cast, sets, shots, beats, timings |

## Using the MCP server directly

`.mcp.json` at the repository root registers the server for Claude Code sessions in this repo
(Claude Code asks you to approve it the first time). Any MCP client can launch it:

```
ai/.venv/Scripts/python.exe ai/run_mcp.py      # stdio transport
```

Production tools: `studio_capabilities`, `create_production`, `add_character`, `add_background`,
`add_shots`, `update_shot`, `delete_shot`, `reorder_shots`, `get_shot`, `get_production`,
`preview_shot` (returns an image), `contact_sheet`, `render_production_video`, `render_status`,
`opentoonz_scenes`, `list_productions`.

Scene tools (work on any .tnz the model supports): `tnz_inspect`, `tnz_create`, `tnz_add_level`,
`tnz_set_cells`, `tnz_set_keyframes`, `tnz_set_object`, `tnz_render`.

## How it maps onto OpenToonz

The layer was written against this repository's sources:

| OpenToonz | Source | AI layer |
|---|---|---|
| Stream format (XML-like tokens, backslash-escaped strings, shared persist ids) | `common/tstream/tstream.cpp` | `otai/tnz/stream.py` |
| Scene file: `<tnz>` > properties, levelSet, xsheet | `toonzlib/toonzscene.cpp` | `otai/tnz/model.py: Scene` |
| Camera (16 x 9 inch, res) and output settings | `toonzlib/sceneproperties.cpp`, `tcamera.cpp` | `CameraSpec`, `_write_properties` |
| Raster levels (`name..png`, custom dpi, `$scenefolder`) | `toonzlib/txshsimplelevel.cpp`, `levelset.cpp` | `Level` |
| Level columns and run-length cells | `toonzlib/txshlevelcolumn.cpp` | `Column` |
| Pegbars, columns and camera as stage objects | `toonzlib/tstageobject.cpp`, `tstageobjecttree.cpp` | `StageObject` |
| Keyframes (Linear / Constant / EaseInOut, per-key `step`) | `common/tparam/tdoubleparam.cpp`, `tdoublekeyframe.cpp` | `Curve` |
| Placement `T(offset+pos) R S T(-center)`, `Stage::inch = 53.333` | `computeLocalPlacement` | `StageObject.local_affine` |
| Fx DAG (column fx -> xsheet fx -> output fx) | `toonzlib/fxdag.cpp`, `tcolumnfx.cpp` | `_write_fx_nodes` |
| Command-line renderer | `tcomposer/tcomposer.cpp` | `tnz_render(engine='tcomposer')` |

Characters are cutout rigs, the standard OpenToonz approach to puppet animation: one pegbar per
character (feet on the ground) and 21 columns per character (ground shadow, torso, 2-bone legs,
2-bone arms with a back copy of the far arm for three-quarter views, head, eyes, mouth, brows,
hair front/back, blush, accessories, symbols), parented like a skeleton with pivots at the joints.
Eye (expression x look direction), mouth, hand and head-view changes are cell swaps in the xsheet.

## Animation engine

`otai/production/motion.py` and `director.py` animate every transform on ones (each frame),
baked to linear keyframes with Ramer-Douglas-Peucker reduction, so the .tnz stays small:

- always alive: breathing, sway, weight shift, micro head motion, blinks (sometimes double),
  eye darts
- acting from the voice track: head bobs land on loudness peaks, brow raises on the strongest
  stresses, talking gestures whose apex hits a stressed word, listeners look at the speaker and nod
- actions as poses with anticipation, back-out overshoot and moving holds (wave, point, facepalm,
  think, cross arms, shrug, cheer, clap, nod, shake head, bow...), takes and jumps with
  volume-preserving squash and stretch while the legs keep their length and feet stay planted
- 2-bone walk cycle (24-frame cycle, knee bend on the swing, hip bob, opposite arm swing) for
  entrances and exits
- secondary motion on damped springs: hair lags the head, forearms drag, symbols pop
- camera: eased push/pull/pan/tilt, zoom snap, breathing drift, decaying shake, vignette
- lip sync on twos, one frame ahead of the audio, with closed lips on m/b/p

Two looks: `anime` and `cartoon` (desi web cartoon: big googly eyes with eyelid caps, thick
ink lines, cloud-curl/swoop hair, hard hue-shifted cel shadows, 4-finger hands). The design rules
came from two research passes, kept in `docs/`.

## Package layout

```
otai/tnz/          .tnz reader/writer and scene model
otai/render/       built-in compositor, ffmpeg helpers
otai/art/          vector toolkit, character generator, backgrounds, captions
otai/audio/        TTS (edge / SAPI / none) and lip-sync timing
otai/production/   schema, rigging, director (shot -> scene), studio, renderer
otai/mcp_server.py MCP tools
otai/pipeline.py   Claude CLI runner (story -> production -> video)
otai/web/          story screen
docs/style_guide_research.md   research notes on the target styles
```

## Limits

- Characters are procedural vector drawings with front and three-quarter views (head, torso and
  shoes); there is no profile or back view yet, and arms/legs use the same drawings in both views.
- Building a character takes about 25 s (all expressions, mouths, hands and both views).
- The built-in renderer covers raster levels, the column/pegbar hierarchy, keyframed transforms and
  column opacity. It ignores z-depth perspective and fx. Shot transitions (fades, flashes) exist only
  in the MP4, not in the .tnz files.
- The .tnz importer reads raster levels, level columns and pegbar animation. Vector (pli) or toonz
  raster (tlv) levels, fx and sound columns are reported as warnings and not kept when a tool saves
  the scene back.
- `tcomposer` rendering is wired up but was not run here, because OpenToonz is not built or
  installed on this machine.
- The "Not Your Type" style preset is based on public facts about the channel (an Indian comedy
  cartoon channel) and general conventions. The visual details were not verified against its
  videos; see `docs/style_guide_research.md`.

## Tests

```
.venv\Scripts\python -m unittest discover -s tests
```
