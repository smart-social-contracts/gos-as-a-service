import assert from 'node:assert/strict';
import test from 'node:test';
import { IDL } from '@dfinity/candid';
import {
	fetchFederationCapital,
	fetchJoinTargets,
	fetchRealmInfo,
	idlFactory,
	resetRealmGosClient
} from './realm-gos-client.js';

/** A realm that implements ggg.did. */
function gggRealm(overrides = {}) {
	const calls = [];
	const actor = {
		calls,
		icrc10_supported_standards: async () => {
			calls.push('icrc10');
			return [
				{ name: 'ICRC-10', url: 'https://github.com/dfinity/ICRC' },
				{ name: 'GGG', url: 'https://github.com/smart-social-contracts/ggg/blob/v0.1.0/ggg.did' }
			];
		},
		ggg_realm_info: async () => ({ name: 'Agora', status: { Beta: null }, logo_url: ['  https://x/logo.png '], federation_realm_id: [] }),
		ggg_join_targets: async () => ({ Ok: { default: ['q1'], targets: ['q1', ' q2 ', ''], mode: [] } }),
		get_runtime_flags: async () => {
			throw new Error('a GGG realm is not asked for runtime flags');
		},
		...overrides
	};
	return actor;
}

/** A realm deployed before GGG: no icrc10_supported_standards, the old JSON methods. */
function legacyRealm() {
	return {
		icrc10_supported_standards: async () => {
			throw new Error('Canister has no query method icrc10_supported_standards');
		},
		get_runtime_flags: async () =>
			JSON.stringify({ success: true, realm_stage: 'Alpha', realm_logo: 'https://x/old.png' }),
		get_join_targets: async () => JSON.stringify({ quarters: [{ canister_id: 'q9' }, {}] })
	};
}

test('a GGG realm is read through ggg_realm_info', async () => {
	resetRealmGosClient();
	const realm = gggRealm();
	const info = await fetchRealmInfo('aaaaa-aa', { createActor: () => realm });
	assert.deepEqual(info, { stage: 'beta', logoUrl: 'https://x/logo.png' });
});

test('a realm that predates GGG is read through get_runtime_flags', async () => {
	resetRealmGosClient();
	const info = await fetchRealmInfo('aaaaa-aa', { createActor: () => legacyRealm() });
	assert.deepEqual(info, { stage: 'alpha', logoUrl: 'https://x/old.png' });
});

test('join targets come from ggg_join_targets, or get_join_targets on older realms', async () => {
	resetRealmGosClient();
	assert.deepEqual(await fetchJoinTargets('aaaaa-aa', { createActor: () => gggRealm() }), ['q1', 'q2']);
	resetRealmGosClient();
	assert.deepEqual(await fetchJoinTargets('aaaaa-aa', { createActor: () => legacyRealm() }), ['q9']);
});

test('a refused or failing call reads as nothing', async () => {
	resetRealmGosClient();
	const refused = gggRealm({ ggg_join_targets: async () => ({ Err: { Unavailable: 'setup' } }) });
	assert.deepEqual(await fetchJoinTargets('aaaaa-aa', { createActor: () => refused }), []);
	resetRealmGosClient();
	const down = gggRealm({ ggg_realm_info: async () => Promise.reject(new Error('IC0301 not found')) });
	assert.equal(await fetchRealmInfo('aaaaa-aa', { createActor: () => down }), null);
	assert.equal(await fetchRealmInfo('', {}), null);
});

test('a quarter names its capital; anything else reads as no capital', async () => {
	resetRealmGosClient();
	const quarter = gggRealm({
		ggg_realm_info: async () => ({ name: 'Q', status: { Beta: null }, logo_url: [], federation_realm_id: [' cap-1 '] })
	});
	assert.equal(await fetchFederationCapital('q1', { createActor: () => quarter }), 'cap-1');
	resetRealmGosClient();
	assert.equal(await fetchFederationCapital('cap-1', { createActor: () => gggRealm() }), '');
	resetRealmGosClient();
	assert.equal(await fetchFederationCapital('old', { createActor: () => legacyRealm() }), '');
	resetRealmGosClient();
	const down = gggRealm({ ggg_realm_info: async () => Promise.reject(new Error('IC0301')) });
	assert.equal(await fetchFederationCapital('q1', { createActor: () => down }), '');
	assert.equal(await fetchFederationCapital('', {}), '');
});

test('ICRC-10 is asked once per canister', async () => {
	resetRealmGosClient();
	const realm = gggRealm();
	await fetchRealmInfo('aaaaa-aa', { createActor: () => realm });
	await fetchJoinTargets('aaaaa-aa', { createActor: () => realm });
	assert.deepEqual(realm.calls, ['icrc10']);
});

test('the IDL decodes what a realm sends, extra fields included', () => {
	// The canister's Realm has many more fields than the portal declares: they are skipped.
	const Full = IDL.Record({
		id: IDL.Text,
		name: IDL.Text,
		manifesto: IDL.Text,
		status: IDL.Variant({ Setup: IDL.Null, Alpha: IDL.Null, Beta: IDL.Null, Production: IDL.Null,
			Deprecation: IDL.Null, Terminated: IDL.Null }),
		logo_url: IDL.Opt(IDL.Text),
		federation_realm_id: IDL.Opt(IDL.Text),
		is_capital: IDL.Bool
	});
	const bytes = IDL.encode([Full], [{ id: '1', name: 'Agora', manifesto: '', status: { Alpha: null },
		logo_url: [], federation_realm_id: ['cap-1'], is_capital: true }]);
	const service = idlFactory({ IDL });
	const [realm] = IDL.decode(service._fields.find(([n]) => n === 'ggg_realm_info')[1].retTypes, bytes);
	assert.equal(realm.name, 'Agora');
	assert.deepEqual(realm.status, { Alpha: null });
	assert.deepEqual(realm.logo_url, []);
	assert.deepEqual(realm.federation_realm_id, ['cap-1']);
});
