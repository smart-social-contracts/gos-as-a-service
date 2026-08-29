const II_REQUIRED_MESSAGE = 'Log in with Internet Identity to redeem';

/**
 * Portal hosts that match realms-billing `app/auth/ii_auth.py`
 * `_TEST_MODE_II_BYPASS_HOSTS`. Billing's test-mode II bypass only runs when
 * no `identity` proof is present, so these hosts must omit the proof even
 * for a real DelegationIdentity (Identity1 with II bypass OFF).
 *
 * Production (`gos.earth`, `registry.realmsgos.org`) is not on this list.
 */
export const BILLING_TEST_MODE_II_BYPASS_HOSTS = Object.freeze([
	'test.gos.earth',
	'staging.gos.earth',
	'demo.gos.earth'
]);

/**
 * Normalize a hostname or origin to the bare host billing compares against.
 *
 * @param {string} [hostname]
 * @returns {string}
 */
export function billingProofHostname(hostname) {
	if (hostname == null || hostname === '') {
		if (typeof window === 'undefined') return '';
		hostname = window.location.hostname;
	}
	return String(hostname)
		.replace(/^https?:\/\//, '')
		.split('/')[0]
		.split(':')[0]
		.toLowerCase();
}

/**
 * True when billing should receive no `identity` proof (dogfood portal hosts).
 *
 * @param {string} [hostname]
 * @returns {boolean}
 */
export function shouldOmitBillingIdentityProof(hostname) {
	return BILLING_TEST_MODE_II_BYPASS_HOSTS.includes(billingProofHostname(hostname));
}

/**
 * Serialize a DelegationIdentity chain for realms-billing II proof (realms-billing#4).
 *
 * @param {import('@dfinity/agent').Identity} identity
 * @returns {{ publicKey: string, delegations: Array<{ signature: string, delegation: object }> } | null}
 */
export function serializeDelegationIdentity(identity) {
	if (!identity) return null;
	if (identity.getPrincipal().isAnonymous()) return null;
	if (typeof identity.getDelegation !== 'function') return null;
	return identity.getDelegation().toJSON();
}

/**
 * Assemble billing POST extras from an already-serialized proof.
 * Used by {@link buildBillingIdentityPayload} and unit tests.
 *
 * @param {{
 *   registryCanisterId?: string,
 *   proof?: object | null,
 *   hostname?: string,
 *   testModeIIBypass?: boolean
 * }} [opts]
 * @returns {{ registry_canister_id: string, identity?: object }}
 */
export function billingIdentityPayload({
	registryCanisterId = '',
	proof = null,
	hostname,
	testModeIIBypass = false
} = {}) {
	if (!proof && !testModeIIBypass) {
		throw new Error(II_REQUIRED_MESSAGE);
	}
	const payload = { registry_canister_id: registryCanisterId || '' };
	if (proof && !shouldOmitBillingIdentityProof(hostname)) {
		payload.identity = proof;
	}
	return payload;
}

/**
 * Build billing POST extras: registry canister id + optional II identity proof.
 *
 * Dogfood portal hosts omit `identity` even when a DelegationIdentity proof
 * exists so realms-billing's host-gated II bypass can run. Production always
 * attaches a real proof (or throws unless the dummy II-bypass session is on).
 *
 * @returns {Promise<{ registry_canister_id: string, identity?: object }>}
 */
export async function buildBillingIdentityPayload() {
	const { CONFIG, getTestModeIIBypass } = await import('$lib/config.js');
	const { getIdentity } = await import('$lib/auth.js');
	const identity = await getIdentity();
	return billingIdentityPayload({
		registryCanisterId: CONFIG.realm_registry_backend_canister_id || '',
		proof: serializeDelegationIdentity(identity),
		hostname: billingProofHostname(),
		testModeIIBypass: getTestModeIIBypass()
	});
}

export { II_REQUIRED_MESSAGE };
