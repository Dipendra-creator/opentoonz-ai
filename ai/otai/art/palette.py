"""Colour helpers and named palettes for characters and backgrounds."""

from __future__ import annotations

import colorsys

SKIN = {
    'fair': '#F8D5B8', 'light': '#F7D0B0', 'peach': '#FBD9A0', 'medium': '#EDB98F',
    'wheat': '#E0A878', 'wheatish': '#E0A878', 'tan': '#C98E66', 'brown': '#A8714E',
    'dark': '#7E5238', 'deep': '#5E3B28',
}

HAIR = {
    'black': '#2A2530', 'dark_brown': '#4A3226', 'brown': '#6E4A33',
    'light_brown': '#9C6B45', 'blonde': '#E8C46E', 'platinum': '#EDE6D2',
    'red': '#B5452F', 'maroon': '#8A1A24', 'ginger': '#C87D3A', 'orange': '#E07B39', 'pink': '#F09AB8',
    'purple': '#7A55A8', 'blue': '#3F64B5', 'navy': '#2B3A67',
    'teal': '#2F9A95', 'green': '#4F8F4A', 'white': '#F2F2F5',
    'grey': '#9A9AA3', 'silver': '#C8CBD3',
}

EYES = {
    'brown': '#7A4A2A', 'dark_brown': '#4A2C1C', 'black': '#2A2228',
    'hazel': '#8F7A3A', 'amber': '#C98A2B', 'green': '#3F8A4F',
    'blue': '#3E7CC9', 'grey': '#7E8796', 'purple': '#7B4FB0',
    'red': '#B23A3A', 'teal': '#2A9A9A', 'gold': '#D4A62A', 'pink': '#D9668F',
}

CLOTH = {
    'white': '#F4F4F2', 'black': '#2E2E36', 'grey': '#8D9099', 'navy': '#2F3E69',
    'blue': '#4A78C2', 'sky': '#8EC3E8', 'red': '#C9423F', 'maroon': '#7D2933',
    'pink': '#F2A2B9', 'orange': '#E98A3A', 'yellow': '#F2CF55', 'green': '#4E9A5A',
    'olive': '#7A7F45', 'teal': '#2E9C93', 'purple': '#7D5BB0', 'lavender': '#B9A6DE',
    'brown': '#7B5236', 'beige': '#D9C6A1', 'khaki': '#B8A57A', 'denim': '#4D6A93',
    'cream': '#F3E9D2', 'mint': '#A9DDC3', 'coral': '#F08A7A', 'saffron': '#F0A030',
}


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(c) -> str:
    return '#%02X%02X%02X' % tuple(max(0, min(255, int(round(v)))) for v in c[:3])


def resolve(name_or_hex: str | None, table: dict, default: str) -> str:
    if not name_or_hex:
        return default
    v = str(name_or_hex).strip()
    if v.startswith('#') and len(v) in (7, 9):
        return v[:7].upper()
    key = v.lower().replace(' ', '_').replace('-', '_')
    if key in table:
        return table[key]
    for k, val in table.items():  # loose match: 'dark blue' -> 'navy'? keep simple
        if k in key or key in k:
            return val
    for tbl in (CLOTH, HAIR, EYES, SKIN):
        if key in tbl:
            return tbl[key]
    return default


def cel_shadow(color: str, kind: str = 'cloth') -> str:
    """Hard cel-shadow tone: darker, slightly more saturated and hue-shifted
    (skin towards red, cloth towards blue-violet, hair just deeper) so shadows
    never look grey."""
    r, g, b = [v / 255 for v in hex_to_rgb(color)]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if kind == 'skin':
        h, s, v = h - 10 / 360, s + 0.10, v - 0.15
    elif kind == 'hair':
        h, s, v = h - 4 / 360, s + 0.05, v - 0.22
    else:
        # pull the hue a little towards blue-violet (250 deg)
        target = 250 / 360
        d = ((target - h + 0.5) % 1.0) - 0.5
        h, s, v = h + max(-12 / 360, min(12 / 360, d)), s + 0.08, v - 0.18
        if s < 0.12:  # near white/grey cloth: cool lavender grey
            s = 0.12
    r2, g2, b2 = colorsys.hsv_to_rgb(h % 1.0, min(max(s, 0.0), 1.0), min(max(v, 0.05), 1.0))
    return rgb_to_hex((r2 * 255, g2 * 255, b2 * 255))


def shade(color: str, factor=(0.78, 0.74, 0.90)) -> str:
    """Anime cel shadow: multiply towards a cool purple tone."""
    r, g, b = hex_to_rgb(color)
    return rgb_to_hex((r * factor[0], g * factor[1], b * factor[2]))


def lighten(color: str, t: float = 0.25) -> str:
    r, g, b = hex_to_rgb(color)
    return rgb_to_hex((r + (255 - r) * t, g + (250 - g) * t, b + (235 - b) * t))


def darken(color: str, t: float = 0.3) -> str:
    r, g, b = hex_to_rgb(color)
    return rgb_to_hex((r * (1 - t), g * (1 - t), b * (1 - t)))


def line_color(color: str) -> str:
    """Coloured line art: a deep, saturated version of the fill."""
    r, g, b = [v / 255 for v in hex_to_rgb(color)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r2, g2, b2 = colorsys.hls_to_rgb(h, max(0.08, l * 0.32), min(1.0, s * 0.8 + 0.1))
    return rgb_to_hex((r2 * 255, g2 * 255, b2 * 255))


def mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def with_alpha(color: str, a: int) -> str:
    return color[:7] + '%02X' % a
