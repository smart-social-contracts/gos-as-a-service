#!/usr/bin/env python3
"""Generate ../static/what-is-this/index.html from steps.md: the "What is this?" presentation.

python3 build.py           # write index.html
python3 build.py --check   # fail when index.html is not what steps.md builds
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
MD_PATH = DIR / "steps.md"
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
    problems = []
    for lang, _ in LOCALES[1:]:
        strings = data.get(lang, {})
        problems += [f"{lang}: missing {u!r}" for u in UNITS if not strings.get(u)]
        problems += [f"{lang}: unused {k!r}" for k in strings if k not in UNITS]
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


def computer_svg() -> str:
    """Abstract chip: a soft halo, circuit traces fading outward, pulses running along them."""
    c = 130
    lengths = [104, 88, 118, 92, 110]
    traces, nodes, pulses = [], [], []
    for side in range(4):
        cos, sin = [(1, 0), (0, 1), (-1, 0), (0, -1)][side]

        def pt(u: float, v: float) -> str:
            return f"{c + u * cos - v * sin:.1f} {c + u * sin + v * cos:.1f}"

        for k, o in enumerate((-30, -15, 0, 15, 30)):
            length = lengths[(k + side * 2) % 5]
            bend = (o > 0) - (o < 0)
            if bend:
                d = f"M{pt(46, o)}L{pt(62, o)}L{pt(74, o + bend * 12)}L{pt(length, o + bend * 12)}"
                end = pt(length, o + bend * 12)
            else:
                d = f"M{pt(46, o)}L{pt(length, o)}"
                end = pt(length, o)
            traces.append(f'<path d="{d}"/>')
            ex, ey = end.split()
            nodes.append(f'<circle cx="{ex}" cy="{ey}" r="2.6"/>')
            delay = ((side * 5 + k * 3) % 10) * 0.55
            pulses.append(
                f'<path d="{d}" pathLength="100" style="animation-delay:-{delay:.2f}s"/>'
            )
    return f"""<svg class="wc-art" viewBox="0 0 260 260" fill="none" aria-hidden="true">
  <defs>
    <radialGradient id="wc-halo">
      <stop offset="0" stop-color="#d4d4d4" stop-opacity="0.6"/>
      <stop offset="0.55" stop-color="#e5e5e5" stop-opacity="0.25"/>
      <stop offset="1" stop-color="#e5e5e5" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="wc-fade-g">
      <stop offset="0.35" stop-color="#fff"/>
      <stop offset="1" stop-color="#000"/>
    </radialGradient>
    <mask id="wc-fade" maskUnits="userSpaceOnUse" x="0" y="0" width="260" height="260">
      <rect width="260" height="260" fill="url(#wc-fade-g)"/>
    </mask>
  </defs>
  <circle class="wc-halo" cx="{c}" cy="{c}" r="128" fill="url(#wc-halo)"/>
  <g mask="url(#wc-fade)">
    <g stroke="#d4d4d4" stroke-width="1.4" stroke-linejoin="round">{"".join(traces)}</g>
    <g stroke="#c4c4c4" stroke-width="1.3" fill="#fff">{"".join(nodes)}</g>
    <g class="wc-pulses" stroke="#737373" stroke-width="1.8" stroke-linecap="round">{"".join(pulses)}</g>
  </g>
  <rect x="{c - 44}" y="{c - 44}" width="88" height="88" rx="12" fill="{ART_FILL}"/>
  <rect x="{c - 27}" y="{c - 27}" width="54" height="54" rx="7" fill="{ART_LIGHT}"/>
  <circle class="wc-core" cx="{c}" cy="{c}" r="10" fill="{ART_FILL}"/>
