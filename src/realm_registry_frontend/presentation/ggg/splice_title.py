"""Put the isometric title map into the GGG deck.

python3 -I splice_title.py <deck index.html> <map.svgfrag>

- removes the old flat hex map's symbols (from "<!-- the title map:" to "<!-- the hub:");
- replaces the title slide's art with the new map, inline (so its CSS animations run);
- adds the styles the map's turbines, smoke and cars need, once.
"""
import re
import sys

deck_path, frag_path = sys.argv[1], sys.argv[2]
deck = open(deck_path, encoding="utf-8").read()
frag = open(frag_path, encoding="utf-8").read()

viewbox = re.match(r"<!-- viewBox (.*?) -->\n", frag).group(1)
art = frag.split("\n", 1)[1].strip()

start = deck.index("      <!-- the title map:")
end = deck.index("      <!-- the hub:")
deck = deck[:start] + deck[end:]

old_art = re.search(r'<div class="art map"><svg viewBox="[^"]*" aria-label="[^"]*"><use href="#landmap"/></svg></div>', deck)
if old_art is None:
    sys.exit("title art not found")
new_art = (f'<div class="art map"><svg viewBox="{viewbox}" aria-label="An abstract landscape: mountains, a lake, '
           f'forest, fields, a town, a city, industry and wind turbines, with realms outlined on a hexagonal grid">'
           f'{art}</svg></div>')
deck = deck[:old_art.start()] + new_art + deck[old_art.end():]

css = """
    /* The title map's moving parts, as in the "What is this?" deck's ground. */
    .wcx-rotor { animation: wcx-spin 4.5s linear infinite; }
    .wcx-smoke { transform-box: fill-box; transform-origin: center; animation: wcx-smoke 3.6s ease-out infinite; opacity: 0; }
    .wcx-car-x { animation: wcx-drive-x 9s linear infinite; }
    .wcx-car-y { animation: wcx-drive-y 10s linear infinite; }
    @keyframes wcx-spin { to { transform: rotate(360deg); } }
    @keyframes wcx-smoke {
      0% { opacity: 0; transform: scale(0.5); }
      20% { opacity: 0.85; }
      100% { opacity: 0; transform: translate(-9px, -24px) scale(1.7); }
    }
    @keyframes wcx-drive-x { to { transform: translateX(400px); } }
    @keyframes wcx-drive-y { to { transform: translateY(400px); } }
"""
anchor = "    @keyframes flow { to { stroke-dashoffset: -12; } }\n"
if ".wcx-rotor" not in deck:
    deck = deck.replace(anchor, anchor + css, 1)
reduced = "      .flow, .page.active .start-hint { animation: none !important; }"
deck = deck.replace(reduced, "      .flow, .page.active .start-hint, .wcx-rotor, .wcx-smoke, .wcx-car-x, .wcx-car-y { animation: none !important; }", 1)

open(deck_path, "w", encoding="utf-8").write(deck)
print("spliced", viewbox, len(art))
