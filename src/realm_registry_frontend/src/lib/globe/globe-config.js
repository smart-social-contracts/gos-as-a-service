/** Zoom-adaptive H3 + map styling for the registry map. */

/**
 * Resolution used when fetching zone data from realm backends.
 * Also the finest H3 cell the browse map will *display* — average edge
 * ≈ 3.2 km (~3,230 m) / area ≈ 35 km². Finer display cells (res 7–8)
 * were disappearing under MapLibre's globe→mercator transition.
 */
export const ZONE_DATA_RESOLUTION = 6;

/** Do not render browse hexes finer than the zone-data resolution. */
export const MAX_H3_DISPLAY_RESOLUTION = ZONE_DATA_RESOLUTION;

export const MAP_BG = '#FAFAFA';
export const FLY_TO_MS = 900;
export const DIM_OPACITY = 0.35;

/** Max display footprint vs true res-6 zone union (area ratio). */
export const HEX_AREA_INFLATION_MAX = 1.45;

/** Realms with more res-6 zone cells skip influence rings (perf guard). */
export const HEX_INFLUENCE_MAX_TRUTH_CELLS = 24;

/**
 * Zoom where MapLibre's globe projection starts flattening toward mercator.
 * Above this we force mercator so GeoJSON hex fills stay visible.
 */
export const MERCATOR_PROJECTION_MIN_ZOOM = 6;

/** Leaflet/MapLibre zoom → H3 display resolution (coarse far, fine near). */
export function h3ResolutionForZoom(zoom) {
  let res = 2;
  if (zoom >= 3) res = 3;
  if (zoom >= 5) res = 4;
  if (zoom >= 7) res = 5;
  if (zoom >= 9) res = 6;
  // Previously climbed to 7–8; cap at zone-data resolution so capital hexes
  // remain a stable ~3 km cell when zoomed in.
  return Math.min(res, MAX_H3_DISPLAY_RESOLUTION);
}

/**
 * Stable key for hex display — only changes when fidelity / coarse-res rules change.
 * @param {number} zoom
 */
export function hexDisplayZoomKey(zoom) {
  const coarse = h3ResolutionForZoom(zoom);
  const maxFine = zoom >= 7 ? ZONE_DATA_RESOLUTION : coarse;
  return `${coarse}:${maxFine}`;
}

/** Influence rings only at full zone resolution (res 6). */
export function influenceRingsForResolution(resolution) {
  return resolution >= ZONE_DATA_RESOLUTION ? 1 : 0;
}

/** Max hex polygons to render at each resolution (performance). */
export function hexCapForResolution(resolution) {
  if (resolution <= 2) return 80;
  if (resolution <= 3) return 160;
  if (resolution <= 4) return 320;
  if (resolution <= 5) return 800;
  // Headroom for every capital cell + a ring of influence.
  if (resolution <= 6) return 4000;
  if (resolution <= 7) return 4000;
  return 4000;
}

/**
 * Soft teal/gray hex styling — close to staging IC map, light Realms aesthetic.
 * @param {number} distance
 */
export function hexStyle(distance, { totalUsers = 0, hasMultipleRealms = false, h3Resolution = 6 } = {}) {
  const userBoost = Math.min((totalUsers / 50) * 0.1, 0.12);
  const fine = h3Resolution >= 6;

  if (distance === 0) {
    return {
      fill: hasMultipleRealms ? '#5B8A8A' : '#6BA3A3',
      // Slightly stronger when fine so capital hexes stay obvious at city zoom.
      opacity: Math.min((fine ? 0.52 : 0.34) + userBoost, 0.72),
      weight: fine ? 2 : 1.2,
    };
  }
  if (distance === 1) {
    return {
      fill: '#8BB8B8',
      stroke: '#3A3A3A',
      opacity: (fine ? 0.22 : 0.16) + userBoost * 0.35,
      weight: fine ? 1.1 : 0.9,
    };
  }
  return {
    fill: '#A8C9C9',
    stroke: '#5A5A5A',
    opacity: fine ? 0.12 : 0.08,
    weight: 0.7,
  };
}

/** @deprecated use hexStyle */
export function grayHexStyle(distance, opts = {}) {
  return hexStyle(distance, opts);
}

/** @param {string} color */
function parseRgbColor(color) {
  if (typeof color !== 'string') return null;
  const rgb = color.match(/rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/i);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  const hex = color.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = Number.parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  return null;
}

/**
 * Darken an rgb/hex color for subtler basemap tuning.
 * @param {string} color
 * @param {number} amount 0 = unchanged, 1 = black
 */
function darkenColor(color, amount = 0.2) {
  const rgb = parseRgbColor(color);
  if (!rgb) return color;
  const factor = 1 - Math.max(0, Math.min(1, amount));
  return `rgb(${rgb.map((channel) => Math.round(channel * factor)).join(', ')})`;
}

