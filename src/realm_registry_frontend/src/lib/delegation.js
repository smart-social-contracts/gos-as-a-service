import { Principal } from '@dfinity/principal';
import { DelegationChain, Ed25519PublicKey } from '@dfinity/identity';
import { Actor, HttpAgent } from '@dfinity/agent';

const DELEGATION_TTL_MS = 55 * 60 * 1000;

/**
 * Mint an II delegation scoped to a realm's backend canisters for iframe handoff.
 *
 * `targets` must cover every backend the embedded realm may call as the user:
 * the capital *and* its quarter canisters (auto-scaled realms route joins to a
 * quarter, and a capital-only delegation makes the replica reject those calls
 * with "not one of the delegation targets").
 *
 * Imports are static (not dynamic) so a mid-session network blip or a stale
 * chunk hash after a portal redeploy cannot break the auth bridge with
 * "Failed to fetch dynamically imported module".
 *
 * @param {import('@dfinity/agent').Identity} identity
 * @param {string[]} targetCanisterIds capital + quarter backend canister ids
 * @param {Uint8Array} sessionPublicKeyDer
 */
export async function createScopedDelegation(identity, targetCanisterIds, sessionPublicKeyDer) {
	const targets = targetCanisterIds.map((id) => Principal.fromText(id));
	const sessionPublicKey = Ed25519PublicKey.fromDer(sessionPublicKeyDer);
	const expiration = new Date(Date.now() + DELEGATION_TTL_MS);
	// The portal identity is a DelegationIdentity (II anchor -> portal session
	// key). Extend that chain with one more hop to the iframe's session key,
	// scoped to the realm's backends, so the iframe acts as the same principal.
	const previous =
		typeof identity.getDelegation === 'function' ? identity.getDelegation() : undefined;
	const chain = await DelegationChain.create(identity, sessionPublicKey, expiration, {
		previous,
		targets
	});
	return {
		delegationChain: chain.toJSON(),
		backendCanisterId: targetCanisterIds[0] || '',
		expiresAt: expiration.getTime()
	};
}

/**
 * Resolve the full delegation target set for a realm: the capital backend plus
 * every quarter it reports via its public `get_join_targets` query. Falls back
 * to just the capital when the query fails (realm without quarter support).
 *
 * @param {string} backendCanisterId the realm's capital backend
 * @returns {Promise<string[]>}
 */
export async function resolveRealmDelegationTargets(backendCanisterId) {
	const targets = [backendCanisterId];
	try {
		const idl = ({ IDL }) => IDL.Service({ get_join_targets: IDL.Func([], [IDL.Text], ['query']) });
		const agent = new HttpAgent();
		const actor = Actor.createActor(idl, { agent, canisterId: backendCanisterId });
		const raw = await actor.get_join_targets();
		const parsed = JSON.parse(raw);
		for (const q of parsed?.quarters || []) {
			const id = (q?.canister_id || '').trim();
			if (id && !targets.includes(id)) targets.push(id);
		}
	} catch (e) {
		console.warn('[delegation] get_join_targets failed; delegating to capital only:', e);
	}
	return targets;
}
