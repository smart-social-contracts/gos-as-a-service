"""The GGG title map, drawn with the "What is this?" deck's own isometric helpers.

python3 -I iso_map.py <path to presentation/build.py> > map.svgfrag

Plane units, as in build.py: x runs right-down, y left-down, (0, 0) is the back corner.
"""
import importlib.util
import math
import random
import sys

spec = importlib.util.spec_from_file_location("deckbuild", sys.argv[1])
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

S = 440          # the slab's side
TOP = 120        # where its back corner is drawn
T = 10           # its thickness
R = 50           # hex radius, in plane units
rnd = random.Random(7)


def iso(x, y, z=0.0):
    return b.iso(x, y, z, TOP)


# ---- hexagons on the plane --------------------------------------------------------------
HW = math.sqrt(3) * R


def hex_center(r, c):
    return c * HW + (r % 2) * HW / 2, r * 1.5 * R


def hex_corners(cx, cy):
    return [(round(cx + R * math.cos(math.radians(a)), 1), round(cy + R * math.sin(math.radians(a)), 1))
            for a in (-90, -30, 30, 90, 150, 210)]


def hexes_near(points):
    """The hex cells whose centres are nearest to the given plane points."""
    cells = set()
    for px, py in points:
        best = min(((r, c) for r in range(-1, 8) for c in range(-1, 7)),
                   key=lambda rc: math.dist(hex_center(*rc), (px, py)))
        cells.add(best)
    return cells


def outline(cells):
    count = {}
    for rc in cells:
        pts = hex_corners(*hex_center(*rc))
        for i in range(6):
            key = tuple(sorted([pts[i], pts[(i + 1) % 6]]))
            count[key] = count.get(key, 0) + 1
    return "".join(f"M{a[0]} {a[1]}L{b_[0]} {b_[1]}" for (a, b_), n in count.items() if n == 1)


grid = []
for r in range(-1, 8):
    for c in range(-1, 7):
        pts = hex_corners(*hex_center(r, c))
        grid.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")

CITY = hexes_near([(220, 150), (270, 150), (250, 210), (210, 210)])
TOWN = hexes_near([(250, 320), (300, 340)])
REGION = CITY | TOWN | hexes_near([(360, 180), (360, 300), (180, 330), (300, 260), (190, 260)])

# ---- the flat ground: roads, a lake, fields, the hex grid and the zones --------------------
def field(x, y, w, d):
    furrows = "".join(f"M{x + 3:.1f} {y + f:.1f}H{x + w - 3:.1f}" for f in range(5, int(d) - 2, 5))
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{d}" rx="3" fill="#f0f0f0" stroke="#d4d4d4"/>'
            f'<path d="{furrows}" stroke="#d6d6d6" stroke-width="1.6"/>')


flat = (
    '<clipPath id="lm-clip"><rect width="440" height="440"/></clipPath>'
    '<g clip-path="url(#lm-clip)">'
    f'<path d="{"".join(grid)}" fill="none" stroke="#e4e4e4" stroke-width="1" vector-effect="non-scaling-stroke"/>'
    # roads
    '<g fill="#fff" stroke="#d4d4d4"><rect x="-5" y="246" width="450" height="14"/><rect x="164" y="-5" width="14" height="450"/></g>'
    '<rect x="164.5" y="246.5" width="13" height="13" fill="#fff"/>'
    '<path d="M-5 253H164M178 253H445M171 -5V246M171 260V445" stroke="#d4d4d4" stroke-dasharray="5 5"/>'
    '<g fill="#737373"><rect class="wcx-car-x" x="20" y="248.5" width="10" height="4.5" rx="1.5"/>'
    '<rect class="wcx-car-y" x="166" y="30" width="4.5" height="10" rx="1.5" style="animation-delay:-3s"/></g>'
    # a lake and fields
    '<ellipse cx="96" cy="160" rx="42" ry="26" fill="#e6e6e6" stroke="#d0d0d0"/>'
    '<path d="M78 154q5-4 10 0t10 0M90 168q5-4 10 0t10 0" fill="none" stroke="#c4c4c4" stroke-width="1.3"/>'
    + field(330, 300, 70, 44) + field(350, 356, 62, 40) + field(296, 392, 46, 34)
    + '<rect x="16" y="282" width="70" height="66" rx="10" fill="#f3f3f3" stroke="#d4d4d4" stroke-dasharray="3 3"/>'
    # zones: a dashed region, and two realms inside it, tinted
    + "".join(f'<polygon points="{" ".join(f"{x},{y}" for x, y in hex_corners(*hex_center(*rc)))}" fill="rgba(107,163,163,0.08)"/>'
              for rc in CITY | TOWN)
    + f'<path d="{outline(REGION)}" fill="none" stroke="#a3a3a3" stroke-width="1.4" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>'
    f'<path d="{outline(CITY)}" fill="none" stroke="rgb(107, 163, 163)" stroke-width="2.4" vector-effect="non-scaling-stroke"/>'
    f'<path d="{outline(TOWN)}" fill="none" stroke="rgb(107, 163, 163)" stroke-width="2" vector-effect="non-scaling-stroke"/>'
    '</g>'
)