</svg>"""


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
    "resources": resources_svg,
    "wars": wars_svg,
}

WAR_SPREAD_KEYFRAMES = "\n".join(
    f"    @keyframes wf-spread-{d} {{ 0%, {8 + d * 15}% {{ fill: {ART_FILL}; }} "
    f"{14 + d * 15}%, 86% {{ fill: {ART_DARK}; }} 100% {{ fill: {ART_FILL}; }} }}\n"
    f"    .wf-hex.wf-d{d} {{ animation: wf-spread-{d} 8s ease-in-out infinite; }}"
    for d in range(5)
)

# The globe is one canvas shared by all slides; each slide marks where it goes with a slot.
GLOBE_HTML = '<div class="wc-art" data-globe-slot></div>'

# (illustration, mirrored: note on the outer side so the bold terms meet at the arrow)
COLUMNS: list[tuple[str, bool]] = [
    (GLOBE_HTML, True),
    (computer_svg(), False),
]

ARROW_SVG = (
    '<svg viewBox="0 0 64 16" fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M5 8h54M11 3 5 8l6 5M53 3l6 5-6 5"/></svg>'
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

  const activeSlot = () => document.querySelector('.page.active [data-globe-slot]');

  function place(animate) {
    const slot = activeSlot();
    canvas.style.transition = animate && !still ? MOVE : 'opacity 0.6s ease';
    clearTimeout(layerTimer);
    const wanted = slot && slot.dataset.globeLayer;
    if (wanted !== layer) layerTarget = 0;
    if (wanted) {
      layerTimer = setTimeout(() => {
        if (layer !== wanted || layerAlpha < 0.01) layerStart = performance.now();
        layer = wanted;
        layerTarget = 1;
      }, animate && !still ? MOVE_MS * 0.8 : 0);
    }
    if (!slot) { canvas.style.opacity = '0'; return; }
    const r = slot.getBoundingClientRect();
    const v = viewport.getBoundingClientRect();
    scale = r.width / size;
    canvas.style.transform = `translate(${r.left - v.left}px, ${r.top - v.top}px) scale(${scale})`;
    canvas.style.opacity = '1';
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    size = Math.max(...Array.from(document.querySelectorAll('[data-globe-slot]'), (s) => s.getBoundingClientRect().width));
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

  // Time into realm i's loop; each realm starts a little later than the one before.
  function cycle(i, period, now) {
    const t = still ? 0 : now - layerStart - 2000 - (i * 3700) % 15000;
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
    const states = DATA.realms.map((realm, i) => realmState(realm, i, now));
    SPLITS.forEach((i, s) => {
      const { split } = states[i];
      pos[i] = d3.geoInterpolate(DATA.realms[i].center, DATA.realms[i].split.centers[0])(split);
      presence[BASE + s] = split;
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

      if (facing(realm.center) < 0.05) return;
      ctx.lineWidth = 0.8 * k;
      ctx.strokeStyle = 'rgba(38, 38, 38, 0.4)';
      if (realm.split) {
        treeLines(realm.edges, 1 - split);
        realm.split.edges.forEach((e) => treeLines(e, split));
      } else {
        treeLines(edges, 1);
      }
      ctx.globalAlpha = layerAlpha;
      ctx.fillStyle = glowingNodes.has(i) ? `rgb(${TEAL_DARK})` : '#262626';
      if (realm.split && split > 0.5) {
        pulses(realm.split.edges[0], i);
        pulses(realm.split.edges[1], i + 0.5);
      } else {
        pulses(edges, i);
      }
    });

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
    const seconds = still ? 0 : (now - t0) / 1000;
    projection.rotate([-15 + seconds * DEG_PER_SECOND, -22]);
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

  const LAYER_FADE_MS = 700;
  const t0 = performance.now();
  let lastFrame = t0;
  function frame(now) {
    draw(now);
    requestAnimationFrame(frame);
  }

  resize();
  place(false);
  requestAnimationFrame(frame);
  window.addEventListener('deck:scene', () => place(true));
  window.addEventListener('resize', () => { resize(); place(false); });
})();
"""

