import {
  DIM_OPACITY,
  hexStyle,
  hexCapForResolution,
  HEX_AREA_INFLATION_MAX,
  HEX_INFLUENCE_MAX_TRUTH_CELLS,
  h3ResolutionForZoom,
  ZONE_DATA_RESOLUTION,
} from './globe-config.js';
import { stageMarkerColor } from '../realm-stages.js';

/** @param {number | null | undefined} lat @param {number | null | undefined} lng */
export function isFiniteLatLng(lat, lng) {
  return Number.isFinite(lat) && Number.isFinite(lng);
}

/** Legacy zone payloads (pre-#254) still expose stored map coordinates. */
function storedZoneLatLng(zone) {
  const lat = Number(zone.center_lat ?? zone.latitude ?? zone.lat);
  const lng = Number(zone.center_lng ?? zone.longitude ?? zone.lng);
  return isFiniteLatLng(lat, lng) ? { lat, lng } : null;
}

/** @param {object | null | undefined} h3 @param {string | null | undefined} h3Index */
function isUsableH3Index(h3, h3Index) {
  if (!h3Index || typeof h3Index !== 'string') return false;
  if (h3Index.startsWith('manual')) return false;
  try {
    if (h3?.isValidCell?.(h3Index) === false) return false;
    if (h3?.isValidIndex?.(h3Index) === false) return false;
  } catch {
    /* optional validators */
  }
  return true;
}

/**
 * @typedef {object} HexRealmEntry
 * @property {object} realm
 * @property {number} users
 * @property {number} distance
 * @property {boolean} isCenter
 * @property {boolean} isHQ
 * @property {string[]} locations
 */

/**
 * @typedef {object} HexPolygon
 * @property {string} hexIndex
 * @property {HexRealmEntry[]} realms
 * @property {number} totalUsers
 * @property {string} fillColor
 * @property {string} strokeColor
 * @property {number} opacity
 * @property {number} weight
 * @property {string[]} realmIds
 * @property {number} minDistance
 * @property {object} geometry
 */

/**
 * Res-6 H3 cells that represent a realm's true zone footprint.
 * @param {object[]} zones
 * @param {object} h3
 * @returns {Set<string>}
 */
export function realmTruthCells(zones, h3) {
  const cells = new Set();
  if (!zones?.length || !h3) return cells;

  for (const zone of zones) {
    if (!isUsableH3Index(h3, zone.h3_index)) continue;
    let idx = null;
    try {
      const res = h3.getResolution?.(zone.h3_index);
      if (res === ZONE_DATA_RESOLUTION) {
        idx = zone.h3_index;
      } else if (typeof res === 'number' && res > ZONE_DATA_RESOLUTION && h3.cellToParent) {
        idx = h3.cellToParent(zone.h3_index, ZONE_DATA_RESOLUTION);
      }
    } catch {
      /* skip invalid cell */
    }
    if (idx) cells.add(idx);
  }

  return cells;
}

/** @param {Iterable<string>} cells @param {object} h3 */
function totalCellsArea(cells, h3) {
  let sum = 0;
  for (const cell of cells) {
    try {
      sum += h3.cellArea(cell, 'km2');
    } catch {
      try {
        sum += h3.cellArea(cell);
      } catch {
        sum += 1;
      }
    }
  }
  return sum || 1;
}

/** @param {Set<string>} truthCells @param {object} h3 @param {number} resolution */
function parentCellsAtResolution(truthCells, h3, resolution) {
  const out = new Set();
  for (const cell of truthCells) {
    try {
      if (resolution >= ZONE_DATA_RESOLUTION) {
        out.add(cell);
      } else {
        out.add(h3.cellToParent(cell, resolution));
      }
    } catch {
      out.add(cell);
    }
  }
  return out;
}

/** @param {Set<string>} cells @param {object} h3 @param {number} rings */
function expandWithInfluenceRings(cells, h3, rings) {
  const out = new Set(cells);
  if (rings <= 0) return out;
  for (const cell of cells) {
    try {
      for (const hex of h3.gridDisk(cell, rings)) {
        out.add(hex);
      }
    } catch {
      /* ignore */
    }
  }
  return out;
}

/** @param {Set<string>} displayCells @param {Set<string>} truthCells @param {object} h3 @param {number} displayRes */
function areaInflationRatio(displayCells, truthCells, h3, displayRes) {
  try {
    const truthArea =
      h3.getHexagonAreaAvg(ZONE_DATA_RESOLUTION, 'km2') * Math.max(1, truthCells.size);
    const displayArea =
      h3.getHexagonAreaAvg(displayRes, 'km2') * Math.max(1, displayCells.size);
    return displayArea / truthArea;
  } catch {
    return totalCellsArea(displayCells, h3) / totalCellsArea(truthCells, h3);
  }
}

