#!/usr/bin/env python3
"""Generate ../static/what-is-this/index.html from steps.md: the "What is this?" presentation.

python3 build.py           # write index.html
python3 build.py --check   # fail when index.html is not what steps.md builds

Slides in steps-archive.md are not built, but they are still checked, and their translations
kept, so one can be moved back into steps.md as it is.
"""

from __future__ import annotations

import colorsys
import html
import json
import math
import random
import re
import sys
import urllib.parse
from pathlib import Path

DIR = Path(__file__).resolve().parent
MD_PATH = DIR / "steps.md"
ARCHIVE_PATH = DIR / "steps-archive.md"
TRANSLATIONS_PATH = DIR / "translations.json"
HTML_PATH = DIR.parent / "static" / "what-is-this" / "index.html"
FOOTER_SITE = "gos.earth"

# Same ids, names and order as supportedLocales in src/lib/i18n/index.ts.
LOCALES = [
    ("en", "English"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("zh-CN", "中文 (简体)"),
    ("it", "Italiano"),
]
START_HINT = "Click or press → to start"
START_HINT_TOUCH = "Tap to start"
LINK_CTA = "Find a realm, or start your own"
IC_LOGO_HTML = (
    '<a class="gos-ic" href="https://internetcomputer.org" target="_blank" '
    'rel="noopener noreferrer" title="Internet Computer">'
    '<img src="assets/internet-computer-icp-logo.svg" alt="Internet Computer"></a>'
)

BASE_CSS = """
    :root {
      --gray-50: #fafafa;
      --gray-100: #f0f0f0;
      --gray-200: #e5e5e5;
      --gray-300: #d4d4d4;
      --gray-400: #a3a3a3;
      --gray-500: #737373;
      --gray-600: #525252;
      --gray-700: #404040;
      --gray-800: #262626;
      --gray-900: #171717;
      --text: var(--gray-900);
      --muted: var(--gray-600);
      --border: var(--gray-200);
      --panel: #ffffff;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html, body { height: 100%; overflow: hidden; }

    body {
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--panel);
      color: var(--text);
      min-height: 100vh;
      min-height: 100dvh;
      display: flex;
      flex-direction: column;
    }

    .deck {
      width: 100%;
      height: 100vh;
      height: 100dvh;
      background: var(--panel);
      padding: 1.25rem 2.5rem 1rem;
      display: flex;
      flex-direction: column;
      flex: 1;
    }

    .viewport {
      flex: 1;
      min-height: 0;
      position: relative;
      user-select: text;
      -webkit-user-select: text;
    }

    .dots, footer { user-select: none; -webkit-user-select: none; }

    .page {
      position: absolute;
      inset: 0;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      z-index: 0;
      transition: opacity 0.45s cubic-bezier(0.4, 0, 0.2, 1), visibility 0.45s;
    }

    .page.active {
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      z-index: 2;
    }

    .page-step {
      position: absolute;
      inset: 0;
      opacity: 0;
      pointer-events: none;
      z-index: 0;
      transition: opacity 0.45s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .page-step.active { opacity: 1; pointer-events: auto; z-index: 1; }

    .arch-box {
      width: 100%;
      height: 100%;
      border: 2px solid var(--gray-800);
      border-radius: 8px;
      padding: 2rem 2.2rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    .box-header {
      border-bottom: 2px solid var(--gray-900);
      padding-bottom: 0.75rem;
      flex-shrink: 0;
    }

    .box-header h2 {
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .box-header p {
      font-size: 0.95rem;
      color: var(--muted);
      margin-top: 0.25rem;
    }

    .box-body {
      flex: 1;
      display: flex;
      align-items: center;
    }

    .box-body ul {
      list-style: none;
      font-size: 1.05rem;
      line-height: 1.7;
      color: var(--gray-700);
      width: 100%;
    }

    .box-body li { padding-left: 1rem; position: relative; margin-bottom: 0.2rem; }
    .box-body li strong { color: var(--text); font-weight: 650; }

    footer {
      margin-top: 0.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }

    footer .site { font-size: 1.17rem; color: var(--gray-500); }

    .dots {
      display: flex;
      gap: 0.35rem;
      justify-content: center;
      margin-top: 0.45rem;
      flex-wrap: wrap;
    }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--gray-200);
      border: none;
      padding: 0;
      cursor: pointer;
      transition: background 0.3s, transform 0.3s;
    }

    .dot.active { background: var(--gray-900); transform: scale(1.2); }

    .arch-box.gos-box-slide {
      position: relative;
      width: min(64rem, 58%);
      height: auto;
      flex: none;
      padding: 2.7rem 3rem;
      gap: 1.8rem;
    }

    .page-step:has(.gos-box-slide):not(:has(.title-slide)):not(:has(.section-divider-slide)) {
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .arch-box.wide-slide { width: min(78rem, 92%); }

    @media (max-width: 900px) {
      .deck { padding: 0.85rem 1rem 0.75rem; }
      .arch-box.gos-box-slide { width: 100%; padding: 1.5rem 1.25rem; }
      .box-header h2 { font-size: 1.5rem; }
    }
"""


def parse_bullets(lines: list[str]) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for line in lines:
        m = re.match(r"^(\s*)-\s+(.*)$", line)
        if not m:
            continue
        depth = 1 if len(m.group(1)) >= 4 else 0
        items.append((depth, m.group(2).strip()))
    return items


def render_inline(text: str) -> str:
    """Escape text, keeping **bold**, *italic* and [links](url)."""
    parts: list[str] = []
    last = 0
    pattern = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|\[([^\]]+)\]\(([^)]+)\)")
    for m in pattern.finditer(text):
        parts.append(html.escape(text[last : m.start()]))
        if m.group(1):
            parts.append(f"<strong>{html.escape(m.group(1))}</strong>")
        elif m.group(2):
            parts.append(f"<em>{html.escape(m.group(2))}</em>")
        else:
            parts.append(
                f'<a href="{html.escape(m.group(4))}" target="_blank" rel="noopener noreferrer">'
                f"{html.escape(m.group(3))}</a>"
            )
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


# Every text tr() renders, in order; the language selector swaps each for its translation.
UNITS: list[str] = []
# The texts of the archived slides (steps-archive.md): translated, but not shipped.
ARCHIVED_UNITS: list[str] = []


def tr(text: str) -> str:
    if text not in UNITS:
        UNITS.append(text)
    return f'<span data-i18n="{UNITS.index(text)}">{render_inline(text)}</span>'


def load_translations() -> dict[str, dict[str, str]]:
    """Translations of every UNITS entry, keyed by language then by the English text.

    Raises ValueError naming what is missing or no longer used, so a change to steps.md
    cannot ship with a language that silently falls back to English.
    """
    data = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    known = UNITS + [u for u in ARCHIVED_UNITS if u not in UNITS]
    problems = []
    for lang, _ in LOCALES[1:]:
        strings = data.get(lang, {})
        problems += [f"{lang}: missing {u!r}" for u in known if not strings.get(u)]
        problems += [f"{lang}: unused {k!r}" for k in strings if k not in known]
    if problems:
        raise ValueError(
            f"{TRANSLATIONS_PATH.name} is out of date:\n  " + "\n  ".join(problems)
        )
    return data


class Slide:
    def __init__(self, marker: str, bullets: list[tuple[int, str]]):
        self.marker = marker
        self.bullets = bullets

    def render(self) -> str:
        raise NotImplementedError


WORLD_TITLE = "Think of our world as a computer"

# Same two grays as the gos.earth globe (ocean and land).
ART_FILL = "#e9e9e9"
ART_LIGHT = "#f9f9f9"


TEAL = "rgb(107, 163, 163)"
TEAL_DARK = "rgb(47, 95, 95)"
HACK_RED = "#b94a48"

# The world computer is an exploded isometric stack drawn in a WCX_W × WCX_H box. A point
# (x, y) of a layer's plane, z above it, lands at iso(x, y, z, top), where top is the
# screen y of that layer's back corner. Every layer is a SIDE × SIDE square.
WCX_W, WCX_H = 1120, 600
WCX_CX = 560
ISO_A, ISO_B = 0.9, 0.32
SIDE = 262
# Back-corner y and thickness of each layer, bottom to top. The hardware is no slab: it is the
# planet's own surface, and its "layer" is just the patch of ground the stack stands on.
WCX_LAYERS = {"hardware": (432, 0), "os": (250, 9), "apps": (140, 9), "users": (30, 9)}
WCX_LABEL_X = 828  # layer names start here, right of the stack
WCX_CALLOUT_X = 300  # what happens to the whole stack is told left of here
# When the Governance Operating System comes in, the whole picture moves right by WCX_SHIFT and
# its points are told left of WCX_GOS_X (both after the move), one beside each layer.
WCX_SHIFT = 100
WCX_GOS_X = WCX_CX - SIDE * ISO_A + WCX_SHIFT - 50
WCX_GOS_HEAD_Y = 64  # where its heading ends
WCX_GOS_HEAD_OUT = 28  # how far its heading starts left of the slide's text
# Callouts point at the operating system: (callout y, plane point it points to).
WCX_CALLOUTS = {
    "upgrade": (205, (0, 0.45 * SIDE)),
    "hack": (300, (0, 0.85 * SIDE)),
    "checks": (395, (0.3 * SIDE, SIDE)),
}
# The globe first sits in the middle. Then it zooms in, tilts and sinks until only its top is
# left: a curved horizon (x, horizon y, radius) running across the bottom of the slide, drawn
# by the planet canvas in GLOBE_JS. WCX_PLANET_ROTATE is the d3 rotation it ends at.
WCX_GLOBE = (WCX_CX, 300, 180)
WCX_PLANET = (WCX_CX, 418, 2400)
WCX_PLANET_ROTATE = (-15, 26)


def horizon_y(x: float) -> float:
    cx, h, r = WCX_PLANET
    return h + r - math.sqrt(r * r - (x - cx) ** 2)


def iso(x: float, y: float, z: float = 0.0, top: float = 0.0) -> tuple[float, float]:
    return WCX_CX + (x - y) * ISO_A, top + (x + y) * ISO_B - z


def _attrs(attrs: dict) -> str:
    return "".join(f' {k.rstrip("_").replace("_", "-")}="{v}"' for k, v in attrs.items())


def _poly(points: list[tuple[float, float]], **attrs) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{pts}"{_attrs(attrs)}/>'


def _line(a: tuple[float, float], b: tuple[float, float], **attrs) -> str:
    return f'<path d="M{a[0]:.1f} {a[1]:.1f}L{b[0]:.1f} {b[1]:.1f}"{_attrs(attrs)}/>'


def _plane(top: float, inner: str, clip: bool = False) -> str:
    """Flat content drawn in plane units, laid onto the layer whose back corner is at top."""
    clip_attr = ' clip-path="url(#wcx-plane)"' if clip else ""
    return (
        f'<g transform="matrix({ISO_A} {ISO_B} {-ISO_A} {ISO_B} {WCX_CX} {top})">'
        f"<g{clip_attr}>{inner}</g></g>"
    )


def _face(top: float) -> list[tuple[float, float]]:
    s = SIDE
    return [iso(0, 0, 0, top), iso(s, 0, 0, top), iso(s, s, 0, top), iso(0, s, 0, top)]


def _slab(key: str, face: str, opacity: float = 1.0) -> str:
    top, t = WCX_LAYERS[key]
    s = SIDE

    def p(x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        return iso(x, y, z, top)

    return (
        f'<g opacity="{opacity}" stroke="#c4c4c4" stroke-width="1" stroke-linejoin="round">'
        + _poly([p(0, s), p(s, s), p(s, s, -t), p(0, s, -t)], fill="#efefef")
        + _poly([p(s, s), p(s, 0), p(s, 0, -t), p(s, s, -t)], fill="#e2e2e2")
        + _poly(_face(top), fill=face)
        + "</g>"
    )


def _pop(inner: str, delay: float) -> str:
    return f'<g class="wcx-pop" style="--d:{delay:.2f}s">{inner}</g>'


def _billboard(key: str, x: float, y: float, inner: str, lift: float = 0.0, shadow: bool = True) -> str:
    """An upright icon standing on plane point (x, y); inner is drawn with its base at 0, 0."""
    bx, by = iso(x, y, 0, WCX_LAYERS[key][0])
    shadow = (
        '<ellipse rx="13" ry="3.2" fill="#000" opacity="0.07"/>' if shadow and not lift else ""
    )
    return f'<g transform="translate({bx:.1f} {by - lift:.1f})">{shadow}{inner}</g>'


def _box(x, y, w, d, h, top, z0=0.0, floors=0.0) -> str:
    def p(px: float, py: float, pz: float) -> tuple[float, float]:
        return iso(px, py, pz, top)

    z1 = z0 + h
    out = [
        _poly([p(x, y + d, z0), p(x + w, y + d, z0), p(x + w, y + d, z1), p(x, y + d, z1)], fill="#ededed"),
        _poly([p(x + w, y + d, z0), p(x + w, y, z0), p(x + w, y, z1), p(x + w, y + d, z1)], fill="#dcdcdc"),
        _poly([p(x, y, z1), p(x + w, y, z1), p(x + w, y + d, z1), p(x, y + d, z1)], fill="#fafafa"),
    ]
    if floors:
        d_ = []
        z = z0 + floors
        while z < z1 - 4:
            for a, b in (
                (p(x + 3, y + d, z), p(x + w - 3, y + d, z)),
                (p(x + w, y + d - 3, z), p(x + w, y + 3, z)),
            ):
                d_.append(f"M{a[0]:.1f} {a[1]:.1f}L{b[0]:.1f} {b[1]:.1f}")
            z += floors
        out.append(
            f'<path d="{"".join(d_)}" fill="none" stroke="#b5b5b5" stroke-width="1.3" stroke-dasharray="2.4 2.2"/>'
        )
    return "".join(out)


def _tree(x: float, y: float, top: float, s: float = 1.0) -> str:
    bx, by = iso(x, y, 0, top)
    cx, cy = iso(x, y, 12 * s, top)
    return (
        f'<ellipse cx="{bx:.1f}" cy="{by:.1f}" rx="{5 * s:.1f}" ry="{1.8 * s:.1f}" fill="#000" opacity="0.07"/>'
        f'<path d="M{bx:.1f} {by:.1f}V{cy:.1f}" stroke="#a3a3a3" stroke-width="1.6"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{6.2 * s:.1f}" fill="#e0e0e0" stroke="#a3a3a3"/>'
    )


def _turbine(x: float, y: float, top: float, phase: float) -> str:
    bx, by = iso(x, y, 0, top)
    hx, hy = iso(x, y, 54, top)
    blades = "".join(
        f'<path d="M0 0-2.2-4 0-21 2.2-4z" transform="rotate({a})"/>' for a in (0, 120, 240)
    )
    return (
        f'<path d="M{bx:.1f} {by:.1f}L{hx:.1f} {hy:.1f}" stroke="#a3a3a3" stroke-width="2.2"/>'
        f'<g transform="translate({hx:.1f} {hy:.1f})"><g class="wcx-rotor" style="animation-delay:-{phase:.1f}s" '
        f'fill="#dcdcdc" stroke="#a3a3a3" stroke-width="0.8">{blades}<circle r="2.6" fill="#a3a3a3"/></g></g>'
    )


def _smoke(x: float, y: float, z: float, top: float) -> str:
    sx, sy = iso(x, y, z, top)
    return "".join(
        f'<circle class="wcx-smoke" cx="{sx:.1f}" cy="{sy - 3:.1f}" r="3.6" fill="#d4d4d4" '
        f'style="animation-delay:-{d:.1f}s"/>'
        for d in (0, 1.2, 2.4)
    )


def _ground_at(x: float, y: float) -> tuple[float, float]:
    """The ground plane point drawn at box point (x, y)."""
    u, v = (x - WCX_CX) / ISO_A, (y - WCX_LAYERS["hardware"][0]) / ISO_B
    return (v + u) / 2, (v - u) / 2


def _house(x: float, y: float, top: float, w: float = 11, d: float = 10, h: float = 8) -> str:
    def p(px: float, py: float, pz: float) -> tuple[float, float]:
        return iso(px, py, pz, top)

    ridge = h + 6
    return (
        _box(x, y, w, d, h, top)
        + _poly([p(x, y, h), p(x + w, y, h), p(x + w, y + d / 2, ridge), p(x, y + d / 2, ridge)], fill="#f2f2f2")
        + _poly([p(x, y + d / 2, ridge), p(x + w, y + d / 2, ridge), p(x + w, y + d, h), p(x, y + d, h)], fill="#e4e4e4")
        + _poly([p(x + w, y, h), p(x + w, y + d, h), p(x + w, y + d / 2, ridge)], fill="#d4d4d4")
    )


def _solar(x: float, y: float, top: float, rows: int = 4, w: float = 46) -> str:
    out = []
    for r in range(rows):
        y0 = y + r * 11
        pts = [iso(x, y0, 2, top), iso(x + w, y0, 2, top), iso(x + w, y0 + 7, 7, top), iso(x, y0 + 7, 7, top)]
        out.append(_poly(pts, fill="#dadada"))
        a, b = iso(x, y0 + 3.5, 4.5, top), iso(x + w, y0 + 3.5, 4.5, top)
        out.append(_line(a, b, stroke="#b8b8b8", stroke_width="0.6"))
    return "".join(out)


def ground_svg() -> str:
    """The hardware: roads, nature, energy and industry on the planet's digital surface."""
    top, _ = WCX_LAYERS["hardware"]
    s = SIDE
    far = 1400
    rnd = random.Random(11)

    def field(cx: float, cy: float, w: float, d: float) -> str:
        x, y = _ground_at(cx, cy)
        x, y = x - w / 2, y - d / 2
        furrows = "".join(f"M{x + 3:.1f} {y + f:.1f}H{x + w - 3:.1f}" for f in range(5, int(d) - 2, 5))
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{d}" rx="3" fill="#f0f0f0" stroke="#d4d4d4"/>'
            f'<path d="{furrows}" stroke="#d6d6d6" stroke-width="1.6"/>'
        )

    flat = (
        # Two roads cross under the stack and run on over the horizon.
        f'<g fill="#fff" stroke="#d4d4d4"><rect x="{-far}" y="150" width="{s + 2 * far}" height="16"/>'
        f'<rect x="96" y="{-far}" width="16" height="{s + 2 * far}"/></g>'
        '<rect x="96.5" y="150.5" width="15" height="15" fill="#fff"/>'
        f'<path d="M{-far} 158H96M112 158H{s + far}M104 {-far}V150M104 166V{s + far}" stroke="#d4d4d4" stroke-dasharray="5 5"/>'
        '<g fill="#737373"><rect class="wcx-car-x" x="-14" y="152.5" width="10" height="5" rx="1.5"/>'
        f'<rect class="wcx-car-xr" x="{s + 4}" y="159" width="10" height="5" rx="1.5" style="animation-delay:-4s"/>'
        '<rect class="wcx-car-y" x="98" y="-14" width="5" height="10" rx="1.5" style="animation-delay:-2s"/></g>'
        # A lake, a park and farmland.
        '<ellipse cx="200" cy="64" rx="40" ry="28" fill="#e6e6e6" stroke="#d0d0d0"/>'
        '<path d="M182 58q5-4 10 0t10 0M194 72q5-4 10 0t10 0" fill="none" stroke="#c4c4c4" stroke-width="1.3"/>'
        '<rect x="12" y="178" width="74" height="72" rx="10" fill="#f3f3f3" stroke="#d4d4d4" stroke-dasharray="3 3"/>'
        + field(215, 560, 70, 44)
        + field(150, 585, 60, 40)
        + field(90, 560, 60, 40)
    )

    # (sort key, svg, box point it stands on): the stack's own patch of ground first.
    objects: list[tuple[float, str, tuple[float, float]]] = []

    def add(x: float, y: float, svg: str, key: float | None = None) -> None:
        objects.append((x + y if key is None else key, svg, iso(x, y, 0, top)))

    trees = [
        (14, 16), (38, 10), (76, 14), (24, 44), (84, 48), (12, 92), (80, 96), (40, 136), (76, 130), (14, 132),
        (128, 18), (152, 12), (250, 18), (134, 72), (128, 126), (162, 134), (246, 104), (232, 136), (252, 128),
        (26, 194), (52, 188), (74, 200), (30, 224), (62, 230), (46, 244), (76, 242), (30, 72), (58, 30),
    ]
    for x, y in trees:
        add(x, y, _tree(x, y, top, 0.85 + 0.3 * rnd.random()))
    buildings = [
        (122, 176, 22, 22, 52), (150, 178, 20, 22, 36), (176, 176, 24, 22, 64), (208, 178, 20, 20, 30),
        (236, 180, 18, 18, 42), (122, 206, 22, 22, 30), (150, 206, 22, 20, 44),
        (124, 236, 20, 20, 22), (152, 236, 20, 20, 16),
    ]
    for x, y, w, d, h in buildings:
        add(x + w / 2, y + d / 2, _box(x, y, w, d, h, top, floors=8))
    factory = (
        _box(182, 212, 56, 32, 18, top)
        + _box(212, 216, 6, 6, 22, top, z0=18)
        + _box(226, 216, 7, 7, 32, top, z0=18)
        + _smoke(229.5, 219.5, 52, top)
    )
    add(210, 228, factory)

    # Around it, the rest of the world, placed by where it shows up in the box.
    side_trees = [
        (70, 505), (96, 497), (122, 510), (142, 500), (112, 538), (150, 526), (205, 488), (240, 476), (178, 498),
        (-20, 562), (-62, 578), (172, 545), (10, 585), (-40, 600), (-90, 612),
        (1140, 532), (1165, 548), (1215, 540), (1150, 618), (1205, 632), (1255, 612), (958, 642), (1045, 650),
        (812, 590),
    ]
    sides = [(X, Y, lambda x, y: _tree(x, y, top, 0.85 + 0.3 * rnd.random())) for X, Y in side_trees]
    sides += [
        (40, 548, lambda x, y: _turbine(x, y, top, 0.0)),
        (88, 530, lambda x, y: _turbine(x, y, top, 2.1)),
        (1188, 582, lambda x, y: _turbine(x, y, top, 1.2)),
        (1240, 572, lambda x, y: _turbine(x, y, top, 3.0)),
        (1010, 604, lambda x, y: _solar(x - 23, y - 20, top)),
        (1100, 628, lambda x, y: _box(x - 25, y - 15, 50, 30, 18, top)
            + _box(x + 2, y - 11, 6, 6, 24, top, z0=18) + _box(x + 14, y - 11, 7, 7, 36, top, z0=18)
            + _smoke(x + 17.5, y - 7.5, 54, top)),
        (850, 576, lambda x, y: _house(x - 5, y - 5, top)),
        (880, 588, lambda x, y: _house(x - 5, y - 5, top, 12, 11, 9)),
        (912, 598, lambda x, y: _house(x - 5, y - 5, top)),
        (905, 572, lambda x, y: _house(x - 5, y - 5, top, 13, 10, 8)),
        (940, 584, lambda x, y: _house(x - 5, y - 5, top)),
    ]
    for X, Y, make in sides:
        assert Y > horizon_y(X) + 20, f"ground object at {X}, {Y} sits on the horizon"
        x, y = _ground_at(X, Y)
        add(x, y, make(x, y))

    objects.sort(key=lambda o: o[0])
    # Things pop up from the middle outwards.
    mx, my = iso(s / 2, s / 2, 0, top)
    things = "".join(
        _pop(svg, 0.2 + math.hypot(bx - mx, (by - my) * 2) / 900) for _, svg, (bx, by) in objects
    )
    return (
        f'<g clip-path="url(#wcx-planet)">{_plane(top, flat)}</g>'
        + f'<g stroke="#a3a3a3" stroke-width="0.8" stroke-linejoin="round">{things}</g>'
    )


