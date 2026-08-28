export function isLocalDevelopment() {
  if (typeof window === 'undefined') return false;
  return window.location.hostname.includes('localhost') || window.location.hostname.includes('127.0.0.1');
}

export function ensureProtocol(url) {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) {
    if (url.includes('localhost') || url.includes('127.0.0.1')) {
      const currentPort = window.location.port;
      if (currentPort) {
        return url.replace(/localhost:\d+/, `localhost:${currentPort}`);
      }
    }
    return url;
  }
  const isLocal = url.includes('localhost') || url.includes('127.0.0.1');
  if (isLocal) {
    const currentPort = window.location.port;
    if (currentPort) {
      const normalized = url.replace(/localhost:\d+/, `localhost:${currentPort}`);
      return `http://${normalized}`;
    }
    return `http://${url}`;
  }
  return `https://${url}`;
}

export function icAssetBaseUrlForCanister(canisterId) {
  if (!canisterId || !String(canisterId).trim()) return '';
  const id = String(canisterId).trim();
  if (typeof window === 'undefined') {
    return `https://${id}.icp0.io`;
  }
  if (isLocalDevelopment()) {
    const port = window.location.port || '4943';
    return `http://${id}.localhost:${port}`;
  }
  const host = window.location.hostname || '';
  if (host.endsWith('.ic0.app') && !host.includes('icp0')) {
    return `https://${id}.ic0.app`;
  }
  return `https://${id}.icp0.io`;
}

export function registryUrlLooksLikeBackendOnly(realm) {
  const bid = (realm.id || '').trim().toLowerCase();
  if (!bid || !realm.url) return false;
  const u = ensureProtocol(realm.url).replace(/\/$/, '').toLowerCase();
  return [
    `https://${bid}.icp0.io`,
    `http://${bid}.icp0.io`,
    `https://${bid}.ic0.app`,
    `http://${bid}.ic0.app`,
  ].includes(u);
}

export function realmFrontendAssetBase(realm) {
  const fe = realm.frontend_canister_id && String(realm.frontend_canister_id).trim();
  if (fe) return icAssetBaseUrlForCanister(fe);
  if (realm.url && !registryUrlLooksLikeBackendOnly(realm)) {
    return ensureProtocol(realm.url).replace(/\/$/, '');
  }
  return '';
}

export function resolveRealmAssetUrl(realm, assetPath) {
  if (!assetPath) return '';
  const path = String(assetPath);
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const base = realmFrontendAssetBase(realm);
  if (!base) return '';
  return `${base}/${path.replace(/^\//, '')}`;
}

export function resolvedRealmLogoUrl(realm) {
  return resolveRealmAssetUrl(realm, '/custom/logo.png') || null;
}

/** Paths a realm frontend may serve for its branding logo. */
export const BRANDING_LOGO_PATHS = ['/custom/logo.png', '/logo.png'];

/**
 * Platform leftovers still shipped by Realms GOS frontends / the portal.
 * Presence of these paths must not be treated as a realm's configured brand.
 */
export const LEFTOVER_PLATFORM_LOGO_PATHS = [
  '/images/logo.png',
  '/images/logo.svg',
  '/images/logo_sphere_only.svg',
  '/images/logo_mark.svg',
];

/**
 * SHA-256 of platform leftovers that must never be painted as a realm brand.
 * Fresh Realms GOS frontends ship the Syntropia DNA/globe and city photo at
 * `/custom/logo.png` and `/custom/background.png` — those bytes are template
 * defaults, not a founder-set brand.
 */
export const LEFTOVER_BRANDING_SHA256 = new Set([
  // Retired clover / figure-eight shipped at `/images/logo.png`.
  '85bf3e1f45bce760e07987764c7435c2c0744db49092d5721cb7a33c25c40898',
  // Shipped Syntropia DNA/globe at `/custom/logo.png`
  // (realms `static/custom/logo.png` and live unbranded frontends).
  'ad61a953728bad3317cec825379f8b00022cda8f48572be34df74f4f65cc70a2',
  // Shipped city photo at `/custom/background.png`
  // (realms `static/custom/background.png` and live unbranded frontends).
  'a2852f05b5ae66b26f169d8efc128326fcdb64dee2915d251e66df477881fed4',
]);

/** Realm frontend path that holds the configured brand when the bytes differ from the template. */
export const REALM_BRAND_LOGO_PATH = '/custom/logo.png';

/**
 * Candidate branding-logo URLs for a realm frontend canister.
 * Empty when `frontendCanisterId` is missing.
 */
export function brandingLogoUrls(frontendCanisterId) {
  const id = frontendCanisterId && String(frontendCanisterId).trim();
  if (!id) return [];
  const realm = { frontend_canister_id: id };
  return BRANDING_LOGO_PATHS.map((path) => resolveRealmAssetUrl(realm, path)).filter(Boolean);
}

