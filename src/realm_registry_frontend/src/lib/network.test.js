import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { detectNetwork, getCanisterId, isUnresolvedPlaceholder, runtimeCanisterIds } from './network.js';
import { resolveGeisterApiOrigin, resolvePortalBaseUrl } from './config-resolvers.js';

// What the conductor writes into /canister_ids.js for a deployment
// (casals.json, realm-registry-frontend `files`).
const RUNTIME = {
	realm_registry_backend: 'aaaaa-aa',
	realm_installer: 'bbbbb-bb',
	casals_frontend: 'ccccc-cc',
	network: 'ic',
	portal_url: 'https://gos.earth'
};

test('detectNetwork takes the conductor-written network first', () => {
	assert.equal(detectNetwork('whatever.icp0.io', undefined, RUNTIME), 'ic');
	assert.equal(detectNetwork('localhost', undefined, RUNTIME), 'ic');
	assert.equal(detectNetwork('gos.earth', undefined, { ...RUNTIME, network: 'local' }), 'local');
});

test('detectNetwork recognises a local replica host', () => {
	assert.equal(detectNetwork('localhost', undefined, {}), 'local');
	assert.equal(detectNetwork('127.0.0.1', undefined, {}), 'local');
	assert.equal(detectNetwork('realm_registry_frontend.localhost', undefined, {}), 'local');
});

test('detectNetwork never guesses an environment from a host name', () => {
	for (const host of [
		'staging.gos.earth',
		'demo.gos.earth',
		'test.gos.earth',
		'gos.earth',
		'realmsgos.org',
		'unknown.example.com',
		'jzbts-3iaaa-aaaai-ax5tq-cai.icp0.io'
	]) {
		assert.equal(detectNetwork(host, undefined, {}), '', host);
	}
});

test('detectNetwork falls back to the gaas-env descriptor network', () => {
	const gaasEnv = { domain: 'partner.example', network: 'custom-net' };
	assert.equal(detectNetwork('partner.example', gaasEnv, {}), 'custom-net');
	assert.equal(detectNetwork('some-id.icp0.io', gaasEnv, {}), 'custom-net');
	assert.equal(detectNetwork('localhost', gaasEnv, {}), 'local');
});

test('getCanisterId reads the conductor-written ids first', () => {
	assert.equal(getCanisterId('realm_registry_backend', { runtimeOverride: RUNTIME }), 'aaaaa-aa');
	assert.equal(getCanisterId('realm_installer', { runtimeOverride: RUNTIME }), 'bbbbb-bb');
	assert.equal(getCanisterId('casals_frontend', { runtimeOverride: RUNTIME }), 'ccccc-cc');
	// Non-id keys of the payload are not canister names.
	assert.equal(getCanisterId('network', { runtimeOverride: { network: 'ic' } }), undefined);
	assert.equal(
		getCanisterId('casals_url', { runtimeOverride: { casals_url: 'https://casals.gos.earth' } }),
		undefined
	);
});

test('getCanisterId falls back to the gaas-env descriptor for its own network', () => {
	const gaasEnv = {
		domain: 'partner.example',
		network: 'partner',
		canisters: { realm_registry_backend: { partner: 'gaas-canister-id' } }
	};
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'partner.example',
			runtimeOverride: {},
			gaasEnvOverride: gaasEnv
		}),
		'gaas-canister-id'
	);
});

test('getCanisterId falls back to the dfx env on a local replica', () => {
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'localhost',
			runtimeOverride: {},
			envOverride: { CANISTER_ID_REALM_REGISTRY_BACKEND: 'local-canister-id' }
		}),
		'local-canister-id'
	);
});

test('getCanisterId returns undefined when nothing resolves', () => {
	assert.equal(
		getCanisterId('nonexistent_canister', {
			hostname: 'gos.earth',
			runtimeOverride: RUNTIME,
			envOverride: {}
		}),
		undefined
	);
});

