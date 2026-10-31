import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveRealmDelegationTargets } from './delegation-targets.js';

const platform = ['registry-id', 'installer-id'];

test('delegates to the backend alone when the registry records no quarters', () => {
	assert.deepEqual(resolveRealmDelegationTargets({ backendCanisterId: 'realm-id' }, platform), [
		'realm-id'
	]);
});

test('adds the quarters the registry recorded, once each', () => {
	const realm = { backendCanisterId: 'realm-id', quarterCanisterIds: ['q1', 'realm-id', 'q1'] };
	assert.deepEqual(resolveRealmDelegationTargets(realm, platform), ['realm-id', 'q1']);
});

test('refuses a platform canister recorded as the backend', () => {
	assert.throws(
		() => resolveRealmDelegationTargets({ backendCanisterId: 'installer-id' }, platform),
		/platform canister installer-id/
	);
});

test('refuses a platform canister recorded as a quarter', () => {
	const realm = { backendCanisterId: 'realm-id', quarterCanisterIds: ['q1', 'registry-id'] };
	assert.throws(() => resolveRealmDelegationTargets(realm, platform), /platform canister registry-id/);
});