def _connectors(upper: str, lower: str) -> str:
    """Dashed posts from a layer's corners down to the layer below, with data running down them."""
    ut, t = WCX_LAYERS[upper]
    lt, _ = WCX_LAYERS[lower]
    out = []
    for i, (x, y) in enumerate(((0, SIDE), (SIDE, SIDE), (SIDE, 0))):
        a, b = iso(x, y, -t, ut), iso(x, y, 0, lt)
        out.append(_line(a, b, stroke="#d4d4d4", stroke_dasharray="3 4"))
        out.append(
            _line(a, b, class_="wcx-flow", pathLength="100", style=f"animation-delay:-{i * 0.9:.1f}s")
        )
    return f'<g fill="none" stroke-width="1.3">{"".join(out)}</g>'


# The operating system's layout, in plane units. Anything standing on it has to be near the front
# edges (0.64 * max(x, y) > its height + 67), or the applications' slab above hides its top.
OS_HUB = (196, 196)  # the capitol, where power sits
OS_SCALES = (78, 236)
OS_LAW = (236, 78)
# The people running the institutions: (where they stand, delay before they are bribed in a hack).
OS_OFFICIALS = [((40, 250), 0.1), ((110, 170), 0.3), ((150, 248), 0.2), ((248, 150), 0.25), ((170, 110), 0.35), ((250, 40), 0.15)]
# Wiring as (path, delay before a hack's red runs along it). The officials' wires run in to the
# capitol, then the capitol's run out to the courts and the law.
OS_WIRES = [
    ("M40 250V170H196V196", 0.45),
    ("M250 40H170V196H196", 0.5),
    ("M150 248V196H196", 0.55),
    ("M248 150H196V196", 0.6),
    ("M110 170V60H40", 0.8),
    ("M170 110H60V40", 0.9),
    ("M196 196V236H78", 1.9),
    ("M196 196H236V78", 2.0),
]
OS_NODES = [(40, 60), (60, 40)] + [xy for xy, _ in OS_OFFICIALS]
HACK_CAPITOL_AT = 1.7  # the officials' red reaches the capitol
HACK_ICONS_AT = 3.0  # and from there the courts and the law
HACK_PALE = "#f6dfde"
HACK_PALER = "#fdf3f3"
# Once the hack holds, the damage spreads through the other layers; the Governance Operating
# System then mends each layer: the operating system and the land after HEAL_DELAY, the
# others after HEAL_SOON.
HEAL_DELAY = 1.9
HEAL_SOON = 0.4
# What comes with the Governance Operating System's click waits this long for the picture to move,
# and a point that comes with the heading follows it after GOS_AFTER_HEAD.
GOS_WAIT = 1.3
GOS_AFTER_HEAD = 0.8
DECAY_SPEED = 360  # how fast the red spreads over the land, in box units per second


def redden_rgb(gray: int) -> tuple[int, int, int]:
    """A grey turned the hack's red, about as light as it was."""
    r, g, b = colorsys.hls_to_rgb(1 / 360, 0.97 * gray / 255, 0.42)
    return round(r * 255), round(g * 255), round(b * 255)


def capitol_svg(hacked: bool = False) -> str:
    line, fill, cols = (HACK_RED, HACK_PALER, HACK_PALE) if hacked else ("#9a9a9a", "#f6f6f6", ART_FILL)
    pillars = "".join(f'<rect x="{c - 2.4}" y="-27" width="4.8" height="19"/>' for c in (-16, -8, 0, 8, 16))
    return (
        f'<g fill="{fill}" stroke="{line}" stroke-width="1.2" stroke-linejoin="round">'
        '<path d="M-27 0h54v-4h-54z"/><path d="M-23 -4h46v-4h-46z"/>'
        f'<g fill="{cols}">{pillars}</g>'
        '<path d="M-25 -27h50v-4h-50z"/><path d="M-25 -31 0-44 25-31z"/></g>'
    )


def scales_svg(hacked: bool = False) -> str:
    line, pan = (HACK_RED, HACK_PALE) if hacked else ("#8a8a8a", ART_FILL)
    return (
        f'<g fill="none" stroke="{line}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M0-2V-33M-9 0H9M-16-29h32"/>'
        '<path d="M-16-29-21-16M-16-29-11-16M16-29 11-16M16-29 21-16"/>'
        f'<path d="M-23-16a7 5 0 0 0 14 0z" fill="{pan}"/><path d="M9-16a7 5 0 0 0 14 0z" fill="{pan}"/>'
        f'<circle cy="-34" r="2" fill="{line}"/></g>'
    )


def law_doc_svg(hacked: bool = False) -> str:
    line, paper, fold, text = (
        (HACK_RED, HACK_PALER, HACK_PALE, "#e0a09f") if hacked else ("#9a9a9a", "#fff", ART_FILL, "#c4c4c4")
    )
    return (
        '<g stroke-linejoin="round">'
        f'<path d="M-12-2V-34H5l7 7V-2z" fill="{paper}" stroke="{line}" stroke-width="1.2"/>'
        f'<path d="M5-34v7h7" fill="{fold}" stroke="{line}" stroke-width="1.2"/>'
        f'<path d="M-7-24H4M-7-19H7M-7-14H7M-7-9H2" stroke="{text}" stroke-width="1.5" stroke-linecap="round"/></g>'
    )


def official_svg(hacked: bool = False) -> str:
    return person_svg(HACK_RED if hacked else "#7a7a7a", scale=0.85)


def os_svg(officials=lambda inner: inner) -> str:
    """The operating system: institutions and the people running them, wired into everything.
    officials(svg) wraps the people, who leave once the Governance Operating System runs it."""
    top, _ = WCX_LAYERS["os"]
    wires = [d for d, _ in OS_WIRES]
    traces = "".join(f'<path d="{d}"/>' for d in wires)
    pulses = "".join(
        f'<path d="{d}" pathLength="100" style="animation-delay:-{i * 0.8:.1f}s"/>' for i, d in enumerate(wires)
    )
    nodes = "".join(f'<circle cx="{x}" cy="{y}" r="3.2"/>' for x, y in OS_NODES)
    flat = (
        f'<g fill="none" stroke="#d4d4d4" stroke-width="1.6" stroke-linejoin="round">{traces}</g>'
        f'<g fill="#fff" stroke="#c4c4c4" stroke-width="1.3">{nodes}</g>'
        f'<g class="wcx-pulses" fill="none" stroke="#7a7a7a" stroke-width="2" stroke-linecap="round">{pulses}</g>'
    )
    icons = [
        _pop(_billboard("os", *OS_LAW, law_doc_svg()), 0.55),
        _pop(_billboard("os", *OS_HUB, capitol_svg()), 0.4),
        _pop(_billboard("os", *OS_SCALES, scales_svg()), 0.7),
    ] + [officials(_pop(_billboard("os", x, y, official_svg()), 0.5 + i * 0.07)) for i, ((x, y), _) in enumerate(OS_OFFICIALS)]
    return (
        _connectors("os", "hardware")
        + _slab("os", "#fff", 0.92)
        + _plane(top, flat)
        + "".join(icons)
    )


APP_ICONS = {
    "education": '<path d="M-10-3 0-8l10 5L0 2z"/><path d="M-6-1v5c3 2.6 9 2.6 12 0v-5M10-3v6"/>',
    "health": '<path d="M-3-9h6v6h6v6H3v6h-6V3h-6v-6h6z"/>',
    "shopping": '<path d="M-8-3h16L6.5 9h-13z"/><path d="M-4-3v-2.5a4 4 0 0 1 8 0V-3"/>',
    "food": '<path d="M-7-9v5a2.5 2.5 0 0 0 5 0v-5M-4.5-9V9"/><path d="M6 9V-9C3-7.5 2-3 2 1h4"/>',
    "labor": '<path d="M-8 8 2-2"/><rect x="-7" y="-3" width="14" height="6" rx="1" transform="translate(4 -4) rotate(45)"/>',
    "tech": '<rect x="-8" y="-8" width="16" height="11" rx="1.5"/><path d="M-11 6.5h22"/>',
}


def app_tile_svg(icon: str, sick: bool = False) -> str:
    tile, line, fill = (HACK_RED, HACK_RED, HACK_PALER) if sick else ("#a3a3a3", "#737373", "#fff")
    return (
        f'<rect x="-19" y="-40" width="38" height="38" rx="9" fill="{fill}" stroke="{tile}" stroke-width="1.3"/>'
        f'<g transform="translate(0 -21)" fill="none" stroke="{line}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{APP_ICONS[icon]}</g>'
    )


def _no_mood(inner: str, delay: float = 0.0) -> str:
    return ""


def _sick_face(key: str) -> str:
    """A faint red over a layer's face, for when the damage reaches it."""
    return _poly(_face(WCX_LAYERS[key][0]), fill=HACK_RED, fill_opacity="0.05", stroke=HACK_RED, stroke_width="1.6")


def apps_svg(sick=_no_mood, happy=_no_mood) -> str:
    """Applications: public services and companies, running on top of the operating system.
    sick(svg, delay) wraps what shows while the damage has reached them."""
    top, _ = WCX_LAYERS["apps"]
    grid = "".join(f'<path d="M{v:.1f} 0V{SIDE}M0 {v:.1f}H{SIDE}"/>' for v in [SIDE * i / 8 for i in range(1, 8)])
    flat = f'<g stroke="#ededed" stroke-width="1">{grid}</g>'
    # Along the front half of the layer, so the users' slab above never hides the tiles' tops.
    spots = [(48, 262), (89, 221), (130, 180), (171, 139), (212, 98), (253, 57)]
    tiles = "".join(
        _pop(_billboard("apps", x, y, f'<g class="wcx-bob" style="animation-delay:-{i * 0.7:.1f}s">'
                        f"{app_tile_svg(icon)}{sick(app_tile_svg(icon, True), 0.3 + i * 0.3)}</g>"), 0.35 + i * 0.12)
        for i, ((x, y), icon) in enumerate(zip(spots, APP_ICONS))
    )
    # The people working in them, in front of the tiles.
    workers = [(100, 256), (160, 250), (200, 224), (236, 196), (256, 140)]
    people = "".join(
        _pop(_billboard("apps", x, y, person_svg("#7a7a7a", 0.8)
                        + sick(person_svg(HACK_RED, 0.8), 0.4 + i * 0.25)), 0.5 + i * 0.08)
        for i, (x, y) in enumerate(workers)
    )
    return (
        _connectors("apps", "os") + _slab("apps", "#fff", 0.9) + sick(_sick_face("apps"), 0.2)
        + _plane(top, flat) + tiles + people
    )


def person_svg(shade: str, scale: float = 1.0) -> str:
    size = f' transform="scale({scale})"' if scale != 1 else ""
    return f'<g fill="{shade}"{size}><circle cy="-15" r="4.6"/><path d="M-8.5-1a8.5 8.5 0 0 1 17 0z"/></g>'


def face_svg(shade: str, mood: str) -> str:
    """A person whose face shows: "sad" or "happy"."""
    mouth = "M-2.3-11.3Q0-13.7 2.3-11.3" if mood == "sad" else "M-2.4-13.2Q0-10.4 2.4-13.2"
    brows = (
        '<path d="M-3.4-18.6-0.9-17.7M3.4-18.6 0.9-17.7" fill="none" stroke="#fff" stroke-width="0.8" stroke-linecap="round"/>'
        if mood == "sad"
        else ""
    )
    return (
        f'<g fill="{shade}"><circle cy="-15" r="5.6"/><path d="M-8.5-1a8.5 8.5 0 0 1 17 0z"/></g>'
        '<g fill="#fff"><circle cx="-1.9" cy="-15.9" r="0.85"/><circle cx="1.9" cy="-15.9" r="0.85"/></g>'
        f'{brows}<path d="{mouth}" fill="none" stroke="#fff" stroke-width="1" stroke-linecap="round"/>'
    )


def users_svg(sick=_no_mood, happy=_no_mood) -> str:
    """Users: people like you and me, on top of everything. sick(svg, delay) wraps how they look
    once the damage reaches them, happy(svg, delay) how they look once it is mended."""
    spots = [
        (40, 44), (120, 30), (206, 54), (66, 120), (152, 110), (234, 132), (30, 206), (122, 190), (204, 214), (100, 244),
        (80, 78), (160, 62), (250, 90), (14, 128), (190, 166), (250, 214), (162, 246),
    ]
    rnd = random.Random(5)

    def person(i: int) -> str:
        shade = "#525252" if i % 3 else "#8a8a8a"
        return (
            person_svg(shade)
            + sick(face_svg(HACK_RED, "sad"), 0.2 + 1.2 * rnd.random())
            + happy(face_svg(shade, "happy"), 0.1 * i)
        )

    people = "".join(
        _pop(_billboard("users", x, y, f'<g class="wcx-bob" style="animation-delay:-{i * 0.45:.2f}s">'
                        f"{person(i)}</g>"), 0.3 + i * 0.06)
        for i, (x, y) in enumerate(spots)
    )
    return _connectors("users", "apps") + _slab("users", "#fff", 0.9) + sick(_sick_face("users"), 0.2) + people


def evil_svg() -> str:
    """A horned, grinning face: whoever captured power."""
    dark = "#4a1716"
    return (
        f'<g stroke="#7d2f2e" stroke-width="1" stroke-linejoin="round" fill="{HACK_RED}">'
        '<path d="M-7.6-17.4-10.5-25-2.8-20.2z"/><path d="M7.6-17.4 10.5-25 2.8-20.2z"/>'
        '<circle cy="-10.5" r="10.5"/></g>'
        f'<g fill="none" stroke="{dark}" stroke-width="1.8" stroke-linecap="round">'
        '<path d="M-7-15.2-2.2-12.6M7-15.2 2.2-12.6"/><path d="M-6.4-6.6Q0-0.6 6.4-6.6"/></g>'
        f'<g fill="{dark}"><circle cx="-3.6" cy="-10.6" r="1.5"/><circle cx="3.6" cy="-10.6" r="1.5"/></g>'
    )


