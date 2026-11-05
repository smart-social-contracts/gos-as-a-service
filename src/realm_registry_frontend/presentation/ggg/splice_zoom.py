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
caption_svg = ""
for i, (title, note) in enumerate(captions):
    inner = (f'<rect x="14" y="14" width="{max(len(note) * 6.5, len(title) * 9.5) + 30:.0f}" height="52" rx="9" '
             f'fill="#fff" stroke="#e5e5e5"/><text class="t" x="28" y="37">{title}</text>'
             f'<text class="ts" x="28" y="55">{note}</text>')
    if i < len(captions) - 1:
        caption_svg += f'<g class="fxu" data-until="{i + 1}"><g class="fx" data-frag="{i}">{inner}</g></g>'
    else:
        caption_svg += f'<g class="fx" data-frag="{i}">{inner}</g>'

markers = "".join(f'<g class="zl{i + 1}" data-frag="{i}"></g>' for i in range(4))

page = f'''      <!-- ======================================================================================
           An example: from the EU to a district of València (generated: presentation/ggg/zoom_map.py, splice_zoom.py)
           ====================================================================================== -->
      <div class="page zoom-page" data-slide="7z">
        <section class="sl">
          <header class="box-header"><div class="kicker">An example</div><h2>From the European Union to a district of València</h2></header>
          <p class="lead">Each level has its own bodies and its own subdivisions. The rest of this presentation follows València.</p>
          <div class="body">
            <div class="art zmap">
              <svg viewBox="0 0 640 460" aria-label="A map that zooms from the European Union to Spain, the Comunitat Valenciana and the districts of València">
                <defs><clipPath id="z-clip"><rect width="640" height="460" rx="12"/></clipPath></defs>
                <rect width="640" height="460" rx="12" fill="#fbfbfb"/>
                <g clip-path="url(#z-clip)"><g class="zoom">
{layers}
                </g></g>
                <rect width="640" height="460" rx="12" fill="none" stroke="#e5e5e5"/>
                {markers}
                {caption_svg}
                <text class="z-credit" x="626" y="450">Map data: Natural Earth · IGN, CC BY 4.0 · Ajuntament de València, CC BY 4.0</text>
              </svg>
            </div>
            <ul class="pts">
              <li class="wc-frag" data-frag="0"><span class="wc-label">The EU: a source</span><span class="wc-note">Its legislation applies in 27 States, but it runs no realm.</span></li>
              <li class="wc-frag teal" data-frag="1"><span class="wc-label">Spain: a realm</span><span class="wc-note">Its 17 communities and 2 autonomous cities make legislation too, so each is a realm with Spain as its parent.</span></li>
              <li class="wc-frag teal" data-frag="2"><span class="wc-label">The Comunitat Valenciana: a realm</span><span class="wc-note">Each of its 542 municipalities is a realm. EMSHI, a water body of 51 of them, is a source beside the line.</span></li>
              <li class="wc-frag teal" data-frag="3"><span class="wc-label">València: one realm, 19 districts</span><span class="wc-note">The districts are zones inside it. Its 808,000 residents fill about 404 quarters.</span></li>
            </ul>
          </div>
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
    .zmap .z-credit {{ font-size: 9px; fill: var(--gray-400); text-anchor: end; }}
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
