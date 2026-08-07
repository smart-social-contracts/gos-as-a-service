import { CONFIG } from './config.js';
import { buildGosManifestBlock } from './gos-implementations.js';

const REALMS_RELEASE_BASE =
  'https://github.com/smart-social-contracts/realms/releases/download';

export function slugify(name) {
  return (
    (name || 'realm')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 48) || 'realm'
  );
}

/** Canonical federation portal URL for a realm slug. */
export function portalUrlForSlug(slug, network) {
  const hosts = {
    staging: 'https://staging.gos.earth',
    demo: 'https://demo.gos.earth',
    test: 'https://test.gos.earth',
    ic: 'https://registry.realmsgos.org',
    production: 'https://registry.realmsgos.org',
  };
  const base = CONFIG.portal_base_url || hosts[network] || hosts.staging;
  return `${base.replace(/\/$/, '')}/r/${slugify(slug)}`;
}

/** Normalize version for Casals wasm keys: semver without leading v, or `main`. */
export function normalizeDeployVersion(version) {
  const v = (version || '').trim();
  if (!v || v === 'latest') return 'main';
  if (v === 'main') return 'main';
  return v.replace(/^v/, '');
}

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

/** Shared infra IDs per network — mirrors deployment-descriptors/*-mundus-layered.yml */
function networkInfra(network) {
  const net = (network || CONFIG.default_deploy_queue_network || 'staging').toLowerCase();
  const file_registry_canister_id =
    CONFIG.file_registry_canister_id ||
    ({
      staging: 'iebdk-kqaaa-aaaau-agoxq-cai',
      demo: 'vi64l-3aaaa-aaaae-qj4va-cai',
      test: 'uq2mu-kaaaa-aaaah-avqcq-cai',
    }[net] ||
      '');
  const marketplace_canister_id =
    CONFIG.marketplace_canister_id ||
    ({
      staging: 'jji3o-uyaaa-aaaah-qreja-cai',
      demo: 'ehyfg-wyaaa-aaaae-qg3qq-cai',
      test: '2wldc-niaaa-aaaad-qlxga-cai',
    }[net] ||
      '');
  // Federation portal: the portal origin is the ONLY II login surface, so realms
  // must NOT pin a derivationOrigin (FEDERATION_PORTAL.md — the ii-alternative-
  // origins 10-origin cap cannot scale with unbounded wizard realms). Escape
  // hatch only: explicit CONFIG.ii_derivation_origin (VITE_II_DERIVATION_ORIGIN).
  const ii_derivation_origin = CONFIG.ii_derivation_origin || '';
  if (!file_registry_canister_id && !marketplace_canister_id && !ii_derivation_origin)
    return null;
  return { file_registry_canister_id, marketplace_canister_id, ii_derivation_origin };
}

/**
 * Staging/demo test flags for wizard-deployed realms — same as mundus layered
 * descriptors (real Internet Identity, Terms step; no II bypass).
 */
function networkTestFlags(network) {
  const net = (network || 'staging').toLowerCase();
  if (net === 'staging') {
    return {
      test_mode: true,
      user_self_registration: true,
      demo_data: false,
      ii_bypass: false,
      skip_terms: false,
    };
  }
  if (net === 'demo') {
    return {
      test_mode: true,
      user_self_registration: true,
      demo_data: true,
      ii_bypass: false,
      skip_terms: false,
    };
  }
  return {};
}

function buildCasalsBlock(realmName, deployVersion) {
  const versionKey = normalizeDeployVersion(deployVersion);
  // Bare family name => Casals picks the newest authorized WASM in that family.
  // Pinned semver (e.g. 0.4.0) => exact realm-backend@0.4.0 key.
  const keySuffix = versionKey === 'main' ? '' : `@${versionKey}`;
  return {
    section: CONFIG.casals_section || 'Deployments',
    stand: slugify(realmName),
    backend_wasm_key: `realm-backend${keySuffix}`,
    frontend_wasm_key: `realm-assets${keySuffix}`,
  };
}

