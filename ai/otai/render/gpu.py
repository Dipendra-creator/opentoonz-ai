"""OpenGL backend for the compositor and the colour grades.

Each layer is a textured quad drawn with premultiplied-alpha blending, the
vignette is a quad on top, and the grade (tone, lift, spotlight, dusk, glow)
runs as fragment shaders with a two-level bloom on downsampled buffers. Text
overlays are drawn after the grade. Results match the CPU path (compositor.py
and grade.py) to within a few levels.

Frames are laid out top row first: screen y grows downwards both in the
geometry and in the readback, so no flips are needed anywhere.

Set OTAI_GPU=0 to force the CPU path. On Optimus laptops Windows must run
python.exe on the discrete GPU (Settings > Display > Graphics > High
performance), otherwise the context lands on the integrated GPU.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

import numpy as np
from PIL import Image

from . import grade as grading

_LOCK = threading.RLock()
_CTX = None
_FAILED = False

_QUAD_VS = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
uniform vec2 size;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_pos / size * 2.0 - 1.0, 0.0, 1.0);
}
"""

_QUAD_FS = """
#version 330
uniform sampler2D tex;
uniform float opacity;
in vec2 v_uv;
out vec4 f;
void main() { f = texture(tex, v_uv) * opacity; }
"""

_MOTE_FS = """
#version 330
uniform vec3 color;
uniform float twinkle;
uniform float reach;
in vec2 v_uv;
out vec4 f;
void main() {
    float d = length(v_uv - 0.5) * 2.0 * reach;
    float a = pow(clamp(1.15 - d, 0.0, 1.0), 1.6) * 0.85 + exp(-d * d * 0.6) * 0.25;
    f = vec4(color, clamp(a, 0.0, 1.0) * twinkle);
}
"""

