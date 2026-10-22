# Style Guide: "Not Your Type"-inspired anime-flavored cutout storytelling (OpenToonz pipeline)

Legend: [V] = verified from a fetched source. [I] = inferred / general convention, NOT verified for this channel. Nothing about the channel's visual technique could be verified; sections 3 onward are general anime / storytime-animation convention.

## 1. Channel overview
Verified [V]:
- A YouTube channel named NOT YOUR TYPE exists (channel ID UCKnNrlSJF_hWoBSz1lY_D7g). Self-description: "Absurd Cartoons & Stories by Aryan & Ayu". ~10.09M subscribers, ~1.35B total views, 64 videos (SocialCounts snapshot). Playboard shows an older figure (9.48M subs, 69 videos).
- FamousBirthdays: India-based, joined YouTube July 2017, first video Feb 2021; humorous animated videos on Indian culture and everyday experiences (holidays, teen-parent relationships, school teachers, exams).
- Sources: https://socialcounts.org/youtube-live-subscriber-count/UCKnNrlSJF_hWoBSz1lY_D7g , https://www.famousbirthdays.com/people/not-your-type.html , https://playboard.co/en/channel/UCKnNrlSJF_hWoBSz1lY_D7g (blocked, 429, only seen in search snippet).

NOT verified (YouTube page, Playboard fetch failed; no secondary source describes it): video length, narration style, shots per minute, animation technique, character design, backgrounds, audio. The user's premise ("anime-style relatable storytelling") may partly mismatch: the only evidence points to humorous, Indian-everyday-life cartoons with two named creators. Treat "Not Your Type" as a loose tonal reference (relatable, humorous, school/family life) and anime conventions as the technical spec. Recommend a human watch 2-3 episodes and correct the [I] items.

## 2. Story/script structure template [I]
Episode (1-10 min) = Hook (0-15 s) -> Setup (10-15%) -> Escalation/conflict (40-50%) -> Twist/climax (15-20%) -> Resolution + punchline/moral (10%) -> short outro.
Pipeline steps:
1. Split story into 5-12 scenes (location/time change = new scene). Rule of thumb: 1 scene per 30-60 s.
2. Split each scene into beats (one idea each) -> 1 beat = 1-3 shots.
3. Narration vs dialogue: use narrator VO for exposition, time jumps, inner thoughts, summaries (target 50-60% of runtime). Use character dialogue only for peak moments: conflicts, jokes, twists (target 30-40%). Silent reaction/beat shots 10%.
4. Dialogue lines <= 12 words each; narration sentences <= 20 words; speech rate ~150 wpm (about 2.5 words/s) -> shot duration derives from audio length + 0.3-0.5 s pad.
5. Hook: open on the funniest/most dramatic moment line or a question, then "let me explain" cut to setup.
6. Each scene ends on a button: reaction shot, punchline, or cliffhanger line.
Speaker names: max 3-4 recurring characters; one narrator-avatar optional.

## 3. Shot and pacing rules [I unless stated]
- Average shot length (ASL): 3-5 s for narrated storytime; 1.5-3 s in comedic exchanges; 5-8 s max hold for establishing shots. TV anime ASL is commonly cited around 3-4 s (not verified here).
- Shots per minute: 12-20 (target 15). A 5-minute video ~ 60-90 shots.
- Shot mix: medium 45%, close-up/bust 25%, wide/establishing 10%, reaction/insert 15%, cutaway symbols/text card 5%.
- Never hold a static image > 6 s without camera drift, a blink, or a text change.
- Rhythm: alternate speaker shots (shot/reverse-shot) in dialogue; insert a reaction shot every 2-3 lines.
- Transitions: hard cut default (85%); cross-dissolve 12 frames for time passage; fade to/from black 12-24 frames for scene/chapter ends; whip-pan/flash-frame 2-4 frames for comedic surprise.