/**
 * Build the JSON manifest for realm_registry_backend.request_deployment.
 *
 * @param {object} formData - create-realm wizard state
 * @param {string} network - e.g. staging, demo
 * @param {{ file_registry_canister_id: string, namespace: string,
 *           files: Record<string,string> }} [branding]
 * @param {{ deployVersion?: string, useCasals?: boolean,
 *           configOverrides?: Record<string, any> }} [options]
 */
export async function buildRealmDeploymentManifest(
  formData,
  network,
  branding,
  options = {},
) {
  const name = (formData.name || '').trim();
  const lang = (formData.languages && formData.languages[0]) || 'en';
  const deployVersion =
    options.deployVersion || formData.deploy_version || CONFIG.default_deploy_version || 'main';
  const useCasals = options.useCasals !== false;

  let manifesto = (formData.manifestos && formData.manifestos[lang]) || '';
  if (!manifesto && formData.manifestos) {
    manifesto =
      Object.values(formData.manifestos).find((s) => s && String(s).trim()) || '';
  }
  manifesto = String(manifesto).trim() || `Welcome to ${name}.`;

  let welcome_message = (formData.welcome_messages && formData.welcome_messages[lang]) || '';
  if (!welcome_message && formData.welcome_messages) {
    welcome_message =
      Object.values(formData.welcome_messages).find((s) => s && String(s).trim()) || '';
  }
  welcome_message =
    String(welcome_message).trim() || `Welcome to ${name}!`;

  const realm = {
    name,
    display_name: name,
    manifesto,
    welcome_message,
    open_registration: !!formData.open_registration,
    // The codex package is the single source of truth for which extensions
    // get installed (issue #242); the wizard no longer picks extensions.
    extensions: [],
  };

  if (formData.codex_package_name?.trim()) {
    realm.codex = {
      package: formData.codex_package_name.trim(),
      version: (formData.codex_package_version || 'latest').trim(),
    };
  } else {
    realm.codex = { package: 'syntropia', version: 'latest' };
  }

  // Realm token choice: mint a new ledger, or adopt an existing shared one
  // (REALMS / ckBTC / ckUSDC).
  if (formData.token_mode === 'existing' && formData.token_existing) {
    realm.token = { existing: String(formData.token_existing) };
  } else if (formData.token_name?.trim() && formData.token_symbol?.trim()) {
    realm.token = {
      name: formData.token_name.trim(),
      symbol: formData.token_symbol.trim().toUpperCase(),
    };
  }

  if (formData.assistant) {
    realm.assistant = formData.assistant;
  }

  // Codex parameter choices (issue #253): nested config values the user
  // changed from the codex defaults. The installer stores them under
  // manifest_data.config_overrides on the new realm; the codex's get_config
  // applies them over its declared blocks.
  if (options.configOverrides && Object.keys(options.configOverrides).length > 0) {
    realm.config_overrides = options.configOverrides;
  }

  const gosImplId = formData.gos_implementation || 'realms-gos';
  const normalizedVersion = normalizeDeployVersion(deployVersion);

  const manifest = {
    name,
    network: network || 'staging',
    deploy_mode: 'install',
    deploy_scope: 'both',
    deploy_version: normalizedVersion,
    gos: buildGosManifestBlock(gosImplId, deployVersion),
    realm,
  };

  if (useCasals) {
    manifest.casals = buildCasalsBlock(name, deployVersion);
  } else {
    const tag = CONFIG.deploy_release_tag;
    Object.assign(manifest, tag ? buildLegacyArtifactRefs(tag) : {});
  }

  const infra = networkInfra(network);
  if (infra) {
    manifest.infra = infra;
  }

  const testFlags = networkTestFlags(network);
  if (Object.keys(testFlags).length > 0) {
    manifest.test_flags = testFlags;
  }

  if (branding?.namespace && branding?.files && Object.keys(branding.files).length > 0) {
    manifest.branding = {
      file_registry_canister_id: branding.file_registry_canister_id || '',
      namespace: branding.namespace,
      files: branding.files,
    };
  }

  const federationSlug = slugify(name);
  manifest.federation = {
    slug: federationSlug,
    portal_url: portalUrlForSlug(federationSlug, network),
  };

  return manifest;
}
