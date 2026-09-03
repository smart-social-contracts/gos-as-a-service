/**
 * Architecture / Casals hub target.
 *
 * Never invent a canister URL. An empty casalsUrl must not navigate anywhere.
 * The principal comes from ``get_runtime_flags`` on the registry backend
 * (survives ``realms seed``). No bake-time fallback.
 *
 * @param {string} [casalsUrl]
 * @returns {string}
 */
export function architectureHref(casalsUrl) {
	const url = typeof casalsUrl === 'string' ? casalsUrl.trim() : '';
	return url;
}

/**
 * @param {string} [runtimeId] live ``casals_frontend_canister_id`` from the registry
 * @returns {string}
 */
export function casalsFrontendUrl(runtimeId) {
	const id = String(runtimeId || '').trim();
	return id ? `https://${id}.icp0.io` : '';
}
