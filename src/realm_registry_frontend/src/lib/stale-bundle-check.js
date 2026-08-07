import { browser } from '$app/environment';

/** @param {string} routePath */
function extractCreateRealmChunkHash(html) {
  const match = html.match(/nodes\/6\.([A-Za-z0-9_-]+)\.js/);
  return match?.[1] || null;
}

/** Collect any loaded create-realm node chunk hashes from the current page. */
function loadedCreateRealmChunkHashes() {
  /** @type {Set<string>} */
  const hashes = new Set();

  for (const script of document.querySelectorAll('script[src]')) {
    const match = script.src.match(/\/nodes\/6\.([A-Za-z0-9_-]+)\.js/);
    if (match) hashes.add(match[1]);
  }

  for (const entry of performance.getEntriesByType('resource')) {
    const match = entry.name.match(/\/nodes\/6\.([A-Za-z0-9_-]+)\.js/);
    if (match) hashes.add(match[1]);
  }

  return [...hashes];
}

/**
 * Returns true when the browser is running an outdated create-realm bundle
 * (usually the IC service worker serving cached HTML/JS after a deploy).
 *
 * @param {string} [routePath='/create-realm']
 */
export async function isCreateRealmBundleStale(routePath = '/create-realm') {
  if (!browser) return false;

  try {
    const response = await fetch(routePath, {
      cache: 'no-store',
      credentials: 'same-origin',
    });
    if (!response.ok) return false;

    const remoteHash = extractCreateRealmChunkHash(await response.text());
    if (!remoteHash) return false;

    const loaded = loadedCreateRealmChunkHashes();
    if (loaded.length === 0) return false;

    return loaded.some((hash) => hash !== remoteHash);
  } catch {
    return false;
  }
}

/** Reload once per tab session when a stale bundle is detected. */
export async function reloadIfCreateRealmBundleStale(routePath = '/create-realm') {
  if (!(await isCreateRealmBundleStale(routePath))) return false;

  const reloadKey = 'realms:create-realm:stale-reload';
  if (sessionStorage.getItem(reloadKey)) return true;

  sessionStorage.setItem(reloadKey, '1');
  window.location.reload();
  return true;
}
