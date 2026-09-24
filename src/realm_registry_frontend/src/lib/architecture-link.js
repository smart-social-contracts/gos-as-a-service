/**
 * Architecture / Casals hub target.
 *
 * Never invent a canister URL. An empty casalsUrl must not navigate anywhere.
 * The principal comes from ``get_runtime_flags`` on the registry backend
 * (written by the sheet's ``configure`` row on every ``casals up``). No
 * bake-time fallback.
 *
 * @param {string} [casalsUrl]
 * @returns {string}
 */
export function architectureHref(casalsUrl) {
	const url = typeof casalsUrl === 'string' ? casalsUrl.trim() : '';
	return url;
}

/**
 * Prefer the conductor-written ``casals_url`` (https://casals.gos.earth).
 * Fall back to the live registry principal as an icp0.io URL.
 *
 * @param {string} [runtimeId] live ``casals_frontend_canister_id`` from the registry
 * @param {string} [casalsUrl] ``casals_url`` from ``/canister_ids.js``
 * @returns {string}
 */
export function casalsFrontendUrl(runtimeId, casalsUrl) {
	const configured = typeof casalsUrl === 'string' ? casalsUrl.trim() : '';
	if (configured) return configured;
	const id = String(runtimeId || '').trim();
	return id ? `https://${id}.icp0.io` : '';
}
