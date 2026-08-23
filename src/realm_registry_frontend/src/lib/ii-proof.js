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
 * Build billing POST body fields from a delegation chain proof.
 *
 * @param {object} proof
 * @param {string} registryCanisterId
 * @returns {{ registry_canister_id: string, identity: object }}
 */
export function buildBillingPayloadFromProof(proof, registryCanisterId) {
	if (!proof) {
		throw new Error(II_REQUIRED_MESSAGE);
	}
	return {
		registry_canister_id: registryCanisterId || '',
		identity: proof,
	};
}

/**
 * Headers billing accepts as an alternate II proof carrier.
 *
 * @param {object} proof
 * @returns {Record<string, string>}
 */
export function billingIdentityHeaders(proof) {
	return { 'X-IC-Identity': JSON.stringify(proof) };
}

/**
 * Build billing POST extras: registry canister id + II identity proof.
 *
 * Portal test-mode II bypass uses deterministic keys without a delegation chain;
 * billing still requires proof, so we fall back to the real AuthClient session or
 * prompt for Internet Identity when `promptLogin` is true.
 *
 * @param {{ promptLogin?: boolean }} [options]
 * @returns {Promise<{ registry_canister_id: string, identity: object }>}
 */
export async function buildBillingIdentityPayload({ promptLogin = false } = {}) {
	const { CONFIG } = await import('$lib/config.js');
	const { getIdentity, getBillingDelegationIdentity, loginForBilling } = await import('$lib/auth.js');

	let proof = serializeDelegationIdentity(await getIdentity());

	if (!proof) {
		proof = serializeDelegationIdentity(await getBillingDelegationIdentity());
	}

	if (!proof && promptLogin) {
		proof = serializeDelegationIdentity(await loginForBilling());
	}

	return buildBillingPayloadFromProof(proof, CONFIG.realm_registry_backend_canister_id || '');
}

export { II_REQUIRED_MESSAGE };
