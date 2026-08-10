import assert from 'node:assert/strict';
import test from 'node:test';
import { Principal } from '@dfinity/principal';
import { Ed25519KeyIdentity } from '@dfinity/identity';

import { serializeDelegationIdentity } from './ii-proof.js';

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