CSS = (
    BASE_CSS
    + """
    /* Slides are sized in rem and never scroll, so short screens shrink the root size. */
    html { font-size: clamp(10px, 2.1vh, 16px); font-size: clamp(10px, 2.1dvh, 16px); }

    .arch-box.wc-slide { border: none; }

    .globe-canvas {
      position: absolute;
      top: 0;
      left: 0;
      z-index: 1;
      transform-origin: 0 0;
      pointer-events: none;
      opacity: 0;
      animation: wc-fade-in 0.9s ease-out both;
    }

    @keyframes wc-fade-in { from { opacity: 0; } }

    .deck > footer, .deck > .dots { position: relative; z-index: 3; }

    .lang {
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
      left: 0;
      right: 0;
      bottom: 0.4rem;
      z-index: 2;
      text-align: center;
      font-size: 1.05rem;
      letter-spacing: 0.02em;
      color: var(--gray-500);
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
      font-size: 2rem;
      font-weight: 650;
      letter-spacing: -0.01em;
      color: var(--text);
      text-decoration: none;
      transition: color 0.2s, opacity 0.45s ease-out, transform 0.45s cubic-bezier(0.2, 0.7, 0.2, 1);
    }

    .gos-link:hover { color: rgb(47, 95, 95); }

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
      gap: 2.4rem;
    }

    .wf-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 2.4rem;
    }

    .wf-item {
      display: grid;
      grid-template-columns: 10.5rem minmax(0, 1fr);
      column-gap: 2rem;
      align-items: center;
    }

    .wf-art svg { display: block; width: 10.5rem; height: 10.5rem; }

    .wf-world, .wf-pc { display: flex; align-items: baseline; gap: 0.9rem; min-width: 0; }
    .wf-world { font-size: 2.1rem; line-height: 1.25; }
    .wf-world .wc-note { font-size: 0.65em; }
    .wf-pc { font-size: 1.3rem; margin-top: 0.55rem; color: var(--gray-600); }
    .wf-world .wc-label { font-weight: 700; }
    .wf-pc .wc-label { font-weight: 600; color: var(--gray-700); white-space: normal; }
    .wf-pc .wc-note { font-size: 1em; }

    .wf-pc svg {
      width: 1.2rem;
      height: 1.2rem;
      flex-shrink: 0;
      align-self: center;
      color: var(--gray-400);
    }

    .wf-coin { animation: wf-coin 3.2s ease-in infinite; }
    .wf-slice { animation: wf-slice 4s ease-in-out infinite alternate; }
    .wf-heat { animation: wf-heat 2.4s ease-out infinite; }

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
    + """

    .wc {
      --wc-gap: 6rem;
      width: 100%;
      display: grid;
      align-items: center;
      row-gap: 0.95rem;
    }

    .wc-col-head {
      grid-row: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.1rem;
    }

    .wc-art {
      width: 17rem;
      height: 17rem;
      display: block;
    }

    .wc-halo { transform-origin: 130px 130px; animation: wc-breathe 6s ease-in-out infinite; }
    .wc-core { transform-origin: 130px 130px; animation: wc-breathe 6s ease-in-out infinite; animation-delay: -3s; }
    .wc-pulses path { stroke-dasharray: 7 93; animation: wc-pulse 5.5s linear infinite; }

    .wc-cell {
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
      font-size: 1.3rem;
      line-height: 1.3;
    }

    .wc-cell.wc-mirror { flex-direction: row-reverse; text-align: right; }

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

    .wc-arrow {
      align-self: center;
      justify-self: center;
      width: 5.5rem;
      color: var(--gray-400);
    }

    .wc-arrow svg { display: block; width: 100%; }

    .page.active .wc-col-head > svg,
    .page.active .wc-arrow { animation: wc-rise 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both; animation-delay: var(--after-move); }
    .page.active .wc-col-head > svg { animation-delay: calc(var(--after-move) + var(--c) * 0.25s); }
    .wc-arrow { margin-bottom: 1.1rem; }
    .wc-cell.wc-frag.shown:not(.wc-mirror) { transition-delay: 0.12s; }

    @keyframes wc-rise { from { opacity: 0; transform: translateY(10px); } }
    @keyframes wc-breathe { 0%, 100% { opacity: 0.65; transform: scale(0.94); } 50% { opacity: 1; transform: scale(1.04); } }
    @keyframes wc-pulse { from { stroke-dashoffset: 7; } to { stroke-dashoffset: -100; } }

    @media (prefers-reduced-motion: reduce) {
      .page.active .wc *, .page.active .wc { animation: none !important; }
      .wc-frag, .wf-item, .page.active .wc-title { transition: none; transform: none; }
      .globe-canvas, .wf-art * { animation: none !important; }
      .wc-pulses { display: none; }
      .page.active .start-hint { animation: none; opacity: 1; }
      .gos-intro-line, .gos-intro-line.shown { transition: none; transform: none; }
    }

    @media (max-width: 900px) {
      .wc { --wc-gap: 2.5rem; }
      .wc-art { width: 8rem; height: 8rem; }
      .wc-cell { font-size: 1rem; }
      .wc-arrow { width: 2rem; }
    }

    @media (max-height: 760px) and (min-aspect-ratio: 1/1) {
      .wc-art { width: 13rem; height: 13rem; }
      .wc { row-gap: 0.7rem; }
      .gos-slide { gap: 2.5rem; }
      .gos-globe-slot { height: 76%; }
    }

    @media (max-height: 500px) {
      .wf-content, .wf-list { gap: 1rem; }
      .wf-item { grid-template-columns: 6rem minmax(0, 1fr); }
      .wf-art svg { width: 6rem; height: 6rem; }
      .wf-world { font-size: 1.7rem; }
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

      .arch-box.gos-box-slide.wc-slide { padding: 0; gap: 0.9rem; }
      .wc { --wc-gap: 1.25rem; row-gap: 0.75rem; }
      .wc-col-head { gap: 0.5rem; margin-bottom: 0.4rem; }
      .wc-art { width: min(7rem, 30vw); height: min(7rem, 30vw); }
      .wc-arrow { width: 1.6rem; margin-bottom: 0.4rem; }
      .wc-cell { flex-direction: column; align-items: flex-start; gap: 0.05rem; font-size: 0.95rem; line-height: 1.25; }
      .wc-cell.wc-mirror { flex-direction: column; align-items: flex-end; }
      .wc-label { white-space: normal; }
      .wc-note { font-size: 0.8em; }

      .wf-globe-slot { left: 50%; top: 0; height: auto; width: 78%; transform: translate(-50%, -58%); }
      .wf-content { left: 0; right: 0; top: 7.5rem; justify-content: flex-start; gap: 1.4rem; }
      .wf-list { gap: 1.5rem; }
      .wf-item { grid-template-columns: 4.75rem minmax(0, 1fr); column-gap: 1rem; }
      .wf-art svg { width: 4.75rem; height: 4.75rem; }
      .wf-world, .wf-pc { flex-wrap: wrap; gap: 0.1rem 0.5rem; }
      .wf-world { font-size: 1.3rem; }
      .wf-world .wc-note { font-size: 0.68em; }
      .wf-pc { font-size: 0.92rem; margin-top: 0.35rem; }
      .wf-pc svg { width: 1rem; height: 1rem; }

      /* A grid so the intro line can share the points' row: it sits under the globe and moves nothing when it goes. */
      .gos-slide { display: grid; grid-template-columns: minmax(0, 1fr); align-content: center; gap: 1.1rem; padding: 0; }
      .gos-slide > * { grid-column: 1; }
      .gos-globe-slot { grid-row: 1; justify-self: center; height: auto; width: min(76%, 36vh); }
      .gos-left { grid-row: 2; }
      .gos-right { grid-row: 3; }
      .gos-intro-line { position: static; grid-row: 2; grid-column: 1; align-self: start; padding-top: 0.6rem; font-size: 1.45rem; }
      .gos-slide.globe-only .gos-globe-slot { width: min(92%, 70vh); }
      .gos-slide.globe-only .gos-side { display: none; }
      .gos-side { flex: none; gap: 0.75rem; }
      .gos-right { flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem 1.25rem; }
      .gos-legend { flex-direction: row; gap: 1.1rem; margin-bottom: 0; }
      .gos-legend-item { font-size: 0.95rem; gap: 0.5rem; }
      .gos-badge { width: 1.9rem; height: 1.9rem; font-size: 0.9rem; }
      .gos-badge img { height: 1.3rem; }
      .gos-link { font-size: 1.2rem; }
      .gos-head { padding-bottom: 0.5rem; margin-bottom: 0.1rem; }
      .gos-head h2 { font-size: 1.45rem; }
      .gos-kicker { font-size: 0.72rem; }
      .gos-point { gap: 0.15rem; }
      .gos-label { font-size: 1.02rem; }
      .gos-note { font-size: 0.85rem; }
    }
"""
)


def render_cell(text: str, row: int, col: int, mirrored: bool) -> str:
    label, _, note = text.strip().partition(" — ")
    note_html = f'<span class="wc-note">{tr(note)}</span>' if note else ""
    cls = "wc-cell wc-frag wc-mirror" if mirrored else "wc-cell wc-frag"
    return (
        f'<div class="{cls}" data-frag="{row + 1}" style="grid-column:{2 * col + 1};grid-row:{row + 2}">'
        f'<span class="wc-label">{tr(label)}</span>{note_html}</div>'
    )


class WorldComputerSlide(Slide):
    def render(self) -> str:
        cells = []
        for c, (art, _) in enumerate(COLUMNS):
            cells.append(
                f'<div class="wc-col-head" style="grid-column:{2 * c + 1};--c:{c}">{art}</div>'
            )
            if c:
                cells.append(
                    f'<div class="wc-arrow" style="grid-column:{2 * c};grid-row:1;--c:{c}" '
                    f'aria-hidden="true">{ARROW_SVG}</div>'
                )
        for r, (_, text) in enumerate(self.bullets):
            for c, part in enumerate(text.split("<=>")):
                cells.append(render_cell(part, r, c, COLUMNS[c][1]))
        grid = " var(--wc-gap) ".join(["minmax(0, 1fr)"] * len(COLUMNS))
        body = f"""
            <div class="page-step active">
              <section class="arch-box gos-box-slide wide-slide wc-slide">
                <header class="box-header wc-title">
                  <h2>{tr(WORLD_TITLE)}</h2>
                </header>
                <div class="box-body">
                  <div class="wc" style="grid-template-columns: {grid}">
                    {"".join(cells)}
                  </div>
                </div>
              </section>
            </div>"""
        return body


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
    """Globe in the centre with realms on it; text blocks on either side."""

    def render(self) -> str:
        sides: dict[str, list[str]] = {"left": [], "right": []}
        legend: list[str] = []
        legend_frag = 0
        side = "left"
        frag = 0
        intro = ""
        for _, text in self.bullets:
            # "intro: …" shows only before the first point, under the globe.
            m = re.match(r"^intro:\s*(.*)$", text)
            if m:
                intro = f'<p class="gos-intro-line" data-until="1">{tr(m.group(1))}</p>'
                continue
            entry = re.match(r"^legend:\s*(realms|other)\s+—\s+(.*)$", text)
            if entry:
                if not legend:
                    frag += 1
                    legend_frag = frag
                gos, label = entry.groups()
                mark = (
                    '<img src="assets/logo_sphere_only.svg" alt="">'
                    if gos == "realms"
                    else "?"
                )
                legend.append(
                    f'<div class="gos-legend-item"><span class="gos-badge gos-badge-{gos}">{mark}</span>'
                    f"{tr(label)}</div>"
                )
                continue
            link = re.match(r"^link:\s*(\S+)$", text)
            if link:
                frag += 1
                url = html.escape(link.group(1))
                sides["right"].append(
                    f'<a class="gos-link wc-frag" data-frag="{frag}" href="{url}" '
                    f'target="_blank" rel="noopener noreferrer">{url}</a>'
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
                sides[side].append(
                    f'<header class="gos-head wc-frag" data-frag="{frag}">{kicker_html}'
                    f"<h2>{tr(title)}</h2></header>"
                )
                continue
            # "A + B — note": points revealed one by one, then the note they share.
            labels, _, note = text.partition(" — ")
            labels = labels.split(" + ")
            parts = []
            for label in labels:
                frag += 1
                parts.append(
                    f'<span class="gos-label wc-frag" data-frag="{frag}">{tr(label)}</span>'
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


def build_html(slides: list[Slide]) -> str:
    UNITS.clear()
    pages_html = []
    for i, slide in enumerate(slides):
        body = slide.render()
        pages_html.append(f"""
        <div class="page{" active" if i == 0 else ""}" data-slide="{i}" data-steps="1">
            {body}
        </div>""")

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
      <label class="lang">{LANG_ICON_SVG}<select id="lang" aria-label="Language">{options}</select></label>
    </footer>
    <nav class="dots" id="dots" aria-label="Slide navigation"></nav>
  </article>
  <script>window.DECK_I18N = {i18n};
  </script>
  <script>{I18N_JS}
  </script>
  <script>{DECK_JS}
  </script>
{scripts}
  <script>{GLOBE_JS}
  </script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    try:
        page = build_html(parse_steps(MD_PATH.read_text(encoding="utf-8")))
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