/**
 * Abstract Realms basemap: land / water / roads only.
 * Strips political borders, all place/water labels, and shields.
 * @param {object} style
 */
export function stripPoliticalLayers(style) {
  if (!style?.layers) return style;
  const next = { ...style, layers: [] };
  for (const layer of style.layers) {
    const id = String(layer.id || '').toLowerCase();
    const sourceLayer = String(layer['source-layer'] || '').toLowerCase();
    const type = String(layer.type || '').toLowerCase();

    const isBoundary =
      sourceLayer.includes('boundary') ||
      sourceLayer === 'admin' ||
      id.includes('boundary') ||
      id.includes('admin') ||
      id.includes('disputed');

    const isLabel =
      type === 'symbol' ||
      id.includes('label') ||
      id.includes('name') ||
      id.includes('shield') ||
      id.includes('airport') ||
      sourceLayer.includes('place') ||
      sourceLayer.includes('housenumber') ||
      sourceLayer === 'poi' ||
      sourceLayer.includes('mountain_peak') ||
      sourceLayer.includes('water_name') ||
      sourceLayer.includes('transportation_name');

    if (isBoundary || isLabel) continue;
    next.layers.push(layer);
  }
  // Neutral lighting — no day/night terminator on the globe
  delete next.light;
  return next;
}

/**
 * Glass-like basemap for globe view.
 *
 * MapLibre still depth-occludes WebGL layers on the far hemisphere — fill opacity alone
 * cannot reveal them. Softening here makes the *front* shell translucent so page
 * background (and DOM markers with opacityWhenCovered) read through the planet.
 * Oceans dominate Positron’s sphere fill, so water is pushed lower than land.
 *
 * @param {object} style
 * @param {{ surfaceOpacity?: number, waterDarken?: number }} [opts]
 */
export function softenGlobeBasemap(style, { surfaceOpacity = 0.18, waterDarken = 0.45 } = {}) {
  if (!style?.layers) return style;
  const clamp = (v) => Math.max(0.04, Math.min(1, v));

  /** Scale numeric outputs inside opacity expressions without nesting `zoom` illegally. */
  function scaleOpacityExpr(expr, factor) {
    if (expr == null) return clamp(factor);
    if (typeof expr === 'number') return clamp(expr * factor);
    if (!Array.isArray(expr) || expr.length === 0) return clamp(factor);

    const op = expr[0];
    if (op === 'interpolate' || op === 'interpolate-hcl' || op === 'interpolate-lab') {
      // ['interpolate', type, input, stop0, out0, stop1, out1, ...]
      const next = expr.slice();
      for (let i = 4; i < next.length; i += 2) {
        if (typeof next[i] === 'number') next[i] = clamp(next[i] * factor);
      }
      return next;
    }
    if (op === 'step') {
      // ['step', input, default, stop0, out0, ...]
      const next = expr.slice();
      if (typeof next[2] === 'number') next[2] = clamp(next[2] * factor);
      for (let i = 4; i < next.length; i += 2) {
        if (typeof next[i] === 'number') next[i] = clamp(next[i] * factor);
      }
      return next;
    }
    if (op === 'literal' && typeof expr[1] === 'number') {
      return ['literal', clamp(expr[1] * factor)];
    }
    // Unknown / compound expression — fall back to a flat opacity
    return clamp(factor);
  }

  const layers = style.layers.map((layer) => {
    const type = String(layer.type || '');
    const id = String(layer.id || '').toLowerCase();
    const paint = { ...(layer.paint || {}) };

    if (type === 'background') {
      // Land in Positron is mostly the background color — keep it very faint
      paint['background-opacity'] = clamp(surfaceOpacity * 0.55);
      return { ...layer, paint };
    }

    if (type === 'fill') {
      // Water covers most of the sphere; keep it glassier than other fills
      if (id.includes('water')) {
        const factor = surfaceOpacity * 0.65;
        paint['fill-opacity'] = scaleOpacityExpr(paint['fill-opacity'], factor);
        paint['fill-color'] = darkenColor(paint['fill-color'] ?? 'rgb(194, 200, 202)', waterDarken);
        return { ...layer, paint };
      }

      paint['fill-opacity'] = scaleOpacityExpr(paint['fill-opacity'], surfaceOpacity);
      return { ...layer, paint };
    }

    if (type === 'line') {
      const lineFactor = Math.min(0.55, surfaceOpacity + 0.22);
      const existing = paint['line-opacity'];
      if (existing == null || typeof existing === 'number') {
        paint['line-opacity'] = clamp((typeof existing === 'number' ? existing : 1) * lineFactor);
      } else {
        paint['line-opacity'] = scaleOpacityExpr(existing, lineFactor);
      }
      return { ...layer, paint };
    }

    return layer;
  });

  return { ...style, layers };
}