/**
 * Pick per-realm display resolution: coarsest zoom-allowed res whose footprint
 * stays within HEX_AREA_INFLATION_MAX of the true res-6 union, or null → markers only.
 * @param {object[]} zones
 * @param {object} h3
 * @param {number} zoom
 */
export function chooseRealmHexResolution(zones, h3, zoom) {
  const truthCells = realmTruthCells(zones, h3);
  if (!truthCells.size) return null;

  const targetCoarse = h3ResolutionForZoom(zoom);
  const maxFine = zoom >= 7 ? ZONE_DATA_RESOLUTION : targetCoarse;

  for (let resolution = targetCoarse; resolution <= maxFine; resolution++) {
    const displayCells = parentCellsAtResolution(truthCells, h3, resolution);
    if (areaInflationRatio(displayCells, truthCells, h3, resolution) > HEX_AREA_INFLATION_MAX) {
      continue;
    }

    if (resolution >= ZONE_DATA_RESOLUTION && truthCells.size <= HEX_INFLUENCE_MAX_TRUTH_CELLS) {
      const withRing = expandWithInfluenceRings(truthCells, h3, 1);
      if (
        areaInflationRatio(withRing, truthCells, h3, ZONE_DATA_RESOLUTION) <=
        HEX_AREA_INFLATION_MAX
      ) {
        return { resolution, truthCells, influenceRings: 1 };
      }
    }

    return { resolution, truthCells, influenceRings: 0 };
  }

  return null;
}

/** @param {object[]} zones @param {object} h3 */
function zoneStatsByTruthCell(zones, h3) {
  /** @type {Map<string, number>} */
  const users = new Map();
  /** @type {Map<string, string[]>} */
  const locations = new Map();

  for (const zone of zones) {
    if (!isUsableH3Index(h3, zone.h3_index)) continue;
    let truthCell = null;
    try {
      const res = h3.getResolution?.(zone.h3_index);
      if (res === ZONE_DATA_RESOLUTION) {
        truthCell = zone.h3_index;
      } else if (typeof res === 'number' && res > ZONE_DATA_RESOLUTION && h3.cellToParent) {
        truthCell = h3.cellToParent(zone.h3_index, ZONE_DATA_RESOLUTION);
      }
    } catch {
      /* skip invalid cell */
    }
    if (!truthCell) continue;
    users.set(truthCell, (users.get(truthCell) || 0) + (zone.user_count || 0));
    if (!locations.has(truthCell)) locations.set(truthCell, []);
    locations.get(truthCell).push(zone.name || zone.location_name || 'Zone');
  }

  return { users, locations };
}

/** @param {Set<string>} truthCells @param {object} h3 @param {number} rings */
function buildCellDistanceMap(truthCells, h3, rings) {
  /** @type {Map<string, number>} */
  const out = new Map();
  for (const truthCell of truthCells) {
    out.set(truthCell, 0);
    if (rings <= 0) continue;
    try {
      for (const hex of h3.gridDisk(truthCell, rings)) {
        if (out.has(hex)) continue;
        out.set(hex, h3.gridDistance(truthCell, hex));
      }
    } catch {
      /* ignore */
    }
  }
  return out;
}

/** @param {Set<string>} truthCells @param {object} h3 @param {number} resolution */
function truthToDisplayParents(truthCells, h3, resolution) {
  /** @type {Map<string, string>} */
  const out = new Map();
  for (const truthCell of truthCells) {
    try {
      out.set(
        truthCell,
        resolution >= ZONE_DATA_RESOLUTION ? truthCell : h3.cellToParent(truthCell, resolution)
      );
    } catch {
      out.set(truthCell, truthCell);
    }
  }
  return out;
}

function statsForDisplayHex(hexIndex, zoneStats, truthToDisplay, truthCells, distance) {
  if (distance > 0) {
    return { users: 0, locations: [] };
  }

  let users = 0;
  const locs = [];
  for (const truthCell of truthCells) {
    if (truthToDisplay.get(truthCell) !== hexIndex && truthCell !== hexIndex) continue;
    users += zoneStats.users.get(truthCell) || 0;
    const names = zoneStats.locations.get(truthCell);
    if (names) locs.push(...names);
  }

  return { users, locations: locs };
}

/**
 * @param {object[]} filteredRealms
 * @param {Record<string, { zones: object[] }>} realmZoneData
 * @param {object} h3
 * @param {{ matchingRealmIds?: Set<string> | null, dimNonMatching?: boolean, zoom?: number }} [options]
 * @returns {HexPolygon[]}
 */
