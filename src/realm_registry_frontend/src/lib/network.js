// Runtime network detection and canister ID resolution.
//
// One dist serves every environment. The conductor writes `/canister_ids.js`
// into the deployed asset canister at deploy time (see casals.json, the
// realm-registry-frontend `files` block); it sets `globalThis.__CANISTER_IDS`
// with the environment's canister ids plus its `network` and `portal_url`.
// That file is the only source of environment identity: nothing here maps a
// host name or a network name to ids or hosts.

const viteEnv = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {};

/**
 * @typedef {import('../../scripts/gaas-env.js').GaasEnv} GaasEnv
 */

/**
 * @typedef {Record<string, string | boolean | undefined>} RuntimeCanisterIds
 */

/**
 * @returns {GaasEnv | undefined}
 */
function runtimeGaasEnv() {
	return typeof __GAAS_ENV__ !== 'undefined' ? __GAAS_ENV__ : undefined;
}

/**
 * `/canister_ids.js` as written by the conductor for this deployment.
 *
 * @returns {RuntimeCanisterIds | undefined}
 */
export function runtimeCanisterIds() {
	const runtime = typeof globalThis !== 'undefined' ? globalThis.__CANISTER_IDS : undefined;
	return runtime && typeof runtime === 'object' ? runtime : undefined;
}

/** Keys of `/canister_ids.js` that describe the environment rather than name a canister. */
const RUNTIME_META_KEYS = new Set(['network', 'portal_url']);

function isLocalHostname(hostname) {
	return hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost');
}

/**
 * The network this deployment was declared for.
 *
 * Order: dev override (`VITE_DEPLOY_QUEUE_NETWORK`), the conductor-written
 * `/canister_ids.js`, a local replica host, the build-time gaas-env descriptor.
 * Unknown means "" — never a guessed environment.
 *
 * @param {string | undefined} [hostname] - Optional hostname for testing
 * @param {GaasEnv | undefined} [gaasEnvOverride] - Optional gaas-env for testing
 * @param {RuntimeCanisterIds | undefined} [runtimeOverride] - Optional `/canister_ids.js` payload for testing
 * @returns {string}
 */
export function detectNetwork(hostname, gaasEnvOverride, runtimeOverride) {
	const override = viteEnv.VITE_DEPLOY_QUEUE_NETWORK;
	if (override) return override;

	const runtime = runtimeOverride ?? runtimeCanisterIds();
	if (runtime && typeof runtime.network === 'string' && runtime.network) {
		return runtime.network;
	}

	if (hostname === undefined) {
		if (typeof window === 'undefined') return '';
		hostname = window.location.hostname;
	}

	if (isLocalHostname(hostname)) {
		return 'local';
	}

	const gaasEnv = gaasEnvOverride ?? runtimeGaasEnv();
	if (gaasEnv?.network) return gaasEnv.network;

	return '';
}

/**
 * Resolve a canister ID for this deployment.
 *
 * Order: the conductor-written `/canister_ids.js`, the build-time gaas-env
 * descriptor (`gaas new --output-file`, one environment), then the dfx env
 * (`CANISTER_ID_*`, a local replica).
 *
 * @param {string} name - Canister name (e.g. 'realm_registry_backend')
 * @param {{ hostname?: string, envOverride?: Record<string, string>, gaasEnvOverride?: GaasEnv, runtimeOverride?: RuntimeCanisterIds }} [options]
 * @returns {string | undefined}
 */
export function getCanisterId(name, options = {}) {
	const { hostname, envOverride, gaasEnvOverride, runtimeOverride } = options;
	const runtime = runtimeOverride ?? runtimeCanisterIds();
	if (
		runtime &&
		!RUNTIME_META_KEYS.has(name) &&
		typeof runtime[name] === 'string' &&
		runtime[name]
	) {
		return runtime[name];
	}

	const network = detectNetwork(hostname, gaasEnvOverride, runtimeOverride);
	const gaasEnv = gaasEnvOverride ?? runtimeGaasEnv();
	const gaasCanisters = gaasEnv?.canisters;
	if (gaasCanisters && network && network !== 'local') {
		const gaasEntry = gaasCanisters[name];
		if (gaasEntry?.[network]) {
			return gaasEntry[network];
		}
	}

	const env = envOverride ?? viteEnv;
	const fromEnv = env[`CANISTER_ID_${name.toUpperCase()}`];
	if (fromEnv) return fromEnv;

	return undefined;
}
