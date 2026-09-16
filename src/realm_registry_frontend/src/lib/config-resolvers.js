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