export function buildHexPolygons(
  filteredRealms,
  realmZoneData,
  h3,
  {
    matchingRealmIds = null,
    dimNonMatching = false,
    zoom = 9,
  } = {}
) {
  /** @type {Record<string, { realms: HexRealmEntry[], totalUsers: number }>} */
  const hexData = {};
  let finestResolution = h3ResolutionForZoom(zoom);

  filteredRealms.forEach((realm) => {
    const realZoneData = realmZoneData[realm.id];
    if (!realZoneData?.zones?.length) return;

    const choice = chooseRealmHexResolution(realZoneData.zones, h3, zoom);
    if (!choice) return;

    const { resolution: h3Resolution, truthCells, influenceRings } = choice;
    finestResolution = Math.max(finestResolution, h3Resolution);

    const zoneStats = zoneStatsByTruthCell(realZoneData.zones, h3);
    const truthToDisplay = truthToDisplayParents(truthCells, h3, h3Resolution);

    /** @type {Map<string, number>} */
    const cellDistances =
      influenceRings > 0
        ? buildCellDistanceMap(truthCells, h3, influenceRings)
        : new Map([...new Set(truthToDisplay.values())].map((hex) => [hex, 0]));

    for (const [hexIndex, distance] of cellDistances) {
      const { users, locations } = statsForDisplayHex(
        hexIndex,
        zoneStats,
        truthToDisplay,
        truthCells,
        distance
      );

      if (!hexData[hexIndex]) {
        hexData[hexIndex] = { realms: [], totalUsers: 0 };
      }

      const existingEntry = hexData[hexIndex].realms.find((r) => r.realm.id === realm.id);
      if (existingEntry) {
        if (distance < existingEntry.distance) {
          existingEntry.distance = distance;
          existingEntry.isCenter = distance === 0;
          existingEntry.isHQ = distance === 0;
          existingEntry.users = users;
          existingEntry.locations = locations;
        } else if (distance === existingEntry.distance && distance === 0) {
          existingEntry.users += users;
          existingEntry.locations = [...new Set([...existingEntry.locations, ...locations])];
        }
      } else {
        hexData[hexIndex].realms.push({
          realm,
          users,
          distance,
          isCenter: distance === 0,
          isHQ: distance === 0,
          locations,
        });
      }

      if (distance === 0) {
        hexData[hexIndex].totalUsers += users;
      }
    }
  });

  const polygons = [];

  for (const [hexIndex, data] of Object.entries(hexData)) {
    let ring;
    try {
      // formatAsGeoJson=true → [lng, lat]
      ring = h3.cellToBoundary(hexIndex, true).map(([lng, lat]) => [lng, lat]);
    } catch {
      try {
        ring = h3.cellToBoundary(hexIndex).map(([lat, lng]) => [lng, lat]);
      } catch {
        continue;
      }
    }
    if (ring.length) ring.push(ring[0]);

    const sortedRealms = [...data.realms].sort((a, b) => b.users - a.users);
    const minDistance = Math.min(...data.realms.map((r) => r.distance));
    const hasMultipleRealms = data.realms.length > 1;
    const style = hexStyle(minDistance, {
      totalUsers: data.totalUsers,
      hasMultipleRealms,
      h3Resolution: finestResolution,
    });

    const realmIds = data.realms.map((r) => r.realm.id);
    const isDimmed =
      dimNonMatching &&
      matchingRealmIds &&
      !realmIds.some((id) => matchingRealmIds.has(id));

    const opacity = isDimmed ? style.opacity * DIM_OPACITY : style.opacity;

    polygons.push({
      hexIndex,
      realms: sortedRealms,
      totalUsers: data.totalUsers,
      geometry: { type: 'Polygon', coordinates: [ring] },
      fillColor: style.fill,
      strokeColor: style.stroke,
      opacity,
      weight: style.weight,
      minDistance,
      realmIds,
    });
  }

  const cap = hexCapForResolution(finestResolution);
  // Always keep every HQ / capital cell (distance 0). Only influence-ring
  // hexes are subject to the performance cap — otherwise dense realms
  // (e.g. Dominion) crowd out smaller Live realms like the E2E capitals.
  const hq = polygons.filter((p) => (p.minDistance ?? 99) === 0);
  const influence = polygons
    .filter((p) => (p.minDistance ?? 99) > 0)
    .sort((a, b) => (a.minDistance ?? 99) - (b.minDistance ?? 99));
  const influenceBudget = Math.max(0, cap - hq.length);
  return hq.concat(influence.slice(0, influenceBudget));
}

