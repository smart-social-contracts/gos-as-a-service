// Runtime configuration — canister IDs and test mode flags.
//
// Test mode flags are read from the registry backend at runtime via
// get_runtime_flags(), NOT baked in at build time. This matches realm frontends
// and allows set_canister_config_json to flip flags without rebuilding assets.
//
// VITE_* and URL params (?testmode=1&ii_bypass=1) remain as local-dev overrides only
// until get_runtime_flags loads; after that the backend is authoritative.

import { getRegistryRuntimeFlagsSnapshot } from '$lib/stores/registryRuntimeFlags.js';
import { detectNetwork, getCanisterId } from './network.js';
import {
	resolveBillingServiceUrl,
	resolveDeployServiceUrl,
	resolvePortalBaseUrl,
	resolvePortalHosts
} from './config-resolvers.js';

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

const gaasEnv = runtimeGaasEnv();
const network = detectNetwork(undefined, gaasEnv);
const portalHosts = resolvePortalHosts(viteEnv, gaasEnv, network);

export { resolveBillingServiceUrl, resolveDeployServiceUrl, resolvePortalBaseUrl, resolvePortalHosts };

export const CONFIG = {
	internet_identity_url: viteEnv.VITE_INTERNET_IDENTITY_URL || 'https://identity.ic0.app/',
	/** Federation portal: login on this origin only — no derivationOrigin pinning. */
	federation_portal: viteEnv.VITE_FEDERATION_PORTAL !== 'false',
	ii_derivation_origin:
		viteEnv.VITE_II_DERIVATION_ORIGIN ||
		(viteEnv.VITE_FEDERATION_PORTAL === 'false' ? portalHosts[network] || '' : ''),
	portal_base_url: resolvePortalBaseUrl(viteEnv, gaasEnv, network),
	portal_hosts: portalHosts,
	deploy_queue_network: network,
	billing_service_url: resolveBillingServiceUrl(viteEnv, gaasEnv),
	realm_registry_backend_canister_id:
		getCanisterId('realm_registry_backend') ||
		viteEnv.VITE_REALM_REGISTRY_BACKEND_CANISTER_ID ||
		viteEnv.CANISTER_ID_REALM_REGISTRY_BACKEND ||
		'',
	realm_installer_canister_id:
		getCanisterId('realm_installer') ||
		viteEnv.VITE_REALM_INSTALLER_CANISTER_ID ||
		viteEnv.CANISTER_ID_REALM_INSTALLER ||
		'',
	default_deploy_queue_network: network,
	deploy_release_tag: viteEnv.VITE_DEPLOY_RELEASE_TAG || 'v0.4.0',
	default_deploy_version: viteEnv.VITE_DEFAULT_DEPLOY_VERSION || 'main',
	casals_section: viteEnv.VITE_CASALS_SECTION || 'Deployments',
	deploy_release_checksums: {
		'realm_backend.wasm.gz':
			viteEnv.VITE_DEPLOY_RELEASE_BACKEND_CHECKSUM ||
			'c9c38a714762fe56e53534c488e645351deb7905020001b408f054c034b5c408',
		'realm_frontend.tar.gz':
			viteEnv.VITE_DEPLOY_RELEASE_FRONTEND_CHECKSUM ||
			'58cf46349679f137c9e481aa7831d367ee14f0f6aba78de9b76a2385d5031406'
	},
	deploy_service_url: resolveDeployServiceUrl(viteEnv, gaasEnv),
	file_registry_canister_id:
		getCanisterId('file_registry') ||
		viteEnv.VITE_FILE_REGISTRY_CANISTER_ID ||
		viteEnv.CANISTER_ID_FILE_REGISTRY ||
		'',
	marketplace_canister_id:
		getCanisterId('marketplace_backend') ||
		viteEnv.VITE_MARKETPLACE_CANISTER_ID ||
		viteEnv.CANISTER_ID_MARKETPLACE_BACKEND ||
		'',
	casals_backend_canister_id:
		getCanisterId('casals_backend') ||
		viteEnv.VITE_CASALS_BACKEND_CANISTER_ID ||
		viteEnv.CANISTER_ID_CASALS_BACKEND ||
		''
};

function _readFlag(envKey, urlParam) {
	if (viteEnv[envKey] === 'true') return true;
	if (typeof window !== 'undefined') {
		const params = new URLSearchParams(window.location.search);
		if (params.get(urlParam) === '1') {
			sessionStorage.setItem(urlParam, '1');
			return true;
		}
		if (sessionStorage.getItem(urlParam) === '1') return true;
	}
	return false;
}

function _viteTestMode() {
	return _readFlag('VITE_TEST_MODE', 'testmode');
}

/** True once get_runtime_flags succeeded — backend flags are then authoritative. */
function _runtimeFlagsReady() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	return !flags.loading && !flags.error;
}

function _localDevFlag(envKey, urlParam) {
	if (!_viteTestMode()) return false;
	return _readFlag(envKey, urlParam);
}

export function getTestMode() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testMode;
	if (flags.testMode) return true;
	return _viteTestMode();
}

export function getTestModeIIBypass() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testModeIIBypass;
	if (flags.testModeIIBypass) return true;
	return _localDevFlag('VITE_TEST_MODE_II_BYPASS', 'ii_bypass');
}

export function getTestModeUserSelfRegistration() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testModeUserSelfRegistration;
	if (flags.testModeUserSelfRegistration) return true;
	return _localDevFlag('VITE_TEST_MODE_USER_SELF_REGISTRATION', 'user_self_registration');
}

export function getTestModeDemoData() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testModeDemoData;
	if (flags.testModeDemoData) return true;
	return _localDevFlag('VITE_TEST_MODE_DEMO_DATA', 'demo_data');
}

export function getTestModeSkipTerms() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testModeSkipTerms;
	if (flags.testModeSkipTerms) return true;
	return _localDevFlag('VITE_TEST_MODE_SKIP_TERMS', 'skip_terms');
}

export function getTestModeSkipPassportZkproof() {
	const flags = getRegistryRuntimeFlagsSnapshot();
	if (_runtimeFlagsReady()) return flags.testModeSkipPassportZkproof;
	if (flags.testModeSkipPassportZkproof) return true;
	return _localDevFlag('VITE_TEST_MODE_SKIP_PASSPORT_ZKPROOF', 'skip_passport_zkproof');
}

// Legacy constant exports — always false at import time. Use getters above.
export const TEST_MODE = false;
export const TEST_MODE_II_BYPASS = false;
export const TEST_MODE_USER_SELF_REGISTRATION = false;
export const TEST_MODE_DEMO_DATA = false;
export const TEST_MODE_SKIP_TERMS = false;
export const TEST_MODE_SKIP_PASSPORT_ZKPROOF = false;