## 4. Animation technique rules (24 fps)
- Verified [V] (Anime News Network lexicon): TV anime is drawn/shot on threes (8 drawings/s), twos (12/s) for smoother, ones for high action, fours+ for near-static talking scenes; "more an average than a rule".
- Default: body poses on 3s (hold 3 frames), mouth and eyes on 2s-3s, camera moves on 1s (smooth) so only cutout motion is stepped.
- Holds: dialogue shots hold body pose 12-48 frames with only mouth + blink + subtle breathing.
- Breathing/idle: torso scale or y-offset +-1-2%, period ~72-96 frames, stepped on 3s.
- Blink [I, typical]: every 3-5 s (random 72-120 frames); sequence open -> half(1-2 f) -> closed (2 f) -> half (2 f) -> open; total 5-8 frames. Skip blinks during strong emotion shots.
- Lip sync: new mouth shape every 3-4 frames (6-8 per s), drop sub-3-frame phonemes, close mouth for 3 frames at pauses; anticipate audio by 1-2 frames.
- Head turn/nod: 6-10 frames, ease out; snap pose changes (anime "pose to pose") with 1-2 smear/blur frames only for fast moves.
- Gestures: arm raise 8-12 frames, hold, return; keep only 1 gesture per sentence max.
- Reaction "take": anticipation 3 f (squash down 5%), snap to extreme 2 f, hold 18-36 f, overshoot 3-4 f scale +8% then settle.
- Walks: 12-16 frame cycle on 3s with bob +-3% height; mostly avoid walking, cut instead.
- Smear / impact: 1-2 frame stretched duplicate; screen shake 6-12 frames, amplitude 8-20 px, decaying.
- Hair/clothes secondary motion: lag 3-6 frames behind head, small overlap.

## 5. Character design spec [I]
Proportions (head heights): adult 7-7.5, teen/student 6-6.5, child 4-5, chibi/reaction form 2-3. Heads relatively large for readability in cutout.
Eyes: large, ~1/4-1/3 face width each, placed at 50-60% down the head, 2-tone iris + 1 large highlight (and optional 1 small), thick upper lash line, no nose beyond a tick/dot, small mouth.
Line weight: outline 3-4 px at 1080p for outer silhouette, 1.5-2 px inner lines, colored lines for hair/eyes optional; consistent per character.
Coloring: flat base + ONE cel shadow tone + optional one highlight; hard-edged shadow shapes.
Shadow derivation: shadow = base multiplied by ~(0.78, 0.74, 0.90) i.e. darker, shifted toward blue/purple; highlight = base lerped 25% toward white, warmer. Skin base example #F7D5BF shadow #E3B3A6; dark skin #C68B63 / #A96A4C. Hair shadow = multiply 0.7 plus +purple.
Palette: 3-5 hues per character; limit saturation of backgrounds to 60-70% of character saturation so characters pop. Differentiate characters by (a) hair color+silhouette (b) one signature outfit color (c) height/head size. Typical outfits: school uniform (Indian/Japanese-style shirt + trousers/skirt), casual t-shirt+jeans, one accessory each.
Cutout rig part list (each a separate vector layer, pivots noted):
1. head base (pivot neck), ears
2. hair back, hair front/bangs (separate side-lock pieces for lag)
3. eyes: open, half, closed, plus 'happy ^^', 'angry', 'sad' variants; pupils/iris as moving child layers (look-direction offset max 15% of eye width)
4. brows x2 (angle/height variants)
5. mouth set (see section 6), optional blush overlay, nose tick
6. neck, torso (pivot hips), optional torso-front 3/4 variant
7. upper arm L/R (pivot shoulder), lower arm L/R (pivot elbow), hands (open, fist, point, relax; 4 variants)
8. upper leg, lower leg, shoes L/R (only if full body shown; prefer waist-up framing)
9. front, 3/4, side head views as swappable sets if camera angle changes (minimum: front + 3/4).
Draw order: hair back < neck < torso < arms < head < hair front.

