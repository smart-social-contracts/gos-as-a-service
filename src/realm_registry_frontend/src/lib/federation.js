import { CONFIG } from '$lib/config.js';

/**
 * IC asset canister origin for a realm frontend.
 * @param {string} frontendCanisterId
 * @param {string} [network]
 * @param {{ portalIframe?: boolean }} [opts]
 *   Portal embeds use `{id}.raw.icp0.io` so the IC service worker does not
 *   run response verification in a third-party iframe (which yields HTTP 503).
 */
export function realmFrontendOrigin(
	frontendCanisterId,
	network = CONFIG.deploy_queue_network,
	{ portalIframe = false } = {},
) {
	const id = (frontendCanisterId || '').trim();
	if (!id) return '';
	if (typeof window !== 'undefined') {
		const host = window.location.hostname;
		if (host.includes('localhost') || host.includes('127.0.0.1')) {
			const port = window.location.port || '4943';
			return `http://${id}.localhost:${port}`;
		}
	}
	if (network === 'local') {
		return `http://${id}.localhost:4943`;
	}
	if (portalIframe) {
		return `https://${id}.raw.icp0.io`;
	}
	return `https://${id}.icp0.io`;
}

/**
 * Map internal extension bundle paths to user-facing realm routes for iframe src.
 * Bad portal history entries may contain `/ext/{id}/…/index.html`; the realm
 * frontend serves those only as static assets, not as SPA routes.
 */
export function normalizeRealmIframePath(subPath = '') {
	const p = subPath.startsWith('/') ? subPath : subPath ? `/${subPath}` : '';
	const extMatch = p.match(/^\/ext\/([^/]+)(?:\/.*)?$/);
	if (extMatch) return `/extensions/${extMatch[1]}`;
	return p || '/';
}

export function realmIframeUrl(frontendCanisterId, slug, subPath = '') {
	const base = realmFrontendOrigin(frontendCanisterId, CONFIG.deploy_queue_network, {
		portalIframe: true,
	});
	if (!base) return '';
	const path = normalizeRealmIframePath(subPath);
	const q = new URLSearchParams({ portal: '1', slug: slug || '' });
	return `${base}${path}?${q.toString()}`;
}

export function portalPath(slug, subPath = '') {
	const p = subPath.startsWith('/') ? subPath : subPath ? `/${subPath}` : '';
	return `/r/${encodeURIComponent(slug)}${p}`;
}
