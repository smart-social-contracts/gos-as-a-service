/** Registry of GOS implementations supported by the create-realm wizard. */

/**
 * @typedef {import('../../scripts/gaas-env.js').GaasEnv} GaasEnv
 */

const DEFAULT_GOS_METADATA = {
	'realms-gos': {
		name: 'Realms GOS',
		tagline: 'Governance Operating System — Python/Basilisk on the Internet Computer',
		description:
			'GGG-compliant governance with extensions, codices, treasury, justice and more.',
		gggConformance: '1.0'
	},
	'monad-gos': {
		name: 'Monad GOS',
		tagline: 'Law-as-inference — the Monad drafts from citizen wishes',
		description:
			'GGG-compliant Motoko governance on the Internet Computer — citizen wishes, inference, and the Monad.',
		gggConformance: '1.0'
	}
};

/** Casals wasm family names per GOS implementation (gaas-env does not send these). */
const GOS_ARTIFACT_KEYS = {
	'realms-gos': {
		backendWasmKey: 'realm-backend',
		frontendWasmKey: 'realm-assets'
	},
	'monad-gos': {
		backendWasmKey: 'monad-backend',
		frontendWasmKey: 'monad-assets'
	}
};

const DEFAULT_GOS_IMPLEMENTATIONS = [
	{
		id: 'realms-gos',
		name: 'Realms GOS',
		tagline: 'Governance Operating System — Python/Basilisk on the Internet Computer',
		description:
			'GGG-compliant governance with extensions, codices, treasury, justice and more.',
		available: true,
		loaderProfile: 'realms-iframe-v1',
		gggConformance: '1.0',
		...GOS_ARTIFACT_KEYS['realms-gos']
	},
	{
		id: 'monad-gos',
		name: 'Monad GOS',
		tagline: 'Law-as-inference — the Monad drafts from citizen wishes',
		description:
			'GGG-compliant Motoko governance on the Internet Computer — citizen wishes, inference, and the Monad.',
		available: true,
		loaderProfile: 'monad-iframe-v1',
		gggConformance: '1.0',
		...GOS_ARTIFACT_KEYS['monad-gos']
	}
];

/**
 * Build GOS implementation list from gaas-env descriptor entries.
 *
 * @param {NonNullable<GaasEnv['gos']>} gosEntries
 * @returns {typeof DEFAULT_GOS_IMPLEMENTATIONS}
 */
export function buildGosImplementationsFromEnv(gosEntries) {
	return gosEntries.map((entry) => {
		const meta = DEFAULT_GOS_METADATA[entry.implementation] || {
			name: entry.implementation,
			tagline: '',
			description: '',
			gggConformance: null
		};
		const artifactKeys = GOS_ARTIFACT_KEYS[entry.implementation] || {
			backendWasmKey: 'realm-backend',
			frontendWasmKey: 'realm-assets'
		};
		return {
			id: entry.implementation,
			name: meta.name,
			tagline: meta.tagline,
			description: meta.description,
			available: entry.available ?? false,
			loaderProfile: entry.loader_profile ?? null,
			gggConformance: meta.gggConformance ?? null,
			...artifactKeys,
			...(entry.version ? { defaultVersion: entry.version } : {})
		};
	});
}

/**
 * @param {GaasEnv | undefined} [gaasEnv]
 * @returns {typeof DEFAULT_GOS_IMPLEMENTATIONS}
 */
export function resolveGosImplementations(gaasEnv) {
	if (gaasEnv?.gos?.length) {
		return buildGosImplementationsFromEnv(gaasEnv.gos);
	}
	return DEFAULT_GOS_IMPLEMENTATIONS;
}

/**
 * @returns {GaasEnv | undefined}
 */
function runtimeGaasEnv() {
	return typeof __GAAS_ENV__ !== 'undefined' ? __GAAS_ENV__ : undefined;
}

export const GOS_IMPLEMENTATIONS = resolveGosImplementations(runtimeGaasEnv());

/** Wizard step definitions — platform concerns only; realm setup happens post-deploy. */
export const WIZARD_STEPS = [
	{ id: 'platform', label: 'Platform' },
	{ id: 'basics', label: 'Basics' },
	{ id: 'deploy', label: 'Review & Deploy' }
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
 *
 * @param {string} [_gosImplementationId]
 * @returns {typeof WIZARD_STEPS}
 */
export function visibleWizardSteps(_gosImplementationId) {
	return WIZARD_STEPS;
}

/**
 * Whether the wizard should render a version `<select>` (multiple choices).
 *
 * @param {Array<{ value: string, label: string }>} [options]
 */
export function shouldShowVersionPicker(options) {
	return Array.isArray(options) && options.length > 1;
}

/**
 * When exactly one version is available, return that option for read-only display.
 *
 * @param {Array<{ value: string, label: string }>} [options]
 * @returns {{ value: string, label: string }|null}
 */
export function soleDeployVersionOption(options) {
	if (!Array.isArray(options) || options.length !== 1) return null;
	return options[0];
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
		loader_profile: gosImpl.loaderProfile
	};
}
