/** Helpers for rendering deployment manifest + branding on the details page. */

const BRANDING_LABELS = {
  '/custom/logo.png': 'Logo',
  'logo.png': 'Logo',
  '/custom/background.png': 'Background',
  'background.png': 'Background',
};

/**
 * @param {string|null|undefined} raw
 * @returns {object|null}
 */
export function parseDeploymentManifest(raw) {
  if (!raw || typeof raw !== 'string') return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * @param {object|null} manifest
 * @returns {object}
 */
export function summarizeManifest(manifest) {
  if (!manifest) return {};
  const realm = manifest.realm || {};
  return {
    name: manifest.name || realm.name || '',
    network: manifest.network || '',
    openRegistration: !!realm.open_registration,
    codex: realm.codex?.package || '',
    codexVersion: realm.codex?.version || '',
    extensions: Array.isArray(realm.extensions) ? realm.extensions : [],
    slug: manifest.federation?.slug || '',
    portalUrl: manifest.federation?.portal_url || '',
    requestingPrincipal: manifest.requesting_principal || '',
  };
}

/**
 * @param {object|null} manifest
 * @param {{ frontendCanisterId?: string }} [opts]
 * @returns {Array<{ key: string, label: string, registryUrl: string|null, realmUrl: string|null }>}
 */
export function brandingAssetsFromManifest(manifest, opts = {}) {
  const branding = manifest?.branding;
  if (!branding?.namespace || !branding?.files) return [];

  const frId = (branding.file_registry_canister_id || manifest?.infra?.file_registry_canister_id || '').trim();
  const frontendId = (opts.frontendCanisterId || '').trim();
  const rawStatus = (opts.rawStatus || '').toLowerCase();
  // User branding is pulled onto the realm frontend during registration.
  // Until then /custom/* serves bundled template placeholders — show registry uploads.
  const preferRegistry =
    opts.preferRegistry === true ||
    (!opts.preferRegistry &&
      rawStatus &&
      !['registering', 'completed'].includes(rawStatus));
  const ns = branding.namespace;
  const out = [];

  for (const [assetKey, registryPath] of Object.entries(branding.files)) {
    const path = String(registryPath || '').replace(/^\//, '');
    const label = BRANDING_LABELS[assetKey] || BRANDING_LABELS[path] || path || assetKey;
    const registryUrl = frId && path
      ? `https://${frId}.raw.icp0.io/${ns}/${path}`
      : null;
    const realmPath = assetKey.startsWith('/') ? assetKey : `/${assetKey}`;
    const realmUrl = frontendId
      ? `https://${frontendId}.icp0.io${realmPath}`
      : null;
    const primaryUrl = preferRegistry ? (registryUrl || realmUrl) : (realmUrl || registryUrl);
    const primarySource = preferRegistry
      ? (registryUrl ? 'registry' : realmUrl ? 'realm' : null)
      : (realmUrl ? 'realm' : registryUrl ? 'registry' : null);
    out.push({
      key: assetKey,
      label,
      registryUrl,
      realmUrl,
      primaryUrl,
      primarySource,
    });
  }
  return out;
}

/**
 * @param {object|null} manifest
 * @returns {string}
 */
export function formatManifestJson(manifest) {
  if (!manifest) return '{}';
  return JSON.stringify(manifest, null, 2);
}