/**
 * Geographic bounds of a realm's true res-6 zone footprint (for map fit).
 * @param {object[]} zones
 * @param {object | null} h3
 * @returns {[[number, number], [number, number]] | null} [[west, south], [east, north]]
 */
export function realmDisplayBounds(zones, h3) {
  if (!zones?.length || !h3) return null;

  const truthCells = realmTruthCells(zones, h3);
  if (!truthCells.size) return null;

  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  const extend = (lng, lat) => {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    minLng = Math.min(minLng, lng);
    minLat = Math.min(minLat, lat);
    maxLng = Math.max(maxLng, lng);
    maxLat = Math.max(maxLat, lat);
  };

  for (const hexIndex of truthCells) {
    try {
      const boundary = h3.cellToBoundary(hexIndex, true);
      for (const [lng, lat] of boundary) {
        extend(lng, lat);
      }
    } catch {
      try {
        const [lat, lng] = h3.cellToLatLng(hexIndex);
        extend(lng, lat);
      } catch {
        /* ignore */
      }
    }
  }

  if (!Number.isFinite(minLng)) return null;

  const lngSpan = maxLng - minLng;
  const latSpan = maxLat - minLat;
  const lngPad = Math.max(lngSpan * 0.14, 0.018);
  const latPad = Math.max(latSpan * 0.14, 0.018);

  return [
    [minLng - lngPad, minLat - latPad],
    [maxLng + lngPad, maxLat + latPad],
  ];
}

export function resolveCapitalZone(zones) {
  if (!zones?.length) return null;
  return [...zones].sort((a, b) => {
    const byUsers = (b.user_count || 0) - (a.user_count || 0);
    if (byUsers !== 0) return byUsers;
    return String(a.name || a.location_name || '').localeCompare(
      String(b.name || b.location_name || '')
    );
  })[0];
}

/**
 * Geometric center of the capital hex at the current display resolution.
 * Falls back to stored lat/lng when H3 cannot resolve the cell.
 * @param {object} zone
 * @param {object | null} h3
 * @param {number} h3Resolution
 * @returns {{ lat: number, lng: number, hexIndex: string | null }}
 */
export function capitalHexCenter(zone, h3, h3Resolution) {
  const stored = storedZoneLatLng(zone);
  const fallback = {
    lat: stored?.lat ?? null,
    lng: stored?.lng ?? null,
    hexIndex: zone.h3_index || null,
  };

  if (!h3 || !isUsableH3Index(h3, zone.h3_index)) {
    return fallback;
  }

  let hexIndex = null;
  try {
    const res = h3.getResolution?.(zone.h3_index);
    if (res === h3Resolution) {
      hexIndex = zone.h3_index;
    } else if (typeof res === 'number' && res > h3Resolution && h3.cellToParent) {
      hexIndex = h3.cellToParent(zone.h3_index, h3Resolution);
    } else {
      hexIndex = zone.h3_index;
    }
  } catch {
    hexIndex = zone.h3_index || null;
  }

  if (!hexIndex) return fallback;

  try {
    const [lat, lng] = h3.cellToLatLng(hexIndex);
    if (isFiniteLatLng(lat, lng)) {
      return { lat, lng, hexIndex };
    }
  } catch {
    /* fall through to stored coordinates */
  }

  return { ...fallback, hexIndex };
}

/**
 * Prefer a distinct capital hex when several realms would otherwise stack on
 * the same cell. Falls back to a small screen-pixel fan only if no alternate
 * zone hex is available — pins stay at true hex centers whenever possible.
 * @param {object[]} markers
 * @param {Record<string, { zones: object[] }>} realmZoneData
 * @param {object | null} h3
 * @param {number} h3Resolution
 * @param {number} [radiusPx]
 */
