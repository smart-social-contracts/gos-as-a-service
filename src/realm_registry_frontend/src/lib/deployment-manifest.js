import { CONFIG } from './config.js';
import { buildRealmDeploymentManifest as buildRealmDeploymentManifestWithConfig } from './deployment-manifest-core.js';

export {
  slugify,
  normalizeDeployVersion,
  portalUrlForSlug,
} from './deployment-manifest-core.js';

const REALMS_RELEASE_BASE =
  'https://github.com/smart-social-contracts/realms/releases/download';

/**
 * Resolve release asset checksums from build-time config (avoids CORS-blocked
 * browser fetch to github.com/releases/download/...).
 */
function releaseChecksums(tag) {
  const cs = CONFIG.deploy_release_checksums || {};
  const map = {};
  for (const [filename, hex] of Object.entries(cs)) {
    if (hex) map[filename] = hex.startsWith('sha256:') ? hex : `sha256:${hex}`;
  }
  return map;
}

/** Legacy GitHub release URLs (fallback when Casals is unavailable). */
function buildLegacyArtifactRefs(tag) {
  const cs = releaseChecksums(tag);
  const backendUrl = `${REALMS_RELEASE_BASE}/${tag}/realm_backend.wasm.gz`;
  const frontendUrl = `${REALMS_RELEASE_BASE}/${tag}/realm_frontend.tar.gz`;
  return {
    artifacts: {
      realm_backend: backendUrl,
      realm_frontend: frontendUrl,
    },
    expected_hashes: {
      backend_wasm: (cs['realm_backend.wasm.gz'] || '').replace(/^sha256:/, ''),
    },
  };
}

/**
 * Build the JSON manifest for realm_registry_backend.request_deployment.
 *
 * @param {object} formData - create-realm wizard state
 * @param {string} network - e.g. staging, demo
 * @param {{ deployVersion?: string, useCasals?: boolean }} [options]
 */
export async function buildRealmDeploymentManifest(formData, network, options = {}) {
  const manifest = buildRealmDeploymentManifestWithConfig(formData, network, CONFIG, options);
  if (options.useCasals === false) {
    const tag = CONFIG.deploy_release_tag;
    if (tag) Object.assign(manifest, buildLegacyArtifactRefs(tag));
  }
  return manifest;
}
