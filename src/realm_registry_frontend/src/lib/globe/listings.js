import { isTerritoryZone } from './hex-data.js';

const PAGE = 50;
const DETAILS_BATCH = 10;
const CACHE_KEY = 'registryListingDetails:v1';

function parseReply(text) {
  const data = JSON.parse(text);
  if (!data.success) throw new Error(data.error || 'Registry error');
  return data;
}

/** A registry listing summary, shaped like the realm objects the list and globe use. */
export function listingToRealm(listing) {
  return {
    id: listing.id,
    name: listing.name,
    realm_name: listing.name,
    logo: listing.logo,
    url: listing.url,
    frontend_canister_id: listing.frontend_canister_id,
    canister_id: listing.canister_id,
    realm_stage: listing.stage || 'alpha',
    users_count: Number(listing.users_count) || 0,
    last_activity_at: Number(listing.last_activity_at) || 0,
    manifesto: listing.manifesto_preview || '',
    revision: Number(listing.revision) || 0,
    created_at: Number(listing.created_at) || 0,
    listing_status: listing.listing_status,
  };
}

/** Every listing, page by page. */
export async function fetchListings(backend) {
  const listings = [];
  let cursor = 1;
  while (cursor != null) {
    const page = parseReply(await backend.list_listings(BigInt(cursor), BigInt(PAGE)));
    listings.push(...page.listings);
    cursor = page.next;
  }
  return listings.map(listingToRealm);
}

function browserStorage() {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

function readCache(storage) {
  try {
    const parsed = JSON.parse(storage?.getItem(CACHE_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * Manifesto and zones for each realm, keyed by id. Only listings whose
 * revision differs from the cached copy are fetched.
 * @returns {Promise<Record<string, { revision: number, manifesto: string, zones: object[] }>>}
 */
export async function fetchListingDetails(backend, realms, storage = browserStorage()) {
  const cache = readCache(storage);
  const wanted = realms.filter((r) => r.revision > 0);
  const stale = wanted.filter((r) => cache[r.id]?.revision !== r.revision).map((r) => r.id);

  const batches = [];
  for (let i = 0; i < stale.length; i += DETAILS_BATCH) {
    batches.push(stale.slice(i, i + DETAILS_BATCH));
  }
  const replies = await Promise.all(
    batches.map((ids) => backend.get_listings(JSON.stringify(ids)).then(parseReply)),
  );
  for (const reply of replies) Object.assign(cache, reply.listings);

  const details = {};
  for (const realm of wanted) {
    if (cache[realm.id]) details[realm.id] = cache[realm.id];
  }
  try {
    storage?.setItem(CACHE_KEY, JSON.stringify(details));
  } catch {
    // A full storage only costs a fetch on the next visit.
  }
  return details;
}

/** The globe's zone data: territory zones per realm id. */
export function zoneDataFromDetails(realms, details) {
  /** @type {Record<string, { realmId: string, realmName: string, zones: object[], totalUsers: number }>} */
  const zoneData = {};
  for (const realm of realms) {
    const zones = (details[realm.id]?.zones || []).filter(isTerritoryZone);
    if (!zones.length) continue;
    zoneData[realm.id] = {
      realmId: realm.id,
      realmName: realm.name,
      zones,
      totalUsers: zones.reduce((sum, z) => sum + (Number(z.user_count) || 0), 0),
    };
  }
  return zoneData;
}
