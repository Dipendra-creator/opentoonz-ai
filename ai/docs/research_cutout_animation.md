# Procedural cutout animation spec (24 fps)

Source note: web search returned mostly generic material. Items marked [S] have a cited source; everything else is [inferred] from standard animation practice (Williams "Animator's Survival Kit", Preston Blair, Disney 12 principles, spring-physics math) and should be treated as tunable defaults, not measured facts.

Sources:
- Toon Boom lip-sync (8 mouth positions A-G + X rest, auto-detect fills cells): https://docs.toonboom.com/help/harmony-24/premium/cut-out-animation/animate-lip-sync.html , https://learn.toonboom.com/modules/lip-sync-animation/topic/activity-3-mapping-lip-sync-detection
- Lip-sync: key only strong vowels/consonants; offset mouth 1-2 frames ahead of audio: https://www.highonfilms.com/lip-sync-animation-techniques-every-character-animator-should-know/
- Moho/Preston Blair set (AI, O, E, U, L, WQ, MBP, FV, rest): https://lostmarble.com/forum/viewtopic.php?p=217061
- Walk cycle poses (contact, down, passing, up; 24-frame loop contacts at 1/13/25; down lowest, up highest): https://animation.monmouth.edu/instruct/?p=351 , https://openlab.bmcc.cuny.edu/ani-260-1300-intro-2d-animation-sp-2021/?p=386
- Blink 2-4 frames (secondary): https://playbooks.com/skills/dylantarre/animation-principles/timing-mastery
- Spring/damping (critical damping = fastest no-overshoot; ratio<1 overshoots): https://developer.android.com/reference/androidx/dynamicanimation/animation/SpringForce , https://github.com/charmbracelet/harmonica (Ryan Juckett damped oscillator)
- Overlap/follow-through (heavier parts lag more, added after main pass): https://en.wikipedia.org/wiki/Follow_through_and_overlapping_action
- Camera shake params (amplitude, frequency, blend in/out; Perlin for strong, sine for soft): https://dev.epicgames.com/documentation/unreal-engine/camera-shakes-in-unreal-engine

## 1. Timing

Rules (inferred, consistent with industry practice):
- Web cartoons (Jaiden, TheOdd1sOut, Domics, Not Your Type) render at 24/25/30 fps but hold most drawings/poses 2-6 frames; the "alive" feel comes from continuous small motion layers, not from every frame being new. Cutout TV (Harmony/Moho) animates the rig on ones for continuous interpolation (the computer tweens) but with eased keys; only drawing swaps (mouth, hands, head angles) are on twos/threes.
- Rule for generator: transforms (position/rotation/scale) = evaluate curve EVERY frame (ones). Drawing substitutions = on twos (mouth on twos, min hold 2 frames; fast action on ones for 1-3 frames only). Never "key on 2s" a transform: sample the eased curve each frame instead.
- Keyframes per action: 3 to 5 per moving part (anticipation, extreme, overshoot, settle) with each part offset in time (section 9).

Typical durations at 24 fps (inferred; ranges are start-to-rest):

| Action | Frames | Structure |
|---|---|---|
| Head turn (small, 15-30 deg) | 8-12 | ease in/out, 1-2 frame anticipation counter-move 2 deg, overshoot 8%, settle 4 |
| Head turn with drawing swap | 6-8 | swap front->3/4 at 40-50%, on a blink or smear frame |
| Nod (one) | 8-10 | down 4 (ease-out), up 5 (ease), 6-10 deg |
| Emphatic nod/bob on stress | 6 | down 2-3 fast, up 3-4 |
| Blink | 5-6 total | open, half (f1), closed (f2-3, hold 2), half (f4), open (f5). On twos: open, closed(2f), half(2f), open |
| Eye dart | 2-3 frame move then hold 12-48 | instant on 1-2 frames, no tween or 2-frame ease |
| Gesture raise / hold / return | 8-10 / 10-24 / 10-14 | hold must be a moving hold (section 3) |
| Reaction take (surprise) | anticip 3, take 4, hold 12-24, settle 8 | squash 3f then stretch 4f |
| Jump | anticip crouch 6-8, launch 3, air 10-14 (apex hang 2-3 slower), land 2, squash 3, recover 6-8 | |
| Sit down | 14-20 | hips lead, torso follows +3, settle bounce 4 |
| Point | raise 6-8, hold 12+, return 8-10 | |
| Wave cycle | 12-16 frames per wave, 3-4 waves | forearm rotation +-25 deg, hand lags 3 |
| Shrug | up 6, hold 6-10, down 8 | shoulders 6-10 px up, head tilts 5 deg, arms rotate out 10 deg |
| Facepalm | raise 8, slap 2, hold 24-48, slow slide down 12 | head dips 4 deg on contact |
| Laugh | 12-frame loop, repeat | body y bounce 3-6 px, head back 5 deg, shoulders shake at 2-frame period |

