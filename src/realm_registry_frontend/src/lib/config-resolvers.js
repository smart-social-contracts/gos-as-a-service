/**
 * Pure config resolution helpers shared by config.js and unit tests.
 */

/**
 * @typedef {import('../../scripts/gaas-env.js').GaasEnv} GaasEnv
 */

const PORTAL_HOSTS = {
	staging: 'https://staging.gos.earth',
	demo: 'https://demo.gos.earth',
	test: 'https://test.gos.earth',
	ic: 'https://registry.realmsgos.org',
	production: 'https://registry.realmsgos.org'
};

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
 * @param {string} network
 * @returns {Record<string, string>}
 */
export function resolvePortalHosts(viteEnvOverride, gaasEnv, network) {
	const hosts = { ...PORTAL_HOSTS };
	if (gaasEnv?.domain) {
		const envNetwork = gaasEnv.network || 'staging';
		hosts[envNetwork] = portalOriginForDomain(gaasEnv.domain);
	}
	if (viteEnvOverride.VITE_PORTAL_BASE_URL) {
		hosts[network] = viteEnvOverride.VITE_PORTAL_BASE_URL;
	}
	return hosts;
}

/**
 * @param {Record<string, string>} viteEnvOverride
 * @param {GaasEnv | undefined} gaasEnv
 * @param {string} network
 * @returns {string}
 */
export function resolvePortalBaseUrl(viteEnvOverride, gaasEnv, network) {
	if (viteEnvOverride.VITE_PORTAL_BASE_URL) return viteEnvOverride.VITE_PORTAL_BASE_URL;
	const hosts = resolvePortalHosts(viteEnvOverride, gaasEnv, network);
	if (gaasEnv?.domain) {
		return hosts[network] || portalOriginForDomain(gaasEnv.domain);
	}
	return hosts[network] || PORTAL_HOSTS.staging;
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

export { PORTAL_HOSTS };
