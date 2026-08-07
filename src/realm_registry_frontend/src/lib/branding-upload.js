/**
 * Decentralized branding upload.
 *
 * Uploads the realm's branding images (logo, background) straight from the
 * user's browser into the file_registry canister — signed by the user's own
 * Internet Identity, with no centralized server in the path. The first caller
 * of a fresh namespace becomes its publisher (file_registry auto-grant), so the
 * user owns their realm's branding namespace.
 *
 * Returns a registry descriptor that maps 1:1 onto the realm backend's
 * `install_branding_from_registry({registry_canister_id, namespace, files})`
 * method, which the realm_installer calls post-provision to serve the images at
 * /custom/ on the realm's frontend asset canister:
 *
 *   { file_registry_canister_id, namespace,
 *     files: { "/custom/logo.png": "logo.png",
 *              "/custom/background.png": "background.png" } }
 */
import { uploadAndPublish } from './file-registry-client.js';

/** Asset keys served on the realm frontend, mapped to their registry paths. */
const ASSET_KEYS = {
  logo: '/custom/logo.png',
  background: '/custom/background.png',
};
const REGISTRY_PATHS = {
  logo: 'logo.png',
  background: 'background.png',
};

/**
 * @param {{
 *   logo?: File|null,
 *   background?: File|null,
 *   namespace: string,
 *   fileRegistryCanisterId: string,
 *   onProgress?: Function,
 * }} opts
 * @returns {Promise<{
 *   file_registry_canister_id: string,
 *   namespace: string,
 *   files: Record<string, string>,
 * } | null>} descriptor for install_branding_from_registry, or null if no images.
 */
export async function uploadBrandingFiles(opts) {
  const { logo, background, namespace, fileRegistryCanisterId, onProgress } = opts || {};

  if (!logo && !background) return null;
  if (!fileRegistryCanisterId) {
    throw new Error('No file_registry canister configured for this network');
  }
  if (!namespace) {
    throw new Error('A branding namespace is required');
  }

  const uploads = [];
  const files = {};
  if (logo) {
    uploads.push({ path: REGISTRY_PATHS.logo, file: logo });
    files[ASSET_KEYS.logo] = REGISTRY_PATHS.logo;
  }
  if (background) {
    uploads.push({ path: REGISTRY_PATHS.background, file: background });
    files[ASSET_KEYS.background] = REGISTRY_PATHS.background;
  }

  await uploadAndPublish(fileRegistryCanisterId, namespace, uploads, onProgress);

  return {
    file_registry_canister_id: fileRegistryCanisterId,
    namespace,
    files,
  };
}

/**
 * Build a stable, collision-resistant branding namespace for a realm.
 * Includes a random suffix so two users picking the same realm name don't
 * fight over namespace ownership (first caller becomes publisher).
 *
 * @param {string} realmName
 * @returns {string}
 */
export function brandingNamespaceFor(realmName) {
  const slug = String(realmName || 'realm')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32) || 'realm';
  let rand;
  try {
    rand = crypto.randomUUID().replace(/-/g, '').slice(0, 8);
  } catch {
    rand = Math.random().toString(36).slice(2, 10);
  }
  return `branding-${slug}-${rand}`;
}
