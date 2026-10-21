#!/usr/bin/env node
// Writes ../static/what-is-this/assets/realms.js: example realms as clusters of H3
// cells (resolution 2), the links between them, and a faint grid of the cells around
// each realm. Some realms grow ring by ring, some split in two (and merge back) while
// the slide is on. Uses the portal's h3-js: `node make-realms.cjs`.

const fs = require("fs");
const path = require("path");
const h3 = require("h3-js");

const RES = 2;
const GRID_RING = 4;

// [lon, lat, radius in cells, options]
//   grow: rings shown at first; the realm grows to `radius` and falls back, in a loop.
//   split: direction (degrees) of the seam along which the realm splits in two.
const CENTERS = [
  [-9.1, 38.7, 2],
  [13.4, 52.5, 3, { grow: 1 }],
  [3.4, 6.5, 3, { split: 70 }],
  [36.8, -1.3, 3, { grow: 1 }],
  [31.2, 30.0, 2],
  [55.3, 25.2, 1],
  [72.9, 19.1, 3, { split: 20 }],
  [-46.6, -23.5, 3, { split: 110 }],
  [-74.0, 40.7, 3, { grow: 1 }],
  [-99.1, 19.4, 2],
  [-74.1, 4.7, 2],
  [103.8, 1.35, 3, { grow: 1 }],
  [139.7, 35.7, 2],
  [151.2, -33.9, 3, { grow: 1 }],
];

// Realms that run some other GOS; the rest run Realms GOS. A split-off half runs
// the other kind.
const OTHER_GOS = new Set([2, 5, 7, 9, 12]);

const LINKS = [
  [0, 1], [0, 2], [1, 4], [2, 3], [3, 4], [4, 5], [5, 6], [6, 3], [6, 11], [11, 12], [11, 13], [12, 13],
  [0, 8], [8, 1], [8, 9], [9, 10], [10, 7], [7, 2], [12, 9],
];

// Cells whose centre is within this many degrees of the seam line empty out on a split.
const SEAM_DEGREES = 1.2;

let seed = 7;
const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const round = (n) => Math.round(n * 100) / 100;

// h3 returns GeoJSON rings (counter-clockwise); d3-geo reads a ring as the smaller area
// only when it is clockwise.
function ring(cell) {
  return h3.cellToBoundary(cell, true).map(([lon, lat]) => [round(lon), round(lat)]).reverse();
}

const centerOf = (cell) => {
  const [lat, lon] = h3.cellToLatLng(cell);
  return [round(lon), round(lat)];
};

// Breadth-first tree over `cells` from `root`: [from, to, ring of `to`] per edge.
function treeEdges(root, cells, origin) {
  const inSet = new Set(cells);
  const seen = new Set([root]);
  const queue = [root];
  const edges = [];
  while (queue.length) {
    const cell = queue.shift();
    for (const next of h3.gridDisk(cell, 1)) {
      if (!inSet.has(next) || seen.has(next)) continue;
      seen.add(next);
      queue.push(next);
      edges.push([centerOf(cell), centerOf(next), h3.gridDistance(origin, next)]);
    }
  }
  return edges;
}

function splitSides(origin, cells, degrees) {
  const [lat0, lon0] = h3.cellToLatLng(origin);
  const a = (degrees * Math.PI) / 180;
  return cells.map((cell) => {
    const [lat, lon] = h3.cellToLatLng(cell);
    const d = (lon - lon0) * Math.cos((lat0 * Math.PI) / 180) * Math.cos(a) + (lat - lat0) * Math.sin(a);
    return Math.abs(d) < SEAM_DEGREES ? -1 : d > 0 ? 1 : 0;
  });
}

// The cell of `cells` nearest their average position.
function middleCell(cells) {
  const points = cells.map((c) => h3.cellToLatLng(c));
  const lat = points.reduce((s, p) => s + p[0], 0) / points.length;
  const lon = points.reduce((s, p) => s + p[1], 0) / points.length;
  const dist = (p) => (p[0] - lat) ** 2 + (p[1] - lon) ** 2;
  return cells[points.indexOf(points.reduce((best, p) => (dist(p) < dist(best) ? p : best)))];
}

const taken = new Set();
const realms = CENTERS.map(([lon, lat, radius, options = {}], index) => {
  const origin = h3.latLngToCell(lat, lon, RES);
  const cells = h3.gridDisk(origin, radius).filter((cell) => {
    const d = h3.gridDistance(origin, cell);
    return d < radius || random() < 0.55;
  });
  const rings = cells.map((cell) => h3.gridDistance(origin, cell));
  cells.forEach((c, i) => {
    if (options.grow === undefined || rings[i] <= options.grow) taken.add(c);
  });
  const gos = OTHER_GOS.has(index) ? "other" : "realms";
  const realm = {
    center: centerOf(origin),
    gos,
    cells: cells.map((cell, i) => ({ ring: rings[i], polygon: ring(cell) })),
    edges: treeEdges(origin, cells, origin),
  };
  if (options.grow !== undefined) realm.grow = options.grow;
  if (options.split !== undefined) {
    const sides = splitSides(origin, cells, options.split);
    sides.forEach((side, i) => (realm.cells[i].side = side));
    const halves = [0, 1].map((side) => cells.filter((_, i) => sides[i] === side));
    const middles = halves.map(middleCell);
    realm.split = {
      gos: gos === "other" ? "realms" : "other",
      centers: middles.map(centerOf),
      edges: halves.map((half, k) => treeEdges(middles[k], half, origin)),
    };
  }
  return realm;
});

const grid = [];
const gridSeen = new Set();
CENTERS.forEach(([lon, lat]) => {
  const origin = h3.latLngToCell(lat, lon, RES);
  for (const cell of h3.gridDisk(origin, GRID_RING)) {
    if (taken.has(cell) || gridSeen.has(cell)) continue;
    gridSeen.add(cell);
    grid.push({ ring: h3.gridDistance(origin, cell), polygon: ring(cell) });
  }
});

const out = path.join(__dirname, "..", "static", "what-is-this", "assets", "realms.js");
fs.writeFileSync(
  out,
  "// Generated by make-realms.cjs (H3 resolution " + RES + ").\n" +
    "window.GOS_REALMS = " + JSON.stringify({ realms, links: LINKS, grid }) + ";\n",
);
console.log(`Wrote ${out}: ${realms.length} realms, ${grid.length} grid cells`);
for (const [i, r] of realms.entries()) {
  if (!r.split) continue;
  const count = (s) => r.cells.filter((c) => c.side === s).length;
  console.log(`  realm ${i} splits: ${count(0)} + ${count(1)} cells, seam ${count(-1)}`);
}