export function pathnameFromAssetUrl(urlOrPath) {
  const raw = String(urlOrPath || '').trim();
  if (!raw) return '';
  if (raw.startsWith('data:')) return '';
  try {
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      return new URL(raw).pathname || '';
    }
  } catch {
    return '';
  }
  return raw.startsWith('/') ? raw : `/${raw}`;
}

/** True when the URL/path is a known GOS leftover mark, not a realm brand. */
export function isLeftoverPlatformLogoPath(urlOrPath) {
  const path = pathnameFromAssetUrl(urlOrPath).toLowerCase();
  return LEFTOVER_PLATFORM_LOGO_PATHS.includes(path);
}

export function isRealmBrandLogoPath(urlOrPath) {
  return pathnameFromAssetUrl(urlOrPath).toLowerCase() === REALM_BRAND_LOGO_PATH;
}

export async function sha256Hex(bytes) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('crypto.subtle is required to hash branding bytes');
  const source =
    bytes instanceof ArrayBuffer
      ? bytes
      : bytes instanceof Uint8Array
        ? bytes
        : new Uint8Array(bytes);
  const digest = await subtle.digest('SHA-256', source);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function isLeftoverBrandingBytes(bytes) {
  if (!bytes || (bytes.byteLength !== undefined && bytes.byteLength === 0)) return false;
  const hex = await sha256Hex(bytes);
  return LEFTOVER_BRANDING_SHA256.has(hex);
}

