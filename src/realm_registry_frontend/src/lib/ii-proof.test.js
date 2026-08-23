import assert from 'node:assert/strict';
import test from 'node:test';
import { Principal } from '@dfinity/principal';
import {
	DelegationChain,
	DelegationIdentity,
	Ed25519KeyIdentity,
} from '@dfinity/identity';

import {
	billingIdentityHeaders,
	buildBillingPayloadFromProof,
	serializeDelegationIdentity,
} from './ii-proof.js';

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

test('serializeDelegationIdentity returns delegation chain JSON', async () => {
	const root = Ed25519KeyIdentity.generate();
	const session = Ed25519KeyIdentity.generate();
	const chain = await DelegationChain.create(
		root,
		session.getPublicKey(),
		new Date(Date.now() + 3_600_000),
	);
	const delegationIdentity = DelegationIdentity.fromDelegation(session, chain);
	const proof = serializeDelegationIdentity(delegationIdentity);
	assert.ok(proof);
	assert.equal(typeof proof.publicKey, 'string');
	assert.ok(Array.isArray(proof.delegations));
	assert.ok(proof.delegations.length > 0);
});

test('buildBillingPayloadFromProof always includes identity', () => {
	const proof = {
		publicKey: 'abcd',
		delegations: [{ delegation: { pubkey: 'ef', expiration: '123' }, signature: '00' }],
	};
	assert.deepEqual(buildBillingPayloadFromProof(proof, 'canister-id'), {
		registry_canister_id: 'canister-id',
		identity: proof,
	});
});

test('buildBillingPayloadFromProof rejects missing proof', () => {
	assert.throws(
		() => buildBillingPayloadFromProof(null, 'canister-id'),
		/Log in with Internet Identity to redeem/,
	);
});

test('billingIdentityHeaders serializes proof for billing X-IC-Identity header', () => {
	const proof = { publicKey: 'ab', delegations: [] };
	assert.deepEqual(billingIdentityHeaders(proof), {
		'X-IC-Identity': JSON.stringify(proof),
	});
});