_FULL_VS = """
#version 330
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

_COMMON = """
float ss(float a, float b, float x) { float t = clamp((x - a) / (b - a), 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
float emit_of(vec3 a) {
    float mx = max(a.r, max(a.g, a.b)), mn = min(a.r, min(a.g, a.b));
    return ss(0.80, 0.96, mx) * ss(0.42, 0.68, (mx - mn) / max(mx, 1e-4));
}
"""

_DOWN_FS = """
#version 330
uniform sampler2D src;
uniform int factor;
out vec4 f;
""" + _COMMON + """
void main() {
    ivec2 o = ivec2(gl_FragCoord.xy) * factor;
    vec3 acc = vec3(0.0);
    for (int j = 0; j < factor; j++)
        for (int i = 0; i < factor; i++) {
            vec3 a = texelFetch(src, o + ivec2(i, j), 0).rgb;
            acc += a * emit_of(a);
        }
    f = vec4(acc / float(factor * factor), 1.0);
}
"""

_BLUR_FS = """
#version 330
uniform sampler2D src;
uniform ivec2 dir;
uniform float sigma;
out vec4 f;
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 hi = textureSize(src, 0) - 1;
    int r = int(ceil(sigma * 3.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int k = -r; k <= r; k++) {
        float w = exp(-0.5 * float(k * k) / (sigma * sigma));
        acc += texelFetch(src, clamp(p + dir * k, ivec2(0), hi), 0).rgb * w;
        wsum += w;
    }
    f = vec4(acc / wsum, 1.0);
}
"""

_GRADE_FS = """
#version 330
uniform sampler2D base;
uniform sampler2D bq;
uniform sampler2D be;
uniform vec2 size;
uniform vec3 mult;
uniform vec3 lift;
uniform float lift_amount;
uniform float satk;
uniform vec3 mult2;
uniform vec3 lift2;
uniform float lift_amount2;
uniform float satk2;
uniform float dusk_t;
uniform int spot;
uniform float glow;
out vec4 f;
""" + _COMMON + """
vec3 tone(vec3 a, float lum, vec3 m, vec3 l, float la, float s) {
    vec3 o = lum + (a - lum) * s;
    o *= m;
    return o + (l - o) * la * (1.0 - lum);
}
void main() {
    vec3 a = texelFetch(base, ivec2(gl_FragCoord.xy), 0).rgb;
    float e = emit_of(a);
    float lum = dot(a, vec3(0.299, 0.587, 0.114));
    vec3 o = tone(a, lum, mult, lift, lift_amount, satk);
    if (dusk_t > 0.0) o = mix(o, tone(a, lum, mult2, lift2, lift_amount2, satk2), dusk_t);
    if (spot == 1) {
        vec2 p = gl_FragCoord.xy - 0.5;
        float d = length(vec2((p.x - size.x * 0.5) / (size.x * 0.21), (p.y - size.y * 0.56) / (size.y * 0.50)));
        o *= 0.12 + 0.88 * (1.0 - ss(0.88, 1.06, d));
    }
    o = o * (1.0 - e) + a * e;
    if (glow > 0.0) {
        vec2 uv = gl_FragCoord.xy / size;
        vec3 b = texture(bq, uv).rgb * 0.6 + texture(be, uv).rgb * 0.8;
        o = 1.0 - (1.0 - o) * (1.0 - clamp(b * glow, 0.0, 1.0));
    }
    f = vec4(clamp(o, 0.0, 1.0), 1.0);
}
"""


def context():
    """The process-wide GL context, or None when no GPU path is available."""
    global _CTX, _FAILED
    if _CTX is not None or _FAILED:
        return _CTX
    if os.environ.get('OTAI_GPU', '1') == '0':
        _FAILED = True
        return None
    try:
        import moderngl
        _CTX = moderngl.create_standalone_context(require=330)
    except Exception:  # no moderngl, no driver, headless box: fall back to the CPU
        _FAILED = True
    return _CTX


def renderer_name() -> str | None:
    ctx = context()
    return ctx.info.get('GL_RENDERER') if ctx is not None else None


class _Textures:
    """Level frames as GPU textures (trimmed, premultiplied, 1 px transparent border)."""

    def __init__(self, ctx, budget: int = 700 << 20) -> None:
        self.ctx, self.budget, self.used = ctx, budget, 0
        self.items: OrderedDict = OrderedDict()

    def get(self, cpu_cache, path):
        key = (str(path), os.path.getmtime(path))
        hit = self.items.get(key)
        if hit is not None:
            self.items.move_to_end(key)
            return hit
        img, off, full = cpu_cache.get(path, 0)
        if img is None:
            entry = None
        else:
            w, h = img.size
            padded = Image.new('RGBa', (w + 2, h + 2), (0, 0, 0, 0))
            padded.paste(img, (1, 1))
            tex = self.ctx.texture(padded.size, 4, padded.tobytes())
            tex.build_mipmaps()
            import moderngl
            tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
            tex.repeat_x = tex.repeat_y = False
            entry = (tex, off, full, (w, h))
            self.used += (w + 2) * (h + 2) * 4 * 4 // 3
        self.items[key] = entry
        while self.used > self.budget and len(self.items) > 1:
            _, old = self.items.popitem(last=False)
            if old is not None:
                self.used -= old[0].width * old[0].height * 4 * 4 // 3
                old[0].release()
        return entry


class GPURenderer:
    """Renders one frame size; shares the process context and texture cache."""

    _textures: _Textures | None = None
    _programs: dict | None = None

    def __init__(self, size: tuple[int, int], background, vignette_img: Image.Image | None) -> None:
        import moderngl
        self.ctx = ctx = context()
        self.size = size
        self.background = background
        w, h = size
        with _LOCK, ctx:
            if GPURenderer._programs is None:
                GPURenderer._programs = {
                    'quad': ctx.program(vertex_shader=_QUAD_VS, fragment_shader=_QUAD_FS),
                    'mote': ctx.program(vertex_shader=_QUAD_VS, fragment_shader=_MOTE_FS),
                    'down': ctx.program(vertex_shader=_FULL_VS, fragment_shader=_DOWN_FS),
                    'blur': ctx.program(vertex_shader=_FULL_VS, fragment_shader=_BLUR_FS),
                    'grade': ctx.program(vertex_shader=_FULL_VS, fragment_shader=_GRADE_FS),
                }
                GPURenderer._textures = _Textures(ctx)
            self.p = GPURenderer._programs
            self.tex = GPURenderer._textures

            def target(tw, th):
                t = ctx.texture((max(1, tw), max(1, th)), 4)
                t.filter = (moderngl.LINEAR, moderngl.LINEAR)
                t.repeat_x = t.repeat_y = False
                return t, ctx.framebuffer(color_attachments=[t])

            self.base_t, self.base = target(w, h)
            self.out_t, self.out = target(w, h)
            self.q = [target(w // 4, h // 4) for _ in range(2)]
            self.e = [target(w // 8, h // 8) for _ in range(2)]
            self.vbo = ctx.buffer(reserve=4 * 4 * 4 * 6)
            self.vao_quad = ctx.vertex_array(self.p['quad'], [(self.vbo, '2f 2f', 'in_pos', 'in_uv')])
            self.vao_mote = ctx.vertex_array(self.p['mote'], [(self.vbo, '2f 2f', 'in_pos', 'in_uv')])
            self.vao = {k: ctx.vertex_array(self.p[k], []) for k in ('down', 'blur', 'grade')}
            self.vignette = None
            if vignette_img is not None:
                self.vignette = ctx.texture(size, 4, vignette_img.convert('RGBa').tobytes())

    # ------------------------------------------------------------------
    def _quad(self, vao, corners, uv=((0, 0), (1, 0), (0, 1), (1, 1))) -> None:
        (a, b, c, d) = corners
        (ua, ub, uc, ud) = uv
        data = np.array([*a, *ua, *b, *ub, *c, *uc, *b, *ub, *d, *ud, *c, *uc], dtype='f4')
        self.vbo.write(data.tobytes())
        vao.render(vertices=6)

    def _layer(self, cpu_cache, path, m: np.ndarray, k: float, opacity: int) -> None:
        try:
            entry = self.tex.get(cpu_cache, path)
        except FileNotFoundError:
            return
        if entry is None:
            return
        tex, off, full, (w, h) = entry
        fw, fh = full
        img_m = np.array([[k, 0, (off[0] - fw / 2) * k], [0, -k, (fh / 2 - off[1]) * k], [0, 0, 1.0]])
        mm = m @ img_m
        pts = mm @ np.array([[-1, w + 1, -1, w + 1], [-1, -1, h + 1, h + 1], [1, 1, 1, 1.0]])
        tex.use(0)
        self.p['quad']['opacity'].value = opacity / 255
        self._quad(self.vao_quad, [tuple(pts[:2, i]) for i in range(4)])

    def _full(self, name: str, fbo, **uniforms) -> None:
        fbo.use()
        prog = self.p[name]
        for key, value in uniforms.items():
            member = prog.get(key, None)  # the compiler drops unused uniforms
            if member is not None:
                member.value = value
        self.vao[name].render(vertices=3)

    def _grade(self, g, name: str, frame: int, progress: float) -> None:
        import moderngl
        ctx = self.ctx
        w, h = self.size
        ctx.disable(moderngl.BLEND)
        if g.glow > 0:
            self.base_t.use(0)
            self._full('down', self.q[0][1], src=0, factor=4)
            self._full('down', self.e[0][1], src=0, factor=8)
            for level, sigma in ((self.q, max(1.0, h / 240)), (self.e, max(1.0, h / 200))):
                level[0][0].use(0)
                self._full('blur', level[1][1], src=0, dir=(1, 0), sigma=sigma)
                level[1][0].use(0)
                self._full('blur', level[0][1], src=0, dir=(0, 1), sigma=sigma)
        end = grading.DUSK_END
        t = 0.0
        if name == 'dusk':
            p = min(max(progress, 0.0), 1.0)
            t = p * p * (3 - 2 * p)
        self.base_t.use(0)
        self.q[0][0].use(1)
        self.e[0][0].use(2)
        self._full('grade', self.out, base=0, bq=1, be=2, size=(float(w), float(h)),
                   mult=tuple(g.mult), lift=tuple(c / 255 for c in g.lift), lift_amount=g.lift_amount,
                   satk=g.sat, mult2=tuple(end.mult), lift2=tuple(c / 255 for c in end.lift),
                   lift_amount2=end.lift_amount, satk2=end.sat, dusk_t=t,
                   spot=1 if name == 'spotlight' else 0, glow=g.glow)
        if g.motes:
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE)
            prog = self.p['mote']
            prog['size'].value = (float(w), float(h))
            prog['color'].value = tuple(c / 255 for c in g.mote_color)
            for x, y, r, twinkle in grading.mote_positions(g, frame, w, h):
                half = 2 * r + 0.5
                cx, cy = x + 0.5, y + 0.5
                prog['twinkle'].value = min(1.0, twinkle) if twinkle < 0.98 else 1.0
                prog['reach'].value = half / r
                self._quad(self.vao_mote, [(cx - half, cy - half), (cx + half, cy - half),
                                           (cx - half, cy + half), (cx + half, cy + half)])

    def render(self, items, cpu_cache, grade_name: str, frame: int, progress: float) -> Image.Image:
        """``items``: (path, matrix, k, mip, opacity, overlay) bottom-up, as built by Compositor."""
        import moderngl
        ctx = self.ctx
        w, h = self.size
        g = grading.GRADES.get(grade_name)
        with _LOCK, ctx:
            self.p['quad']['size'].value = (float(w), float(h))
            self.p['quad']['tex'].value = 0
            self.base.use()
            ctx.viewport = (0, 0, w, h)
            bg = self.background
            ctx.clear(bg[0] / 255, bg[1] / 255, bg[2] / 255, 1.0)
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
            for path, m, k, mip, opacity, overlay in items:
                if not overlay:
                    self._layer(cpu_cache, path, m, k, opacity)
            if self.vignette is not None:
                self.vignette.use(0)
                self.p['quad']['opacity'].value = 1.0
                self._quad(self.vao_quad, [(0, 0), (w, 0), (0, h), (w, h)])
            final = self.base
            if g is not None:
                self._grade(g, grade_name, frame, progress)
                final = self.out
                final.use()
                ctx.viewport = (0, 0, w, h)
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
            for path, m, k, mip, opacity, overlay in items:
                if overlay:
                    self._layer(cpu_cache, path, m, k, opacity)
            data = final.read(components=4, alignment=1)
        return Image.frombytes('RGBA', self.size, data)
