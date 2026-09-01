import { buildGosManifestBlock, getGosImplementation } from './gos-implementations.js';

export function slugify(name) {
  return (
    (name || 'realm')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 48) || 'realm'
  );
}

/** Normalize version for Casals wasm keys: semver without leading v, or `main`. */
export function normalizeDeployVersion(version) {
  const v = (version || '').trim();
  if (!v || v === 'latest') return 'main';
  if (v === 'main') return 'main';
  return v.replace(/^v/, '');
}

/** Canonical federation portal URL for a realm slug. */
export function portalUrlForSlug(slug, network, config = {}) {
  const hosts = {
    staging: 'https://staging.gos.earth',
    demo: 'https://demo.gos.earth',
    test: 'https://test.gos.earth',
    ic: 'https://registry.realmsgos.org',
    production: 'https://registry.realmsgos.org',
  };
  const base = config.portal_base_url || hosts[network] || hosts.staging;
  return `${base.replace(/\/$/, '')}/r/${slugify(slug)}`;
}

function networkTestFlags(network, config = {}) {
  if (config.can_test_mode === false) {
    return {};
  }
  const net = (network || 'staging').toLowerCase();
  if (net === 'ic' || net === 'production' || net === 'demo') {
    return {};
  }
  if (net === 'test') {
    return {
      test_mode: true,
      user_self_registration: true,
      demo_data: true,
      ii_bypass: true,
      skip_terms: true,
    };
  }
  if (net === 'staging') {
    return {
      test_mode: true,
      user_self_registration: true,
      demo_data: false,
      ii_bypass: false,
      skip_terms: false,
    };
  }
  return {};
}

export function networkInfra(network, config) {
  const ii_derivation_origin = config.ii_derivation_origin || '';
  if (!ii_derivation_origin) return null;
  return { ii_derivation_origin };
}

function buildCasalsBlock(realmName, deployVersion, config, formData = {}) {
  const versionKey = normalizeDeployVersion(deployVersion);
  const gosImplId = formData.gos_implementation || 'realms-gos';
  const gosImpl = getGosImplementation(gosImplId);
  const backendKey = gosImpl?.backendWasmKey || 'realm-backend';
  const frontendKey = gosImpl?.frontendWasmKey || 'realm-assets';
  // Always pin the channel: a bare family name resolves conductor-side to the
  // newest *semver* in the family, which would silently pick e.g. 0.4.0 over
  // the main-channel snapshot whenever both are authorized.
  const block = {
    section: config.casals_section || 'Deployments',
    stand: slugify(realmName),
    backend_wasm_key: `${backendKey}@${versionKey}`,
    frontend_wasm_key: `${frontendKey}@${versionKey}`,
  };

  const choice = (formData.subnet_choice || 'automatic').toLowerCase();
  if (choice === 'european') {
    block.subnet_type = 'european';
  } else if (choice === 'other') {
    const subnetId = (formData.subnet_id || '').trim();
    if (subnetId) {
      block.subnet = subnetId;
    }
  }

  return block;
}

/**
 * Build deployment manifest JSON (config-injected for unit tests).
 *
 * Codex, token, and branding are configured in-realm after deploy (issue #8).
 */
export function buildRealmDeploymentManifest(formData, network, config = {}, options = {}) {
  const name = (formData.name || '').trim();
  const deployVersion =
    options.deployVersion || formData.deploy_version || config.default_deploy_version || 'main';
  const useCasals = options.useCasals !== false;

  const realm = {
    name,
    display_name: name,
    manifesto: `Welcome to ${name}.`,
    welcome_message: `Welcome to ${name}!`,
    open_registration: false,
    extensions: [],
  };

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
    manifest.casals = buildCasalsBlock(name, deployVersion, config, formData);
  }

  const infra = networkInfra(network, config);
  if (infra) manifest.infra = infra;

  if (config.can_test_mode === true) {
    manifest.can_test_mode = true;
  }

  const testFlags = networkTestFlags(network, config);
  if (Object.keys(testFlags).length > 0) manifest.test_flags = testFlags;

  const slugInput = (formData.slug || '').trim();
  const federationSlug = slugify(slugInput || name);
  manifest.federation = {
    slug: federationSlug,
    portal_url: portalUrlForSlug(federationSlug, network, config),
  };

  const founder = ((formData.founder || options.founder || '')).trim();
  if (founder) {
    manifest.founder = founder;
  }

  return manifest;
}
