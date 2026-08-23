import {
	DelegationChain,
	DelegationIdentity,
	Ed25519KeyIdentity,
} from '@dfinity/identity';

const II_REQUIRED_MESSAGE = 'Log in with Internet Identity to redeem';
const BYPASS_PROOF_TTL_MS = 8 * 60 * 60 * 1000;

/**
 * Mint a short-lived delegation chain rooted at a raw key identity.
 *
 * Portal II bypass signs in with Ed25519KeyIdentity (no getDelegation).
 * Billing still requires a chain, so we delegate from that test key to a
 * fresh session key instead of opening Internet Identity.
 *
 * @param {import('@dfinity/agent').Identity | null} rootIdentity
 * @returns {Promise<{ publicKey: string, delegations: Array<{ signature: string, delegation: object }> } | null>}
 */
export async function proofFromRootIdentity(rootIdentity) {
	if (!rootIdentity) return null;
	if (rootIdentity.getPrincipal().isAnonymous()) return null;
	const existing = serializeDelegationIdentity(rootIdentity);
	if (existing) return existing;

	const session = Ed25519KeyIdentity.generate();
	const chain = await DelegationChain.create(
		rootIdentity,
		session.getPublicKey(),
		new Date(Date.now() + BYPASS_PROOF_TTL_MS),
	);
	return serializeDelegationIdentity(DelegationIdentity.fromDelegation(session, chain));
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
 * When portal II bypass is on, mint a chain from the test key and never
 * open Internet Identity. Otherwise use the real II session, prompting
 * when `promptLogin` is true.
 *
 * @param {{ promptLogin?: boolean }} [options]
 * @returns {Promise<{ registry_canister_id: string, identity: object }>}
 */
export async function buildBillingIdentityPayload({ promptLogin = false } = {}) {
	const { CONFIG, getTestModeIIBypass } = await import('$lib/config.js');
	const { getIdentity, getBillingDelegationIdentity, loginForBilling } = await import('$lib/auth.js');
	const registryId = CONFIG.realm_registry_backend_canister_id || '';

	if (getTestModeIIBypass()) {
		return buildBillingPayloadFromProof(await proofFromRootIdentity(await getIdentity()), registryId);
	}

	let proof = serializeDelegationIdentity(await getIdentity());

	if (!proof) {
		proof = serializeDelegationIdentity(await getBillingDelegationIdentity());
	}

	if (!proof && promptLogin) {
		proof = serializeDelegationIdentity(await loginForBilling());
	}

	return buildBillingPayloadFromProof(proof, registryId);
}

export { II_REQUIRED_MESSAGE };