function decodeDataUrlBytes(dataUrl) {
  const raw = String(dataUrl || '');
  const comma = raw.indexOf(',');
  if (!raw.startsWith('data:') || comma < 0) return null;
  const header = raw.slice(0, comma);
  const payload = raw.slice(comma + 1);
  if (!header.includes(';base64')) return null;
  try {
    const binary = atob(payload);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

/**
 * Splash candidates: configured `logo_url` first, then frontend branding paths.
 * Leftover GOS/clover/planet paths are never candidates.
 */
export function splashLogoCandidates({ frontendCanisterId = '', configuredLogoUrl = '' } = {}) {
  const out = [];
  const seen = new Set();
  const push = (url) => {
    if (!url || seen.has(url) || isLeftoverPlatformLogoPath(url)) return;
    seen.add(url);
    out.push(url);
  };

  const configured = String(configuredLogoUrl || '').trim();
  if (configured) {
    if (configured.startsWith('data:') || configured.startsWith('http://') || configured.startsWith('https://')) {
      push(configured);
    } else {
      push(resolveRealmAssetUrl({ frontend_canister_id: frontendCanisterId }, configured));
    }
  }

  for (const url of brandingLogoUrls(frontendCanisterId)) push(url);
  return out;
}

/**
 * First splash candidate once a frontend canister is known.
 * Still hashed before paint — shipped Syntropia DNA is not a realm brand.
 */
export function firstSplashLogoUrl({ frontendCanisterId = '', configuredLogoUrl = '' } = {}) {
  return splashLogoCandidates({ frontendCanisterId, configuredLogoUrl })[0] || '';
}

/** Persisted slug → frontend canister so a hard reload can paint `/custom/logo.png` immediately. */
export const SPLASH_BRAND_HINT_STORAGE_KEY = 'gaas.portal.splashBrand.v1';

function defaultSplashHintStorage() {
  if (typeof localStorage === 'undefined') return null;
  return localStorage;
}

function normalizeSplashHint(entry) {
  const frontendCanisterId = String(entry?.frontendCanisterId || '').trim();
  if (!frontendCanisterId) return null;
  return {
    frontendCanisterId,
    configuredLogoUrl: String(entry?.configuredLogoUrl || '').trim(),
  };
}

/**
 * @param {string} slug
 * @param {Pick<Storage, 'getItem'> | null} [storage]
 * @returns {{ frontendCanisterId: string, configuredLogoUrl: string } | null}
 */
export function readSplashBrandHint(slug, storage = defaultSplashHintStorage()) {
  const key = String(slug || '').trim().toLowerCase();
  if (!key || !storage) return null;
  try {
    const store = JSON.parse(storage.getItem(SPLASH_BRAND_HINT_STORAGE_KEY) || '{}');
    return normalizeSplashHint(store?.[key]);
  } catch {
    return null;
  }
}

/**
 * @param {string} slug
 * @param {{ frontendCanisterId?: string, configuredLogoUrl?: string }} hint
 * @param {Pick<Storage, 'getItem' | 'setItem'> | null} [storage]
 */
export function writeSplashBrandHint(slug, hint, storage = defaultSplashHintStorage()) {
  const key = String(slug || '').trim().toLowerCase();
  const normalized = normalizeSplashHint(hint);
  if (!key || !normalized || !storage) return;
  try {
    const store = JSON.parse(storage.getItem(SPLASH_BRAND_HINT_STORAGE_KEY) || '{}');
    store[key] = normalized;
    storage.setItem(SPLASH_BRAND_HINT_STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* quota / private mode */
  }
}

/**
 * @param {string} slug
 * @param {Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null} [storage]
 */
export function clearSplashBrandHint(slug, storage = defaultSplashHintStorage()) {
  const key = String(slug || '').trim().toLowerCase();
  if (!key || !storage) return;
  try {
    const store = JSON.parse(storage.getItem(SPLASH_BRAND_HINT_STORAGE_KEY) || '{}');
    if (!store || !Object.prototype.hasOwnProperty.call(store, key)) return;
    delete store[key];
    if (Object.keys(store).length) {
      storage.setItem(SPLASH_BRAND_HINT_STORAGE_KEY, JSON.stringify(store));
    } else {
      storage.removeItem(SPLASH_BRAND_HINT_STORAGE_KEY);
    }
  } catch {
    /* quota / private mode */
  }
}

function looksLikeImageBytes(bytes, contentType) {
  const type = String(contentType || '').toLowerCase();
  if (type.startsWith('image/')) return true;
  if (bytes.byteLength >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return true;
  }
  if (bytes.byteLength >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return true;
  }
  const head = new TextDecoder().decode(bytes.slice(0, 80)).trimStart().toLowerCase();
  return head.startsWith('<svg') || head.startsWith('<?xml');
}

/**
 * Accept a branding image (logo or background) if it loads and is not a
 * shipped template leftover. `/custom/*` is eligible only when the bytes
 * differ from the Syntropia DNA / city defaults.
 * @param {string} url
 * @param {typeof fetch} [fetchImpl]
 */
export async function acceptBrandingAssetUrl(url, fetchImpl = globalThis.fetch) {
  const candidate = String(url || '').trim();
  if (!candidate) return false;

  if (candidate.startsWith('data:')) {
    if (!candidate.startsWith('data:image/')) return false;
    const bytes = decodeDataUrlBytes(candidate);
    if (!bytes) return false;
    return !(await isLeftoverBrandingBytes(bytes));
  }

  if (typeof fetchImpl !== 'function') return false;
  const res = await fetchImpl(candidate, { method: 'GET', mode: 'cors' });
  if (!res || !res.ok) return false;
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (!bytes.byteLength) return false;
  if (!looksLikeImageBytes(bytes, res.headers?.get?.('content-type'))) return false;
  return !(await isLeftoverBrandingBytes(bytes));
}

/**
 * Accept a splash logo if it loads as an image and is not leftover branding.
 * Shipped Syntropia DNA at `/custom/logo.png` is rejected; a founder-uploaded
 * file with different bytes is accepted. Clover / GOS planet paths are rejected.
 * @param {string} url
 * @param {typeof fetch} [fetchImpl]
 */
export async function acceptSplashLogoUrl(url, fetchImpl = globalThis.fetch) {
  const candidate = String(url || '').trim();
  if (!candidate || isLeftoverPlatformLogoPath(candidate)) return false;
  return acceptBrandingAssetUrl(candidate, fetchImpl);
}

export function formatFullDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatTimeAgo(timestamp, t, locale) {
  const now = Date.now();
  const date = new Date(timestamp * 1000);
  const seconds = Math.floor((now - date.getTime()) / 1000);

  if (seconds < 60) return t('time.just_now');
  if (seconds < 3600) return t('time.minutes_ago', { values: { count: Math.floor(seconds / 60) } });
  if (seconds < 86400) return t('time.hours_ago', { values: { count: Math.floor(seconds / 3600) } });
  if (seconds < 604800) return t('time.days_ago', { values: { count: Math.floor(seconds / 86400) } });
  if (seconds < 2592000) return t('time.weeks_ago', { values: { count: Math.floor(seconds / 604800) } });
  return date.toLocaleDateString(locale || 'en', { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * @param {object[]} realms
 * @param {string} searchQuery
 * @param {string} filterStage
 * @param {string} sortBy
 */
export function filterAndSortRealms(realms, searchQuery, filterStage, sortBy) {
  let result = realms;

  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    result = result.filter(
      (realm) =>
        realm.id?.toLowerCase().includes(query) ||
        (realm.name || '').toLowerCase().includes(query) ||
        (realm.realm_name || '').toLowerCase().includes(query) ||
        (realm.manifesto || '').toLowerCase().includes(query)
    );
  }

  if (filterStage) {
    result = result.filter((realm) => (realm.realm_stage || 'alpha') === filterStage);
  }

  if (sortBy === 'users_desc') {
    result = [...result].sort((a, b) => (b.users_count || 0) - (a.users_count || 0));
  } else if (sortBy === 'users_asc') {
    result = [...result].sort((a, b) => (a.users_count || 0) - (b.users_count || 0));
  } else if (sortBy === 'newest') {
    result = [...result].sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  } else {
    result = [...result].sort((a, b) =>
      (a.name || a.realm_name || '').localeCompare(b.name || b.realm_name || '')
    );
  }

  return result;
}

export function getPrimaryZone(realm, realmZoneData) {
  const zones = realmZoneData[realm.id]?.zones;
  if (!zones?.length) return null;
  return [...zones].sort((a, b) => b.user_count - a.user_count)[0];
}
