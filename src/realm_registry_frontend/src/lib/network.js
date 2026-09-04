// Runtime network detection and canister ID resolution.
//
// Release builds ship a single tarball deployed to demo/staging/test/ic.
// Canister IDs are resolved at runtime from hostname + the build-injected
// __CANISTER_IDS__ map (full contents of repo-root canister_ids.json).

const viteEnv = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {};

/**
 * @typedef {import('../../scripts/gaas-env.js').GaasEnv} GaasEnv
 */

/**
 * @returns {GaasEnv | undefined}
 */
function runtimeGaasEnv() {
	return typeof __GAAS_ENV__ !== 'undefined' ? __GAAS_ENV__ : undefined;
}

/**
 * Detect the deployment network from hostname or build-time override.
 *
 * @param {string | undefined} [hostname] - Optional hostname for testing
 * @param {GaasEnv | undefined} [gaasEnvOverride] - Optional gaas-env for testing
 * @returns {string}
 */
export function detectNetwork(hostname, gaasEnvOverride) {
	const override = viteEnv.VITE_DEPLOY_QUEUE_NETWORK;
	if (override) return override;

	const gaasEnv = gaasEnvOverride ?? runtimeGaasEnv();

	if (hostname === undefined) {
		if (typeof window === 'undefined') return 'staging';
		hostname = window.location.hostname;
	}

	if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
		return 'local';
	}

	if (gaasEnv?.domain && hostname === gaasEnv.domain.replace(/^https?:\/\//, '').split('/')[0]) {
		return gaasEnv.network || 'staging';
	}

	if (hostname === 'test.gos.earth') return 'test';
	if (hostname === 'staging.gos.earth') return 'staging';
	if (hostname === 'demo.gos.earth') return 'demo';
	if (hostname === 'gos.earth' || hostname === 'registry.realmsgos.org') return 'ic';

	// Unrecognized host — typically the raw <canister-id>.icp0.io URL, used
	// whenever the custom domain is not wired up yet. The bundle was built for one
	// environment, so trust that rather than guessing: defaulting to staging made
	// a test deployment resolve staging canister ids and call canisters that do
	// not exist there.
	if (gaasEnv?.network) return gaasEnv.network;

	return 'staging';
}

/**
 * Resolve a canister ID for the current (or specified) network.
 *
 * @param {string} name - Canister name as in canister_ids.json (e.g. 'realm_registry_backend')
 * @param {{ hostname?: string, canisterIdsMap?: Record<string, Record<string, string>>, envOverride?: Record<string, string>, gaasEnvOverride?: GaasEnv }} [options]
 * @returns {string | undefined}
 */
export function getCanisterId(name, options = {}) {
	const { hostname, canisterIdsMap, envOverride, gaasEnvOverride } = options;
	const network = detectNetwork(hostname, gaasEnvOverride);
	const envKey = `CANISTER_ID_${name.toUpperCase()}`;

	const gaasEnv = gaasEnvOverride ?? runtimeGaasEnv();
	const gaasCanisters = gaasEnv?.canisters;
	if (gaasCanisters && network !== 'local') {
		const gaasEntry = gaasCanisters[name];
		if (gaasEntry?.[network]) {
			return gaasEntry[network];
		}
	}

	const ids =
		canisterIdsMap ??
		(typeof __CANISTER_IDS__ !== 'undefined' ? __CANISTER_IDS__ : undefined);

	if (ids) {
		const entry = ids[name];
		if (entry && network !== 'local' && entry[network]) {
			return entry[network];
		}
	}

	const env = envOverride ?? viteEnv;
	const fromEnv = env[envKey];
	if (fromEnv) return fromEnv;

	return undefined;
}