def shield_svg() -> str:
    return (
        f'<path d="M0-26 14-20.5V-10C14-1 7 4 0 7-7 4-14-1-14-10V-20.5z" fill="{TEAL}" '
        f'stroke="{TEAL_DARK}" stroke-width="1.2" stroke-linejoin="round"/>'
        '<path d="M-6-9.5-1.5-5 6.5-13" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def upgrade_svg() -> str:
    """A new version rolls across the operating system."""
    top, _ = WCX_LAYERS["os"]
    band = f'<rect class="wcx-sweep" x="-70" y="0" width="70" height="{SIDE}" fill="url(#wcx-sweep-g)"/>'
    return _plane(top, band, clip=True) + _poly(
        _face(top), fill="none", stroke=TEAL, stroke_width="1.8", class_="wcx-glow"
    )


def mend_svg(key: str) -> str:
    """The Governance Operating System mends a layer: one teal sweep across it."""
    top, _ = WCX_LAYERS[key]
    band = f'<rect class="wcx-mend-band" x="-70" y="0" width="70" height="{SIDE}" fill="url(#wcx-sweep-g)"/>'
    return _plane(top, band, clip=True) + _poly(
        _face(top), fill="none", stroke=TEAL, stroke_width="1.8", class_="wcx-mend-edge"
    )


def gos_layer_svg(key: str) -> str:
    """The layer the Governance Operating System runs on stays faintly teal."""
    return _poly(_face(WCX_LAYERS[key][0]), fill=TEAL, fill_opacity="0.07", stroke=TEAL, stroke_width="1.6")


def hack_svg() -> str:
    """Power gets captured: the officials are bribed and turn red, the red runs along their wires
    to the capitol, and from there to the courts and the law."""
    top, _ = WCX_LAYERS["os"]
    paths = "".join(
        f'<path class="wcx-capture" d="{d}" pathLength="100" style="--d:{delay:.2f}s"/>' for d, delay in OS_WIRES
    )
    flat = (
        f'<rect class="wcx-glitch" width="{SIDE}" height="{SIDE}" fill="{HACK_RED}"/>'
        f'<g fill="none" stroke="{HACK_RED}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{paths}</g>'
    )

    def taint(xy: tuple[float, float], art: str, delay: float) -> str:
        """A red copy laid over the grey one, fading in once the red reaches it."""
        return f'<g class="wcx-taint" style="--d:{delay:.2f}s">{_billboard("os", *xy, art, shadow=False)}</g>'

    red = (
        [taint(xy, official_svg(True), delay) for xy, delay in OS_OFFICIALS]
        + [taint(OS_HUB, capitol_svg(True), HACK_CAPITOL_AT)]
        + [taint(xy, art, HACK_ICONS_AT) for xy, art in ((OS_SCALES, scales_svg(True)), (OS_LAW, law_doc_svg(True)))]
    )
    return (
        _plane(top, flat, clip=True)
        + _poly(_face(top), fill="none", stroke=HACK_RED, stroke_width="1.8", class_="wcx-glitch-edge")
        + "".join(red)
    )


def checks_svg() -> str:
    """Checks and balances try to undo the hack: the red gives way for a moment, then comes back."""
    top, _ = WCX_LAYERS["os"]
    ring = f'<circle class="wcx-ring" cx="{SIDE / 2}" cy="{SIDE / 2}" r="125" fill="none" stroke="{TEAL}" stroke-width="2.5"/>'
    return _plane(top, ring, clip=True) + _poly(
        _face(top), fill="none", stroke=TEAL, stroke_width="1.8", class_="wcx-checks-edge"
    )


def broken_shield_svg() -> str:
    """The shield, with the crack it gets when the hack holds."""
    return (
        f'<g class="wcx-fail">{shield_svg()}'
        '<path class="wcx-crack" d="M-1-26 2-18.5-2.5-12 2.5-5-1 2" fill="none" stroke="#1d3b3b" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


# Badges sit on the capitol's roof but are drawn over the whole stack so the upper slabs never hide them.
WCX_BADGES = {
    "hack": lambda: _pop(_billboard("os", *OS_HUB, f'<g class="wcx-evil">{evil_svg()}</g>', lift=47), HACK_CAPITOL_AT),
    "checks": lambda: _pop(_billboard("os", *OS_HUB, broken_shield_svg(), lift=46), 0.25),
}


WCX_ART = {
    "hardware": ground_svg,
    "os": os_svg,
    "apps": apps_svg,
    "users": users_svg,
    "upgrade": upgrade_svg,
    "hack": hack_svg,
    "checks": checks_svg,
}
WCX_STACK = ["hardware", "os", "upgrade", "hack", "checks", "apps", "users"]

CALLOUT_ICONS = {
    "upgrade": f'<svg viewBox="0 0 24 24" fill="none" stroke="{TEAL_DARK}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v4h-4"/></svg>',
    "hack": '<svg viewBox="-14 -26 28 27" aria-hidden="true">' + evil_svg() + "</svg>",
    "checks": '<svg viewBox="-16 -28 32 37" aria-hidden="true">' + shield_svg() + "</svg>",
}


def _lead(key: str, frag: int) -> str:
    """The hairline from a label to what it names."""
    if key in WCX_CALLOUTS:
        y, (px, py) = WCX_CALLOUTS[key]
        a, b = (WCX_CALLOUT_X + 10, y), iso(px, py, 0, WCX_LAYERS["os"][0])
    else:
        top, _ = WCX_LAYERS[key]
        b = iso(SIDE, 0, 0, top)
        a, b = (WCX_LABEL_X - 12, b[1]), (b[0] + 10, b[1])
    color = {"upgrade": TEAL, "checks": TEAL, "hack": HACK_RED}.get(key, "#bdbdbd")
    return (
        f'<g class="wcx-fade wcx-lead wcx-{key}-lead" data-frag="{frag}">'
        + _line(a, b, stroke=color, stroke_width="1.2", fill="none")
        + f'<circle cx="{b[0]:.1f}" cy="{b[1]:.1f}" r="2.6" fill="{color}"/></g>'
    )


def _gos_lead(layer: str, frag: int, wait: float = 0.0) -> str:
    """The hairline from a Governance Operating System point to its layer, drawn before the move,
    after wait seconds."""
    b = iso(0, SIDE, 0, WCX_LAYERS[layer][0])
    a, b = (WCX_GOS_X + 8 - WCX_SHIFT, b[1]), (b[0] - 10, b[1])
    style = f' style="--in:{wait}s"' if wait else ""
    return (
        f'<g class="wcx-fade wcx-lead wcx-gos-lead wcx-gos-{layer}-lead" data-frag="{frag}"{style}>'
        + _line(a, b, stroke=TEAL, stroke_width="1.2", fill="none")
        + f'<circle cx="{b[0]:.1f}" cy="{b[1]:.1f}" r="2.6" fill="{TEAL}"/></g>'
    )


def world_computer_svg(
    frags: dict[str, int],
    gos: int | None = None,
    gos_points: list[tuple[str, int]] = (),
    decay: dict[str, int] | None = None,
    head: int | None = None,
) -> str:
    """decay maps a layer to the click the hack's damage reaches it; each GOS point mends its
    layer, and the operating system's point mends the hardware too."""
    decay = decay or {}
    heal = {layer: click for layer, click in gos_points}
    if "os" in heal:
        heal["hardware"] = heal["os"]
    heal_in = {k: HEAL_DELAY if k in ("os", "hardware") else HEAL_SOON for k in heal}

    def healed(key: str, inner: str) -> str:
        """Shown until the layer is mended."""
        if key not in heal:
            return inner
        return f'<g class="wcx-fade wcx-heal" data-until="{heal[key]}" style="--out:{heal_in[key]}s">{inner}</g>'

    def sick(key: str):
        if key not in decay:
            return _no_mood
        return lambda inner, delay=0.0: (
            f'<g class="wcx-fade wcx-sick wcx-sick-{key}" data-frag="{decay[key]}" style="--in:{delay:.2f}s">'
            f"{healed(key, inner)}</g>"
        )

    def happy(key: str):
        if key not in heal:
            return _no_mood
        return lambda inner, delay=0.0: (
            f'<g class="wcx-fade wcx-happy" data-frag="{heal[key]}" style="--in:{heal_in[key] + delay:.2f}s">{inner}</g>'
        )

    def mend(key: str) -> str:
        if key not in heal:
            return ""
        return f'<g class="wcx-mend" data-frag="{heal[key]}" style="--out:{heal_in[key]}s">{mend_svg(key)}</g>'

    # The operating system is mended over whatever was last laid on it.
    os_last = [k for k in ("os", "upgrade", "hack", "checks") if k in frags][-1:]
    groups, badges = [], []
    for key in WCX_STACK:
        if key not in frags:
            continue
        frag = frags[key]
        cls = "wcx-fade wcx-ground" if key == "hardware" else "wcx-step"
        if key in ("apps", "users"):
            art = WCX_ART[key](sick(key), happy(key))
        elif key == "os":
            art = os_svg(lambda inner: healed("os", inner))
        else:
            art = WCX_ART[key]()
        parts = [(groups, art)] + ([(badges, WCX_BADGES[key]())] if key in WCX_BADGES else [])
        for out, inner in parts:
            if key == "upgrade" and "hack" in frags:
                inner = f'<g class="wcx-fade" data-until="{frags["hack"]}">{inner}</g>'
            if key in ("hack", "checks"):
                inner = healed("os", inner)
            out.append(f'<g class="{cls} wcx-{key}" data-frag="{frag}">{inner}</g>')
        if key in os_last:
            groups.append(mend("os"))
            if "os" in heal:
                groups.append(
                    f'<g class="wcx-fade wcx-gos-layer" data-frag="{heal["os"]}" style="--in:{heal_in["os"]}s">'
                    f'{gos_layer_svg("os")}</g>'
                )
        if key in ("apps", "users"):
            groups.append(mend(key))
    # The land's red is drawn by CSS and GLOBE_JS; this only says when.
    groups.append(sick("hardware")(""))
    groups += badges
    px, ph, pr = WCX_PLANET
    leads = "".join(
        f'<g class="wcx-fade" data-until="{gos}">{_lead(k, f)}</g>' if gos and k in WCX_CALLOUTS else _lead(k, f)
        for k, f in frags.items()
    ) + "".join(
        _gos_lead(layer, f, GOS_WAIT if f == gos else GOS_AFTER_HEAD if f == head else 0.0) for layer, f in gos_points
    )
    return f"""<svg viewBox="0 0 {WCX_W} {WCX_H}" fill="none" aria-hidden="true">
  <defs>
    <clipPath id="wcx-plane"><rect width="{SIDE}" height="{SIDE}"/></clipPath>
    <clipPath id="wcx-planet"><circle cx="{px}" cy="{ph + pr}" r="{pr}"/></clipPath>
    <linearGradient id="wcx-sweep-g">
      <stop offset="0" stop-color="{TEAL}" stop-opacity="0"/>
      <stop offset="0.7" stop-color="{TEAL}" stop-opacity="0.4"/>
      <stop offset="1" stop-color="{TEAL}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  {"".join(groups)}
  {leads}
</svg>"""


def _globe_slot(spot: tuple[float, float, float], attrs: str) -> str:
    x, y, r = spot
    return (
        f'<div class="wcx-globe" data-globe-slot {attrs} style="left:{(x - r) / WCX_W:.3%};'
        f'top:{(y - r) / WCX_H:.3%};width:{2 * r / WCX_W:.3%}"></div>'
    )


WORLD_FAILURES_TITLE = "When the world computer malfunctions"

ART_DARK = "#525252"


def corruption_svg() -> str:
    """A government building on a screen; money slips out under the desk."""
    columns = "".join(
        f'<rect x="{cx - 3:.1f}" y="39" width="6" height="21" fill="{ART_FILL}"/>'
        for cx in (40, 53.3, 66.7, 80)
    )
    return f"""<svg viewBox="0 0 120 120" fill="none" aria-hidden="true">
  <defs><clipPath id="wf-under"><rect x="0" y="74" width="120" height="46"/></clipPath></defs>
  <g clip-path="url(#wf-under)"><circle class="wf-coin" cx="30" cy="70" r="5.5" fill="{ART_DARK}"/></g>
  <rect x="16" y="12" width="88" height="62" rx="6" fill="{ART_LIGHT}" stroke="#a3a3a3" stroke-width="1.75"/>
  <path d="M30 36 60 22 90 36z" fill="{ART_FILL}"/>
  {columns}
  <rect x="32" y="60" width="56" height="5" rx="1" fill="{ART_FILL}"/>
  <rect x="54" y="74" width="12" height="18" fill="{ART_FILL}"/>
  <path d="M8 92h104" stroke="#a3a3a3" stroke-width="1.75" stroke-linecap="round"/>
  <path d="M17 99v12a4 4 0 0 0 4 4h18a4 4 0 0 0 4-4v-12" stroke="#737373" stroke-width="2" stroke-linecap="round"/>
</svg>"""


def bureaucracy_svg() -> str:
    """Windows pile up one on another, and the front one never stops loading."""
    windows = []
    for i in range(5):
        x, y = 12 + i * 9, 12 + i * 9
        anim = f' class="wf-pile wf-p{i}"' if i else ""
        spinner = (
            f'<circle cx="{x + 31}" cy="{y + 28}" r="9" stroke="{ART_FILL}" stroke-width="3"/>'
            f'<path class="wf-spin" style="transform-origin:{x + 31}px {y + 28}px" '
            f'd="M{x + 31} {y + 19}a9 9 0 0 1 9 9" stroke="{ART_DARK}" stroke-width="3" stroke-linecap="round"/>'
            if i == 4
            else ""
        )
        windows.append(
            f"<g{anim}>"
            f'<rect x="{x}" y="{y}" width="62" height="48" rx="4" fill="{ART_LIGHT}" stroke="#a3a3a3" stroke-width="1.75"/>'
            f'<path d="M{x + 1} {y + 9}h60" stroke="#a3a3a3" stroke-width="1.75"/>'
            f'<rect x="{x + 1}" y="{y + 1}" width="60" height="8" rx="3" fill="{ART_FILL}"/>'
            f"{spinner}</g>"
        )
    return f'<svg viewBox="0 0 120 120" fill="none" aria-hidden="true">{"".join(windows)}</svg>'


def resources_svg() -> str:
    """The globe as a pie: one big slice is pulled away, and heat rises."""
    rest = "M56 68 87.95 56.37A34 34 0 1 1 61.9 34.52z"
    slice_ = "M56 68 61.9 34.52A34 34 0 0 1 87.95 56.37z"
    waves = "".join(
        f'<path class="wf-heat" d="M{x} 30q-3-4 0-8t0-8" style="animation-delay:-{d}s"/>'
        for x, d in ((26, 0), (36, 0.8), (46, 1.6))
    )
    return f"""<svg viewBox="0 0 120 120" fill="none" aria-hidden="true">
  <defs><clipPath id="wf-rest"><path d="{rest}"/></clipPath></defs>
  <path d="{rest}" fill="{ART_FILL}"/>
  <g clip-path="url(#wf-rest)" stroke="{ART_LIGHT}" stroke-width="2.5">
    <ellipse cx="56" cy="68" rx="14" ry="34"/><path d="M20 68h72M24 51h64M24 85h64"/>
  </g>
  <path class="wf-slice" d="{slice_}" fill="{ART_DARK}"/>
  <g stroke="#a3a3a3" stroke-width="1.75" stroke-linecap="round">{waves}</g>
</svg>"""


def wars_svg() -> str:
    """Hexagon territories: dark tiles spread from one edge and take over the map."""
    size = 11
    corners = [
        (0.92 * size * c, 0.92 * size * s)
        for c, s in (
            (0, -1),
            (0.866, -0.5),
            (0.866, 0.5),
            (0, 1),
            (-0.866, 0.5),
            (-0.866, -0.5),
        )
    ]
    hexes = []
    for q in range(-2, 3):
        for r in range(-2, 3):
            if abs(q + r) > 2:
                continue
            x = 60 + size * 1.732 * (q + r / 2)
            y = 60 + size * 1.5 * r
            dist = (abs(q + 2) + abs(r) + abs(q + 2 + r)) // 2
            pts = " ".join(f"{x + dx:.1f},{y + dy:.1f}" for dx, dy in corners)
            hexes.append(f'<polygon class="wf-hex wf-d{dist}" points="{pts}"/>')
    return f'<svg viewBox="0 0 120 120" aria-hidden="true">{"".join(hexes)}</svg>'


FAILURE_ART = {
    "corruption": corruption_svg,
    "bureaucracy": bureaucracy_svg,
    "resources": resources_svg,
    "wars": wars_svg,
}

WAR_SPREAD_KEYFRAMES = "\n".join(
    f"    @keyframes wf-spread-{d} {{ 0%, {8 + d * 15}% {{ fill: {ART_FILL}; }} "
    f"{14 + d * 15}%, 86% {{ fill: {ART_DARK}; }} 100% {{ fill: {ART_FILL}; }} }}\n"
    f"    .wf-hex.wf-d{d} {{ animation: wf-spread-{d} 8s ease-in-out infinite; }}"
    for d in range(5)
)

# Window i of the bureaucracy pile drops in at its own moment; then they all clear at once.
BUREAUCRACY_KEYFRAMES = "\n".join(
    f"    @keyframes wf-pile-{i} {{ 0%, {4 + i * 14}% {{ opacity: 0; transform: translate(-4px, -4px); }} "
    f"{9 + i * 14}%, 86% {{ opacity: 1; transform: none; }} 94%, 100% {{ opacity: 0; transform: none; }} }}\n"
    f"    .wf-pile.wf-p{i} {{ animation: wf-pile-{i} 7s ease-out infinite; }}"
    for i in range(1, 5)
)

GLOBE_SCRIPTS = (
    "assets/d3-array.min.js",
    "assets/d3-geo.min.js",
    "assets/land-50m.js",
    "assets/realms.js",
)

LANG_ICON_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9'
    'M12 3c-2.5 2.6-3.8 5.6-3.8 9s1.3 6.4 3.8 9"/></svg>'
)

# Picks the language the way the portal does (src/lib/i18n/index.ts) and shares its stored choice.
I18N_JS = """
(function () {
  const { strings, titles } = window.DECK_I18N;
  const select = document.getElementById('lang');
  const KEY = 'registryPreferredLocale';
  const ids = Object.keys(strings);

  function preferred() {
    const fromUrl = new URLSearchParams(location.search).get('locale');
    if (ids.includes(fromUrl)) return fromUrl;
    try {
      const stored = localStorage.getItem(KEY);
      if (ids.includes(stored)) return stored;
    } catch (e) {}
    for (const l of navigator.languages || [navigator.language]) {
      if (ids.includes(l)) return l;
      const code = l.split('-')[0];
      if (code === 'zh') return 'zh-CN';
      if (ids.includes(code)) return code;
    }
    return 'en';
  }

  function apply(lang) {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      el.innerHTML = strings[lang][parseInt(el.dataset.i18n, 10)];
    });
    document.documentElement.lang = lang;
    document.title = titles[lang];
    select.value = lang;
  }

  apply(preferred());
  select.addEventListener('change', () => {
    const lang = select.value;
    try { localStorage.setItem(KEY, lang); } catch (e) {}
    const url = new URL(location.href);
    if (url.searchParams.has('locale')) {
      url.searchParams.set('locale', lang);
      history.replaceState(null, '', url);
    }
    apply(lang);
    window.dispatchEvent(new Event('resize'));
  });
})();
"""

# Pages and fragments: elements with data-frag="N" appear at step N of their page, and
# data-until="N" ones leave at step N. Click, →, ↓ or space advances; ←, ↑ goes back.
DECK_JS = """
(function () {
  const pages = Array.from(document.querySelectorAll('.page'));
  const dotsEl = document.getElementById('dots');
  const sceneMap = [];
  const pageStart = [];
  let sceneIndex = 0;

  pages.forEach((page, pageIdx) => {
    const frags = Array.from(page.querySelectorAll('[data-frag]'), (f) => parseInt(f.dataset.frag, 10));
    const steps = Math.max(parseInt(page.dataset.steps || '1', 10), 1 + Math.max(0, ...frags));
    pageStart.push(sceneMap.length);
    for (let s = 0; s < steps; s++) sceneMap.push({ pageIdx, stepIdx: s });
  });

  function renderDots(activePage) {
    if (!dotsEl) return;
    dotsEl.innerHTML = '';
    pages.forEach((_, i) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'dot' + (i === activePage ? ' active' : '');
      btn.setAttribute('aria-label', 'Slide ' + (i + 1));
      btn.addEventListener('click', () => window.__goToScene(pageStart[i] + 1));
      dotsEl.appendChild(btn);
    });
  }

  function applyScene(idx) {
    if (!sceneMap.length) return 0;
    sceneIndex = Math.max(0, Math.min(idx, sceneMap.length - 1));
    const { pageIdx, stepIdx } = sceneMap[sceneIndex];
    pages.forEach((page, pi) => {
      const active = pi === pageIdx;
      page.classList.toggle('active', active);
      const steps = page.querySelectorAll('.page-step');
      steps.forEach((step, si) => {
        step.classList.toggle('active', active && (steps.length === 1 || si === stepIdx));
      });
      page.querySelectorAll('[data-frag]').forEach((f) => {
        f.classList.toggle('shown', active && parseInt(f.dataset.frag, 10) <= stepIdx);
      });
      page.querySelectorAll('[data-until]').forEach((f) => {
        f.classList.toggle('shown', active && stepIdx < parseInt(f.dataset.until, 10));
      });
    });
    renderDots(pageIdx);
    window.dispatchEvent(new CustomEvent('deck:scene', { detail: { pageIdx, stepIdx } }));
    const hash = '#' + (sceneIndex + 1);
    if (location.hash !== hash) history.replaceState(null, '', hash);
    return sceneIndex + 1;
  }

  window.__goToScene = function (n) {
    const target = Math.max(1, Math.min(parseInt(n, 10) || 1, sceneMap.length));
    return applyScene(target - 1);
  };

  function sceneFromHash() {
    const m = /^#(\\d+)$/.exec(location.hash);
    return m ? parseInt(m[1], 10) : 1;
  }

  applyScene(sceneFromHash() - 1);
  window.addEventListener('hashchange', () => applyScene(sceneFromHash() - 1));

  window.addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('select')) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ' || e.key === 'PageDown') {
      e.preventDefault();
      window.__goToScene(sceneIndex + 2);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'PageUp') {
      e.preventDefault();
      window.__goToScene(sceneIndex);
    } else if (e.key === 'Home') {
      e.preventDefault();
      window.__goToScene(1);
    } else if (e.key === 'End') {
      e.preventDefault();
      window.__goToScene(sceneMap.length);
    }
  });

  document.addEventListener('click', (e) => {
    if (e.button !== 0 || e.target.closest('a, button, .dots, .lang')) return;
    if (String(window.getSelection())) return;
    window.__goToScene(sceneIndex + 2);
  });

  // Served by the portal (gos.earth, staging.gos.earth, demo.gos.earth, …): link back to that same portal.
  if (/^([a-z0-9-]+[.])?gos[.]earth$/.test(location.hostname)) {
    document.querySelectorAll('[data-home-link]').forEach((a) => {
      a.href = location.origin + '/';
      a.querySelector('.gos-link-url').textContent = location.hostname;
    });
  }

  let touch = null;
  document.addEventListener('touchstart', (e) => {
    touch = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
  }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (!touch) return;
    const dx = e.changedTouches[0].clientX - touch.x;
    const dy = e.changedTouches[0].clientY - touch.y;
    touch = null;
    if (Math.abs(dx) < 40 || Math.abs(dx) < 1.5 * Math.abs(dy)) return;
    window.__goToScene(dx < 0 ? sceneIndex + 2 : sceneIndex);
  });
})();
"""

# Portrait screens stack the world computer's picture over its text, and the text changes from
# click to click (and with the language). The picture gets the height the tallest text leaves, so
# it neither moves nor gets covered: each step is replayed on a hidden copy of the text to find it.
WCX_FIT_JS = """
(function () {
  const portrait = matchMedia('(max-aspect-ratio: 1/1)');

  function fit() {
    document.querySelectorAll('.wcx-slide').forEach((slide) => {
      if (!portrait.matches) { slide.style.removeProperty('--wcx-art-h'); return; }
      const wcx = slide.querySelector('.wcx');
      const inner = slide.querySelector('.wcx-inner');
      const ghost = inner.cloneNode(false);
      ghost.appendChild(inner.querySelector('.wcx-labels').cloneNode(true));
      ghost.setAttribute('aria-hidden', 'true');
      ghost.style.cssText = `position:absolute;left:0;top:0;width:${inner.clientWidth}px;visibility:hidden;pointer-events:none`;
      wcx.appendChild(ghost);
      const els = [ghost, ...ghost.querySelectorAll('[data-frag], [data-until]')];
      const frags = Array.from(slide.closest('.page').querySelectorAll('[data-frag]'), (f) => parseInt(f.dataset.frag, 10));
      const labels = ghost.lastChild;
      let text = 0;
      for (let s = 0; s <= Math.max(0, ...frags); s++) {
        els.forEach((e) => {
          const from = e.dataset.frag === undefined || parseInt(e.dataset.frag, 10) <= s;
          const until = e.dataset.until === undefined || s < parseInt(e.dataset.until, 10);
          e.classList.toggle('shown', from && until);
        });
        text = Math.max(text, labels.offsetHeight);
      }
      ghost.remove();
      const gap = parseFloat(getComputedStyle(inner).rowGap) || 0;
      slide.style.setProperty('--wcx-art-h', Math.max(120, wcx.clientHeight - text - gap - 8) + 'px');
    });
  }

  fit();
  window.addEventListener('resize', fit);
  if (document.fonts) document.fonts.ready.then(() => window.dispatchEvent(new Event('resize')));
})();
"""

GLOBE_JS = """
(function () {
  const viewport = document.getElementById('viewport');
  if (!viewport || !window.d3 || !window.WORLD_LAND) return;
  const canvas = document.createElement('canvas');
  canvas.className = 'globe-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  viewport.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DEG_PER_SECOND = 2;
  // The spin starts over from Europe each time the realms come in; spinFrom (how far it was from
  // there) eases away, so a restart in sight never jumps.
  let spinAt = performance.now();
  let spinFrom = 0;
  const MOVE_MS = 1800;
  const MOVE = `transform ${MOVE_MS}ms cubic-bezier(0.65, 0, 0.35, 1), opacity 0.6s ease`;
  const projection = d3.geoOrthographic().clipAngle(90).precision(0.6);
  const path = d3.geoPath(projection, ctx);
  const sphere = { type: 'Sphere' };
  let size = 0;
  let scale = 1;

  const DATA = window.GOS_REALMS || { realms: [], links: [], grid: [] };
  // Nodes: every realm, then the half each splitting realm sheds (present only while split).
  const BASE = DATA.realms.length;
  const SPLITS = DATA.realms.map((r, i) => i).filter((i) => DATA.realms[i].split);
  const LINKS = DATA.links.concat(SPLITS.map((i, s) => [i, BASE + s]));
  const pos = DATA.realms.map((r) => r.center).concat(SPLITS.map((i) => DATA.realms[i].split.centers[1]));
  const presence = pos.map(() => 1);
  const TEAL = '107, 163, 163';
  const TEAL_DARK = '47, 95, 95';
  const glowStart = pos.map(() => -1e9);
  const GROW = { period: 42000, ringEvery: 6000, fadeIn: 1200, flash: 1600, shrinkAt: 35500, shrink: 2500 };
  const SPLIT = { period: 48000, at: 5000, mergeAt: 38000, take: 2200 };
  let layerStart = 0;
  let nextGlow = 0;
  const gridByRing = {};
  DATA.grid.forEach((c) => (gridByRing[c.ring] = gridByRing[c.ring] || []).push(c.polygon));
  let layer = null;
  let layerAlpha = 0;
  let layerTarget = 0;
  let layerTimer = 0;
  const travelers = [];
  let nextMessage = 0;
  let nextPerson = 0;
  const logo = new Image();
  logo.src = 'assets/logo_sphere_only.svg';

  // A slot with data-frag / data-until holds the globe only at the steps it is shown.
  const activeSlot = () => Array.from(document.querySelectorAll('.page.active [data-globe-slot]')).find(
    (s) => !('frag' in s.dataset || 'until' in s.dataset) || s.classList.contains('shown')
  );

  let lastSlot = null;
  function place(animate) {
    const slot = activeSlot();
    const from = lastSlot;
    lastSlot = slot;
    canvas.style.transition = animate && !still ? MOVE : 'opacity 0.6s ease';
    clearTimeout(layerTimer);
    const handoff = placePlanet(animate && !still, from, slot);
    // The globe waits, unseen, where the planet is shrinking into.
    if (handoff) canvas.style.transition = 'none';
    const wanted = slot && slot.dataset.globeLayer;
    if (wanted !== layer) layerTarget = 0;
    if (wanted && (wanted !== layer || layerAlpha < 0.01) && !still) {
      const now = performance.now();
      spinFrom = ((((globeLam(now) + 15) % 360) + 540) % 360) - 180;
      spinAt = now;
    }
    if (wanted) {
      layerTimer = setTimeout(() => {
        if (layer !== wanted || layerAlpha < 0.01) layerStart = performance.now();
        layer = wanted;
        layerTarget = 1;
      }, handoff ? GLIDE_MS : animate && !still ? MOVE_MS * 0.8 : 0);
    }
    if (!slot) { canvas.style.opacity = '0'; return; }
    const r = slot.getBoundingClientRect();
    const v = viewport.getBoundingClientRect();
    scale = r.width / size;
    canvas.style.transform = `translate(${r.left - v.left}px, ${r.top - v.top}px) scale(${scale})`;
    // Gliding back out of the planet: the globe shows up only once the planet has shrunk into it.
    canvas.style.opacity = handoff ? '0' : '1';
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const slots = document.querySelectorAll('[data-globe-slot]');
    size = Math.max(...Array.from(slots, (s) => s.getBoundingClientRect().width));
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    canvas.style.width = canvas.style.height = size + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    projection.translate([size / 2, size / 2]).scale(size / 2 - 1);
  }

  const cellPath = (polygon) => path({ type: 'Polygon', coordinates: [polygon] });
  const linePath = (a, b) => path({ type: 'LineString', coordinates: [a, b] });

  function envelope(x, y, k) {
    const w = 9 * k, h = 6.5 * k;
    ctx.fillStyle = '#fff';
    ctx.strokeStyle = '#404040';
    ctx.lineWidth = 1.3 * k;
    ctx.beginPath(); ctx.rect(x - w / 2, y - h / 2, w, h); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x - w / 2, y - h / 2); ctx.lineTo(x, y + h * 0.1); ctx.lineTo(x + w / 2, y - h / 2); ctx.stroke();
  }

  function person(x, y, k) {
    ctx.fillStyle = '#262626';
    ctx.beginPath(); ctx.arc(x, y - 4.5 * k, 2.8 * k, 0, 2 * Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(x, y + 4.5 * k, 5 * k, Math.PI, 2 * Math.PI); ctx.fill();
  }

  // Devils: where no GOS runs yet, power stays captured. At first only one realm runs a GOS and a
  // devil sits where each other realm will be; one by one they turn into realms (those facing us
  // first), until only the strays are left.
  const DEVILS = __DEVILS__;
  const devil = new Image();
  devil.src = DEVILS.sprite;
  const CONVERT = { first: 1800, last: 15000, take: 1600, firstRealm: 0 };
  const born = DATA.realms.map(() => -1e9);
  let bornFor = null;
  function scheduleBirths() {
    bornFor = layerStart;
    const left = DATA.realms.map((r, i) => i).filter((i) => i !== CONVERT.firstRealm);
    left.slice().forEach((_, j, all) => {
      const t = CONVERT.first + ((CONVERT.last - CONVERT.first) * j) / Math.max(1, all.length - 1);
      const center = [-globeLam(layerStart + t), 22];
      const best = left.reduce((a, b) => (d3.geoDistance(DATA.realms[b].center, center) < d3.geoDistance(DATA.realms[a].center, center) ? b : a));
      left.splice(left.indexOf(best), 1);
      born[best] = t;
    });
  }
  // How far realm i is into its birth: below 0 it is still a devil, from 1 on it is a realm.
  const age = (i, now) => (still ? 1e9 : now - layerStart - born[i]);
  const birth = (i, now) => clamp01(age(i, now) / CONVERT.take);

  function drawDevils(now, k, facing) {
    if (!devil.complete || !devil.naturalWidth) return;
    const h = 28 * k, w = h * devil.naturalWidth / devil.naturalHeight;
    const spots = DEVILS.spots.map((p) => [p, 0]).concat(
      DATA.realms.map((r, i) => [r.center, age(i, now) / CONVERT.take]).filter(([, b]) => b < 1)
    );
    // They turn away with the globe: kept inside its outline, and fading towards the edge.
    ctx.save();
    ctx.beginPath(); path(sphere); ctx.clip();
    spots.forEach(([p, b], i) => {
      const c = facing(p);
      if (c < 0.15) return;
      const [x, y] = projection(p);
      const edge = Math.min(1, (c - 0.15) * 4);
      // Converting: a teal ring bursts out while the devil swells and fades.
      const gone = clamp01(b * 1.8);
      if (b > 0) {
        ctx.globalAlpha = layerAlpha * edge * (1 - b);
        ctx.strokeStyle = `rgb(${TEAL})`;
        ctx.lineWidth = 2.5 * k * (1 - b);
        ctx.beginPath(); ctx.arc(x, y, (8 + 34 * ease(b)) * k, 0, 2 * Math.PI); ctx.stroke();
      }
      if (gone >= 1) return;
      const bob = still ? 0 : Math.sin(now / 700 + i * 1.9) * 1.5 * k;
      const s = 1 + 0.35 * gone;
      ctx.globalAlpha = layerAlpha * edge * (1 - gone);
      ctx.drawImage(devil, x - (w * s) / 2, y - h * s * 0.62 + bob, w * s, h * s);
    });
    ctx.restore();
    ctx.globalAlpha = layerAlpha;
  }

  function badge(x, y, k, gos, glowing) {
    const r = 14 * k;
    ctx.save();
    ctx.shadowColor = glowing ? `rgba(${TEAL}, 0.9)` : 'rgba(0, 0, 0, 0.18)';
    ctx.shadowBlur = (glowing ? 12 : 5) * k * (window.devicePixelRatio || 1);
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = gos === 'realms' ? '#fff' : '#f3f3f3';
    ctx.fill();
    ctx.restore();
    ctx.lineWidth = 1.2 * k;
    ctx.strokeStyle = glowing ? `rgb(${TEAL_DARK})` : 'rgba(38, 38, 38, 0.55)';
    if (gos === 'realms') {
      ctx.stroke();
      if (logo.complete && logo.naturalWidth) {
        const h = 1.6 * r, w = h * logo.naturalWidth / logo.naturalHeight;
        ctx.drawImage(logo, x - w / 2, y - h / 2, w, h);
      }
    } else {
      ctx.setLineDash([2.4 * k, 2 * k]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(64, 64, 64, 0.7)';
      ctx.font = `700 ${15 * k}px system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('?', x, y + 0.5 * k);
    }
  }

  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const ease = (x) => { const t = clamp01(x); return t * t * (3 - 2 * t); };

  // Time into realm i's loop, which starts a little after the realm is born.
  function cycle(i, period, now) {
    const t = still ? 0 : age(i, now) - 2500 - (born[i] < 0 ? (i * 3700) % 15000 : 0);
    return t <= 0 ? 0 : t % period;
  }

  // Per cell: opacity and a teal flash (cells appearing as the realm grows, or the seam
  // emptying when it splits); which tree edges show; how far apart a split realm is.
  function realmState(realm, i, now) {
    const alpha = realm.cells.map(() => 1);
    const flash = realm.cells.map(() => 0);
    let edges = realm.edges;
    let split = 0;
    if (realm.grow !== undefined) {
      const u = cycle(i, GROW.period, now);
      const out = clamp01((GROW.shrinkAt + GROW.shrink - u) / GROW.shrink);
      const since = (ring) => u - (ring - realm.grow - 1) * GROW.ringEvery;
      realm.cells.forEach((c, j) => {
        if (c.ring <= realm.grow) return;
        const t = since(c.ring) - (j % 5) * 250;
        alpha[j] = Math.min(clamp01(t / GROW.fadeIn), out);
        if (t > 0 && t < GROW.flash) flash[j] = Math.sin((Math.PI * t) / GROW.flash) * out;
      });
      edges = realm.edges.filter((e) => e[2] <= realm.grow || (since(e[2]) > GROW.fadeIn && out > 0.5));
    }
    if (realm.split) {
      const u = cycle(i, SPLIT.period, now);
      split = ease((u - SPLIT.at) / SPLIT.take) * (1 - ease((u - SPLIT.mergeAt) / SPLIT.take));
      realm.cells.forEach((c, j) => {
        if (c.side !== -1) return;
        alpha[j] = 1 - split;
        flash[j] = Math.sin(Math.PI * split);
      });
    }
    // Being born: the cells come in ring by ring from the centre, each with a teal flash.
    const a = age(i, now);
    if (a < CONVERT.take + 2000) {
      realm.cells.forEach((c, j) => {
        const t = a - 250 - c.ring * 320 - (j % 4) * 60;
        alpha[j] *= clamp01(t / 450);
        if (t > 0 && t < 1100) flash[j] = Math.max(flash[j], Math.sin((Math.PI * t) / 1100) * alpha[j]);
      });
    }
    return { alpha, flash, edges, split };
  }

  function spawn(now) {
    const open = LINKS.filter(([a, b]) => presence[a] > 0.95 && presence[b] > 0.95);
    if (!open.length) return;
    if (now > nextMessage) {
      const [a, b] = open[Math.floor(Math.random() * open.length)];
      const flip = Math.random() < 0.5;
      travelers.push({ from: flip ? b : a, to: flip ? a : b, t0: now, dur: 2600 + Math.random() * 1800, kind: 'message' });
      nextMessage = now + 280 + Math.random() * 360;
    }
    if (now > nextPerson) {
      const [a, b] = open[Math.floor(Math.random() * open.length)];
      const flip = Math.random() < 0.5;
      travelers.push({ from: flip ? b : a, to: flip ? a : b, t0: now, dur: 6500 + Math.random() * 2500, kind: 'person' });
      nextPerson = now + 1600 + Math.random() * 1400;
    }
  }

  function drawRealms(now) {
    // Badges keep their on-screen size, shrinking only on globes smaller than 480px (phones).
    const k = Math.min(1, (size * scale) / 480) / scale;
    const dpr = window.devicePixelRatio || 1;
    const rot = projection.rotate();
    const center = [-rot[0], -rot[1]];
    const facing = (p) => Math.cos(d3.geoDistance(p, center));
    if (bornFor !== layerStart) scheduleBirths();
    DATA.realms.forEach((r, i) => (presence[i] = ease(birth(i, now))));
    const states = DATA.realms.map((realm, i) => realmState(realm, i, now));
    SPLITS.forEach((i, s) => {
      const { split } = states[i];
      pos[i] = d3.geoInterpolate(DATA.realms[i].center, DATA.realms[i].split.centers[0])(split);
      presence[BASE + s] = split * presence[i];
    });
    ctx.save();
    ctx.globalAlpha = layerAlpha;

    ctx.lineWidth = 0.8 * k;
    Object.keys(gridByRing).forEach((ring) => {
      ctx.strokeStyle = `rgba(64, 64, 64, ${Math.max(0.03, 0.2 - ring * 0.035)})`;
      ctx.beginPath();
      gridByRing[ring].forEach(cellPath);
      ctx.stroke();
    });

    ctx.setLineDash([4 * k, 5 * k]);
    ctx.lineWidth = 1.2 * k;
    ctx.strokeStyle = 'rgba(82, 82, 82, 0.4)';
    LINKS.forEach(([a, b]) => {
      const shown = Math.min(presence[a], presence[b]);
      if (shown < 0.01) return;
      ctx.globalAlpha = layerAlpha * shown;
      ctx.beginPath();
      linePath(pos[a], pos[b]);
      ctx.stroke();
    });
    ctx.setLineDash([]);
    ctx.globalAlpha = layerAlpha;

    const pulses = (edges, seed) => {
      for (let q = 0; q < 2 && edges.length; q++) {
        const phase = now / 650 + seed * 1.7 + q * 3.1;
        const [a, b] = edges[Math.floor(phase) % edges.length];
        const p = d3.geoInterpolate(a, b)(phase % 1);
        if (facing(p) < 0.05) continue;
        const [x, y] = projection(p);
        ctx.beginPath(); ctx.arc(x, y, 1.6 * k, 0, 2 * Math.PI); ctx.fill();
      }
    };
    const treeLines = (edges, alpha) => {
      if (alpha < 0.01) return;
      ctx.globalAlpha = layerAlpha * alpha;
      ctx.beginPath();
      edges.forEach(([a, b]) => linePath(a, b));
      ctx.stroke();
    };

    const glowingNodes = new Set();
    DATA.realms.forEach((realm, i) => {
      if (facing(realm.center) < -0.3) return;
      const { alpha, flash, edges, split } = states[i];
      const half = realm.split ? BASE + SPLITS.indexOf(i) : -1;
      const fillCell = (c) => {
        ctx.beginPath();
        cellPath(c.polygon);
        ctx.fill();
        ctx.stroke();
      };
      ctx.fillStyle = 'rgba(64, 64, 64, 0.16)';
      ctx.lineWidth = 0.9 * k;
      ctx.strokeStyle = 'rgba(38, 38, 38, 0.45)';
      ctx.beginPath();
      realm.cells.forEach((c, j) => { if (alpha[j] >= 0.999) cellPath(c.polygon); });
      ctx.fill();
      ctx.stroke();
      realm.cells.forEach((c, j) => {
        if (alpha[j] >= 0.999 || alpha[j] < 0.01) return;
        ctx.globalAlpha = layerAlpha * alpha[j];
        fillCell(c);
      });
      ctx.globalAlpha = layerAlpha;

      realm.cells.forEach((c, j) => {
        const node = half >= 0 && split > 0.5 && c.side === 1 ? half : i;
        const f = (now - glowStart[node] - c.ring * 150) / 1500;
        const wave = f > 0 && f < 1 ? Math.sin(Math.PI * f) * alpha[j] : 0;
        if (wave > 0.01) glowingNodes.add(node);
        const g = Math.max(wave, flash[j]);
        if (g < 0.01) return;
        ctx.save();
        ctx.shadowColor = `rgba(${TEAL}, ${0.95 * g})`;
        ctx.shadowBlur = 14 * g * dpr;
        ctx.fillStyle = `rgba(${TEAL}, ${0.6 * g})`;
        ctx.lineWidth = 1.3 * k;
        ctx.strokeStyle = `rgba(${TEAL_DARK}, ${0.9 * g})`;
        fillCell(c);
        ctx.restore();
      });

      if (facing(realm.center) < 0.05 || presence[i] < 0.01) return;
      ctx.lineWidth = 0.8 * k;
      ctx.strokeStyle = 'rgba(38, 38, 38, 0.4)';
      if (realm.split) {
        treeLines(realm.edges, (1 - split) * presence[i]);
        realm.split.edges.forEach((e) => treeLines(e, split * presence[i]));
      } else {
        treeLines(edges, presence[i]);
      }
      ctx.globalAlpha = layerAlpha;
      if (presence[i] < 0.95) return;
      ctx.fillStyle = glowingNodes.has(i) ? `rgb(${TEAL_DARK})` : '#262626';
      if (realm.split && split > 0.5) {
        pulses(realm.split.edges[0], i);
        pulses(realm.split.edges[1], i + 0.5);
      } else {
        pulses(edges, i);
      }
    });

    drawDevils(now, k, facing);

    pos.forEach((p, n) => {
      const c = facing(p);
      if (c < 0.05 || presence[n] < 0.01) return;
      const [x, y] = projection(p);
      const gos = n < BASE ? DATA.realms[n].gos : DATA.realms[SPLITS[n - BASE]].split.gos;
      ctx.globalAlpha = layerAlpha * presence[n] * Math.min(1, (c - 0.05) * 5);
      badge(x, y, k * (0.6 + 0.4 * presence[n]), gos, glowingNodes.has(n));
    });
    ctx.globalAlpha = layerAlpha;

    for (let j = travelers.length - 1; j >= 0; j--) {
      const t = travelers[j];
      const f = (now - t.t0) / t.dur;
      if (f >= 1) {
        if (t.kind === 'person') glowStart[t.to] = now;
        travelers.splice(j, 1);
        continue;
      }
      const eased = f < 0.5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
      const p = d3.geoInterpolate(pos[t.from], pos[t.to])(eased);
      const c = facing(p);
      if (c < 0.05) continue;
      const [x, y] = projection(p);
      const shown = Math.min(presence[t.from], presence[t.to]);
      ctx.globalAlpha = layerAlpha * shown * Math.min(1, c * 4, f * 8, (1 - f) * 8);
      if (t.kind === 'person') person(x, y, k); else envelope(x, y, k);
    }
    ctx.restore();

    if (now > nextGlow) {
      const candidates = pos.map((p, n) => n).filter((n) => presence[n] > 0.95 && facing(pos[n]) > 0.3);
      if (candidates.length) glowStart[candidates[Math.floor(Math.random() * candidates.length)]] = now;
      nextGlow = now + 1400 + Math.random() * 2000;
    }
  }

  function draw(now) {
    projection.rotate([globeLam(now), -22]);
    ctx.clearRect(0, 0, size, size);
    ctx.beginPath(); path(sphere); ctx.fillStyle = '#e9e9e9'; ctx.fill();
    ctx.beginPath(); path(window.WORLD_LAND); ctx.fillStyle = '#f9f9f9'; ctx.fill();
    const dt = Math.min(now - lastFrame, 100);
    lastFrame = now;
    const stepAlpha = still ? 1 : dt / LAYER_FADE_MS;
    layerAlpha = layerTarget > layerAlpha ? Math.min(layerTarget, layerAlpha + stepAlpha) : Math.max(layerTarget, layerAlpha - stepAlpha);
    if (layerAlpha < 0.01 && layerTarget === 0) { layer = null; travelers.length = 0; return; }
    if (layer === 'realms') {
      if (!still) spawn(now);
      drawRealms(now);
    }
  }

  // The planet: when the world-computer slide's first layer shows, the globe glides down and
  // swells until only its top is left, a curved horizon across the bottom of the window.
  // Its surface turns into ones and zeros, anchored to the ground (see .wcx-planet).
  const planet = document.createElement('canvas');
  planet.className = 'planet-canvas';
  planet.setAttribute('aria-hidden', 'true');
  viewport.prepend(planet);
  const pctx = planet.getContext('2d');
  const pproj = d3.geoOrthographic().clipAngle(90).precision(0.6);
  const ppath = d3.geoPath(pproj, pctx);
  const portrait = matchMedia('(max-aspect-ratio: 1/1)');
  const GLIDE_MS = 2600;
  const SURFACE = 246; // gray level of the planet's plain digital surface
  const PLANET_FADE = 'opacity 0.45s ease';
  const RAD = Math.PI / 180;
  let marker = null; // the .wcx-planet the planet is drawn for, null when off
  let glide = null; // { from, back, t0 }
  let glyphFrom = 0;
  let glyphStart = 0;
  let planetDrawn = 0;
  let planetG = null;
  let planetW = 0;
  let planetH = 0;

  const globeLam = (now) => {
    if (still) return -15;
    const s = Math.max(0, now - spinAt);
    return -15 + (s / 1000) * DEG_PER_SECOND + spinFrom * (1 - ease(s / 1500));
  };
  // Where the globe canvas is right now, even halfway through a CSS move.
  function globeGeom(now) {
    const m = new DOMMatrix(getComputedStyle(canvas).transform);
    const v = viewport.getBoundingClientRect();
    const r = m.a * (size / 2 - 1);
    return { x: v.left + m.e + (m.a * size) / 2, h: v.top + m.f + (m.a * size) / 2 - r, r, lam: globeLam(now), phi: -22 };
  }
  function groundGeom(el) {
    const b = el.parentElement.querySelector('svg').getBoundingClientRect();
    const k = b.width / 1120;
    const [x, h, r, lam, phi] = el.dataset.planet.split(' ').map(Number);
    return { x: b.left + x * k, h: b.top + h * k, r: r * k, lam, phi, k };
  }
  const glideEase = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  function mix(a, b, t) {
    const dl = ((((b.lam - a.lam) % 360) + 540) % 360) - 180;
    return {
      x: a.x + (b.x - a.x) * t,
      h: a.h + (b.h - a.h) * t,
      r: Math.exp(Math.log(a.r) + (Math.log(b.r) - Math.log(a.r)) * t),
      lam: a.lam + dl * t,
      phi: a.phi + (b.phi - a.phi) * t,
      k: b.k || a.k,
    };
  }

  function setLanding(on) {
    const slide = marker && marker.closest('.wcx-slide');
    if (slide) slide.classList.toggle('wcx-landing', on);
  }

  // Called by place(); returns true when the globe must stay hidden while the planet shrinks into it.
  function placePlanet(animate, fromSlot, slot) {
    const el = document.querySelector('.page.active .wcx-planet.shown');
    if (el) {
      if (marker === el && !(glide && glide.back)) return false;
      const wasOn = marker === el;
      // From a globe, on this slide or another, it glides down into the planet.
      const glideIn = animate && (wasOn || !!fromSlot);
      // Before anything reads styles: the ground's transitions must start with the landing delay.
      el.closest('.wcx-slide').classList.toggle('wcx-landing', glideIn);
      const live = glide ? currentGeom(performance.now()) : null;
      marker = el;
      if (glideIn) {
        // Glide down from wherever the globe (or a half-way planet) is right now.
        glide = { from: live || globeGeom(performance.now()), back: false, t0: performance.now() };
        planet.style.transition = 'none';
        planet.style.opacity = '1';
        drawPlanet(performance.now(), true);
        canvas.style.transition = 'none';
        if (!wasOn) glyphStart = performance.now() + 200;
      } else {
        glide = null;
        planet.style.transition = PLANET_FADE;
        planet.style.opacity = '1';
        glyphStart = performance.now() - 1e4;
        drawPlanet(performance.now(), true);
      }
      return false;
    }
    if (!marker) return false;
    // Back to a globe, on this slide or the next: the planet rises and shrinks into it.
    if (animate && slot) {
      const from = planetG || currentGeom(performance.now());
      glide = { from, back: true, t0: performance.now() };
      setLanding(false);
      return true;
    }
    setLanding(false);
    planet.style.transition = PLANET_FADE;
    planet.style.opacity = '0';
    marker = null;
    glide = null;
    return false;
  }

  function currentGeom(now) {
    const to = glide && glide.back ? globeGeom(now) : groundGeom(marker);
    if (!glide) return to;
    return mix(glide.from, to, glideEase(Math.min(1, (now - glide.t0) / GLIDE_MS)));
  }

  function resizePlanet() {
    const dpr = window.devicePixelRatio || 1;
    planetW = innerWidth;
    planetH = innerHeight;
    planet.width = Math.round(planetW * dpr);
    planet.height = Math.round(planetH * dpr);
    planetDrawn = 0;
  }

  // Ones and zeros sit on a lat/lon grid of 4096 steps around. Grid points have levels (how
  // often their index halves); only levels coarse enough to stay readable are drawn, and the
  // finest one fades in or out as the planet zooms.
  const STEPS = 4096;
  const STEP = 360 / STEPS;
  const level = (i, max) => (i === 0 ? max : Math.min(max, 31 - Math.clz32(i & -i)));
  const hash = (i, j) => {
    let h = Math.imul(i, 374761393) ^ Math.imul(j, 668265263);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  };
  const sprites = {};
  function sprite(key, red) {
    const id = key + (red ? 'r' : '');
    if (!sprites[id]) {
      const c = document.createElement('canvas');
      c.width = c.height = 64;
      const g = c.getContext('2d');
      g.font = '700 46px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillStyle = red ? DECAY.glyph : '#8f8f8f';
      g.fillText(key, 32, 34);
      sprites[id] = c;
    }
    return sprites[id];
  }

  // The hack's damage reaches the land (the .wcx-sick-hardware step): the red spreads out from
  // under the stack as fast as the CSS turns the land's things red, and mending fades it.
  const DECAY = __DECAY__;
  let decayAt = null; // when the red started spreading; null while the land is fine
  let healAt = null; // when it started being mended
  let decayFor = null; // the planet marker this state belongs to
  function decayState(now) {
    const on = !!marker.closest('.wcx-inner').querySelector('.wcx-sick-hardware.shown > .shown');
    if (decayFor !== marker) {
      decayFor = marker;
      decayAt = on ? -1e9 : null;
      healAt = null;
    } else if (on && (decayAt === null || healAt !== null)) {
      decayAt = still ? -1e9 : now;
      healAt = null;
    } else if (!on && decayAt !== null && healAt === null) {
      healAt = still ? -1e9 : now;
    }
    if (healAt !== null && now - healAt > DECAY.heal + DECAY.fade) decayAt = healAt = null;
    if (decayAt === null) return null;
    const keep = healAt === null ? 1 : 1 - Math.min(1, Math.max(0, (now - healAt - DECAY.heal) / DECAY.fade));
    const spread = (now - decayAt) / 1000 - 0.2;
    return { keep, spread, busy: healAt !== null || spread < 4.5 };
  }
  // How red the land is at box distance d from under the stack (y counts double, as in ground_svg).
  const decayAtDist = (dec, d) => dec.keep * Math.min(1, Math.max(0, (dec.spread - d / DECAY.speed) / 0.8));

  function drawGlyphs(g, clip, alpha, now, dec) {
    const { x: cx, r } = g;
    const cy = g.h + r;
    const dy0 = g.h + DECAY.center * (g.k || 1);
    const lam0 = -g.lam, phi0 = -g.phi;
    const sp0 = Math.sin(phi0 * RAD), cp0 = Math.cos(phi0 * RAD);
    const k = g.k || 1;
    const minPx = Math.min(0.05 * r, 18 * Math.max(0.6, k));
    // The spacing is judged where the eye is: the middle of a globe, the ground under the stack.
    const ry = Math.min(cy, g.h + 100 * k);
    const ref = pproj.invert([cx, ry]);
    if (!ref) return;
    const pxPerDeg = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
    const p0 = pproj(ref);
    const dLat = pxPerDeg(p0, pproj([ref[0], ref[1] + 0.5])) * 2;
    const dLon = pxPerDeg(p0, pproj([ref[0] + 0.5, ref[1]])) * 2 / Math.max(0.05, Math.cos(ref[1] * RAD));
    if (!(dLat > 0 && dLon > 0)) return;
    const Llat = Math.max(0, Math.log2(minPx / (STEP * dLat)));
    const Llon0 = Math.log2(minPx / (STEP * dLon));

    // Which lat/lon range can show up inside the clip at all.
    let latMin = 90, latMax = -90, lonMin = 180, lonMax = -180;
    const take = (sx, sy) => {
      if (Math.hypot(sx - cx, sy - cy) > r) return;
      const q = pproj.invert([sx, sy]);
      if (!q) return;
      const dl = ((((q[0] - lam0) % 360) + 540) % 360) - 180;
      latMin = Math.min(latMin, q[1]); latMax = Math.max(latMax, q[1]);
      lonMin = Math.min(lonMin, dl); lonMax = Math.max(lonMax, dl);
    };
    for (let a = 0; a <= 16; a++) for (let b = 0; b <= 10; b++) {
      take(clip.x + (clip.w * a) / 16, clip.y + (clip.h * b) / 10);
    }
    for (let a = 0; a < 128; a++) {
      const t = (a / 128) * 2 * Math.PI;
      const sx = cx + (r - 0.5) * Math.cos(t), sy = cy + (r - 0.5) * Math.sin(t);
      if (sx >= clip.x && sx <= clip.x + clip.w && sy >= clip.y && sy <= clip.y + clip.h) take(sx, sy);
    }
    if (latMin > latMax) return;
    const inClip = (p) => {
      const q = pproj(p);
      return q[0] >= clip.x && q[0] <= clip.x + clip.w && q[1] >= clip.y && q[1] <= clip.y + clip.h;
    };
    const north = Math.sin(90 * RAD) * sp0 > 0 && inClip([0, 90]);
    const south = -sp0 > 0 && inClip([0, -90]);
    const pad = 4 * STEP * Math.pow(2, Llat);
    latMin = south ? -90 : Math.max(-90, latMin - pad);
    latMax = north ? 90 : Math.min(90, latMax + pad);
    if (north || south) { lonMin = -180; lonMax = 180; }

    const tick = still ? 0 : now / 900;
    const dpr = window.devicePixelRatio || 1;
    const size0 = 0.72 * minPx;
    const latStep = 1 << Math.min(11, Math.floor(Llat));
    const iMin = Math.ceil((latMin + 90) / STEP / latStep) * latStep;
    const iMax = Math.floor((latMax + 90) / STEP);
    for (let i = iMin; i <= iMax; i += latStep) {
      const lat = -90 + i * STEP;
      const aLat = Math.min(1, Math.max(0, 3 * (level(i, 11) - Llat) + 1));
      if (aLat <= 0) continue;
      const cl = Math.cos(lat * RAD), sl = Math.sin(lat * RAD);
      if (cl < 1e-6) continue;
      const Llon = Math.max(0, Llon0 + Math.log2(1 / cl));
      if (Llon > 12) continue;
      const lonStep = 1 << Math.min(12, Math.floor(Llon));
      const lonPad = 2 * STEP * lonStep;
      const j0 = Math.floor((lam0 + lonMin - lonPad + 180) / STEP / lonStep) * lonStep;
      const j1 = Math.ceil((lam0 + lonMax + lonPad + 180) / STEP / lonStep) * lonStep;
      for (let jj = j0; jj <= j1 && jj - j0 < STEPS; jj += lonStep) {
        const j = ((jj % STEPS) + STEPS) % STEPS;
        const aLon = Math.min(1, Math.max(0, 3 * (level(j, 12) - Llon) + 1));
        if (aLon <= 0) continue;
        const lon = -180 + j * STEP;
        const dl = (lon - lam0) * RAD;
        const cdl = Math.cos(dl);
        const c = sp0 * sl + cp0 * cl * cdl;
        if (c < 0.02) continue;
        const sx = cx + r * cl * Math.sin(dl);
        const sy = cy - r * (cp0 * sl - sp0 * cl * cdl);
        if (sx < clip.x - size0 || sx > clip.x + clip.w + size0 || sy < clip.y - size0 || sy > clip.y + clip.h + size0) continue;
        const seed = hash(i, j);
        const bit = Math.floor(tick * (0.4 + seed) + 10 * seed) & 1;
        // Lying on the surface: squashed towards the planet's middle as it curves away (but
        // never so flat that it stops reading as a digit).
        let ux = sx - cx, uy = sy - cy;
        const len = Math.hypot(ux, uy) || 1;
        ux /= len; uy /= len;
        const f = 0.5 * (c - 1);
        const s = (size0 / 64) * dpr;
        pctx.setTransform(
          (1 + f * ux * ux) * s, f * ux * uy * s, f * ux * uy * s, (1 + f * uy * uy) * s,
          sx * dpr, sy * dpr
        );
        const edge = Math.min(1, (c - 0.02) / 0.08);
        const a = alpha * aLat * aLon * edge;
        const red = dec ? decayAtDist(dec, Math.hypot(sx - cx, 2 * (sy - dy0)) / k) : 0;
        if (red < 1) {
          pctx.globalAlpha = a * (1 - red);
          pctx.drawImage(sprite(bit ? '1' : '0'), -32, -32);
        }
        if (red > 0) {
          pctx.globalAlpha = a * red;
          pctx.drawImage(sprite(bit ? '1' : '0', true), -32, -32);
        }
      }
    }
    pctx.globalAlpha = 1;
  }

  function drawPlanet(now, force) {
    if (!marker) return;
    if (!marker.closest('.page.active') && !(glide && glide.back)) {
      marker = null;
      glide = null;
      planet.style.opacity = '0';
      return;
    }
    const moving = !!glide;
    const g = currentGeom(now);
    const dec = decayState(now);
    // The ground can also move under it (the picture moving right for the Governance Operating System).
    const shifted = !planetG || g.x !== planetG.x || g.h !== planetG.h || g.r !== planetG.r;
    if (!force && !moving && !shifted && !(dec && dec.busy) && now - planetDrawn < 100) return;
    planetDrawn = now;
    planetG = g;
    if (planetW !== innerWidth || planetH !== innerHeight) resizePlanet();
    const dpr = window.devicePixelRatio || 1;
    pctx.setTransform(1, 0, 0, 1, 0, 0);
    pctx.clearRect(0, 0, planet.width, planet.height);
    let clip = { x: 0, y: 0, w: planetW, h: planetH };
    if (portrait.matches) {
      // Below the picture are its labels, so the planet stays above them, until it rises away.
      const bottom = marker.closest('.wcx-crop').getBoundingClientRect().bottom;
      const t = glide && glide.back ? glideEase(Math.min(1, (now - glide.t0) / GLIDE_MS)) : 0;
      clip.h = bottom + (planetH - bottom) * t;
    }
    pctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    pctx.save();
    pctx.beginPath(); pctx.rect(clip.x, clip.y, clip.w, clip.h); pctx.clip();
    pproj.translate([g.x, g.h + g.r]).scale(g.r).rotate([g.lam, g.phi]).precision(moving ? 2 : 0.6)
      .clipExtent([[clip.x - 2, clip.y - 2], [clip.x + clip.w + 2, clip.y + clip.h + 2]]);
    // The map (the globe's own look) melts away into a plain surface while gliding down,
    // and comes back while gliding up, so the globe canvas can take over seamlessly.
    const t = glide ? Math.min(1, (now - glide.t0) / GLIDE_MS) : 1;
    const map = glide && glide.back ? Math.min(1, Math.max(0, (t - 0.35) / 0.55)) : glide ? 1 - Math.min(1, t / 0.6) : 0;
    const sea = Math.round(SURFACE + (233 - SURFACE) * map);
    pctx.beginPath(); ppath({ type: 'Sphere' }); pctx.fillStyle = `rgb(${sea}, ${sea}, ${sea})`; pctx.fill();
    if (dec) {
      const k = g.k || 1;
      const outer = Math.max(1, dec.spread * DECAY.speed * k);
      const inner = Math.max(0, (dec.spread - 0.8) * DECAY.speed * k);
      pctx.save();
      pctx.clip();
      pctx.translate(g.x, g.h + DECAY.center * k);
      pctx.scale(1, 0.5);
      const red = pctx.createRadialGradient(0, 0, 0, 0, 0, outer);
      red.addColorStop(0, `rgba(${DECAY.sea}, ${dec.keep})`);
      red.addColorStop(inner / outer, `rgba(${DECAY.sea}, ${dec.keep})`);
      red.addColorStop(1, `rgba(${DECAY.sea}, 0)`);
      pctx.fillStyle = red;
      pctx.fillRect(-1e5, -1e5, 2e5, 2e5);
      pctx.restore();
    }
    if (map > 0) {
      pctx.globalAlpha = map;
      pctx.beginPath(); ppath(window.WORLD_LAND); pctx.fillStyle = '#f9f9f9'; pctx.fill();
    }
    pctx.globalAlpha = 1 - map;
    pctx.beginPath(); pctx.arc(g.x, g.h + g.r, g.r, 0, 2 * Math.PI);
    pctx.strokeStyle = '#dcdcdc'; pctx.lineWidth = 1; pctx.stroke();
    pctx.globalAlpha = 1;
    const fade = glide && glide.back ? 1 - Math.min(1, (now - glide.t0) / (GLIDE_MS * 0.5)) : Math.min(1, (now - glyphStart) / 700);
    if (fade > 0) drawGlyphs(g, clip, fade, now, dec);
    pctx.restore();

    if (glide && now - glide.t0 >= GLIDE_MS) {
      const back = glide.back;
      glide = null;
      if (back) {
        // Hand the planet, shrunk back into a globe, over to the globe canvas.
        canvas.style.transition = 'none';
        canvas.style.opacity = '1';
        planet.style.transition = 'none';
        planet.style.opacity = '0';
        marker = null;
      } else {
        setLanding(false);
      }
    }
  }

  const LAYER_FADE_MS = 700;
  const t0 = performance.now();
  let lastFrame = t0;
  function frame(now) {
    draw(now);
    drawPlanet(now, false);
    requestAnimationFrame(frame);
  }

  resize();
  resizePlanet();
  place(false);
  requestAnimationFrame(frame);
  window.addEventListener('deck:scene', () => place(true));
  window.addEventListener('resize', () => { resize(); resizePlanet(); place(false); drawPlanet(performance.now(), true); });
})();
"""

# [lon, lat] on land, far from every realm (make-realms.cjs): devils that stay, where no GOS runs
# yet. GLOBE_JS also puts a devil on every realm but the first, until that realm is born.
GLOBE_DEVILS = [(10, 22), (45, 50), (-63, -10), (90, 62), (125, -24)]


def devil_sprite() -> str:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -26 24 27" width="96" height="108">{evil_svg()}</svg>'
    return "data:image/svg+xml," + urllib.parse.quote(svg)


GLOBE_JS = GLOBE_JS.replace(
    "__DEVILS__", json.dumps({"sprite": devil_sprite(), "spots": GLOBE_DEVILS})
).replace(
    "__DECAY__",
    json.dumps(
        {
            "sea": ", ".join(map(str, redden_rgb(246))),
            "glyph": "rgb({}, {}, {})".format(*redden_rgb(0x8F)),
            "speed": DECAY_SPEED,
            "center": round(iso(SIDE / 2, SIDE / 2, 0, WCX_LAYERS["hardware"][0])[1] - WCX_PLANET[1], 1),
            "heal": HEAL_DELAY * 1000,
            "fade": 1200,
        }
    ),
)


def ground_decay_css() -> str:
    """Once the damage reaches the land, every grey of its things turns red, spreading out from
    under the stack at DECAY_SPEED (their pop delay --d already grows with that distance).

    Each thing that sets a grey owns a --sick (0 to 1) that transitions, and its colour mixes
    from it: Chromium keeps restarting fill transitions while other things around animate."""
    on = ".wcx-inner:has(.wcx-sick-hardware.shown > .shown) .wcx-ground"
    rules = [
        "@property --sick { syntax: '<number>'; inherits: false; initial-value: 0; }",
        f".wcx-ground :is([fill], [stroke]) {{ transition: --sick 1.2s ease {HEAL_DELAY}s; }}",
        f"{on} :is([fill], [stroke]) {{ --sick: 1; transition: --sick 0.8s ease "
        f"calc((var(--d, 0.2s) - 0.2s) * {900 / DECAY_SPEED} + 0.2s); }}",
        f"{on} :is(.wcx-rotor, .wcx-car-x, .wcx-car-xr, .wcx-car-y) {{ animation-play-state: paused; }}",
    ]
    mixes = []
    for attr, color in sorted(set(re.findall(r'\b(fill|stroke)="(#[0-9a-f]{3}|#[0-9a-f]{6})"', ground_svg()))):
        hex6 = color[1:] if len(color) == 7 else "".join(c * 2 for c in color[1:])
        r, g, b = (int(hex6[i : i + 2], 16) for i in (0, 2, 4))
        if r == g == b and r:
            red = "rgb({}, {}, {})".format(*redden_rgb(r))
            mixes.append(
                f'.wcx-ground [{attr}="{color}"] {{ {attr}: color-mix(in srgb, {red} calc(var(--sick) * 100%), {color}); }}'
            )
    rules.append("@supports (fill: color-mix(in srgb, red 50%, blue)) {\n      " + "\n      ".join(mixes) + "\n    }")
    return "\n    ".join(rules)


CSS = (
    BASE_CSS
    + """
    /* Slides are sized in rem and never scroll, so short screens shrink the root size. */
    html { font-size: clamp(10px, 2.1vh, 16px); font-size: clamp(10px, 2.1dvh, 16px); }

    .globe-canvas {
      position: absolute;
      top: 0;
      left: 0;
      z-index: 1;
      transform-origin: 0 0;
      pointer-events: none;
      opacity: 0;
      /* backwards, not both: a filling animation would override the opacity transitions. */
      animation: wc-fade-in 0.9s ease-out backwards;
    }

    @keyframes wc-fade-in { from { opacity: 0; } }

    .planet-canvas { position: fixed; inset: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none; opacity: 0; }

    .deck > footer, .deck > .dots { position: relative; z-index: 3; }

    .lang {
      position: fixed;
      top: 0.7rem;
      right: 1.25rem;
      z-index: 4;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      color: var(--gray-500);
      cursor: pointer;
      transition: color 0.2s;
    }
    .lang:hover, .lang:focus-within { color: var(--gray-900); }
    .lang svg { width: 1.1rem; height: 1.1rem; flex: none; }
    .lang select {
      appearance: none;
      -webkit-appearance: none;
      border: none;
      background: transparent;
      color: inherit;
      font: inherit;
      font-size: 1rem;
      line-height: 1.2;
      height: 1.2em;
      cursor: pointer;
      padding: 0;
    }
    .lang select:focus-visible { outline: 2px solid rgb(107, 163, 163); outline-offset: 2px; border-radius: 3px; }

    .start-hint {
      position: absolute;
      inset: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      font-size: 1.3rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      color: var(--gray-800);
      text-shadow: 0 0 6px #fff, 0 0 14px #fff;
      pointer-events: none;
      opacity: 0;
    }
    .page.active .start-hint { animation: hint-in 0.8s ease-out 1.2s both, hint-pulse 2.6s ease-in-out 2s infinite; }
    .hint-touch { display: none; }
    @media (hover: none) and (pointer: coarse) {
      .hint-pointer { display: none; }
      .hint-touch { display: inline; }
    }
    .gos-intro-line {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0.2rem;
      z-index: 2;
      text-align: center;
      font-size: 1.75rem;
      font-weight: 650;
      letter-spacing: -0.01em;
      pointer-events: none;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.35s ease, transform 0.35s ease;
    }
    .gos-intro-line.shown {
      opacity: 1;
      transform: none;
      transition: opacity 0.7s ease-out var(--after-move), transform 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) var(--after-move);
    }
    @keyframes hint-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; } }
    @keyframes hint-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

    .wf-slide,
    .gos-slide {
      position: absolute;
      inset: 0;
    }

    .gos-slide {
      display: flex;
      align-items: center;
      gap: 3.5rem;
      padding: 0 1.5rem;
    }

    .gos-globe-slot {
      flex: none;
      height: 82%;
      aspect-ratio: 1;
    }

    .gos-side {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 1.6rem;
    }

    .gos-left { order: -1; }

    .gos-right { align-items: center; }

    .gos-link {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.65rem;
      font-size: 1.6rem;
      font-weight: 650;
      letter-spacing: -0.01em;
      color: var(--text);
      text-decoration: none;
      white-space: nowrap;
      transition: opacity 0.45s ease-out, transform 0.45s cubic-bezier(0.2, 0.7, 0.2, 1);
    }

    .gos-link-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      padding: 0.5rem 1.25rem 0.55rem;
      border: 2px solid var(--gray-900);
      border-radius: 999px;
      transition: background 0.2s, color 0.2s;
    }
    .gos-link:hover .gos-link-pill { background: var(--gray-900); color: #fff; }
    .gos-link:focus-visible { outline: none; }
    .gos-link:focus-visible .gos-link-pill { outline: 2px solid rgb(107, 163, 163); outline-offset: 3px; }
    .gos-link-arrow { display: inline-block; }
    .gos-link.shown .gos-link-arrow { animation: link-nudge 2.4s ease-in-out 1s infinite; }
    @keyframes link-nudge { 0%, 55%, 100% { transform: none; } 25% { transform: translateX(0.35em); } }
    .gos-link-cta { font-size: 1rem; font-weight: 500; letter-spacing: 0; color: var(--gray-500); transition: color 0.2s; }
    .gos-link:hover .gos-link-cta { color: rgb(47, 95, 95); }

    .gos-legend {
      display: flex;
      flex-direction: column;
      gap: 0.9rem;
      margin-bottom: 2.5rem;
    }

    .gos-legend-item {
      display: flex;
      align-items: center;
      gap: 0.8rem;
      font-size: 1.2rem;
      font-weight: 650;
    }

    .gos-legend-title {
      font-size: 0.8rem;
      font-weight: 650;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--gray-500);
    }

    .gos-legend-label { display: block; }
    .gos-legend-note {
      display: block;
      max-width: 17rem;
      margin-top: 0.2rem;
      font-size: 0.95rem;
      font-weight: 400;
      line-height: 1.35;
      color: var(--gray-500);
    }

    .gos-badge {
      flex: none;
      display: grid;
      place-items: center;
      width: 2.4rem;
      height: 2.4rem;
      border-radius: 50%;
      border: 1.5px solid rgba(38, 38, 38, 0.55);
      background: #fff;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
      font-size: 1.05rem;
      font-weight: 700;
      color: rgba(64, 64, 64, 0.7);
    }

    .gos-badge img { width: auto; height: 1.65rem; }

    .gos-badge-other {
      border-style: dashed;
      background: #f3f3f3;
    }

    .gos-head {
      border-bottom: 2px solid var(--gray-900);
      padding-bottom: 0.7rem;
      margin-bottom: 0.3rem;
    }

    .gos-head h2 { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; }

    .gos-kicker {
      font-size: 0.85rem;
      font-weight: 650;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--gray-500);
      margin-bottom: 0.35rem;
    }

    .gos-point { display: flex; flex-direction: column; gap: 0.3rem; }
    .gos-label { font-size: 1.35rem; font-weight: 400; line-height: 1.25; }
    .gos-label strong { font-weight: 700; }
    .gos-ic {
      display: inline-block;
      margin-left: 0.4em;
      vertical-align: -0.12em;
      line-height: 0;
    }
    .gos-ic img { display: block; height: 1.1em; width: auto; }
    .gos-ic:hover img { opacity: 0.75; }

    /* Titles and the art beside the globe wait for it to finish moving (MOVE_MS in GLOBE_JS). */
    .viewport { --after-move: 1.6s; }

    .wc-title {
      opacity: 0;
      transform: translateY(0.6rem);
      transition: opacity 0.3s ease;
    }

    .page.active .wc-title {
      opacity: 1;
      transform: none;
      transition: opacity 0.6s ease-out var(--after-move), transform 0.6s cubic-bezier(0.2, 0.7, 0.2, 1) var(--after-move);
    }
    .gos-note { font-size: 1.08rem; color: var(--gray-500); line-height: 1.4; }

    .gos-note a,
    .gos-legend-item a {
      color: inherit;
      text-decoration: none;
      transition: color 0.2s;
    }

    .gos-note a:hover,
    .gos-legend-item a:hover { color: rgb(47, 95, 95); }

    .wf-globe-slot {
      position: absolute;
      top: 50%;
      left: -8%;
      height: 115%;
      aspect-ratio: 1;
      transform: translate(-50%, -50%);
    }

    .wf-content {
      position: absolute;
      top: 0;
      bottom: 0;
      left: 29%;
      right: 6%;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 2rem;
    }

    .wf-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .wf-item {
      display: grid;
      grid-template-columns: 8rem minmax(0, 1fr);
      column-gap: 2rem;
      align-items: center;
    }

    .wf-art svg { display: block; width: 8rem; height: 8rem; }

    .wf-world { display: flex; align-items: baseline; gap: 0.9rem; min-width: 0; }
    .wf-world { font-size: 1.9rem; line-height: 1.25; }
    .wf-world .wc-note { font-size: 0.65em; }
    .wf-pc { font-size: 1.3rem; margin-top: 0.55rem; color: var(--gray-600); padding-left: 1.8rem; text-indent: -1.8rem; }
    .wf-world .wc-label { font-weight: 700; }
    .wf-pc .wc-label { font-weight: 600; color: var(--gray-700); white-space: normal; display: inline; }
    .wf-pc .wc-note { font-size: 1em; display: inline; margin-left: 0.6rem; }

    .wf-pc svg {
      display: inline-block;
      width: 1.2rem;
      height: 1.2rem;
      margin-right: 0.6rem;
      vertical-align: -0.2em;
      color: var(--gray-400);
    }

    .wf-coin { animation: wf-coin 3.2s ease-in infinite; }
    .wf-slice { animation: wf-slice 4s ease-in-out infinite alternate; }
    .wf-heat { animation: wf-heat 2.4s ease-out infinite; }
    .wf-spin { animation: wf-spin 1.1s linear infinite; }
    @keyframes wf-spin { to { transform: rotate(360deg); } }

    @keyframes wf-coin {
      0%, 15% { transform: translateY(0); opacity: 1; }
      70% { transform: translateY(38px); opacity: 1; }
      85%, 100% { transform: translateY(38px); opacity: 0; }
    }
    @keyframes wf-slice { from { transform: translate(2px, -2.5px); } to { transform: translate(9px, -11px); } }
    @keyframes wf-heat {
      0% { opacity: 0; transform: translateY(4px); }
      40% { opacity: 1; }
      100% { opacity: 0; transform: translateY(-6px); }
    }
"""
    + WAR_SPREAD_KEYFRAMES
    + "\n"
    + BUREAUCRACY_KEYFRAMES
    + """

    .wc-label { font-weight: 650; color: var(--text); white-space: nowrap; }
    .wc-note { font-size: 0.8em; color: var(--gray-500); }

    .wc-frag,
    .wf-item {
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.45s ease-out, transform 0.45s cubic-bezier(0.2, 0.7, 0.2, 1);
    }

    .wc-frag.shown,
    .wf-item.shown { opacity: 1; transform: none; }

    .wc-frag:not(.shown), .wf-item:not(.shown) { pointer-events: none; }
    /* A block that comes in with its slide waits for the globe to get there. */
    .gos-arrive.shown { transition-delay: 1.6s; }

    /* The world computer: an isometric stack drawn in a 1120 × 600 box (WCX_W × WCX_H). */
    .wcx-slide {
      position: absolute;
      inset: 0;
      margin: 0 auto;
      width: min(84rem, 100%);
      padding: 1.6rem 1rem 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .wcx {
      flex: 1;
      min-height: 0;
      container-type: size;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .wcx-inner {
      position: relative;
      width: min(100cqw, 100cqh * 1120 / 600);
      aspect-ratio: 1120 / 600;
      container-type: inline-size;
    }

    .wcx-crop, .wcx-art { position: absolute; inset: 0; }
    .wcx-art svg { display: block; width: 100%; height: 100%; overflow: visible; }
    .wcx-globe { position: absolute; aspect-ratio: 1; }

    .wcx-label { position: absolute; width: 25.9%; transform: translateY(-50%); }
    .wcx-left { text-align: right; }
    .wcx-label .wc-frag.shown { transition-delay: var(--in, 0.2s); }
    .wcx-label .wc-label { display: block; font-size: 1.85cqw; white-space: normal; line-height: 1.2; }
    .wcx-label .wc-note { display: block; font-size: 1.35cqw; line-height: 1.35; margin-top: 0.2em; }
    .wcx-label .wc-label svg { display: inline-block; height: 1.05em; width: auto; margin-right: 0.4em; vertical-align: -0.15em; }

    .wcx-step, .wcx-fade { opacity: 0; transition: opacity 0.4s ease, transform 0.4s ease; }
    .wcx-step { transform: translateY(-22px); }
    .wcx-step.shown, .wcx-fade.shown {
      opacity: 1;
      transform: none;
      transition: opacity 0.7s ease-out var(--in, 0s), transform 0.9s cubic-bezier(0.2, 0.7, 0.2, 1) var(--in, 0s);
    }
    /* While the globe glides down into the planet (GLOBE_JS sets .wcx-landing), the ground waits for it. */
    .wcx-ground, .wcx-hardware-label, .wcx-hardware-lead { --in: 0.3s; }
    .wcx-landing :is(.wcx-ground, .wcx-hardware-label, .wcx-hardware-lead) { --in: 1.9s; }
    .wcx-label :is(.wc-label, .wc-note) { text-shadow: 0 0 3px #fff, 0 0 6px #fff, 0 0 10px #fff; }
    .wcx-label .wc-frag:has(.wcx-swap) { display: grid; }
    .wcx-swap { grid-area: 1 / 1; opacity: 0; transition: opacity 0.35s ease; }
    .wcx-swap.shown { opacity: 1; transition: opacity 0.6s ease 0.3s; }
    /* The layers take their computer names, with a teal glow, once the picture has moved. */
    .wcx-swap[data-until]:not(.shown) { transition: opacity 0.35s ease 1.3s; }
    .wcx-swap[data-frag].shown { transition: opacity 0.5s ease 1.5s; }
    .wcx-swap[data-frag].shown .wc-label { animation: wcx-name-glow 2.6s ease-in-out 1.6s both; }

    /* The Governance Operating System comes in: the picture moves right by WCX_SHIFT, the
       callouts leave and its points take the left (WCX_GOS_X), one beside each layer. */
    .wcx-art, .wcx-right {
      transition: transform 1.3s cubic-bezier(0.45, 0, 0.2, 1), width 1.3s cubic-bezier(0.45, 0, 0.2, 1);
    }
    .wcx-inner[data-shift].shown .wcx-art { transform: translateX(8.929cqw); }
    .wcx-inner[data-shift].shown .wcx-right { transform: translate(8.929cqw, -50%); width: 17.143%; }
    .wcx-until { transition: opacity 0.4s ease; }
    .wcx-until:not(.shown) { opacity: 0; pointer-events: none; }
    .wcx-gos-head { width: 54%; text-align: left; }
    .wcx-gos-title { display: block; font-size: 2.8cqw; font-weight: 800; letter-spacing: -0.025em; line-height: 1.1; }
    .wcx-gos-abbr { font-size: 0.62em; font-weight: 750; letter-spacing: 0.06em; white-space: nowrap; }
    .wcx-gos .wc-label + .wc-label, .wcx-gos .wc-note + .wc-label { margin-top: 0.55em; }
    .wcx-gos .wc-label:has(.wcx-gos-abbr) { font-weight: 800; }
    .wcx-gos .wc-note .gos-ic { margin-left: 0.3em; }
    .wcx-nowrap { white-space: nowrap; }
    /* The last click boxes the Governance Operating System point, to stress it. */
    .wcx-gos-os .wc-frag { position: relative; isolation: isolate; width: fit-content; margin-left: auto; }
    .wcx-gos-box {
      position: absolute;
      inset: -0.7cqw -0.9cqw -0.7cqw -1.1cqw;
      border: 0.16cqw solid rgb(47, 95, 95);
      border-radius: 1cqw;
      background: rgba(255, 255, 255, 0.55);
      box-shadow: 0 0.3cqw 1.4cqw rgba(47, 95, 95, 0.18);
      z-index: -1;
      opacity: 0;
      transform: scale(1.08);
      transition: opacity 0.3s ease, transform 0.3s ease;
    }
    .wcx-gos-box.shown { opacity: 1; transform: none; transition: opacity 0.6s ease, transform 0.7s cubic-bezier(0.2, 0.7, 0.2, 1); }
    /* The users point's title stays on one line, reaching left as far as it needs. */
    .wcx-gos-users .wc-frag { display: flex; flex-direction: column; align-items: flex-end; }
    .wcx-gos-users .wc-label:first-child { white-space: nowrap; }
    /* A point's first line meets its lead, and the rest hangs below; the heading sits above them. */
    .wcx-gos { transform: translateY(-1cqw); }
    .wcx-gos-head { transform: translateY(-100%); }
    .wcx-gos .gos-ic img { height: 0.95em; }
    .wcx-gos a:not(.gos-ic) {
      color: inherit;
      text-decoration: underline;
      text-decoration-color: rgba(107, 163, 163, 0.6);
      text-underline-offset: 0.15em;
      transition: color 0.2s;
    }
    .wcx-gos a:not(.gos-ic):hover { color: rgb(47, 95, 95); }
    /* Both sides share the narrower room once the picture has moved. */
    .wcx-label :is(.wc-label, .wc-note) { transition: font-size 1.3s cubic-bezier(0.45, 0, 0.2, 1); }
    .wcx-inner[data-shift].shown :is(.wcx-right, .wcx-gos) .wc-label { font-size: 1.6cqw; }
    .wcx-inner[data-shift].shown :is(.wcx-right, .wcx-gos) .wc-note { font-size: 1.2cqw; }
    .wcx-inner[data-shift].shown .wcx-gos .wc-label { font-size: 1.3cqw; }
    /* The hardware label sits on the planet's surface: a soft white patch keeps it readable. */
    .wcx-hardware-label { position: relative; isolation: isolate; width: fit-content; }
    .wcx-hardware-label::before {
      content: "";
      position: absolute;
      inset: -0.9em -1.6em -0.9em -1.1em;
      z-index: -1;
      background: radial-gradient(closest-side, #fff 62%, rgba(255, 255, 255, 0.85) 80%, rgba(255, 255, 255, 0));
    }

    .wcx-pop {
      opacity: 0;
      transform: translateY(4px) scale(0.25);
      transform-box: fill-box;
      transform-origin: 50% 100%;
      transition: opacity 0.3s ease, transform 0.3s ease;
    }
    .shown .wcx-pop {
      opacity: 1;
      transform: none;
      transition: opacity 0.4s ease-out calc(var(--in, 0s) + var(--d, 0s)),
        transform 0.55s cubic-bezier(0.3, 1.45, 0.5, 1) calc(var(--in, 0s) + var(--d, 0s));
    }
    /* A pop inside a shown data-until wrapper still waits for its own step. */
    .wcx g[data-frag]:not(.shown) .wcx-pop {
      opacity: 0;
      transform: translateY(4px) scale(0.25);
      transition: opacity 0.3s ease, transform 0.3s ease;
    }

    .wcx-car-x { animation: wcx-drive-x 9s linear infinite; }
    .wcx-car-xr { animation: wcx-drive-xr 11s linear infinite; }
    .wcx-car-y { animation: wcx-drive-y 10s linear infinite; }
    .wcx-rotor { animation: wcx-spin 4.5s linear infinite; }
    .wcx-smoke { transform-box: fill-box; transform-origin: center; animation: wcx-smoke 3.6s ease-out infinite; opacity: 0; }
    .wcx-pulses path { stroke-dasharray: 6 94; animation: wcx-pulse 4.8s linear infinite; }
    .wcx-flow { stroke: #8a8a8a; stroke-dasharray: 5 95; animation: wcx-flow 2.7s linear infinite; }
    .wcx-bob { animation: wcx-bob 2.8s ease-in-out infinite alternate; }
    .wcx-sweep { animation: wcx-sweep 2.6s cubic-bezier(0.45, 0, 0.55, 1) infinite; }
    .wcx-glow { animation: wcx-glow 2.6s ease-in-out infinite; }
    .wcx-capture { stroke-dasharray: 100; stroke-dashoffset: 100; }
    .wcx-hack.shown .wcx-capture { animation: wcx-capture 1.3s ease-in var(--d) forwards; }
    .wcx-glitch { opacity: 0; }
    .wcx-hack.shown .wcx-glitch { animation: wcx-glitch 1.7s steps(1) 1.7s infinite; }
    .wcx-taint { opacity: 0; }
    .wcx-hack.shown .wcx-taint { animation: wcx-taint 0.5s ease-out var(--d) forwards; }
    .wcx-glitch-edge { animation: wcx-glitch-edge 1.7s steps(1) infinite; }
    .wcx-ring { transform-box: fill-box; transform-origin: center; opacity: 0; }
    /* Checks and balances try: the red gives way, then comes back, and the shield breaks. */
    .wcx-checks.shown .wcx-ring { animation: wcx-ring 1.4s ease-out 0.2s 2 both; }
    .wcx-checks-edge { opacity: 0; }
    .wcx-checks.shown .wcx-checks-edge { animation: wcx-checks-edge 3.4s ease forwards; }
    .wcx-fail, .wcx-evil { transform-box: fill-box; transform-origin: 50% 100%; }
    .wcx-crack { opacity: 0; }
    .wcx-checks.shown .wcx-fail { animation: wcx-fail 3.4s ease-in forwards; }
    .wcx-checks.shown .wcx-crack { animation: wcx-crack 3.4s steps(1) forwards; }
    .wcx svg:has(.wcx-checks.shown) .wcx-hack.shown :is(.wcx-taint, .wcx-capture) {
      opacity: 1;
      stroke-dashoffset: 0;
      animation: wcx-resist 3.4s ease-in-out forwards;
    }
    .wcx svg:has(.wcx-checks.shown) .wcx-evil { animation: wcx-evil 3.4s ease-out forwards; }
    /* The damage spreads (.wcx-sick), and the Governance Operating System mends it (.wcx-heal,
       after --out) with one teal sweep (.wcx-mend). Sad people stop bobbing. */
    .wcx-heal:not(.shown) { transition: opacity 1.2s ease var(--out, 0.3s); }
    .wcx-bob:has(> .wcx-sick.shown > .shown) { animation-play-state: paused; }
    .wcx-mend-band, .wcx-mend-edge { opacity: 0; }
    .wcx-mend.shown .wcx-mend-band { animation: wcx-mend 1.6s cubic-bezier(0.45, 0, 0.55, 1) var(--out) both; }
    .wcx-mend.shown .wcx-mend-edge { animation: wcx-mend-edge 2.2s ease var(--out) both; }

    @keyframes wcx-drive-x { to { transform: translateX(285px); } }
    @keyframes wcx-drive-xr { to { transform: translateX(-285px); } }
    @keyframes wcx-drive-y { to { transform: translateY(285px); } }
    @keyframes wcx-spin { to { transform: rotate(360deg); } }
    @keyframes wcx-smoke {
      0% { opacity: 0; transform: scale(0.5); }
      20% { opacity: 0.85; }
      100% { opacity: 0; transform: translate(-9px, -24px) scale(1.7); }
    }
    @keyframes wcx-pulse { from { stroke-dashoffset: 6; } to { stroke-dashoffset: -100; } }
    @keyframes wcx-flow { from { stroke-dashoffset: 5; } to { stroke-dashoffset: -100; } }
    @keyframes wcx-bob { to { transform: translateY(-2.5px); } }
    @keyframes wcx-sweep { to { transform: translateX(340px); } }
    @keyframes wcx-glow { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
    @keyframes wcx-capture { to { stroke-dashoffset: 0; } }
    @keyframes wcx-taint { to { opacity: 1; } }
    @keyframes wcx-glitch { 0%, 100% { opacity: 0.06; } 20% { opacity: 0.16; } 24% { opacity: 0.04; } 58% { opacity: 0.13; } 62% { opacity: 0.07; } }
    @keyframes wcx-glitch-edge { 0%, 100% { opacity: 1; } 20% { opacity: 0.3; } 24% { opacity: 1; } 58% { opacity: 0.5; } }
    @keyframes wcx-ring { from { opacity: 0.9; transform: scale(0.12); } to { opacity: 0; transform: scale(1); } }
    @keyframes wcx-checks-edge { 0% { opacity: 0; } 10%, 55% { opacity: 1; } 80%, 100% { opacity: 0; } }
    @keyframes wcx-resist { 0% { opacity: 1; } 22%, 50% { opacity: 0.12; } 82%, 100% { opacity: 1; } }
    @keyframes wcx-crack { 0% { opacity: 0; } 53%, 100% { opacity: 1; } }
    @keyframes wcx-fail {
      0%, 52% { opacity: 1; transform: none; }
      56% { transform: rotate(-7deg); }
      60% { transform: rotate(6deg); }
      64% { opacity: 1; transform: rotate(-3deg); }
      100% { opacity: 0; transform: translateY(18px) rotate(18deg); }
    }
    @keyframes wcx-name-glow {
      0%, 100% { color: inherit; text-shadow: 0 0 3px #fff, 0 0 6px #fff, 0 0 10px #fff; }
      15%, 50% {
        color: rgb(47, 95, 95);
        text-shadow: 0 0 2px #fff, 0 0 8px rgba(107, 163, 163, 0.95), 0 0 18px rgba(107, 163, 163, 0.8), 0 0 30px rgba(107, 163, 163, 0.6);
      }
      32% { color: rgb(47, 95, 95); text-shadow: 0 0 3px #fff, 0 0 6px #fff, 0 0 10px #fff; }
      75% { color: rgb(47, 95, 95); text-shadow: 0 0 3px #fff, 0 0 6px #fff, 0 0 10px #fff; }
    }
    @keyframes wcx-mend { 0%, 85% { opacity: 1; } 0% { transform: none; } 100% { opacity: 0; transform: translateX(340px); } }
    @keyframes wcx-mend-edge { 0%, 100% { opacity: 0; } 30% { opacity: 1; } }
    @keyframes wcx-evil {
      0% { opacity: 1; transform: none; }
      8%, 72% { opacity: 0; transform: scale(0.5); }
      86% { opacity: 1; transform: scale(1.2); }
      100% { opacity: 1; transform: none; }
    }

    @media (prefers-reduced-motion: reduce) {
      .wcx * { animation: none !important; transition: none !important; }
      .wcx-capture { stroke-dashoffset: 0; }
      .wcx-taint { opacity: 1; }
      .wcx-checks .wcx-fail { opacity: 0; }
      .wcx-hack .wcx-glitch { opacity: 0.08; }
      .wcx-pulses, .wcx-flow, .wcx-sweep, .wcx-ring, .wcx-smoke, .wcx-mend { display: none; }
      .wf-item, .page.active .wc-title { transition: none; transform: none; }
      .globe-canvas, .wf-art * { animation: none !important; }
      .page.active .start-hint { animation: none; opacity: 1; }
      .gos-link.shown .gos-link-arrow { animation: none; }
      .gos-intro-line, .gos-intro-line.shown { transition: none; transform: none; }
    }

    @media (max-height: 760px) and (min-aspect-ratio: 1/1) {
      .gos-slide { gap: 2.5rem; }
      .gos-globe-slot { height: 76%; }
      .wf-content { gap: 1.4rem; }
      .wf-list { gap: 1.1rem; }
      .wf-item { grid-template-columns: 6.5rem minmax(0, 1fr); }
      .wf-art svg { width: 6.5rem; height: 6.5rem; }
      .wf-world { font-size: 1.75rem; }
      .wf-pc { margin-top: 0.35rem; }
    }

    @media (max-height: 500px) {
      .wf-content { gap: 0.8rem; }
      .wf-list { gap: 0.6rem; }
      .wf-item { grid-template-columns: 4.5rem minmax(0, 1fr); }
      .wf-art svg { width: 4.5rem; height: 4.5rem; }
      .wf-world { font-size: 1.45rem; }
      .wf-pc { font-size: 1.1rem; margin-top: 0.2rem; }
      .gos-slide { gap: 1.5rem; padding: 0; }
      .gos-globe-slot { height: 72%; }
      .gos-side { gap: 0.7rem; }
      .gos-head h2 { font-size: 1.5rem; }
      .gos-label { font-size: 1.2rem; }
    }

    /* Portrait screens: the globe goes on top and the text stacks below it. */
    @media (max-aspect-ratio: 1/1) {
      .deck { padding: 0.75rem 1rem 0.6rem; }
      footer .site { font-size: 0.95rem; }

      /* The stack, cropped to its middle, on top; the labels in a list below it. */
      .wcx-slide { padding: 0; gap: 0.6rem; }
      /* The title wraps clear of the language selector. */
      .wc-title h2 { padding-right: 7rem; font-size: 1.35rem; }
      /* Anchored to the top so the picture stays put while the text below it changes; WCX_FIT_JS sizes it to what the text leaves. */
      .wcx { position: relative; container-type: normal; flex-direction: column; justify-content: flex-start; gap: 0.8rem; }
      .wcx-inner { width: 100%; aspect-ratio: auto; container-type: normal; display: flex; flex-direction: column; gap: 0.8rem; }
      .wcx-crop { position: relative; inset: auto; width: min(100%, var(--wcx-art-h, 38dvh) * 520 / 600); aspect-ratio: 520 / 600; margin: 0 auto; }
      /* The planet's ground runs the full width but stops above the labels (so does GLOBE_JS's planet). */
      .wcx-crop { clip-path: inset(-100vh -100vw 0 -100vw); }
      .wcx-art { inset: auto; top: 0; left: -57.7%; width: 215.4%; aspect-ratio: 1120 / 600; }
      .wcx-lead { display: none; }
      .wcx-labels { display: grid; grid-template-columns: 1fr 1fr; gap: 0.55rem 1rem; }
      .wcx-label { position: static; width: auto; transform: none; text-align: left; }
      .wcx-label .wc-label { font-size: 0.95rem; }
      .wcx-label .wc-note { font-size: 0.78rem; margin-top: 0.05em; }
      .wcx-inner[data-shift].shown :is(.wcx-art, .wcx-right) { transform: none; }
      .wcx-inner[data-shift].shown .wcx-right { width: auto; }
      .wcx-until:not(.shown), .wcx-gos:has(> .wc-frag:not(.shown)) { display: none; }
      .wcx-gos { width: auto !important; transform: none; grid-column: 1 / -1; }
      /* Room for the Governance Operating System's points: the layers keep just their names. */
      .wcx-inner[data-shift].shown .wcx-right .wc-note { display: none; }
      .wcx-gos-head { grid-column: 1 / -1; }
      .wcx-gos-title { font-size: 1.15rem; }
      .wcx-gos-users .wc-frag { display: block; }
      .wcx-gos-os .wc-frag { margin: 0.35rem 0 0.35rem 0.6rem; max-width: calc(100% - 1.2rem); }
      .wcx-gos .wcx-nowrap { white-space: normal; }
      .wcx-gos-box { inset: -0.35rem -0.6rem; border-width: 1.5px; border-radius: 0.6rem; }
      .wcx-gos-users .wc-label:first-child { white-space: normal; }
      .wcx-inner[data-shift].shown :is(.wcx-right, .wcx-gos) .wc-label { font-size: 0.95rem; }
      .wcx-inner[data-shift].shown :is(.wcx-right, .wcx-gos) .wc-note { font-size: 0.78rem; }

      .wf-globe-slot { left: 50%; top: 0; height: auto; width: 78%; transform: translate(-50%, -58%); }
      .wf-content { left: 0; right: 0; top: 7.5rem; justify-content: flex-start; gap: 1.4rem; }
      .wf-list { gap: 1.1rem; }
      .wf-item { grid-template-columns: 4.25rem minmax(0, 1fr); column-gap: 0.9rem; }
      .wf-art svg { width: 4.25rem; height: 4.25rem; }
      .wf-world { flex-wrap: wrap; gap: 0.1rem 0.5rem; }
      .wf-world { font-size: 1.3rem; }
      .wf-world .wc-note { font-size: 0.68em; }
      .wf-pc { font-size: 0.92rem; margin-top: 0.35rem; padding-left: 1.35rem; text-indent: -1.35rem; }
      .wf-pc svg { width: 1rem; height: 1rem; margin-right: 0.35rem; vertical-align: -0.15em; }
      .wf-pc .wc-note { display: block; margin-left: 0; text-indent: 0; }

      /* A grid so the intro line can share the points' row: it sits under the globe and moves nothing when it goes. */
      .gos-slide { display: grid; grid-template-columns: minmax(0, 1fr); align-content: center; gap: 0.8rem; padding: 0; }
      .gos-slide > * { grid-column: 1; }
      .gos-globe-slot { grid-row: 1; justify-self: center; height: auto; width: max(26vh, min(84%, 100dvh - 35rem)); }
      .gos-left { grid-row: 2; }
      .gos-right { grid-row: 3; }
      .gos-intro-line { position: static; grid-row: 2; grid-column: 1; align-self: start; padding-top: 0.6rem; font-size: 1.45rem; }
      .gos-slide.globe-only .gos-globe-slot { width: min(92%, 70vh); }
      .gos-slide.globe-only .gos-side { display: none; }
      .gos-side { flex: none; gap: 0.6rem; }
      .gos-right { flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem 1.25rem; }
      .gos-legend { flex-direction: row; flex-wrap: wrap; gap: 0.6rem 1.1rem; margin-bottom: 0; }
      .gos-legend-title { flex-basis: 100%; font-size: 0.7rem; }
      .gos-legend-note { font-size: 0.8rem; }
      .gos-legend-item { font-size: 0.95rem; gap: 0.5rem; }
      .gos-badge { width: 1.9rem; height: 1.9rem; font-size: 0.9rem; }
      .gos-badge img { height: 1.3rem; }
      .gos-link { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.8rem; font-size: 1.15rem; white-space: normal; }
      .gos-link-pill { padding: 0.35rem 0.95rem 0.4rem; }
      .gos-link-cta { font-size: 0.85rem; }
      .gos-head { padding-bottom: 0.5rem; margin-bottom: 0.1rem; }
      .gos-head h2 { font-size: 1.45rem; }
      .gos-kicker { font-size: 0.72rem; }
      .gos-point { gap: 0.15rem; }
      .gos-label { font-size: 1.02rem; }
      .gos-note { font-size: 0.85rem; }
    }

    @media (max-aspect-ratio: 1/1) and (max-height: 700px) {
      .gos-globe-slot { width: max(22vh, min(84%, 100dvh - 35rem)); }
      .wf-content { top: 6.5rem; gap: 1rem; }
      .wf-list { gap: 0.8rem; }
    }
"""
    + "\n    "
    + ground_decay_css()
    + "\n"
)


GOS_POINTS = {"gos-os": "os", "gos-apps": "apps", "gos-users": "users"}


class WorldComputerSlide(Slide):
    """The world as a computer: the globe becomes a digital planet surface, and layers stack on it.

    Bullets are ":key: Label — note", one per click; keys are those of WCX_ART. A layer can be
    named for the world first and for the computer later: ":key: World — note <=> Computer — note".
    ":decay: layer" (hardware, apps or users) is the click the hack's damage reaches that layer.
    ":gos:" is the click where the new governance stack comes in: the picture moves right, the
    callouts on the left leave, and the layers take their computer names (the part after "<=>").
    ":gos-head: Title" is its heading. Its points are ":gos-os:", ":gos-apps:" and ":gos-users:"
    bullets: lines "A — note — note + B", where notes are optional, "{ic}" ends a line or note
    with the Internet Computer logo, and a line "Title (Abbr)" sets the abbreviation apart. Each point
    mends its layer. A nested bullet comes with the click of the bullet above it. ":gos-box:" is the
    click that draws a rounded box round the ":gos-os:" point, to stress it.
    """

    def render(self) -> str:
        frags: dict[str, int] = {}
        decay: dict[str, int] = {}
        gos_points: list[tuple[str, int]] = []
        labels = []
        clicks, n = [], 0
        for depth, _ in self.bullets:
            n += depth == 0
            clicks.append(max(n, 1))
        gos = next((c for c, (_, t) in zip(clicks, self.bullets) if re.match(r"^:gos:(\s|$)", t.strip())), None)
        head_click = next((c for c, (_, t) in zip(clicks, self.bullets) if t.strip().startswith(":gos-head:")), None)
        box_click = next((c for c, (_, t) in zip(clicks, self.bullets) if re.match(r"^:gos-box:(\s|$)", t.strip())), None)

        def text_html(text: str) -> str:
            label, _, note = text.strip().partition(" — ")
            note_html = f'<span class="wc-note">{tr(note)}</span>' if note else ""
            return f'<span class="wc-label">{CALLOUT_ICONS.get(key, "")}{tr(label)}</span>{note_html}'

        def titled(text: str) -> str:
            title, abbr = re.match(r"^(.*?)(?:\s*\(([^()]+)\))?$", text).groups()
            return tr(title) + (f' <span class="wcx-gos-abbr">({tr(abbr)})</span>' if abbr else "")

        def with_ic(html_text: str) -> str:
            # The logo keeps to the last word, so it never wraps onto a line of its own.
            head, sep, last = html_text.rpartition(" ")
            if "<" in last or ">" in last:
                head, sep, last = "", "", html_text
            return f'{head}{sep}<span class="wcx-nowrap">{last}{IC_LOGO_HTML}</span>'

        def point_html(text: str) -> str:
            lines = []
            for line in text.strip().split(" + "):
                name, *notes = line.split(" — ")
                ic = name.endswith("{ic}")
                name = name.removesuffix("{ic}").rstrip()
                lines.append(f'<span class="wc-label">{with_ic(titled(name)) if ic else titled(name)}</span>')
                for note in notes:
                    ic = note.endswith("{ic}")
                    note = note.removesuffix("{ic}").rstrip()
                    lines.append(f'<span class="wc-note">{with_ic(tr(note)) if ic else tr(note)}</span>')
            return "".join(lines)

        def gos_label(y: float, body: str, frag: int, cls: str, extra: str = "") -> str:
            # The heading starts just left of the slide's text; the points end at WCX_GOS_X.
            place = (
                f"left:{-WCX_GOS_HEAD_OUT / WCX_W:.3%}"
                if cls == "wcx-gos-head"
                else f"right:{1 - WCX_GOS_X / WCX_W:.3%};width:{WCX_GOS_X / WCX_W:.3%}"
            )
            if frag == gos:
                place += f";--in:{GOS_WAIT}s"
            elif frag == head_click and cls != "wcx-gos-head":
                place += f";--in:{GOS_AFTER_HEAD}s"
            return (
                f'<div class="wcx-label wcx-left wcx-gos {cls}" style="top:{y / WCX_H:.3%};{place}">'
                f'<div class="wc-frag" data-frag="{frag}">{extra}{body}</div></div>'
            )

        for click, (_, text) in zip(clicks, self.bullets):
            m = re.match(r"^:([\w-]+):\s*(.*)$", text)
            if not m or m.group(1) not in {*WCX_ART, *GOS_POINTS, "gos", "gos-head", "gos-box", "decay"}:
                raise ValueError(
                    f"world-computer: expected :gos:, :gos-head:, :gos-box:, :decay:, one of {sorted(GOS_POINTS)} or one of {sorted(WCX_ART)} in {text!r}"
                )
            key, rest = m.groups()
            if key == "decay":
                if rest not in ("hardware", "apps", "users"):
                    raise ValueError(f"world-computer: :decay: takes hardware, apps or users, not {rest!r}")
                decay[rest] = click
                continue
            if key == "gos":
                if rest:
                    raise ValueError(f"world-computer: :gos: takes no text (the heading is :gos-head:), not {rest!r}")
                continue
            if key == "gos-box":
                if rest:
                    raise ValueError(f"world-computer: :gos-box: takes no text, not {rest!r}")
                if not any(t.strip().startswith(":gos-os:") for _, t in self.bullets):
                    raise ValueError("world-computer: :gos-box: needs a :gos-os: point to box")
                continue
            if key == "gos-head":
                head = f'<span class="wcx-gos-title">{titled(rest)}</span>'
                labels.append(gos_label(WCX_GOS_HEAD_Y, head, click, "wcx-gos-head"))
                continue
            if key in GOS_POINTS:
                layer = GOS_POINTS[key]
                gos_points.append((layer, click))
                y = iso(0, SIDE, 0, WCX_LAYERS[layer][0])[1]
                box = f'<span class="wcx-gos-box" data-frag="{box_click}" aria-hidden="true"></span>' if box_click and layer == "os" else ""
                labels.append(gos_label(y, point_html(rest), click, f"wcx-gos-{layer}", box))
                continue
            frags[key] = click
            world, swap, computer = rest.partition("<=>")
            if swap and gos is None:
                raise ValueError(f"world-computer: {text!r} has a computer name but no :gos: click")
            if swap:
                # Both names share one grid cell, so swapping them does not move anything.
                body = (
                    f'<span class="wcx-name wcx-swap" data-until="{gos}">{text_html(world)}</span>'
                    f'<span class="wcx-name wcx-swap" data-frag="{gos}">{text_html(computer)}</span>'
                )
            else:
                body = text_html(world)
            until = ""
            if key in WCX_CALLOUTS:
                y = WCX_CALLOUTS[key][0]
                side, pos = "left", f"right:{1 - WCX_CALLOUT_X / WCX_W:.3%}"
                # The callouts make room for the Governance Operating System.
                until = f' wcx-until" data-until="{gos}' if gos else ""
            else:
                y = iso(SIDE, 0, 0, WCX_LAYERS[key][0])[1]
                side, pos = "right", f"left:{WCX_LABEL_X / WCX_W:.3%}"
            labels.append(
                f'<div class="wcx-label wcx-{side}{until}" style="top:{y / WCX_H:.3%};{pos}">'
                f'<div class="wc-frag wcx-{key}-label" data-frag="{click}">{body}</div></div>'
            )
        first = frags.get("hardware", 1)
        planet = " ".join(str(v) for v in (*WCX_PLANET, *WCX_PLANET_ROTATE))
        # The globe sits in its slot until the first click; then GLOBE_JS glides it into the
        # planet whose top the marker describes (in viewBox units) and draws that full-window.
        globes = _globe_slot(WCX_GLOBE, f'data-until="{first}"') + (
            f'<div class="wcx-planet" data-planet="{planet}" data-frag="{first}"></div>'
        )
        shift = f' data-frag="{gos}" data-shift' if gos else ""
        return f"""
            <div class="page-step active">
              <section class="wcx-slide">
                <header class="box-header wc-title">
                  <h2>{tr(WORLD_TITLE)}</h2>
                </header>
                <div class="wcx">
                  <div class="wcx-inner"{shift}>
                    <div class="wcx-crop">
                      <div class="wcx-art">
                        {world_computer_svg(frags, gos, gos_points, decay, head_click)}
                        {globes}
                      </div>
                    </div>
                    <div class="wcx-labels">{"".join(labels)}</div>
                  </div>
                </div>
              </section>
            </div>"""


CHIP_MINI_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/>'
    '<path d="M10 2.5v3.5M14 2.5v3.5M10 18v3.5M14 18v3.5M2.5 10H6M2.5 14H6M18 10h3.5M18 14h3.5"/></svg>'
)


