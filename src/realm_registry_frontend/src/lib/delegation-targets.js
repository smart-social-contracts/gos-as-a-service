/**
 * Which canisters the portal lets an embedded realm act on as the visitor.
 *
 * The backend comes from the registry. Quarters come from the realm itself,
 * which a hijacked or self-registered realm could use to name the registry, the
 * installer or another realm and receive the visitor's delegation there. So a
 * quarter is accepted only when the canister itself says its capital is this
 * realm's backend: a realm can then only widen the delegation to canisters that
 * claim to be its own quarters, which harms nobody else. Another realm's
 * backend is a capital or independent realm and reports no capital.
 */
import { fetchFederationCapital, fetchJoinTargets } from './realm-gos-client.js';

const REQUEST_TIMEOUT_MS = 5000;

function withTimeout(promise, timeoutMs) {
	let timer;
	const timeout = new Promise((_, reject) => {
		timer = setTimeout(() => reject(new Error(`no answer in ${timeoutMs} ms`)), timeoutMs);
	});
	return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function claimsToBeQuarterOf(backendCanisterId, candidate, fetchCapital, timeoutMs) {
	try {
		const capital = await withTimeout(fetchCapital(candidate), timeoutMs);
		if (capital === backendCanisterId) return true;
		console.warn(`[delegation] not delegating to ${candidate}: its capital is '${capital}'`);
	} catch (err) {
		console.warn(`[delegation] not delegating to ${candidate}: could not verify it`, err);
	}
	return false;
}

/**
 * @param {string} backendCanisterId the realm's capital backend, as the registry recorded it
 * @param {string[]} platformCanisterIds registry, installer, file registry, ...
 *   Refused even when named, because a slug claim can record any ID as the realm.
 * @param {{ fetchQuarterIds?: Function, fetchCapital?: Function, timeoutMs?: number }} [options]
 * @returns {Promise<string[]>} the backend first, then its verified quarters
 */
export async function resolveRealmDelegationTargets(
	backendCanisterId,
	platformCanisterIds,
	{
		fetchQuarterIds = fetchJoinTargets,
		fetchCapital = fetchFederationCapital,
		timeoutMs = REQUEST_TIMEOUT_MS
	} = {}
) {
	if (platformCanisterIds.includes(backendCanisterId)) {
		throw new Error(`Refusing to delegate to platform canister ${backendCanisterId}`);
	}
	let reported = [];
	try {
		reported = await withTimeout(fetchQuarterIds(backendCanisterId), timeoutMs);
	} catch (err) {
		console.warn('[delegation] could not read the realm quarters, delegating to its backend only', err);
	}
	const candidates = [...new Set(reported)].filter((id) => id !== backendCanisterId);
	const notPlatform = candidates.filter((id) => !platformCanisterIds.includes(id));
	for (const id of candidates.filter((id) => !notPlatform.includes(id))) {
		console.warn(`[delegation] not delegating to ${id}: it is a platform canister`);
	}
	const verified = await Promise.all(
		notPlatform.map((id) => claimsToBeQuarterOf(backendCanisterId, id, fetchCapital, timeoutMs))
	);
	return [backendCanisterId, ...notPlatform.filter((_, i) => verified[i])];
}