## 6. Expression library [I]
Mouth set (8 shapes, Japanese vowel based): closed(M/B/P), A (wide open), I (wide thin), U (small round), E (medium flat open), O (round open), N/rest (slight line), smile/grin and 'W' cat mouth for jokes. Mapping: あ=A, い=I, う=U, え=E, お=O; consonants use the following vowel or closed.
- Happy: eyes ^^ or open+highlight, brows raised, big smile, optional sparkles, blush.
- Sad: eyes half + large highlight, brows inner-up, small wavy mouth, tear line, blue-tinted overlay.
- Angry: brows inward-down, eyes narrowed with no highlight, teeth clench mouth, anger vein (cross-shaped), red tint.
- Surprised: eyes wide small pupils, brows high, mouth O, vertical lines, jump 6 px.
- Embarrassed: blush lines (///) across cheeks, sweat drop, eyes wavering, mouth wavy.
- Annoyed/deadpan: half-lid eyes, flat mouth, brow low, optional "..." bubble.
- Nervous: sweat drop(s), pupils small, wobbly mouth.
- Shock/overreaction: chibi swap 12-24 frames, white eyes, jaw drop, shake.
- Love/crush: heart eyes or heart symbol, blush, sparkle.
- Confused: tilted brow, "?" symbol, head tilt 8 degrees.
Symbols pop in on 2 frames with scale overshoot, hold 24-48 frames, fade 6 frames. Chibi reactions used sparingly (<= 1 per 40 s).

## 7. Backgrounds and camera rules [I]
- Style: simplified painterly/flat vector, soft gradient sky, minimal line, 2-3 depth planes (BG / midground props / foreground blur or silhouette).
- Reuse: 5-8 locations per episode (home room, kitchen, school classroom, corridor, street, shop, bedroom night); each as one wide plate + 2 crops/zoom angles. Day/night/emotional variants via color overlay (multiply blue for night, warm for evening).
- Detail: characters carry the contrast; backgrounds get blurred or desaturated in close-ups.
- Camera: slow push-in 100% -> 108% over 3-5 s on emotional beats; pan 40-120 px over a shot for establishing; shake on impacts; speed lines/radial focus lines for shocking reveals; zoom-in snap to face on punchline (6 frames); cuts rather than complex moves.
- Parallax: BG moves 0.5x of fg during pans.
- Resolution 1920x1080, 24 fps, 16:9 (also 9:16 option for shorts).

## 8. Audio and subtitle conventions [I]
- Voice: TTS or recorded narrator, steady; characters differentiated by pitch/speed. Normalize VO to -16 LUFS; music bed -28 to -24 LUFS under VO; SFX -18 dB peaks.
- Music: light lo-fi/comedic loops, change on scene boundaries; duck 6-10 dB under speech.
- SFX: pop on symbol appearance, whoosh on whip-pan, impact on shake, bell/ding on epiphany, record-scratch on twist. 1 SFX per 5-8 s max.
- Subtitles: burn-in captions, bottom third, 2 lines max, <=42 chars/line, white with dark outline 3 px, appear in sync with audio, 1-3 s per caption; key words highlighted in accent color. Speech bubbles optional: use for short gags (<=6 words), tail pointing to speaker.
- Dialogue is not required to be bubbled if the speaker is shown and captioned.

## 9. NOT feasible programmatically and best approximation
| Hard to imitate | Approximation |
|---|---|
| Hand-drawn frame-by-frame action, key animation, smear art | Cutout rig + stepped keys on 3s, 1-2 prebuilt smear/blur variants |
| Unique channel art style/character likeness | Original characters following the generic anime spec; never copy the channel's designs |
| Rich painted backgrounds | Layered vector plates with gradients, blur, noise; reuse locations |
| Natural acting nuance, hand-drawn expressive faces | Library of ~10 eye/brow/mouth swaps and a chibi swap |
| True 3D head turns | Swap 3 pre-drawn head views (front/3-4/side) |
| Perfect lip sync | Vowel-based mouth switching from audio phoneme/amplitude analysis; accept approximation |
| Complex crowd/vehicle/fluid FX | Silhouettes, simple loops, particles as repeated vector shapes |
| Original voice acting/comedic timing | TTS + manual-style pauses (0.2-0.5 s) inserted by the script |
| Verifying the channel's exact techniques | Human reviewer checks 2-3 episodes and updates [I] values |

## References
- Verified: https://AnimeNewsNetwork.com/encyclopedia/lexicon.php?id=61 (shot on ones/twos/threes). Channel facts: socialcounts.org, famousbirthdays.com URLs above.
- All numeric shot/blink/mouth/palette/audio values above are working defaults ("inferred"), not measurements from the channel.