def label_and_note(text: str) -> str:
    label, _, note = text.strip().partition(" — ")
    note_html = f'<span class="wc-note">{tr(note)}</span>' if note else ""
    return f'<span class="wc-label">{tr(label)}</span>{note_html}'


class WorldFailuresSlide(Slide):
    def render(self) -> str:
        items = []
        for i, (_, text) in enumerate(self.bullets):
            m = re.match(r"^:([\w-]+):\s*(.*)$", text)
            art, rest = (FAILURE_ART[m.group(1)](), m.group(2)) if m else ("", text)
            world, _, pc = rest.partition("<=>")
            items.append(
                f'<li class="wf-item" data-frag="{i + 1}">'
                f'<div class="wf-art">{art}</div>'
                f'<div><div class="wf-world">{label_and_note(world)}</div>'
                f'<div class="wf-pc">{CHIP_MINI_SVG}{label_and_note(pc)}</div></div>'
                "</li>"
            )
        body = f"""
            <div class="page-step active">
              <section class="wf-slide">
                <div class="wf-globe-slot" data-globe-slot></div>
                <div class="wf-content">
                  <header class="box-header wc-title">
                    <h2>{tr(WORLD_FAILURES_TITLE)}</h2>
                  </header>
                  <ol class="wf-list">
                    {"".join(items)}
                  </ol>
                </div>
              </section>
            </div>"""
        return body