## 2. Easing, anticipation, overshoot

```
ease_in_out_sine(t) = 0.5 - 0.5*cos(pi*t)
ease_in_out_cubic(t) = t<0.5 ? 4t^3 : 1 - (-2t+2)^3/2
ease_out_back(t, s=1.7) = 1 + (s+1)*(t-1)^3 + s*(t-1)^2   # ~10% overshoot at s=1.7
```
Defaults: use cubic in/out for body, sine for small head/eye moves, "fast-in slow-out" (ease_out_cubic) for snappy gestures and takes.

Anticipation: move 10-15% of the main amplitude in the opposite direction over 3-6 frames (arm raise: arm dips 6 deg, 4 frames; jump: crouch 15-25% body height 6-8 frames; head turn: 2 deg counter, 2 frames; take: 3 frames squash).

Overshoot/settle: overshoot 8-15% of move for arms/heads, 5% for torso, 20-30% for cartoon takes; settle within 6-12 frames, 1-2 reversals.

Damped spring (exact solution, for per-frame sampling at t = frame/24):
```
# x(t) from x0 to target, v0 initial, freq f (Hz), zeta damping ratio
w = 2*pi*f
if zeta < 1:
  wd = w*sqrt(1-zeta^2)
  A = x0 - target; B = (v0 + zeta*w*A)/wd
  x(t) = target + exp(-zeta*w*t)*(A*cos(wd*t) + B*sin(wd*t))
else (critical): x(t)=target+(A+(v0+w*A)*t)*exp(-w*t)
overshoot% = 100*exp(-pi*zeta/sqrt(1-zeta^2))
```
Presets (inferred):

| Use | f (Hz) | zeta | overshoot |
|---|---|---|---|
| Arm/hand settle | 3.0 | 0.45 | ~20% |
| Head settle | 2.5 | 0.55 | ~12% |
| Torso | 2.0 | 0.7 | ~5% |
| Hair / ponytail | 3.5 | 0.25 | ~45%, rings 3-4 cycles |
| Ear / floppy | 4.0 | 0.3 | ~37% |
| Cloth hem / sleeve | 2.5 | 0.4 | ~25% |
| Cartoon take pop | 4.0 | 0.2 | ~53% |
| Camera settle | 1.5 | 0.9 | ~0.2% |

## 3. Idle / always alive

| Layer | Parameters (inferred) |
|---|---|
| Breathing | torso scaleY 1.0 -> 1.015 (1-2%), shoulders y +-1.5 px, period 3.5-4.5 s (84-108 f), sine; head follows delayed 4 f at 50% amplitude |
| Weight shift | every 3-6 s random: hips x +-6 px, torso counter-rotate 1.5 deg, 20-30 f ease, hold; lean to one leg |
| Micro head | sum of 2 sines (periods 3.1 s, 5.3 s), +-1.0 deg rotation, +-1 px; independent phase per character |
| Blink | interval random 2.5-6 s (mean 4); 10-15% chance double blink; also blink on every head turn and big gaze shift; blink when listener nods |
| Eye dart | every 0.8-3 s (speaker looks away at thought, listener holds contact); 1-3 px pupil jump; 70% return to camera/partner |
| Brows | tiny +-1 px drift every 2-4 s; raise 3-5 px on stress |

