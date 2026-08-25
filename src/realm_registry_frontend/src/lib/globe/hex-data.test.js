import assert from 'node:assert/strict';
import test from 'node:test';
import h3 from 'h3-js';
import {
  buildHexPolygons,
  chooseRealmHexResolution,
  computeKpis,
  isTerritoryZone,
  normalizeZoneToTruthCell,
  realmTruthCells,
} from './hex-data.js';

const RES3 = '83541cfffffffff'; // live RealmTest6 territory cell (West Africa)
const RES6 = '861f1d48fffffff';
const RES6_CHILD = h3.cellToChildren(RES6, 7)[0];

const realm = {
  id: 'wtn66-6qaaa-aaaae-agz6a-cai',
  name: 'RealmTest6',
  realm_name: 'RealmTest6',
  realm_stage: 'alpha',
  users_count: 1,
};

test('isTerritoryZone skips land-registry parcels', () => {
  assert.equal(isTerritoryZone({ h3_index: RES3 }), true);
  assert.equal(isTerritoryZone({ h3_index: RES3, land: null }), true);
  assert.equal(isTerritoryZone({ h3_index: RES3, land_id: '' }), true);
  assert.equal(isTerritoryZone({ h3_index: RES3, land: 'land_1' }), false);
  assert.equal(isTerritoryZone({ h3_index: RES3, land_id: 'land_1' }), false);
});

test('normalizeZoneToTruthCell keeps coarse cells and parents finer than res 6', () => {
  assert.equal(h3.getResolution(RES3), 3);
  assert.equal(normalizeZoneToTruthCell({ h3_index: RES3 }, h3), RES3);
  assert.equal(normalizeZoneToTruthCell({ h3_index: RES6 }, h3), RES6);
  assert.equal(normalizeZoneToTruthCell({ h3_index: RES6_CHILD }, h3), RES6);
  assert.equal(
    normalizeZoneToTruthCell({ h3_index: RES3, land_id: 'land_1' }, h3),
    null
  );
});

test('realmTruthCells keeps res-3 territory and drops land parcels', () => {
  const cells = realmTruthCells(
    [
      { h3_index: RES3, name: 'Residential' },
      { h3_index: RES6, name: 'HQ' },
      { h3_index: RES6, name: 'Parcel', land_id: 'land_1' },
    ],
    h3
  );
  assert.equal(cells.has(RES3), true);
  assert.equal(cells.has(RES6), true);
  assert.equal(cells.size, 2);
});

test('chooseRealmHexResolution draws 300 res-3 zones at globe zoom', () => {
  const origin = h3.latLngToCell(12, -8, 3);
  const zones = h3.gridDisk(origin, 10).slice(0, 300).map((h3_index, i) => ({
    h3_index,
    name: `z${i}`,
    user_count: 1,
  }));
  assert.equal(zones.length, 300);
  assert.ok(zones.every((z) => h3.getResolution(z.h3_index) === 3));

  const choice = chooseRealmHexResolution(zones, h3, 2.65);
  assert.ok(choice, 'coarse territory cells must render as hexes, not markers');
  assert.equal(choice.truthCells.size, 300);
  assert.ok(choice.resolution <= 3);

  const polygons = buildHexPolygons([realm], { [realm.id]: { zones } }, h3, {
    zoom: 2.65,
  });
  assert.ok(polygons.length > 0, 'globe must fill territory hexes');
  assert.ok(polygons.every((p) => (p.minDistance ?? 99) === 0));
});

test('live RealmTest6 res-3 index paints a hex at globe zoom', () => {
  const zones = [{ h3_index: RES3, name: 'Residential zone', user_count: 1 }];
  const [lat, lng] = h3.cellToLatLng(RES3);
  assert.ok(lat > 0 && lat < 25, `expected West Africa lat, got ${lat}`);
  assert.ok(lng > -20 && lng < 20, `expected West Africa lng, got ${lng}`);

  const polygons = buildHexPolygons([realm], { [realm.id]: { zones } }, h3, {
    zoom: 2.65,
  });
  assert.ok(polygons.length > 0, 'res-3 cell must not be dropped');
  const [plat, plng] = h3.cellToLatLng(polygons[0].hexIndex);
  assert.ok(plat > 0 && plat < 25);
  assert.ok(plng > -20 && plng < 20);
});

test('city-zoom Spain hexes still fill at globe zoom', () => {
  const origin = h3.latLngToCell(37.6, -1.0, 8);
  const spain = h3.gridDisk(origin, 2).slice(0, 16).map((h3_index, i) => ({
    h3_index,
    name: `spain${i}`,
    user_count: 1,
  }));
  assert.equal(spain.length, 16);

  const choice = chooseRealmHexResolution(spain, h3, 2.65);
  assert.ok(choice, 'city-scale territory must render as hexes, not markers');
  const polygons = buildHexPolygons([realm], { [realm.id]: { zones: spain } }, h3, {
    zoom: 2.65,
  });
  assert.ok(polygons.length > 0, 'globe must fill Spain-drawn hexes');
  const inSpain = polygons.filter((p) => {
    const [lat, lng] = h3.cellToLatLng(p.hexIndex);
    return lat >= 35 && lat <= 44 && lng >= -10 && lng <= 5;
  });
  assert.ok(inSpain.length > 0, 'fill must sit on Iberia, not only the capital pin');
});

test('mixed Africa res-3 and Spain res-8 both fill at globe zoom', () => {
  const africaOrigin = h3.latLngToCell(12, -8, 3);
  const africa = h3.gridDisk(africaOrigin, 10).slice(0, 300).map((h3_index, i) => ({
    h3_index,
    name: `a${i}`,
    user_count: 1,
  }));
  const spainOrigin = h3.latLngToCell(37.6, -1.0, 8);
  const spain = h3.gridDisk(spainOrigin, 2).slice(0, 16).map((h3_index, i) => ({
    h3_index,
    name: `s${i}`,
    user_count: 1,
  }));
  const zones = [...africa, ...spain];

  const choice = chooseRealmHexResolution(zones, h3, 2.65);
  assert.ok(choice, 'mixed-resolution territory must not fall back to markers');
  const polygons = buildHexPolygons([realm], { [realm.id]: { zones } }, h3, {
    zoom: 2.65,
  });
  assert.ok(polygons.length > 0);
  const inSpain = polygons.filter((p) => {
    const [lat, lng] = h3.cellToLatLng(p.hexIndex);
    return lat >= 35 && lat <= 44 && lng >= -10 && lng <= 5;
  });
  const inAfrica = polygons.filter((p) => {
    const [lat, lng] = h3.cellToLatLng(p.hexIndex);
    return lat >= 0 && lat <= 35 && lng >= -30 && lng <= 20;
  });
  assert.ok(inAfrica.length > 0, 'coarse West Africa hexes must remain');
  assert.ok(inSpain.length > 0, 'Spain-drawn cells must not drop the whole fill');
});

test('buildHexPolygons never draws land-registry cells', () => {
  const zones = [
    { h3_index: RES6, name: 'Parcel A', land_id: 'land_1', user_count: 4 },
    { h3_index: RES3, name: 'Parcel B', land: 'land_2', user_count: 2 },
  ];
  assert.equal(realmTruthCells(zones, h3).size, 0);
  assert.equal(chooseRealmHexResolution(zones, h3, 9), null);
  assert.deepEqual(buildHexPolygons([realm], { [realm.id]: { zones } }, h3, { zoom: 9 }), []);
  assert.equal(computeKpis([realm], { [realm.id]: { zones } }).locationClusters, 0);
});