# ---- what stands on it, sorted back to front -------------------------------------------------
objects = []


def add(x, y, svg):
    objects.append((x + y, svg))


def mountain(x, y, r, h):
    p = lambda px, py, pz=0: iso(px, py, pz)
    peak = p(x, y, h)
    snow = [p(x, y, h), p(x - r * 0.28, y + r * 0.28, h * 0.72), p(x + r * 0.28, y + r * 0.28, h * 0.72)]
    snow_r = [p(x, y, h), p(x + r * 0.28, y + r * 0.28, h * 0.72), p(x + r * 0.28, y - r * 0.28, h * 0.72)]
    return (b._poly([p(x - r, y + r), p(x + r, y + r), peak], fill="#ededed")
            + b._poly([p(x + r, y - r), p(x + r, y + r), peak], fill="#dcdcdc")
            + b._poly(snow, fill="#fff") + b._poly(snow_r, fill="#f3f3f3"))


def person(x, y):
    px, py = iso(x, y)
    return f'<g transform="translate({px:.1f} {py:.1f})">{b.person_svg("#8a8a8a", scale=0.55)}</g>'


for x, y, r, h in [(40, 40, 34, 48), (100, 26, 26, 34), (34, 104, 24, 28), (128, 70, 20, 22)]:
    add(x, y, mountain(x, y, r, h))
for x, y in [(30, 300), (52, 296), (70, 312), (36, 330), (64, 338), (22, 360), (48, 372), (80, 380), (110, 300),
             (120, 340), (100, 410), (40, 410), (140, 380), (20, 230), (60, 210), (130, 200), (140, 120), (110, 230),
             (412, 250), (420, 280), (300, 30), (250, 40), (270, 70)]:
    add(x, y, b._tree(x, y, TOP, 0.85 + 0.3 * rnd.random()))
for x, y, w, d, h in [(196, 120, 22, 22, 56), (224, 122, 20, 22, 38), (250, 120, 24, 22, 68), (280, 124, 20, 20, 30),
                      (196, 150, 22, 22, 34), (226, 152, 22, 20, 48), (254, 150, 20, 20, 26),
                      (196, 180, 20, 22, 24), (224, 182, 20, 20, 30), (196, 210, 20, 20, 18), (226, 210, 22, 20, 22)]:
    add(x + w / 2, y + d / 2, b._box(x, y, w, d, h, TOP, floors=8))
for x, y, s in [(204, 290, (11, 10, 8)), (226, 300, (12, 11, 9)), (252, 292, (11, 10, 8)), (212, 324, (13, 10, 8)),
                (240, 330, (11, 10, 8)), (270, 322, (12, 11, 9)), (286, 352, (11, 10, 8)), (250, 360, (11, 10, 8))]:
    add(x, y, b._house(x - 5, y - 5, TOP, *s))
factory = (b._box(330, 150, 56, 32, 18, TOP) + b._box(360, 154, 6, 6, 22, TOP, z0=18)
           + b._box(374, 154, 7, 7, 32, TOP, z0=18) + b._smoke(377.5, 157.5, 52, TOP))
add(358, 166, factory)
add(352, 66, b._solar(330, 50, TOP))
add(400, 40, b._turbine(400, 40, TOP, 0.0))
add(420, 100, b._turbine(420, 100, TOP, 2.1))
add(372, 112, b._turbine(372, 112, TOP, 1.2))
for x, y in [(186, 236), (190, 270), (232, 268), (300, 268)]:
    add(x, y, person(x, y))

objects.sort(key=lambda o: o[0])
things = "".join(svg for _, svg in objects)

slab = b._box(0, 0, S, S, T, TOP, z0=-T)
art = (
    f'<g stroke="#a3a3a3" stroke-width="0.8" stroke-linejoin="round">{slab}</g>'
    + b._plane(TOP, flat)
    + f'<g stroke="#a3a3a3" stroke-width="0.8" stroke-linejoin="round">{things}</g>'
)
xs = [iso(0, S)[0], iso(S, 0)[0]]
sys.stdout.write(f'<!-- viewBox {xs[0] - 20:.0f} 50 {xs[1] - xs[0] + 40:.0f} {iso(S, S)[1] + T + 20 - 50:.0f} -->\n')
sys.stdout.write(art + "\n")
