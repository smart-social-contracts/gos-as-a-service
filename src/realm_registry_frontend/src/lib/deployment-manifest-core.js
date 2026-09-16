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

/**
 * Canonical federation portal URL for a realm slug. The portal origin comes
 * from this deployment's config (`/canister_ids.js` → CONFIG.portal_base_url);
 * "" when none is declared, in which case the registry fills in its own
 * configured portal when the slug is claimed.
 */
export function portalUrlForSlug(slug, network, config = {}) {
  const base = (config.portal_base_url || '').replace(/\/$/, '');
  if (!base) return '';
  return `${base}/r/${slugify(slug)}`;
}

export function networkInfra(network, config) {
  const ii_derivation_origin = config.ii_derivation_origin || '';
  if (!ii_derivation_origin) return null;
  return { ii_derivation_origin };
}

function buildCasalsBlock(realmName, config, formData = {}) {
  // Which WASMs a realm runs is declared once by the Deployments
  // stand_template in the GaaS sheet; the wizard only names the stand.
  const block = {
    section: config.casals_section || 'Deployments',
    stand: slugify(realmName),
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
    network: network || '',
    deploy_mode: 'install',
    deploy_scope: 'both',
    deploy_version: normalizedVersion,
    gos: buildGosManifestBlock(gosImplId, deployVersion),
    realm,
  };

  if (useCasals) {
    manifest.casals = buildCasalsBlock(name, config, formData);
  }

  const infra = networkInfra(network, config);
  if (infra) manifest.infra = infra;

  if (config.can_test_mode === true) {
    manifest.can_test_mode = true;
  }

  // Test flags are the registry's to stamp (apply_env_inheritance, from the
  // environment's casals.json); the wizard sends none of its own.

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
