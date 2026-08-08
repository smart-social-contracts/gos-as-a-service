import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';

export const GAAS_ENV_FILENAME = 'gaas-env.json';

/**
 * @typedef {Object} GaasEnv
 * @property {string} [name]
 * @property {string} domain
 * @property {string} [network]
 * @property {{ billing_url?: string, deploy_url?: string }} [services]
 * @property {Record<string, Record<string, string>>} [canisters]
 * @property {Array<{ implementation: string, version?: string, loader_profile?: string, available?: boolean }>} [gos]
 * @property {string[]} [ii_alternative_origins]
 */

/**
 * Normalize raw gaas-env input (file or env vars) into a consistent shape.
 *
 * @param {Record<string, unknown>} raw
 * @returns {GaasEnv}
 */
export function normalizeGaasEnv(raw) {
	const domain = String(raw.domain || '').trim();
	if (!domain) {
		throw new Error('gaas-env requires domain when present');
	}

	/** @type {GaasEnv} */
	const env = { domain };

	if (raw.name != null && String(raw.name).trim()) {
		env.name = String(raw.name).trim();
	}

	if (raw.network != null && String(raw.network).trim()) {
		env.network = String(raw.network).trim();
	}

	const services = /** @type {Record<string, unknown>} */ (raw.services || {});
	const billingUrl = services.billing_url != null ? String(services.billing_url).trim() : '';
	const deployUrl = services.deploy_url != null ? String(services.deploy_url).trim() : '';
	if (billingUrl || deployUrl) {
		env.services = {};
		if (billingUrl) env.services.billing_url = billingUrl;
		if (deployUrl) env.services.deploy_url = deployUrl;
	}

	if (raw.canisters && typeof raw.canisters === 'object') {
		env.canisters = /** @type {Record<string, Record<string, string>>} */ (raw.canisters);
	}

	if (Array.isArray(raw.gos) && raw.gos.length > 0) {
		env.gos = raw.gos.map((entry) => {
			const item = /** @type {Record<string, unknown>} */ (entry);
			return {
				implementation: String(item.implementation || '').trim(),
				...(item.version != null ? { version: String(item.version).trim() } : {}),
				...(item.loader_profile != null
					? { loader_profile: String(item.loader_profile).trim() }
					: {}),
				...(item.available != null ? { available: Boolean(item.available) } : {})
			};
		});
	}

	if (Array.isArray(raw.ii_alternative_origins)) {
		env.ii_alternative_origins = raw.ii_alternative_origins
			.map((origin) => String(origin).trim())
			.filter(Boolean);
	}

	return env;
}

/**
 * Load gaas-env from repo-root gaas-env.json when present.
 *
 * @param {string} repoRoot
 * @returns {GaasEnv | null}
 */
export function loadGaasEnvFromFile(repoRoot) {
	const path = join(repoRoot, GAAS_ENV_FILENAME);
	if (!existsSync(path)) return null;

	try {
		const raw = JSON.parse(readFileSync(path, 'utf-8'));
		return normalizeGaasEnv(raw);
	} catch (e) {
		throw new Error(`Failed to read ${GAAS_ENV_FILENAME}: ${e.message}`);
	}
}

/**
 * Load gaas-env from GAAS_* environment variables when GAAS_DOMAIN is set.
 *
 * @returns {GaasEnv | null}
 */
export function loadGaasEnvFromEnv() {
	const domain = process.env.GAAS_DOMAIN?.trim();
	if (!domain) return null;

	const services = {};
	if (process.env.GAAS_BILLING_URL?.trim()) {
		services.billing_url = process.env.GAAS_BILLING_URL.trim();
	}
	if (process.env.GAAS_DEPLOY_URL?.trim()) {
		services.deploy_url = process.env.GAAS_DEPLOY_URL.trim();
	}

	let gos;
	if (process.env.GAAS_GOS?.trim()) {
		try {
			gos = JSON.parse(process.env.GAAS_GOS);
		} catch (e) {
			throw new Error(`Failed to parse GAAS_GOS JSON: ${e.message}`);
		}
	}

	let iiAlternativeOrigins;
	if (process.env.GAAS_II_ALTERNATIVE_ORIGINS?.trim()) {
		try {
			iiAlternativeOrigins = JSON.parse(process.env.GAAS_II_ALTERNATIVE_ORIGINS);
		} catch (e) {
			throw new Error(`Failed to parse GAAS_II_ALTERNATIVE_ORIGINS JSON: ${e.message}`);
		}
	}

	return normalizeGaasEnv({
		name: process.env.GAAS_NAME,
		domain,
		network: process.env.GAAS_NETWORK,
		services,
		gos,
		ii_alternative_origins: iiAlternativeOrigins
	});
}

/**
 * Load gaas-env from file (primary) or env vars (fallback).
 *
 * @param {string} repoRoot
 * @returns {GaasEnv | null}
 */
export function loadGaasEnv(repoRoot) {
	return loadGaasEnvFromFile(repoRoot) || loadGaasEnvFromEnv();
}

/**
 * Build ic-domains file content (one domain per line).
 *
 * @param {GaasEnv} gaasEnv
 * @returns {string}
 */
export function buildIcDomainsContent(gaasEnv) {
	return `${gaasEnv.domain.trim()}\n`;
}

/**
 * Build ii-alternative-origins JSON for Internet Identity.
 *
 * @param {GaasEnv} gaasEnv
 * @returns {string}
 */
export function buildIiAlternativeOriginsContent(gaasEnv) {
	const domainOrigin = `https://${gaasEnv.domain.replace(/^https?:\/\//, '').replace(/\/$/, '')}`;
	const extra = gaasEnv.ii_alternative_origins || [];
	const origins = [domainOrigin, ...extra].filter(
		(origin, index, all) => origin && all.indexOf(origin) === index
	);
	return `${JSON.stringify({ alternativeOrigins: origins }, null, 2)}\n`;
}

/**
 * Write .well-known files for a gaas-env deployment.
 *
 * @param {GaasEnv} gaasEnv
 * @param {string} staticDir
 */
export function generateWellKnownFiles(gaasEnv, staticDir) {
	const wellKnownDir = join(staticDir, '.well-known');
	mkdirSync(wellKnownDir, { recursive: true });
	writeFileSync(join(wellKnownDir, 'ic-domains'), buildIcDomainsContent(gaasEnv), 'utf-8');
	writeFileSync(
		join(wellKnownDir, 'ii-alternative-origins'),
		buildIiAlternativeOriginsContent(gaasEnv),
		'utf-8'
	);
}

/**
 * Vite define entry for build-time gaas-env injection.
 *
 * @param {GaasEnv | null | undefined} gaasEnv
 * @returns {Record<string, string>}
 */
export function getGaasEnvViteDefine(gaasEnv) {
	if (!gaasEnv) return {};
	return { __GAAS_ENV__: JSON.stringify(gaasEnv) };
}

/**
 * Resolve runtime gaas-env global when injected at build time.
 *
 * @returns {GaasEnv | undefined}
 */
export function getRuntimeGaasEnv() {
	return typeof __GAAS_ENV__ !== 'undefined' ? __GAAS_ENV__ : undefined;
}