test('the bundle bakes no canister ids, network or portal host', () => {
	const here = dirname(fileURLToPath(import.meta.url));
	const viteSource = readFileSync(join(here, '../../vite.config.js'), 'utf-8');
	assert.doesNotMatch(viteSource, /__CANISTER_IDS__/);
	assert.doesNotMatch(viteSource, /canister_ids\.json/);
	assert.doesNotMatch(viteSource, /DFX_NETWORK/);
	for (const file of ['network.js', 'config-resolvers.js', 'deployment-manifest-core.js']) {
		const src = readFileSync(join(here, file), 'utf-8');
		assert.doesNotMatch(src, /gos\.earth|realmsgos\.org/, `${file} carries a host`);
		assert.doesNotMatch(src, /'staging'|'demo'/, `${file} names an environment`);
	}
});

// What the local stack's /canister_ids.js really holds (gos-as-a-service#108): the conductor resolves
// $canister: tokens but leaves a $env. token whose value itself holds a ${canister:x} reference.
const LOCAL_AS_WRITTEN = {
	realm_registry_backend: '7st3i-aaaaa-aaaaa-aaaaa-cai',
	realm_installer: '73qqu-aaaaa-aaaaa-aaaaa-cai',
	network: 'local',
	portal_url: '$env.portal_url',
	casals_url: '$env.casals_url',
	gos_environment: 'local'
};

test('isUnresolvedPlaceholder recognises what the conductor leaves behind', () => {
	for (const value of [
		'$env.portal_url',
		'$canister:realm-installer',
		'http://${canister:realm-registry-frontend}.localhost:8000',
		'$stand.backend',
		'$principal:operator',
		'$self',
		'$this'
	]) {
		assert.equal(isUnresolvedPlaceholder(value), true, value);
	}
	for (const value of ['https://gos.earth', 'http://abc-cai.localhost:8000', 'local', '', undefined, true]) {
		assert.equal(isUnresolvedPlaceholder(value), false, String(value));
	}
});

test('runtimeCanisterIds ignores a key whose value is still a placeholder, and says so', () => {
	const warnings = [];
	const warn = console.warn;
	console.warn = (message) => warnings.push(message);
	globalThis.__CANISTER_IDS = LOCAL_AS_WRITTEN;
	try {
		const runtime = runtimeCanisterIds();
		assert.equal(runtime.portal_url, undefined);
		assert.equal(runtime.casals_url, undefined);
		assert.equal(runtime.network, 'local');
		assert.equal(runtime.realm_installer, '73qqu-aaaaa-aaaaa-aaaaa-cai');
		assert.equal(getCanisterId('realm_installer', { runtimeOverride: runtime }), '73qqu-aaaaa-aaaaa-aaaaa-cai');

		runtimeCanisterIds();
		assert.equal(warnings.length, 1, 'said once, not on every read');
		assert.match(warnings[0], /portal_url="\$env\.portal_url"/);
		assert.match(warnings[0], /casals_url="\$env\.casals_url"/);
	} finally {
		console.warn = warn;
		delete globalThis.__CANISTER_IDS;
	}
});

test('a placeholder is never taken as the portal origin or another declared host', () => {
	globalThis.__CANISTER_IDS = { ...LOCAL_AS_WRITTEN, geister_api_url: '$env.geister_api_url' };
	const warn = console.warn;
	console.warn = () => {};
	try {
		const runtime = runtimeCanisterIds();
		assert.equal(resolvePortalBaseUrl({}, undefined, runtime), '');
		// An undeclared Geister API on a local network is none, not a host named "$env.geister_api_url".
		assert.equal(resolveGeisterApiOrigin({}, runtime, 'local'), '');
	} finally {
		console.warn = warn;
		delete globalThis.__CANISTER_IDS;
	}
});

test('a fully resolved /canister_ids.js is returned as written', () => {
	globalThis.__CANISTER_IDS = { ...RUNTIME };
	try {
		assert.deepEqual(runtimeCanisterIds(), RUNTIME);
	} finally {
		delete globalThis.__CANISTER_IDS;
	}
});
