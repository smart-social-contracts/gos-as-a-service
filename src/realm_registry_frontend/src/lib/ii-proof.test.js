import assert from 'node:assert/strict';
import test from 'node:test';
import { Principal } from '@dfinity/principal';
import { Ed25519KeyIdentity } from '@dfinity/identity';

import {
	BILLING_TEST_MODE_II_BYPASS_HOSTS,
	II_REQUIRED_MESSAGE,
	billingIdentityPayload,
	billingProofHostname,
	serializeDelegationIdentity,
	shouldOmitBillingIdentityProof
} from './ii-proof.js';

const PROOF = { publicKey: 'aa', delegations: [] };
const REGISTRY = 'snqhl-daaaa-aaaan-q6n3q-cai';

test('serializeDelegationIdentity returns null for anonymous identity', () => {
	const identity = Ed25519KeyIdentity.generate();
	const anon = {
		getPrincipal: () => Principal.anonymous(),
		getDelegation: () => identity.getDelegation(),
	};
	assert.equal(serializeDelegationIdentity(anon), null);
});

test('serializeDelegationIdentity returns null without getDelegation', () => {
	const identity = Ed25519KeyIdentity.generate();
	assert.equal(serializeDelegationIdentity(identity), null);
});

test('serializeDelegationIdentity returns null for missing identity', () => {
	assert.equal(serializeDelegationIdentity(null), null);
});

test('billing bypass host list matches test, staging, and demo portals', () => {
	assert.deepEqual([...BILLING_TEST_MODE_II_BYPASS_HOSTS], [
		'test.gos.earth',
		'staging.gos.earth',
		'demo.gos.earth'
	]);
	assert.ok(!BILLING_TEST_MODE_II_BYPASS_HOSTS.includes('gos.earth'));
	assert.ok(!BILLING_TEST_MODE_II_BYPASS_HOSTS.includes('registry.realmsgos.org'));
});

test('shouldOmitBillingIdentityProof is true on dogfood portal hosts', () => {
	assert.equal(shouldOmitBillingIdentityProof('test.gos.earth'), true);
	assert.equal(shouldOmitBillingIdentityProof('staging.gos.earth'), true);
	assert.equal(shouldOmitBillingIdentityProof('demo.gos.earth'), true);
	assert.equal(shouldOmitBillingIdentityProof('https://demo.gos.earth/my-dashboard'), true);
	assert.equal(shouldOmitBillingIdentityProof('Demo.Gos.Earth'), true);
});

test('shouldOmitBillingIdentityProof is false on production hosts', () => {
	assert.equal(shouldOmitBillingIdentityProof('gos.earth'), false);
	assert.equal(shouldOmitBillingIdentityProof('registry.realmsgos.org'), false);
	assert.equal(shouldOmitBillingIdentityProof('https://gos.earth/'), false);
	assert.equal(shouldOmitBillingIdentityProof('localhost'), false);
	assert.equal(shouldOmitBillingIdentityProof(''), false);
});

test('billingProofHostname reads window.location when hostname is omitted', () => {
	const previous = globalThis.window;
	globalThis.window = { location: { hostname: 'demo.gos.earth' } };
	try {
		assert.equal(billingProofHostname(), 'demo.gos.earth');
		assert.equal(shouldOmitBillingIdentityProof(), true);
	} finally {
		if (previous === undefined) delete globalThis.window;
		else globalThis.window = previous;
	}
});

test('buildBillingIdentityPayload omits identity on test, staging, and demo', () => {
	for (const hostname of ['test.gos.earth', 'staging.gos.earth', 'demo.gos.earth']) {
		const payload = billingIdentityPayload({
			registryCanisterId: REGISTRY,
			proof: PROOF,
			hostname,
			testModeIIBypass: false
		});
		assert.deepEqual(payload, { registry_canister_id: REGISTRY });
		assert.equal('identity' in payload, false);
	}
});

test('buildBillingIdentityPayload attaches identity on production hosts', () => {
	for (const hostname of ['gos.earth', 'registry.realmsgos.org']) {
		const payload = billingIdentityPayload({
			registryCanisterId: REGISTRY,
			proof: PROOF,
			hostname,
			testModeIIBypass: false
		});
		assert.deepEqual(payload, {
			registry_canister_id: REGISTRY,
			identity: PROOF
		});
	}
});

test('dummy II-bypass session still omits identity without a proof', () => {
	const payload = billingIdentityPayload({
		registryCanisterId: REGISTRY,
		proof: null,
		hostname: 'gos.earth',
		testModeIIBypass: true
	});
	assert.deepEqual(payload, { registry_canister_id: REGISTRY });
});

test('production without a proof and without II bypass still requires login', () => {
	assert.throws(
		() =>
			billingIdentityPayload({
				registryCanisterId: REGISTRY,
				proof: null,
				hostname: 'gos.earth',
				testModeIIBypass: false
			}),
		{ message: II_REQUIRED_MESSAGE }
	);
});
