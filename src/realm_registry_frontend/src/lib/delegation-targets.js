/**
 * Which canisters the portal lets an embedded realm act on as the visitor.
 *
 * Only IDs the registry records for the realm count. Never ask the realm for
 * its own list: a hijacked or self-registered realm would name the registry,
 * the installer or another realm and receive the visitor's delegation there.
 */

/**
 * @param {{ backendCanisterId: string, quarterCanisterIds?: string[] }} realm
 *   what the registry recorded for the slug. The registry does not record
 *   quarters yet, so until it does the list is empty and only the backend is
 *   delegated to.
 * @param {string[]} platformCanisterIds registry, installer, file registry, ...
 *   Platform canisters are refused even when the registry names one, because a
 *   slug claim can record any ID as the realm.
 * @returns {string[]}
 */
export function resolveRealmDelegationTargets(realm, platformCanisterIds) {
	const targets = [realm.backendCanisterId, ...(realm.quarterCanisterIds || [])]
		.map((id) => (id || '').trim())
		.filter(Boolean);
	const refused = targets.filter((id) => platformCanisterIds.includes(id));
	if (refused.length) {
		throw new Error(`Refusing to delegate to platform canister ${refused.join(', ')}`);
	}
	return [...new Set(targets)];
}