class GosIntroSlide(Slide):
    """Globe in the centre with realms on it; text blocks on either side.

    Without an "intro:" line, the first block comes in with the slide, once the globe is there.
    """

    def render(self) -> str:
        sides: dict[str, list[str]] = {"left": [], "right": []}
        legend: list[str] = []
        legend_frag = 0
        side = "left"
        frag = 0 if any(re.match(r"^intro:", t) for _, t in self.bullets) else -1
        intro = ""
        for _, text in self.bullets:
            # "intro: …" shows only before the first point, under the globe.
            m = re.match(r"^intro:\s*(.*)$", text)
            if m:
                intro = f'<p class="gos-intro-line" data-until="1">{tr(m.group(1))}</p>'
                continue
            # "legend: title — …", or "legend: realms|other — label[ — note]".
            entry = re.match(r"^legend:\s*(title|realms|other)\s+—\s+(.*)$", text)
            if entry:
                if not legend:
                    frag += 1
                    legend_frag = frag
                kind, rest = entry.groups()
                if kind == "title":
                    legend.append(f'<div class="gos-legend-title">{tr(rest)}</div>')
                    continue
                label, _, note = rest.partition(" — ")
                mark = (
                    '<img src="assets/logo_sphere_only.svg" alt="">'
                    if kind == "realms"
                    else "?"
                )
                text_html = (
                    f'<span><span class="gos-legend-label">{tr(label)}</span>'
                    f'<span class="gos-legend-note">{tr(note)}</span></span>'
                    if note
                    else tr(label)
                )
                legend.append(
                    f'<div class="gos-legend-item"><span class="gos-badge gos-badge-{kind}">{mark}</span>'
                    f"{text_html}</div>"
                )
                continue
            link = re.match(r"^link:\s*(\S+)$", text)
            if link:
                frag += 1
                url = html.escape(link.group(1))
                shown = re.sub(r"^https?://", "", url).rstrip("/")
                sides["right"].append(
                    f'<a class="gos-link wc-frag" data-frag="{frag}" data-home-link href="{url}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'<span class="gos-link-pill"><span class="gos-link-url">{shown}</span>'
                    f'<span class="gos-link-arrow" aria-hidden="true">→</span></span>'
                    f'<span class="gos-link-cta">{tr(LINK_CTA)}</span></a>'
                )
                continue
            m = re.match(r"^(left|right):\s*(.*)$", text)
            if m:
                side = m.group(1)
                kicker, _, title = m.group(2).partition(" — ")
                if not title:
                    kicker, title = "", kicker
                kicker_html = (
                    f'<div class="gos-kicker">{tr(kicker)}</div>' if kicker else ""
                )
                frag += 1
                arrive = " gos-arrive" if frag == 0 else ""
                sides[side].append(
                    f'<header class="gos-head wc-frag{arrive}" data-frag="{frag}">{kicker_html}'
                    f"<h2>{tr(title)}</h2></header>"
                )
                continue
            # "A + B — note": points revealed one by one, then the note they share.
            labels, _, note = text.partition(" — ")
            labels = labels.split(" + ")
            parts = []
            for label in labels:
                frag += 1
                ic = label.endswith("{ic}")
                if ic:
                    label = label[: -len("{ic}")].rstrip()
                mark = IC_LOGO_HTML if ic else ""
                parts.append(
                    f'<span class="gos-label wc-frag" data-frag="{frag}">{tr(label)}{mark}</span>'
                )
            if note:
                if len(labels) > 1:
                    frag += 1
                parts.append(
                    f'<span class="gos-note wc-frag" data-frag="{frag}">{tr(note)}</span>'
                )
            sides[side].append(f'<div class="gos-point">{"".join(parts)}</div>')
        if legend:
            sides["right"].insert(
                0,
                f'<div class="gos-legend wc-frag" data-frag="{legend_frag}">{"".join(legend)}</div>',
            )
        body = f"""
            <div class="page-step active">
              <section class="gos-slide">
                <div class="gos-globe-slot" data-globe-slot data-globe-layer="realms"></div>
                <div class="gos-side gos-left">{"".join(sides["left"])}</div>
                <div class="gos-side gos-right">{"".join(sides["right"])}</div>
                {intro}
              </section>
            </div>"""
        return body


