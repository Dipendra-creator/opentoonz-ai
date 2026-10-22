# Web-cartoon character/background spec (for programmatic generator)

Evidence key: [IMG] = observed in the 4 reference images; [WEB] = found in web search (thin: generic cel-shading guides, Toon Boom rig listings); [INF] = inferred from general knowledge of the genre, not verified. Web search returned almost nothing channel-specific, so most numbers below are [IMG]/[INF]. Treat pixel values as starting points to tune by eye.

## 1. What the reference images show

**Img 1 (yellow bg, laughing boy, podcast-style avatar, close-up):**
- Outline: pure near-black (#1a1a1a), thick: about 3-4% of head width on the outer silhouette; hair outline heaviest. Inner face lines (eyes, nose, brow) much thinner, about 1/3 of outer weight. Lines taper at ends (closed-eye arcs end in points, lash flicks).
- Eyes: closed happy arcs (upside-down U) with a thin second line above as lid crease; no eyeball visible.
- Hair: black (#2b2b2e) with a few spiky tufts; a grey-blue (#6f7378) secondary under-layer at the sideburn; white thin highlight stroke along outer edge of hair (rim stroke, 2 short parallel white lines at top-right).
- Skin: peach #fbd9a0 with a darker orange-tan cel shadow #f0b878 under the fringe (a band following the hair edge, ~15% of face height) and on the face side.
- Blush: 3 short diagonal hatch strokes per cheek, salmon-red #e8705a, thin, slightly tapered, set under the eyes.
- Mouth: huge open grin, white teeth as one rounded trapezoid with faint grey cel shade (#dcdcdc) at the bottom and thin tooth-separation lines; no visible tongue, black outline around the mouth.
- Ears: simple C-shape with inner curl line, same skin colour, outline same weight as face.
- Background: flat saturated yellow #f9ec55.

**Img 2 (green bg, bored guy with mask, half-lidded):**
- Eye: white eyeball is a wide rounded shape (~1.6:1 w:h), iris dark brown (#5a4430) with black pupil and a white highlight dot; the upper eyelid is a skin-coloured cap that covers the top ~45% of the eyeball with a thick dark line along its edge (half-lidded, bored/smug). Lower lid has a thin line. Brows are thick, dark (#3a2a22), angular, sitting low over the lid.
- Hair: curly cloud silhouette (scalloped, 10-14 bumps), two-tone: left half #3b2d28, right half darker/lighter #4a3d3a split with a hard vertical-ish shape edge (cel shadow as one big hard-edged region). Sides shaved (faded) shown as skin/stubble tone.
- Skin: #f6c89a with shadow #e0a577 under the brow and on the neck.
- Clothing: green hoodie #3fa63c (light) / #2f8a2f (shadow); drawstrings white with black outline and small metal tips; chest patch (smiling toast). Black mask #232323 with subtle lighter grey highlight edge.
- Background: vertical gradient green #1e9c1e to #3bc23b with subtle arrow-pattern texture, soft vignette/dark shadow behind the character (drop glow, ~10% opacity black).

**Img 3 ("Types of Indian Teachers": Indian-channel look; classroom corridor):**
- Characters: huge round-rectangle eyes (white eyeballs about 25% head width each, touching or nearly touching, nose bridge hidden), tiny black dot pupils (~15-20% of eyeball width) placed toward a looking direction, thick black eye outline. Half-lid by a tinted cap (pinkish skin shadow colour #d99a9a over the top third).
- Hair: dark red/maroon cloud curls #8a1a24 with darker shade #5a0f18; second character orange-brown #c87d3a.
- Skin: pinkish/light peach #f5c0b0 with pink shadow; second character tan; third darker brown #8a5a3a with yellow-gold clothes (#e8c040).
- Mouth: open shape with dark red-brown interior #7a2a2a, pink tongue #e07a8a, few small teeth.
- Hands: 4 fingers + thumb in the held-sign hand? Visible hand reads as a simple mitten with fingers lines (4 fingers + thumb on the close hand). Hands are small (about 1/2 face height) and chunky.
- Body: head about 1/2 to 1/3 of total character height (very big heads), short torso, thin limbs with simple tube shapes. Clothing: hoodie with white drawstrings and a kangaroo pocket; colour-blocked shirts (black/purple/pink panels) = diagonal-split shading.
- Background: flat pastel (lilac #c9a9d0 walls, pink #e8a0c0 pillar, mint-green lockers #5aa37a with darker rim edges), thin outlines (about 1/3 of character outline weight), light shafts as pale white diagonal parallelograms on the floor at 30-40% opacity. Foreground characters pop since they have thick black outlines and saturated hues; the BG has thin or no outline and lower contrast.
- Title text: bold sans (Impact/Bangers-like), white fill with thick black stroke (~8-10% of cap height) plus faint drop shadow.

**Img 4 (white bg, group of four):**
- Heads very big, bodies about 1.5-2 heads tall. Cloud-curl maroon hair (#7a0f14), outline black ~3 px at 700 px wide image (about 1% of image width).
- Eyes: big white ovals, small black pupils with white highlight; eyelid cap in pinkish skin-shadow (#e8a0a0) so the eye looks tired. Eyebrows are often absent or a thin line.
- Characters: freckles / acne dots (#d07070), buck-teeth mouth. Skin ranges from peach #f8c8b8 to tan #e8a070.
- Shirt: white with a single wide colour stripe (#d05070); shade is a hard vertical split on the right/left half: light grey-blue #dcdce8.
- Ground shadow: flat ellipse in desaturated purple (#a88bb0, ~60% opacity) under each character, no outline.

## 2. Character design rules (numbers)

Treat head height H as the unit (at 1080p, a full-body character is ~500-700 px tall, H about 220-300 px when 2.0-2.5 heads).
- **Head:body**: standard 1:1.5 to 1:2.5 (total 2.5-3.5 heads) for chibi/bean style [IMG]/[INF]. Torso about 0.8 H, legs 0.6-0.9 H, arms about 0.8 H from shoulder, thick-ish tubes 0.12 H wide. Head width about 1.0-1.15 H (wider than tall is okay).
- **Head shape**: rounded rectangle / rice-bean; cheeks wider than the cranium for expressive faces; jaw radius 0.35 H.
- **Eyes** (googly/bean style): eyeball width 0.24-0.28 head width each, height 0.20-0.26 head width; spacing between eyes 0-0.08 head width (nearly touching) [IMG 3, 4]. Place eye centre line at 50-58% down the head. Pupils small: 0.15-0.30 of eyeball width, black, optional white highlight circle 0.3 of pupil, offset to upper-right. Iris variant (Img 2): iris 0.5 of eyeball width, pupil 0.55 of the iris.
- **Eyeball outline**: 1.5-2.5 px at 1080p (thin relative to head outline) [INF].
- **Eyelid language**: eyelid is a skin-shadow-coloured (not skin) cap shape clipped to the eyeball, with a hard straight or slightly curved lower edge:
  - neutral: lid cover 0-10%
  - bored/tired: 40-50% cover, flat edge (Img 2)
  - smug/suspicious: 35% cover on one eye, angled; brow low
  - angry: lid edge slanted inward-down at 20-30 degrees, 25-35% cover
  - sad: lid edge slanted outward-down, brow raised at the inner end
  - surprised: lid 0%, pupils shrink to 0.12, brows high, eyeball wider (+10%)
  - happy laugh: eyes replaced with arc ^ ^ (Img 1) with 1-2 px lash tick
  - blink: lid 100% plus a line; 2-3 frames
- **Brows**: thick (6-10 px) solid dark shapes, tapered; hair colour or darker; vertical travel up to 0.15 H.
- **Mouth set** (drawing substitutions): closed flat line, smile, frown, open-small (O), open-wide (D), teeth-grin (white trapezoid with 1-2 tooth lines), shout (huge open with tongue), smirk (one-sided), buck teeth, "ugh" wavy. Mouth interior #7a2a2a (dark red-brown) [IMG 3], tongue #e07a8a, teeth #ffffff with shade #dcdcdc. Mouth width 0.25-0.5 head width; sits 72-80% down the head. For lip sync: 6-9 visemes (closed MBP, A, E, O, U, F/V, L/TH, rest) [INF].
- **Nose**: tiny: a single curve or two dots, or just a small tick; 0.05 H.
- **Ears**: C shape with an inner curl, at eye-line to mouth-line height.
- **Hands**: 4 fingers + thumb (chunky, sausage), mitten-like; palm about 0.3 H; substitutions: open, fist, point, thumbs up, peace, hold-object, relaxed. Hand outline same weight as the body.
- **Silhouette readability**: each character needs a distinct hair silhouette (curl cloud, spiky, flat top, bun), distinct dominant clothing colour, and a distinct height. Different heads in the same scene differ by at least 15% in height or hair shape.

## 3. Line art

- **Outer silhouette**: 4-6 px at 1080p for full-body characters in wide shots (about 2% of character height); 6-10 px for close-ups (Img 1: about 3-4% of head width) [IMG/INF].
- **Inner lines** (eye contours, fingers, folds, hair strands): 2-3 px (about 40-50% of the outer weight).
- **Detail lines** (blush hatching, teeth separators, wrinkles): 1.5-2 px.
- **Colour**: near-black #1a1a1a / #222 [IMG]; some channels use dark brown for hair/skin internal lines (#3a2020) [INF]. Never pure #000 on skin interior details if you want softness; keep outer line pure dark.
- **Taper**: ends of inner strokes taper to 30% width; outer silhouette near-uniform with slight width variation (+/-15%) [IMG 1]. Implement as variable-width polylines (offset polygon with width profile = sin(pi t)^0.5 for inner lines).
- **Background lines**: 1-2 px, colour a darker shade of the fill (not black), or no line [IMG 3].
- **Render at 2x then downsample** (supersample) to get clean anti-aliased vectors [INF].
- Line ends: round caps and round joins everywhere.

## 4. Colour and shading

- **Technique**: flat base + ONE hard-edged cel shadow + optional highlight; no soft gradients on characters [IMG all].
- **Shadow colour derivation** (hue shift): shadow = multiply of base by a cool/warm tint. In HSV: hue shift -8 to -15 degrees toward red/magenta for skin, saturation +5 to +15%, value -12 to -22%. In RGB: base * (0.85, 0.75, 0.80) for skin. For clothes: hue shift toward blue-violet (+10 to +15 deg), value -20% [INF; WEB confirms multiply-layer method and that grey shadows look bad on skin].
- **Shadow shape**: a copy of the part shape, offset by (+0.10 H, +0.08 H) from the upper-left light, clipped (intersected) to the original shape, then subtract the offset-copy, so a crescent remains on the lower-right edge; width about 10-18% of part width. For hair a big hard-edged two-tone split (one half darker) [IMG 2].
- **Under-hair shadow** (face): band under the fringe following its lower edge; height about 12-18% of face height, shadow-skin colour [IMG 1, 2].
- **Neck shadow**: the entire neck in shadow colour under the chin, height about 0.25 H, or a chin-cast shape.
- **Hair highlights**: 1-3 thin white or light curved strokes (3-5 px, tapered, 60-100% opacity) along the top-left edge; in curly hair one short arc per 2-3 curls [IMG 1].
- **Rim light**: optional 2 px pale-warm stroke inside the silhouette on the shadow-side edge, Screen blend at 40% [WEB: rim = screen blend].
- **Blush**: 3 diagonal strokes per cheek, length 0.07 H, 2 px, angle about 60 degrees, colour #e8705a (or skin-shadow redder), opacity 80%.
- **Ground shadow**: ellipse under feet, width about 1.0-1.3 x character width, height about 0.12 x width, colour = ground colour multiplied by (0.7, 0.65, 0.8), opacity 50-60%, no outline [IMG 4]. Contact shadows under objects the same way.
- **Ambient occlusion** under chin, under hair, where arms meet torso: the same hard shadow colour, not a blur.

### Palettes (hex)
Skin tones (base / shadow):
- Fair: #f8d5b8 / #e6b090
- Light peach (Img 1): #fbd9a0 / #f0b878
- Wheatish (typical Indian): #e0a878 / #c88860
- Medium brown: #c68642 / #a06a38
- Brown: #a0693f / #804e2e
- Dark brown: #7a4a2a / #5c3620
Hair: black #26262c (shadow #14141a), dark brown #3b2d28, maroon #8a1a24 (shadow #5a0f18), ginger #c87d3a, blonde #e8c66a. Highlight #ffffff or base +25% value.
Clothes: school uniform white shirt #f4f4f8 + navy #2a3a6a trousers; hoodie green #3fa63c, red #c24850, yellow #e8c040; shade each by section 4 rules.
Mouth: #7a2a2a; tongue #e07a8a; teeth #ffffff / #dcdce6.

### Saturation and value rules
- Characters: saturation 50-80%, value 70-95%; outline black.
- Backgrounds: saturation 20-45% (pastel) and value 75-95%; thin coloured lines or none; no pure black.
- Keep character/background value contrast at least 25% where possible, or rely on the black outline to separate them [IMG 3].
- Avoid putting a hair/clothing colour equal to the background hue in the same region; if the bg is green (Img 2), the character clothing is still green, so a darker vignette and outline separate them [IMG 2].
- Limit each character to 3-4 main colours, plus the shadow shades.

## 5. Backgrounds

- **Style**: flat fills in pastel colours; simple 1-point or 2-point perspective; walls, floor, windows as big rectangles [IMG 3].
- **Line weight**: 1/3 of the character outline (about 1.5-2 px at 1080p) in darker tint; character lines 4-6 px.
- **Light shafts**: 2-4 diagonal parallelograms (slant 25-40 degrees) from windows onto floor and wall, white, opacity 25-40%, hard or slightly soft edges, extended toward the bottom-right [IMG 3].
- **Gradients**: allowed on backgrounds: vertical, 10-15% value change; a vignette darkening corners 10-15% [IMG 2].
- **Depth**: far elements lighter and lower contrast (atmospheric); a blur of 0-2 px on far elements optional [INF].
- **Locations**:
  - Indian classroom: green or black board (#3a6b4a), wooden benches (#b07a48) in rows, windows with grills, white/yellow walls with a lower blue/green dado band (#7ab0c8), ceiling fan, wall clock, tube light, school bags.
  - Home: pastel walls (peach, #f4d8c0), sofa, TV, a window with curtains, a steel almirah, a tile floor with a grid at 2-point perspective.
  - Street: a flat sky gradient (#a8d8f0 to #e8f4fc), buildings in muted terracotta/yellow/teal, a signboard, auto-rickshaw (yellow/green), electric wires, a tree.
  - Corridor (Img 3): lockers, pillars, a window with a bright sky.
- **Readability**: put characters in the lower 2/3, leave the centre of BG low-detail, keep the busiest detail at the edges.

## 6. Typical software and rig structure [WEB thin; mostly INF]

- Tools: Adobe Animate (symbols, nested movie clips), Toon Boom Harmony (cut-out with pegs, drawing substitution, auto lip-sync with mouth shapes) [WEB], Moho, After Effects (with Duik/rubberhose, camera shake, effects), Photoshop/Procreate/Clip Studio for art [INF].
- Workflow: script, voice-over, storyboard, animatic, rig-based scene assembly, lip-sync by mouth substitution, compositing and subtle camera shake/zoom, SFX/music.
- **Part list** (cut-out rig): head (several angle drawings: front, 3/4, profile, back), hair front/back (separate layers so the head can sit between), brow L/R, eye L/R (eyeball + pupil + lid cap), mouth (library), nose, ears, neck, torso, pelvis, upper arm/forearm/hand L/R (hand library), thigh/shin/foot L/R, accessories (bag, mask, glasses).
- **Z-order** (back to front): hair back, back arm, back leg, torso, front leg, head base, ears, mouth, nose, eye whites, pupils, lids, brows, hair front, front arm, props.
- **Pivots**: head at the neck base (bottom centre of the head); upper arm at the shoulder (top centre); forearm at the elbow; hand at the wrist; thigh at the hip; shin at the knee; foot at the ankle; eyes at their centre; pupil at the eyeball centre; mouth at the mouth centre; torso/pelvis at the hip centre (root).
- **Expression swaps**: eye states (open, half, closed, happy arc, angry, sad, wide), mouth set (section 2), brow set (5-7), hand set (6-8). Head angles: front, 3/4 L/R, profile L/R (about 5 drawings).
- Export parts to PNG at 2x of the final size (e.g. head 600-800 px) with transparent background; OpenToonz scene can use them as raster levels with column pegbars.

## 7. Implementation checklist (priority)
1. Big heads (2-3 heads tall), huge eyes with tiny pupils, thick outline.
2. Variable-width tapered inner lines, outer silhouette 4-6 px.
3. Hair as a cloud silhouette (circles unioned), with two-tone split and highlight strokes.
4. Eyelid caps in shadow-skin colour with variable cover.
5. Single hard cel shadow per part, hue-shifted colour, clipped to the shape.
6. Blush hatches, freckles, teeth with grey shade.
7. Ground ellipse shadow, flat pastel BG with thin lines, light-shaft polygons.
8. Hands: 4 fingers + thumb sausage shapes.
9. Indian skin palette and varied hair/clothes per character.
