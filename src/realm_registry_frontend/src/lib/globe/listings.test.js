import test from 'node:test';
import assert from 'node:assert/strict';

import { fetchListingDetails, fetchListings, listingToRealm, zoneDataFromDetails } from './listings.js';

const SUMMARY = {
  id: 'harbour-commons',
  name: 'Harbour Commons',
  logo: '',
  url: '',
  frontend_canister_id: '',
  canister_id: '',
  stage: 'beta',
  users_count: 8420,
  last_activity_at: 1_792_000_000,
  manifesto_preview: 'Harbour Commons is where…',
  revision: 2,
  created_at: 1_791_000_000,
  listing_status: 'live',
};

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
  };
}

test('a listing becomes a realm the list and globe understand', () => {
  const realm = listingToRealm(SUMMARY);
  assert.equal(realm.realm_stage, 'beta');
  assert.equal(realm.manifesto, 'Harbour Commons is where…');
  assert.equal(realm.users_count, 8420);
  assert.equal(listingToRealm({ ...SUMMARY, stage: '' }).realm_stage, 'alpha');
});

test('fetchListings follows the cursor to the last page', async () => {
  const calls = [];
  const backend = {
    list_listings: async (from, count) => {
      calls.push([from, count]);
      const next = from === 1n ? 51 : null;
      return JSON.stringify({ success: true, listings: [{ ...SUMMARY, id: `x-${from}` }], next });
    },
  };
  const realms = await fetchListings(backend);
  assert.deepEqual(calls, [[1n, 50n], [51n, 50n]]);
  assert.deepEqual(realms.map((r) => r.id), ['x-1', 'x-51']);
});

test('fetchListings surfaces a registry error', async () => {
  const backend = { list_listings: async () => JSON.stringify({ success: false, error: 'boom' }) };
  await assert.rejects(fetchListings(backend), /boom/);
});

test('details are fetched only for changed revisions, ten ids at a time', async () => {
  const realms = Array.from({ length: 12 }, (_, i) => ({ id: `c-${i}`, revision: 1 }));
  realms.push({ id: 'no-details', revision: 0 });
  const cached = { 'c-0': { revision: 1, manifesto: 'cached', zones: [] } };
  const storage = memoryStorage({ 'registryListingDetails:v1': JSON.stringify(cached) });
  const batches = [];
  const backend = {
    get_listings: async (idsJson) => {
      const ids = JSON.parse(idsJson);
      batches.push(ids);
      const listings = Object.fromEntries(ids.map((id) => [id, { revision: 1, manifesto: id, zones: [] }]));
      return JSON.stringify({ success: true, listings });
    },
  };

  const details = await fetchListingDetails(backend, realms, storage);
  assert.deepEqual(batches.map((b) => b.length), [10, 1]);
  assert.ok(!batches.flat().includes('c-0'));
  assert.ok(!batches.flat().includes('no-details'));
  assert.equal(details['c-0'].manifesto, 'cached');
  assert.equal(details['c-11'].manifesto, 'c-11');

  batches.length = 0;
  await fetchListingDetails(backend, realms, storage);
  assert.deepEqual(batches, []);

  await fetchListingDetails(backend, [{ id: 'c-3', revision: 2 }], storage);
  assert.deepEqual(batches, [['c-3']]);
  assert.deepEqual(Object.keys(JSON.parse(storage.data['registryListingDetails:v1'])), ['c-3']);
});

test('the globe gets territory zones only', () => {
  const realms = [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }];
  const details = {
    a: {
      zones: [
        { h3_index: '86394600fffffff', user_count: 3 },
        { h3_index: '8839540ad1fffff', user_count: 1, land: '7' },
      ],
    },
    b: { zones: [{ h3_index: '8839540ad1fffff', land_id: 'p1' }] },
  };
  const data = zoneDataFromDetails(realms, details);
  assert.deepEqual(Object.keys(data), ['a']);
  assert.equal(data.a.zones.length, 1);
  assert.equal(data.a.totalUsers, 3);
});