class GlobeSlide(Slide):
    """Just the rotating globe, centred."""

    def render(self) -> str:
        body = f"""
            <div class="page-step active">
              <section class="gos-slide globe-only">
                <div class="gos-side"></div>
                <div class="gos-globe-slot" data-globe-slot></div>
                <div class="gos-side"></div>
                <p class="start-hint">
                  <span class="hint-pointer">{tr(START_HINT)}</span>
                  <span class="hint-touch">{tr(START_HINT_TOUCH)}</span>
                </p>
              </section>
            </div>"""
        return body


SLIDE_TYPES: dict[str, type[Slide]] = {
    "globe": GlobeSlide,
    "world-computer": WorldComputerSlide,
    "world-failures": WorldFailuresSlide,
    "gos-intro": GosIntroSlide,
}


def parse_steps(md_text: str) -> list[Slide]:
    slides: list[Slide] = []
    for block in re.split(r"\n(?=# )", md_text.strip()):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("# "):
            continue
        marker = next((l[3:].strip() for l in lines[1:] if l.startswith("## ")), "")
        if marker not in SLIDE_TYPES:
            raise ValueError(
                f"unknown slide marker {marker!r}; expected one of {sorted(SLIDE_TYPES)}"
            )
        bullets = parse_bullets([l for l in lines[1:] if re.match(r"^\s*-\s+", l)])
        slides.append(SLIDE_TYPES[marker](marker, bullets))
    return slides