Moving holds: never output a constant pose. Rather than stopping, make the last 10% of a move "creep" (ease-out to 0 velocity over a long tail) then switch to idle layer. Add 1-3 px drift on the held limbs (arms drift 0.5-1 deg), or alternate 2 poses ("hold with a cycle of 12-24 frames"). Idle noise is ADDITIVE on top of action curves and fades to 30% during big actions.

## 4. Talking and acting

- Mouth set (Preston Blair / Hanna-Barbera, 8-10 shapes): rest/closed, MBP (closed pressed), AI (wide open), E (half open, wide), O (round), U/WQ (small round), FV (teeth on lip), L/TH/DT (tongue up), etc. Toon Boom auto-lip-sync uses 8 (A-G, X rest) [S].
- Mouth on twos (hold >= 2 frames; 3-4 on slow vowels). Key only strong vowels and hard consonants (MBP, FV), skip tiny ones [S]. Place mouth key 1-2 frames BEFORE the audio onset [S]. Always show closed mouth on MBP; close for 1-2 frames between words/phrases. Open size scales with loudness (3 sizes per vowel).
- Head: bob down 2-4 px/1-3 deg on each stressed syllable (loudness peak > 1.3x local mean), 4-6 frame ease; larger tilt on phrase ends. Head moves start ~2 frames before the stress.
- Brow raise on stressed words (1 per 1-2 phrases), 3-6 px up, 4 frames in, 8 frames out, 1 frame ahead of head.
- Gestures: 1 per 1.5-3 s of speech, on the strongest stress of a phrase: raise 8 f, apex lands ON the stressed word, hold, drop at phrase end. Alternate hands, vary size; return to idle between, not to a dead pose.
- Listener: nod every 2-4 s (small, 6 f), blink on speaker's phrase boundaries, eyes stay on speaker with an occasional dart away; reaction (brows, small head tilt 3-5 deg) 4-8 frames after key line.

## 5. Secondary motion

- Chains: each child lags parent by 2-4 frames (forearm 2, hand 3-4, hair root 3, hair tip 6-8).
- Implement as spring following parent angle: `theta_child'' = -w^2*(theta_child - theta_parent) - 2*zeta*w*theta_child'` with presets from section 2. Add parent velocity coupling: hair rotation += -0.3 * parent angular velocity.
- Squash/stretch (volume preserving: sx = 1/sy): head/body take: stretch sy 1.12-1.2 (sx 0.9) for 3-4 frames, then squash sy 0.85-0.9 (sx 1.1) 2-3 frames, settle spring. Jump: anticipation squash sy 0.85, launch stretch 1.1, apex 1.0, landing squash 0.88 (2-3 f), rebound 1.04, rest. Subtle (talking/nod): 1-3%. Pivot at the feet for body, at the neck for head.

## 6. Head turns

Front -> 3/4 -> side drawings (3 head sets, plus mirrored). Sequence over 6-10 frames: frames 0-2 anticipate (head x -2 px, scale), frame 3: width squash to 0.85 and features slide 30% toward turn direction, frame 4-5: swap to 3/4 drawing (ideally on a blink frame or a 1-frame smear/blur), then 3/4 holds with features slid, optionally to side. Facial feature slide: eyes/nose/mouth x offset = turn * face_width * 0.35, with nose sliding more (1.2x) than eyes (1.0x), far eye squashed to 0.8 scale. Hair front/back layers slide opposite, delayed 2 f. Keep on ones for the 2 swap frames, twos around them.

## 7. Walk cycle (2-bone leg, cutout)

Use 24 frames per 2 steps (contact frames 0, 12, 24 [S: Monmouth]) = 12-frame step (0.5 s, relaxed); 16 frames per 2 steps (8-frame step) is brisk; 8 per 2 steps (4 per step) for run. Poses: contact, down, passing, up, each 3 frames apart at 12-frame step [S: poses; spacing inferred].

Leg angles (thigh from vertical, + forward; shin relative to thigh, - = knee bend), per step with phases p = 0, 3, 6, 9 of 12 (inferred values):

