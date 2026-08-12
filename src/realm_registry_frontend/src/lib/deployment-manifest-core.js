import { buildGosManifestBlock } from './gos-implementations.js';

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

function networkTestFlags(network) {
  const net = (network || 'staging').toLowerCase();
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

export function networkInfra(network, config) {
  const net = (network || config.default_deploy_queue_network || 'staging').toLowerCase();
  // test is rebuilt from scratch by gaas; IDs must come from __GAAS_ENV__ injection.
  // A stale hardcoded fallback is worse than none (dead marketplace trust anchor).
  const fileRegistryFallbacks =
    net === 'test'
      ? null
      : {
          staging: 'iebdk-kqaaa-aaaau-agoxq-cai',
          demo: 'vi64l-3aaaa-aaaae-qj4va-cai',
        };
  const marketplaceFallbacks =
    net === 'test'
      ? null
      : {
          staging: 'jji3o-uyaaa-aaaah-qreja-cai',
          demo: 'ehyfg-wyaaa-aaaae-qg3qq-cai',
        };
  const file_registry_canister_id =
    config.file_registry_canister_id || (fileRegistryFallbacks?.[net] || '');
  const marketplace_canister_id =
    config.marketplace_canister_id || (marketplaceFallbacks?.[net] || '');
  const ii_derivation_origin = config.ii_derivation_origin || '';
  if (!file_registry_canister_id && !marketplace_canister_id && !ii_derivation_origin) return null;
  return { file_registry_canister_id, marketplace_canister_id, ii_derivation_origin };
}

function buildCasalsBlock(realmName, deployVersion, config, formData = {}) {
  const versionKey = normalizeDeployVersion(deployVersion);
  // Always pin the channel: a bare family name resolves conductor-side to the
  // newest *semver* in the family, which would silently pick e.g. 0.4.0 over
  // the main-channel snapshot whenever both are authorized.
  const block = {
    section: config.casals_section || 'Deployments',
    stand: slugify(realmName),
    backend_wasm_key: `realm-backend@${versionKey}`,
    frontend_wasm_key: `realm-assets@${versionKey}`,
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

  const testFlags = networkTestFlags(network);
  if (Object.keys(testFlags).length > 0) manifest.test_flags = testFlags;

  const slugInput = (formData.slug || '').trim();
  const federationSlug = slugify(slugInput || name);
  manifest.federation = {
    slug: federationSlug,
    portal_url: portalUrlForSlug(federationSlug, network, config),
  };

  return manifest;
}
