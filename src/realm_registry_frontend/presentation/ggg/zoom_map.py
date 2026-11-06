"""The zoom map of the GGG deck: EU -> Spain -> Comunitat Valenciana -> Valencia's districts.

python3 -I zoom_map.py <geo-data dir> <out dir>

Writes <out>/zoom.svgfrag (the zooming group and its layers) and <out>/zoom.css (the transform
of each level). Everything is projected once (Lambert azimuthal equal-area, centred on Europe,
in km, y pointing down) and simplified per level, so the deck holds plain SVG paths.

Sources: Natural Earth (public domain); Instituto Geografico Nacional, via the georef-spain
datasets (CC BY 4.0); Ajuntament de Valencia, open data (CC BY 4.0).
"""
import json
import math
import sys
from pathlib import Path

GEO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
VIEW_W, VIEW_H = 640, 460

EU = {"AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA",
      "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"}
EMSHI = set("46005,46007,46009,46013,46014,46015,46021,46022,46025,46026,46032,46054,46065,46074,46078,46093,"
            "46094,46117,46126,46135,46152,46156,46159,46163,46164,46165,46166,46169,46171,46172,46176,46177,"
            "46186,46190,46193,46194,46199,46205,46204,46102,46207,46212,46216,46903,46223,46230,46237,46244,"
            "46250,46260,46110".split(","))

LAT0, LON0, RADIUS = math.radians(52), math.radians(10), 6371.0


def project(lon, lat):
    la, lo = math.radians(lat), math.radians(lon)
    k = math.sqrt(2 / (1 + math.sin(LAT0) * math.sin(la) + math.cos(LAT0) * math.cos(la) * math.cos(lo - LON0)))
    x = RADIUS * k * math.cos(la) * math.sin(lo - LON0)
    y = RADIUS * k * (math.cos(LAT0) * math.sin(la) - math.sin(LAT0) * math.cos(la) * math.cos(lo - LON0))
    return x, -y


def rings(geometry):
    if geometry["type"] == "Polygon":
        polys = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polys = geometry["coordinates"]
    else:
        return []
    return [ring for poly in polys for ring in poly]


def simplify(points, tol):
    """Douglas-Peucker on a closed ring."""
    if len(points) < 4:
        return points

    def dp(pts):
        a, b = pts[0], pts[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / norm
            if d > best:
                best, idx = d, i
        if best <= tol:
            return [a, b]
        return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])

    far = max(range(len(points)), key=lambda i: math.dist(points[0], points[i]))
    return dp(points[: far + 1])[:-1] + dp(points[far:])


def area(points):
    return abs(sum(points[i][0] * points[i - 1][1] - points[i - 1][0] * points[i][1] for i in range(len(points)))) / 2


def path(geometry, tol, digits, shift=(0, 0), keep=lambda pt: True, min_area=0.0, move=None):
    parts = []
    for ring in rings(geometry):
        pts = [project(lon, lat) for lon, lat in ring]
        pts = [(x + shift[0], y + shift[1]) for x, y in pts]
        if move:
            pts = [move(p) for p in pts]
        if not keep(pts[0]):
            continue
        pts = simplify(pts, tol)
        if len(pts) < 3 or area(pts) < min_area:
            continue
        f = f"{{:.{digits}f}}"
        parts.append("M" + "L".join(f"{f.format(x)} {f.format(y)}" for x, y in pts) + "Z")
    return "".join(parts)


def bbox(paths_points):
    xs = [x for x, _ in paths_points]
    ys = [y for _, y in paths_points]
    return min(xs), min(ys), max(xs), max(ys)


def points_of(features):
    return [project(lon, lat) for f in features for ring in rings(f["geometry"]) for lon, lat in ring]


def load(name):
    return json.load(open(GEO / name, encoding="utf-8"))["features"]


countries, ccaa, munis, districts = load("countries.geojson"), load("ccaa.geojson"), load("cv_municipios.geojson"), load("districtes.geojson")


def in_europe(pt):
    x, y = pt
    return -3200 < x < 2600 and -2600 < y < 2200


def first(value):
    return value[0] if isinstance(value, list) else value


# ---- level 1: Europe, the EU's members, Spain highlighted --------------------------------
out = []
eu_d, other_d, spain_d = [], [], ""
for f in countries:
    a3 = f["properties"].get("ADM0_A3")
    d = path(f["geometry"], 4.0, 0, keep=in_europe, min_area=60)
    if not d:
        continue
    if a3 == "ESP":
        spain_d = d
    (eu_d if a3 in EU else other_d).append(d)
