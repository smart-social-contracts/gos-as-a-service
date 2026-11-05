"""Put the zoom slide (EU -> Spain -> Comunitat Valenciana -> Valencia) into the GGG deck.

python3 -I splice_zoom.py <deck index.html> <dir with zoom.svgfrag and zoom.json>

Inserts the slide before the divider "One GOS that follows it", and its styles once. Running it
again replaces the slide and the styles it inserted before.
"""
import json
import re
import sys
from pathlib import Path

deck_path, src = Path(sys.argv[1]), Path(sys.argv[2])
deck = deck_path.read_text(encoding="utf-8")
layers = (src / "zoom.svgfrag").read_text(encoding="utf-8").strip()
meta = json.loads((src / "zoom.json").read_text(encoding="utf-8"))
transforms = {level: t for level, t, *_ in meta["css"]}

labels = "".join(
    f'<text class="z-label" x="{x:.2f}" y="{y:.2f}">{name}</text>' for name, x, y in meta["labels"]
)
layers = layers.replace('<g class="z-l4"><path class="z-dist" d="', f'<g class="z-l4">{labels}<path class="z-dist" d="', 1)
# labels go after the districts so they sit on top
layers = re.sub(r'(<g class="z-l4">)(.*?)(<path class="z-dist" d="[^"]*"/>)', r"\1\3\2", layers, count=1, flags=re.S)

captions = [
    ("European Union", "27 member states · a source of legislation, with no realm"),
    ("Spain", "17 autonomous communities and 2 autonomous cities"),
    ("Comunitat Valenciana", "542 municipalities · shaded: EMSHI's 51 member towns"),
    ("València", "19 districts: zones of one realm"),
]
caption_html = ""
for i, (title, note) in enumerate(captions):
    inner = f'<div class="z-cap fx" data-frag="{i}"><b>{title}</b><span>{note}</span></div>'
    caption_html += f'<div class="fxu" data-until="{i + 1}">{inner}</div>' if i < len(captions) - 1 else inner

markers = "".join(f'<g class="zl{i + 1}" data-frag="{i}"></g>' for i in range(4))

# The map fills the whole window; the heading, the caption, the points and the credit float over it.
page = f'''      <!-- ======================================================================================
           An example: from the EU to a district of València (generated: presentation/ggg/zoom_map.py, splice_zoom.py)
           ====================================================================================== -->
      <div class="page zoom-page" data-slide="7z">
        <div class="zmap">
          <svg viewBox="0 0 640 460" aria-label="A map that zooms from the European Union to Spain, the Comunitat Valenciana and the districts of València">
            <g class="zoom">
{layers}
            </g>
            {markers}
          </svg>
        </div>
        <section class="sl zoom-over">
          <header class="box-header"><div class="kicker">An example</div><h2>From the European Union to a district of València</h2></header>
          <p class="lead">Each level has its own bodies and its own subdivisions. The rest of this presentation follows València.</p>
          <div class="z-caps">{caption_html}</div>
          <ul class="pts">
            <li class="wc-frag" data-frag="0"><span class="wc-label">The EU: a source</span><span class="wc-note">Its legislation applies in 27 States, but it runs no realm.</span></li>
            <li class="wc-frag teal" data-frag="1"><span class="wc-label">Spain: a realm</span><span class="wc-note">Its 17 communities and 2 autonomous cities make legislation too, so each is a realm with Spain as its parent.</span></li>
            <li class="wc-frag teal" data-frag="2"><span class="wc-label">The Comunitat Valenciana: a realm</span><span class="wc-note">Each of its 542 municipalities is a realm. EMSHI, a water body of 51 of them, is a source beside the line.</span></li>
            <li class="wc-frag teal" data-frag="3"><span class="wc-label">València: one realm, 19 districts</span><span class="wc-note">The districts are zones inside it. Its 808,000 residents fill about 404 quarters.</span></li>
          </ul>
          <p class="z-credit">Map data: Natural Earth · IGN, CC BY 4.0 · Ajuntament de València, CC BY 4.0</p>
        </section>
      </div>

'''

