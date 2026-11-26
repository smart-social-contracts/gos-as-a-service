/**
 * Pure config resolution helpers shared by config.js and unit tests.
 *
 * The portal origin is declared per environment in casals.json
 * (`environments.<env>.portal_url`) and reaches this bundle through the
 * conductor-written `/canister_ids.js` (`portal_url`). There is no table of
 * hosts by network name here.
 */

/**
 * @typedef {import('../../scripts/gaas-env.js').GaasEnv} GaasEnv
 */

/**
 * @param {string} domain
 * @returns {string}
 */
export function portalOriginForDomain(domain) {
	return `https://${domain.replace(/^https?:\/\//, '').replace(/\/$/, '')}`;
}

/**
 * @param {Record<string, string>} viteEnvOverride
 * @param {GaasEnv | undefined} gaasEnv
 * @param {{ portal_url?: string | boolean } | undefined} [runtime] - `/canister_ids.js` payload
 * @returns {string} the portal origin, or "" when this deployment declares none
 */
export function resolvePortalBaseUrl(viteEnvOverride, gaasEnv, runtime) {
	if (viteEnvOverride.VITE_PORTAL_BASE_URL) return viteEnvOverride.VITE_PORTAL_BASE_URL;
	if (runtime && typeof runtime.portal_url === 'string' && runtime.portal_url.trim()) {
		return runtime.portal_url.trim().replace(/\/$/, '');
	}
	if (gaasEnv?.domain) {
		return portalOriginForDomain(gaasEnv.domain);
	}
	return '';
}

/** Where people sign in when a deployment names no Internet Identity of its own. */
export const MAINNET_INTERNET_IDENTITY_URL = 'https://identity.ic0.app/';

/**
 * The Internet Identity this deployment signs people in at.
 *
 * Order: dev override (`VITE_INTERNET_IDENTITY_URL`), the conductor-written `/canister_ids.js`
 * (`internet_identity`, the key a realm frontend reads too), then the mainnet one. A local network or a
 * staging stack with its own Internet Identity names it in the sheet's `files` block, with no rebuild.
 *
 * @param {Record<string, string>} viteEnvOverride
 * @param {{ internet_identity?: string | boolean } | undefined} [runtime] - `/canister_ids.js` payload
 * @returns {string}
 */
export function resolveInternetIdentityUrl(viteEnvOverride, runtime) {
	if (viteEnvOverride.VITE_INTERNET_IDENTITY_URL) return viteEnvOverride.VITE_INTERNET_IDENTITY_URL;
	if (runtime && typeof runtime.internet_identity === 'string' && runtime.internet_identity.trim()) {
		return runtime.internet_identity.trim();
	}
	return MAINNET_INTERNET_IDENTITY_URL;
}

/**
 * The origin whose Internet Identity principals this portal signs people in with, or "" for the portal's
 * own. II gives one person a different principal per origin; naming another origin here makes the
 * portal's principals that origin's, which II allows only when that origin lists the portal in its
 * `/.well-known/ii-alternative-origins` (else every sign-in fails with "Unverified origin"). Realms
 * created here are told the same origin (`networkInfra`).
 *
 * Order: dev override (`VITE_II_DERIVATION_ORIGIN`), the conductor-written `/canister_ids.js`
 * (`derivation_origin`, the key a realm frontend reads too), then the legacy non-portal build
 * (`VITE_FEDERATION_PORTAL=false`), where realms signed in directly and pinned the portal's origin.
 *
 * @param {Record<string, string>} viteEnvOverride
 * @param {{ derivation_origin?: string | boolean } | undefined} runtime - `/canister_ids.js` payload
 * @param {string} portalBaseUrl - from `resolvePortalBaseUrl`
 * @returns {string} an origin without a trailing slash, or ""
 */
export function resolveIiDerivationOrigin(viteEnvOverride, runtime, portalBaseUrl) {
	if (viteEnvOverride.VITE_II_DERIVATION_ORIGIN) return viteEnvOverride.VITE_II_DERIVATION_ORIGIN;
	if (runtime && typeof runtime.derivation_origin === 'string' && runtime.derivation_origin.trim()) {
		return runtime.derivation_origin.trim().replace(/\/$/, '');
	}
	return viteEnvOverride.VITE_FEDERATION_PORTAL === 'false' ? portalBaseUrl : '';
}

/** The Geister API every non-local deployment has used so far. */
export const DEFAULT_GEISTER_API_ORIGIN = 'https://geister-api.realmsgos.dev';

/**
 * The Geister API the assistant talks to, or "" when this deployment has none.
 *
 * Order: dev override (`VITE_GEISTER_API_ORIGIN`, a local end-to-end build), the conductor-written
 * `/canister_ids.js` (`geister_api_url`; an empty one declares "none"), then the default host. A local
 * network has no default: a local stack must not depend on a remote service being up (the assistant
 * panel says it is off instead).
 *
 * @param {Record<string, string>} viteEnvOverride
 * @param {{ geister_api_url?: string | boolean } | undefined} runtime - `/canister_ids.js` payload
 * @param {string} network - from `detectNetwork`
 * @returns {string} an origin without a trailing slash, or ""
 */
export function resolveGeisterApiOrigin(viteEnvOverride, runtime, network) {
	const origin = (value) => value.trim().replace(/\/$/, '');
	if (viteEnvOverride.VITE_GEISTER_API_ORIGIN) return origin(viteEnvOverride.VITE_GEISTER_API_ORIGIN);
	if (runtime && typeof runtime.geister_api_url === 'string') return origin(runtime.geister_api_url);
	return network === 'local' ? '' : DEFAULT_GEISTER_API_ORIGIN;
}

/**
 * @param {Record<string, string>} viteEnvOverride
 * @param {GaasEnv | undefined} gaasEnv
 * @returns {string | null}
 */
export function resolveBillingServiceUrl(viteEnvOverride, gaasEnv) {
	if (viteEnvOverride.VITE_BILLING_SERVICE_URL) return viteEnvOverride.VITE_BILLING_SERVICE_URL;
	if (gaasEnv) return gaasEnv.services?.billing_url ?? null;
	return 'https://billing.realmsgos.dev';
}

/**
 * @param {Record<string, string>} viteEnvOverride
 * @param {GaasEnv | undefined} gaasEnv
 * @returns {string | null}
 */
export function resolveDeployServiceUrl(viteEnvOverride, gaasEnv) {
	if (viteEnvOverride.VITE_DEPLOY_SERVICE_URL) return viteEnvOverride.VITE_DEPLOY_SERVICE_URL;
	if (gaasEnv) return gaasEnv.services?.deploy_url ?? null;
	return 'https://deploy.realmsgos.dev';
}
