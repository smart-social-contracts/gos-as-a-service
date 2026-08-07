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