css = f'''
    /* ---- the zoom map: EU, Spain, the Comunitat Valenciana, València (one level per click) -- */
    .zmap .zoom {{ transform-box: view-box; transform-origin: 0 0; transform: {transforms[1]}; transition: transform 1.6s cubic-bezier(0.45, 0, 0.2, 1); }}
    .zmap:has(.zl2.shown) .zoom {{ transform: {transforms[2]}; }}
    .zmap:has(.zl3.shown) .zoom {{ transform: {transforms[3]}; }}
    .zmap:has(.zl4.shown) .zoom {{ transform: {transforms[4]}; }}
    .zmap path {{ vector-effect: non-scaling-stroke; stroke-linejoin: round; }}
    .zmap .z-land {{ fill: #f2f2f2; stroke: #e2e2e2; stroke-width: 0.8; }}
    .zmap .z-eu {{ fill: #fff; stroke: #a3a3a3; stroke-width: 0.8; }}
    .zmap .z-hl {{ fill: rgba(107, 163, 163, 0.22); stroke: rgb(47, 95, 95); stroke-width: 1.6; opacity: 0; transition: opacity 0.6s ease; }}
    .zmap:has(.zl1.shown):not(:has(.zl2.shown)) .z-hl1,
    .zmap:has(.zl2.shown):not(:has(.zl3.shown)) .z-hl2,
    .zmap:has(.zl3.shown):not(:has(.zl4.shown)) .z-hl3 {{ opacity: 1; transition: opacity 0.8s ease 1.2s; }}
    .zmap :is(.z-l2, .z-l3, .z-l4) {{ opacity: 0; transition: opacity 0.6s ease; }}
    .zmap:has(.zl2.shown) .z-l2, .zmap:has(.zl3.shown) .z-l3, .zmap:has(.zl4.shown) .z-l4 {{ opacity: 1; transition: opacity 0.8s ease 0.9s; }}
    .zmap:has(.zl4.shown) :is(.z-l2, .z-l3) {{ opacity: 0; }}
    .zmap :is(.z-eu, .z-land) {{ transition: opacity 0.6s ease; }}
    .zmap:has(.zl4.shown) :is(.z-eu, .z-land) {{ opacity: 0; }}
    .zmap .z-ccaa {{ fill: none; stroke: #a3a3a3; stroke-width: 0.8; }}
    .zmap .z-inset {{ fill: #fbfbfb; stroke: #d4d4d4; stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; }}
    .zmap .z-muni {{ fill: none; stroke: #c4c4c4; stroke-width: 0.5; }}
    .zmap .z-emshi {{ fill: rgba(115, 115, 115, 0.22); stroke: none; }}
    .zmap .z-dist {{ fill: rgba(107, 163, 163, 0.1); stroke: rgb(47, 95, 95); stroke-width: 1.2; }}
    .zmap .z-label {{ font-size: 0.75px; font-weight: 650; fill: var(--gray-800); text-anchor: middle; paint-order: stroke; stroke: #fff; stroke-width: 0.18px; stroke-linejoin: round; }}
    /* full window: the page covers the deck, the footer and the dots stay above it */
    footer, .dots {{ position: relative; z-index: 3; }}
    .zoom-page {{ position: fixed; inset: 0; background: #fbfbfb; overflow: hidden; }}
    .zoom-page::before, .zoom-page::after {{ content: ""; position: absolute; left: 0; right: 0; z-index: 1; pointer-events: none; }}
    .zoom-page::before {{ top: 0; height: 13rem; background: linear-gradient(#fbfbfb 55%, rgba(251, 251, 251, 0)); }}
    .zoom-page::after {{ bottom: 0; height: 6rem; background: linear-gradient(rgba(251, 251, 251, 0), #fbfbfb 70%); }}
    .zoom-page .zmap {{ position: absolute; top: 14.5rem; bottom: 5.5rem; left: 2.5rem; right: max(2.5rem, calc((100vw - 84rem) / 2 + 28rem)); }}
    .zoom-page .zmap svg {{ display: block; width: 100%; height: 100%; overflow: visible; }}
    .zoom-over {{ z-index: 2; width: min(89rem, 100%); padding: 1.65rem 2.5rem 4.6rem; pointer-events: none; }}
    .z-caps {{ display: grid; justify-items: start; align-items: start; }}
    .z-caps > * {{ grid-area: 1 / 1; }}
    .z-cap {{ display: flex; flex-direction: column; gap: 0.15rem; padding: 0.55rem 0.9rem; background: #fff; border: 1px solid var(--gray-200); border-radius: 9px; }}
    .z-cap b {{ font-size: 1.05rem; font-weight: 700; color: var(--gray-900); }}
    .z-cap span {{ font-size: 0.88rem; color: var(--gray-500); }}
    .zoom-over .pts {{ position: absolute; right: 2.5rem; top: 10.5rem; width: 25rem; gap: 0.8rem; }}
    .zoom-over .pts li {{ padding: 0.85rem 1.1rem; background: rgba(255, 255, 255, 0.94); border: 1px solid var(--gray-200); border-left-width: 3px; border-radius: 10px; box-shadow: 0 6px 24px rgba(23, 23, 23, 0.05); }}
    .zoom-over .pts li.teal {{ border-left-color: var(--teal); }}
    .zoom-over .pts li.shown:has(~ li.shown) {{ padding-block: 0.55rem; }}
    .zoom-over .pts li.shown:has(~ li.shown) .wc-label {{ font-size: 1.05rem; color: var(--gray-600); }}
    .zoom-over .pts li.shown:has(~ li.shown) .wc-note {{ display: none; }}
    .zoom-over .z-credit {{ position: absolute; right: 2.5rem; bottom: 4.4rem; font-size: 0.72rem; color: var(--gray-400); }}
    @media (max-aspect-ratio: 1/1) {{
      .zoom-page::before {{ height: 10rem; }}
      .zoom-page .zmap {{ top: 9.5rem; bottom: 12rem; left: 1rem; right: 1rem; }}
      .zoom-over {{ overflow: hidden; padding: 1.15rem 1rem 3.6rem; }}
      .zoom-over .lead {{ display: none; }}
      .z-cap {{ padding: 0.4rem 0.7rem; }}
      .z-cap b {{ font-size: 0.92rem; }}
      .z-cap span {{ font-size: 0.78rem; }}
      .zoom-over .pts {{ top: auto; bottom: 4.9rem; left: 1rem; right: 1rem; width: auto; }}
      .zoom-over .pts li {{ padding: 0.6rem 0.8rem; }}
      .zoom-over .pts li:not(.shown), .zoom-over .pts li.shown:has(~ li.shown) {{ display: none; }}
      .zoom-over .z-credit {{ left: 1rem; right: 1rem; bottom: 3.4rem; font-size: 0.6rem; text-align: right; }}
    }}
    /* ---- end of the zoom map */
'''

# replace an earlier insertion, if any
deck = re.sub(r"      <!-- =+\n           An example: from the EU.*?(?=      <div class=\"page\" data-slide=\"8\">)", "", deck, flags=re.S)
deck = re.sub(r"\n    /\* ---- the zoom map:.*?/\* ---- end of the zoom map \*/\n", "\n", deck, flags=re.S)

anchor = '      <div class="page" data-slide="8">\n        <section class="divider">'
if anchor not in deck:
    sys.exit("divider not found")
deck = deck.replace(anchor, page + anchor, 1)
css_anchor = "    /* ---- the title and closing slides"
deck = deck.replace(css_anchor, css.lstrip("\n") + "\n" + css_anchor, 1)
deck_path.write_text(deck, encoding="utf-8")
print("zoom slide inserted;", len(page), "bytes")
