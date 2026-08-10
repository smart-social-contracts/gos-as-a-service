const II_REQUIRED_MESSAGE = 'Log in with Internet Identity to redeem';

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
 * Build billing POST extras: registry canister id + optional II identity proof.
 *
 * @returns {Promise<{ registry_canister_id: string, identity?: object }>}
 */
export async function buildBillingIdentityPayload() {
	const { CONFIG, getTestModeIIBypass } = await import('$lib/config.js');
	const { getIdentity } = await import('$lib/auth.js');
	const identity = await getIdentity();
	const proof = serializeDelegationIdentity(identity);
	if (!proof) {
		if (getTestModeIIBypass()) {
			return { registry_canister_id: CONFIG.realm_registry_backend_canister_id || '' };
		}
		throw new Error(II_REQUIRED_MESSAGE);
	}
	return {
		registry_canister_id: CONFIG.realm_registry_backend_canister_id || '',
		identity: proof,
	};
}

export { II_REQUIRED_MESSAGE };