export function separateCoincidentMarkers(
  markers,
  realmZoneData,
  h3,
  h3Resolution,
  radiusPx = 12
) {
  const keyOf = (m) => {
    if (m.hexIndex) return m.hexIndex;
    if (isFiniteLatLng(m.lat, m.lng)) {
      return `${Number(m.lat).toFixed(5)},${Number(m.lng).toFixed(5)}`;
    }
    return '';
  };

  /** @type {Map<string, object[]>} */
  let groups = new Map();
  const regroup = () => {
    groups = new Map();
    for (const marker of markers) {
      const key = keyOf(marker);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(marker);
    }
  };
  regroup();

  for (const group of [...groups.values()]) {
    if (group.length < 2) continue;
    // Keep the first realm on the shared capital; move the rest to another
    // of their zones whose display hex differs.
    for (let i = 1; i < group.length; i++) {
      const marker = group[i];
      const zones = realmZoneData[marker.realmId]?.zones || [];
      const occupied = new Set(
        markers.filter((m) => m !== marker).map((m) => keyOf(m))
      );
      const ranked = [...zones].sort((a, b) => {
        const byUsers = (b.user_count || 0) - (a.user_count || 0);
        if (byUsers !== 0) return byUsers;
        return String(a.name || a.location_name || '').localeCompare(
          String(b.name || b.location_name || '')
        );
      });
      const alternate = ranked.find((zone) => {
        const center = capitalHexCenter(zone, h3, h3Resolution);
        if (!isFiniteLatLng(center.lat, center.lng)) return false;
        const key =
          center.hexIndex ||
          `${center.lat.toFixed(5)},${center.lng.toFixed(5)}`;
        return key && !occupied.has(key);
      });
      if (!alternate) continue;
      const center = capitalHexCenter(alternate, h3, h3Resolution);
      if (!isFiniteLatLng(center.lat, center.lng)) continue;
      marker.lat = center.lat;
      marker.lng = center.lng;
      marker.hexIndex = center.hexIndex;
      marker.location = alternate.name || alternate.location_name;
      marker.users = alternate.user_count;
    }
  }

  regroup();
  for (const group of groups.values()) {
    if (group.length < 2) {
      group[0].pixelOffset = [0, 0];
      continue;
    }
    group.forEach((marker, index) => {
      const angle = (2 * Math.PI * index) / group.length - Math.PI / 2;
      marker.pixelOffset = [
        Math.round(Math.cos(angle) * radiusPx),
        Math.round(Math.sin(angle) * radiusPx),
      ];
    });
  }

  return markers;
}

/**
 * @param {object[]} filteredRealms
 * @param {Record<string, { zones: object[] }>} realmZoneData
 * @param {{ matchingRealmIds?: Set<string> | null, dimNonMatching?: boolean, h3?: object | null, h3Resolution?: number }} [options]
 */
export function buildPointMarkers(
  filteredRealms,
  realmZoneData,
  {
    matchingRealmIds = null,
    dimNonMatching = false,
    h3 = null,
    h3Resolution = ZONE_DATA_RESOLUTION,
  } = {}
) {
  const markers = [];

  filteredRealms.forEach((realm) => {
    const zones = realmZoneData[realm.id]?.zones;
    if (!zones?.length) return;

    const ranked = [...zones].sort((a, b) => {
      const byUsers = (b.user_count || 0) - (a.user_count || 0);
      if (byUsers !== 0) return byUsers;
      return String(a.name || a.location_name || '').localeCompare(
        String(b.name || b.location_name || '')
      );
    });
    let capital = null;
    let center = null;
    for (const zone of ranked) {
      const candidate = capitalHexCenter(zone, h3, h3Resolution);
      if (isFiniteLatLng(candidate.lat, candidate.lng)) {
        capital = zone;
        center = candidate;
        break;
      }
    }
    if (!capital || !center) return;

    const isDimmed =
      dimNonMatching && matchingRealmIds && !matchingRealmIds.has(realm.id);

    markers.push({
      realmId: realm.id,
      realmName: realm.name || realm.realm_name,
      lat: center.lat,
      lng: center.lng,
      hexIndex: center.hexIndex,
      users: capital.user_count,
      totalUsers: realm.users_count || capital.user_count,
      location: capital.name || capital.location_name,
      stage: realm.realm_stage,
      manifesto: realm.manifesto,
      color: stageMarkerColor(realm.realm_stage, { dimmed: isDimmed }),
      size: isDimmed ? 0.7 : 1,
      pixelOffset: [0, 0],
    });
  });

  return separateCoincidentMarkers(
    markers,
    realmZoneData,
    h3,
    h3Resolution
  );
}

/**
 * @param {object[]} realms
 * @param {Record<string, { zones: object[] }>} realmZoneData
 */
export function computeKpis(realms, realmZoneData) {
  const totalRealms = realms.length;
  const totalUsers = realms.reduce((sum, r) => sum + (r.users_count || 0), 0);

  const locationClusters = new Set();
  Object.values(realmZoneData).forEach((data) => {
    data.zones?.forEach((zone) => {
      if (zone.h3_index) {
        locationClusters.add(zone.h3_index);
      }
    });
  });

  const stageCounts = {};
  realms.forEach((r) => {
    const stage = r.realm_stage || 'alpha';
    stageCounts[stage] = (stageCounts[stage] || 0) + 1;
  });

  return {
    totalRealms,
    totalUsers,
    locationClusters: locationClusters.size,
    stageCounts,
  };
}