def slide_title(slide: Slide) -> str:
    if isinstance(slide, WorldComputerSlide):
        return WORLD_TITLE
    if isinstance(slide, WorldFailuresSlide):
        return WORLD_FAILURES_TITLE
    if isinstance(slide, GosIntroSlide):
        return "Governance Operating System"
    if isinstance(slide, GlobeSlide):
        return "gos.earth"
    raise TypeError(type(slide).__name__)


def i18n_data(slides: list[Slide]) -> str:
    """JSON for I18N_JS: each language's rendered UNITS and page title."""
    translations = load_translations()
    strings, titles = {}, {}
    for lang, _ in LOCALES:
        t = translations.get(lang, {})
        strings[lang] = [render_inline(t.get(u, u)) for u in UNITS]
        titles[lang] = " · ".join(t.get(x, x) for x in map(slide_title, slides))
    data = json.dumps({"strings": strings, "titles": titles}, ensure_ascii=False)
    return data.replace("</", "<\\/")


def build_html(slides: list[Slide], archived: list[Slide] = ()) -> str:
    UNITS.clear()
    pages_html = []
    for i, slide in enumerate(slides):
        body = slide.render()
        pages_html.append(f"""
        <div class="page{" active" if i == 0 else ""}" data-slide="{i}" data-steps="1">
            {body}
        </div>""")
    # Archived slides render only to check them and to collect their texts.
    shipped = len(UNITS)
    for slide in archived:
        slide.render()
    ARCHIVED_UNITS[:] = UNITS[shipped:]
    del UNITS[shipped:]

    title_str = " · ".join(slide_title(s) for s in slides)
    scripts = "\n".join(f'  <script src="{src}"></script>' for src in GLOBE_SCRIPTS)
    pages_joined = "\n".join(pages_html)
    i18n = i18n_data(slides)
    options = "".join(
        f'<option value="{lang}">{html.escape(name)}</option>' for lang, name in LOCALES
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title_str)}</title>
  <style>{CSS}
  </style>
</head>
<body>
  <article class="deck">
    <div class="viewport" id="viewport">
{pages_joined}
    </div>
    <footer>
      <span class="site">{html.escape(FOOTER_SITE)}</span>
    </footer>
    <label class="lang">{LANG_ICON_SVG}<select id="lang" aria-label="Language">{options}</select></label>
    <nav class="dots" id="dots" aria-label="Slide navigation"></nav>
  </article>
  <script>window.DECK_I18N = {i18n};
  </script>
  <script>{I18N_JS}
  </script>
  <script>{DECK_JS}
  </script>
  <script>{WCX_FIT_JS}
  </script>
{scripts}
  <script>{GLOBE_JS}
  </script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    try:
        archived = parse_steps(ARCHIVE_PATH.read_text(encoding="utf-8")) if ARCHIVE_PATH.exists() else []
        page = build_html(parse_steps(MD_PATH.read_text(encoding="utf-8")), archived)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    if "--check" in argv:
        if HTML_PATH.read_text(encoding="utf-8") != page:
            print(
                f"{HTML_PATH} is stale: run python3 {Path(__file__).name}",
                file=sys.stderr,
            )
            return 1
        return 0
    HTML_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {HTML_PATH.relative_to(DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
