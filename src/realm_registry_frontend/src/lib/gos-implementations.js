/** Registry of GOS implementations supported by the create-realm wizard. */

export const GOS_IMPLEMENTATIONS = [
  {
    id: 'realms-gos',
    name: 'Realms GOS',
    tagline: 'Governance Operating System — Python/Basilisk on the Internet Computer',
    description:
      'GGG-compliant governance with extensions, codices, treasury, justice and more.',
    available: true,
    loaderProfile: 'realms-iframe-v1',
    gggConformance: '1.0',
  },
  {
    id: 'chora-gos',
    name: 'Chora GOS',
    tagline: 'A second GOS implementation',
    description:
      'In development. The gos.earth platform is implementation-agnostic — any GGG-conforming GOS can join.',
    available: false,
    loaderProfile: null,
    gggConformance: null,
  },
];

/** Wizard step definitions (platform first, then Realms-specific steps). */
export const WIZARD_STEPS = [
  { id: 'platform', label: 'Platform' },
  { id: 'codex', label: 'Codex', realmsOnly: true },
  { id: 'token', label: 'Token', realmsOnly: true },
  { id: 'basics', label: 'Basics' },
  { id: 'branding', label: 'Branding' },
  { id: 'deploy', label: 'Deploy' },
];

/**
 * @param {string} [id]
 * @returns {typeof GOS_IMPLEMENTATIONS[number]|undefined}
 */
export function getGosImplementation(id) {
  if (!id) return undefined;
  return GOS_IMPLEMENTATIONS.find((impl) => impl.id === id);
}

/**
 * Steps visible for the chosen GOS implementation.
 * Realms-specific codex/token steps are omitted for other implementations.
 *
 * @param {string} [gosImplementationId]
 * @returns {typeof WIZARD_STEPS}
 */
export function visibleWizardSteps(gosImplementationId) {
  const isRealms = (gosImplementationId || 'realms-gos') === 'realms-gos';
  return WIZARD_STEPS.filter((step) => !step.realmsOnly || isRealms);
}

/** Normalize version for GOS manifest: semver without leading v, or `main`. */
export function normalizeGosDeployVersion(version) {
  const v = (version || '').trim();
  if (!v || v === 'latest') return 'main';
  if (v === 'main') return 'main';
  return v.replace(/^v/, '');
}

/**
 * Build the top-level `gos` block for a deployment manifest.
 *
 * @param {string} [gosImplementationId]
 * @param {string} [deployVersion]
 */
export function buildGosManifestBlock(gosImplementationId, deployVersion) {
  const gosImpl = getGosImplementation(gosImplementationId) || getGosImplementation('realms-gos');
  const version = normalizeGosDeployVersion(deployVersion);
  return {
    implementation: gosImpl.id,
    version,
    ggg_conformance: gosImpl.gggConformance,
    loader_profile: gosImpl.loaderProfile,
  };
}
