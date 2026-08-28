/**
 * Architecture / Casals hub target.
 *
 * Never invent a canister URL. An empty casalsUrl must not navigate anywhere.
 *
 * @param {string} [casalsUrl]
 * @returns {string}
 */
export function architectureHref(casalsUrl) {
	const url = typeof casalsUrl === 'string' ? casalsUrl.trim() : '';
	return url;
}