out.append(f'<path class="z-land" d="{"".join(other_d)}"/>')
out.append(f'<path class="z-eu" d="{"".join(eu_d)}"/>')
out.append(f'<path class="z-hl z-hl1" d="{spain_d}"/>')

# ---- level 2: Spain's communities and autonomous cities; Canarias in an inset ---------------
mainland = [f for f in ccaa if first(f["properties"]["acom_name"]) not in ("Canarias", "Territorio no asociado a ninguna autonomía")]
canarias = [f for f in ccaa if first(f["properties"]["acom_name"]) == "Canarias"]
cv = [f for f in ccaa if first(f["properties"]["acom_name"]) == "Comunitat Valenciana"]
sx0, sy0, sx1, sy1 = bbox(points_of(mainland))
cx0, cy0, cx1, cy1 = bbox(points_of(canarias))
# Canarias, at 0.55 of its size, in a box over the ocean at the frame's bottom-left corner
K = 0.55
iw, ih = (cx1 - cx0) * K + 24, (cy1 - cy0) * K + 24
ix, iy = sx0 - 30, sy1 - ih + 10
move = lambda p: (ix + 12 + (p[0] - cx0) * K, iy + 12 + (p[1] - cy0) * K)
ccaa_d = "".join(path(f["geometry"], 1.2, 1, min_area=2) for f in mainland)
can_d = "".join(path(f["geometry"], 0.8, 1, min_area=1, move=move) for f in canarias)
out.append(f'<g class="z-l2"><path class="z-ccaa" d="{ccaa_d}"/>'
           f'<rect class="z-inset" x="{ix:.0f}" y="{iy:.0f}" width="{iw:.0f}" height="{ih:.0f}"/>'
           f'<path class="z-ccaa" d="{can_d}"/></g>')
out.append(f'<path class="z-hl z-hl2" d="{"".join(path(f["geometry"], 1.2, 1) for f in cv)}"/>')

# ---- level 3: the Comunitat's 542 municipalities; EMSHI's members; Valencia ------------------
muni_d, emshi_d, vlc_d = [], [], ""
for f in munis:
    code = first(f["properties"]["mun_code"])
    d = path(f["geometry"], 0.4, 1, min_area=0.05)
    muni_d.append(d)
    if code in EMSHI:
        emshi_d.append(d)
    if code == "46250":
        vlc_d = path(f["geometry"], 0.03, 2)               # Valencia itself stays sharp when zoomed in
out.append(f'<g class="z-l3"><path class="z-emshi" d="{"".join(emshi_d)}"/><path class="z-muni" d="{"".join(muni_d)}"/></g>')
out.append(f'<path class="z-hl z-hl3" d="{vlc_d}"/>')

# ---- level 4: Valencia's 19 districts -----------------------------------------------------
dist_d = "".join(path(f["geometry"], 0.02, 2) for f in districts)
out.append(f'<g class="z-l4"><path class="z-dist" d="{dist_d}"/></g>')

# district labels (two the example uses)
labels = []
for name, label, dx, dy in (("CIUTAT VELLA", "Ciutat Vella", -0.9, 0.55), ("BENIMACLET", "Benimaclet", 0.9, -0.35)):
    pts = [project(lon, lat) for f in districts if f["properties"]["nombre"] == name for ring in rings(f["geometry"]) for lon, lat in ring]
    x0, y0, x1, y1 = bbox(pts)
    labels.append((label, (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy))

# ---- the four frames --------------------------------------------------------------------------
eu_pts = [p for f in countries if f["properties"].get("ADM0_A3") in EU for ring in rings(f["geometry"])
          for p in (project(lon, lat) for lon, lat in ring) if in_europe(p)]
frames = {
    1: bbox(eu_pts),
    2: (sx0, sy0, sx1, sy1),
    3: bbox(points_of(cv)),
    4: bbox(points_of(districts)),
}
css = []
for level, (x0, y0, x1, y1) in frames.items():
    s = 0.94 * min(VIEW_W / (x1 - x0), VIEW_H / (y1 - y0))
    fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
    css.append((level, f"translate({VIEW_W / 2}px, {VIEW_H / 2}px) scale({s:.5f}) translate({-fx:.3f}px, {-fy:.3f}px)", s, fx, fy))

(OUT / "zoom.svgfrag").write_text("\n".join(out) + "\n", encoding="utf-8")
(OUT / "zoom.json").write_text(json.dumps({"css": css, "labels": labels}, indent=1), encoding="utf-8")
print({k: len(v) for k, v in (("svg", "\n".join(out)),)}, [c[2] for c in css])