| Pose (frame) | Front leg thigh/shin | Back leg thigh/shin | Hip y (px, + up) | Arm swing (front-side arm) |
|---|---|---|---|---|
| Contact (0) | +28 / 0 | -22 / -10 | 0 (mid-high) | opposite arm fwd +25 |
| Down (3) | +18 / -12 | -28 / -35 | -6 (lowest) | +15 |
| Passing (6) | 0 / -45 (swing leg) | 0 / 0 (planted) | +2 | 0 |
| Up (9) | -10 / -60 | +20 / -5 | +6 (highest) | -20 |

Simpler continuous form:
```
phase = (frame % period)/period * 2pi
thigh_L =  A*sin(phase);          thigh_R = -A*sin(phase)    # A = 25 deg
shin_L  = -max(0, sin(phase - 0.6))*55   # knee bends only in swing
hip_y   = bob * cos(2*phase)               # bob 6-8 px at 100 px leg length (~6%)
hip_rot = 2.5*sin(phase); shoulder_rot = -3*sin(phase)
arm_upper = -0.8*thigh_same_side (ie +-20 deg); forearm = lagged 3 f, extra bend -10..-25 deg when arm swings fwd
head y = hip_y*0.6 delayed 2 f; head rot 1 deg opposite shoulders
```
Foot stays planted: solve IK (or compute foot x velocity = -body speed during stance) to avoid sliding. Front view: horizontal sway of hips +-4 px and legs scale not rotate (foreshortened); feet lift 6-10 px, bob doubled. 3/4 view: far leg drawn behind, 0.9 scale, same angles with 70% amplitude. Vertical motion on cubic arcs, not linear.

## 8. Camera

- Pan/zoom: ease_in_out_cubic, or sine; durations 24-72 f for slow push; sudden snap 8-12 f ease-out.
- Slow push-in on dialogue: 3-8% scale over shot length (3-8 s), linear-ish with sine ends; punch-in on punchline: 8-15% in 6-8 f with spring (f 2 Hz, zeta 0.8).
- Shake: offset = A*exp(-t/tau)*noise(t*freq): A 6-20 px (1-3% of frame), freq 12-18 Hz (every 1-2 f), tau 0.3-0.5 s (8-12 f), rotation 0.5 deg. Heavier hits use tau 0.8 s. [S for the amplitude/frequency/blend concept; numbers inferred]
- Parallax (multiplane): layer speed ratio = 1/depth: far bg 0.2-0.4, mid 0.6-0.8, char plane 1.0, fg 1.3-1.6 [inferred].
- Cutting rhythm: web storytelling: shot 2-6 s (48-144 f), avg ~3-4 s; punchline/reaction cuts 0.5-1.5 s; change framing (wide/medium/closeup) every 2-3 shots; insert a reaction close-up after every key joke [inferred].

## 9. Polish tricks

- Offset timing: root/hips at t0, torso +1-2 f, head +2-3, upper arm +2, forearm +3-4, hand +4-5, hair +4-8. Never start two big parts on the same frame; duration also varies +-20% per part.
- Arcs: move hands/heads along quadratic arcs (offset the midpoint perpendicular by 10-15% of the distance) rather than straight lines.
- Vary hold lengths: draw from {6, 10, 14, 20, 30, 48} frames, avoid regular rhythm.
- Smears/motion blur on fast moves: on 1-2 frames of a fast limb, stretch part 1.3-1.6x along motion and 20-40% alpha ghost (or directional blur); hand gets a smear for waves/points.
- Contact shadows: ellipse under feet, scale 0.8 -> 0.5 and alpha 60% -> 25% as character rises in jump; softly ride body sway.
- Lighting/color: 1 rim light or multiply gradient overlay; subtle bg blur/vignette; film grain 3-5%.
- Always overlay the idle layer (section 3) and a global "subtle camera drift" (1-2 px sine, period 8 s) so no frame is ever static.

## Implementation order
1. Sample every transform per frame with ease/spring curves. 2. Add idle layers. 3. Add per-part time offsets. 4. Drawing swaps on twos (mouth, blink, head turn). 5. Speech-driven stress events. 6. Camera moves + shake.
