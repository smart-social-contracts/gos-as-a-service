import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { detectNetwork, getCanisterId } from './network.js';

const CANISTER_MAP = {
	realm_registry_backend: {
		demo: 'rhw4p-gqaaa-aaaac-qbw7q-cai',
		staging: 'snqhl-daaaa-aaaan-q6n3q-cai',
		test: 'yhw3g-fyaaa-aaaas-qgorq-cai'
	},
	file_registry: {
		test: 'uq2mu-kaaaa-aaaah-avqcq-cai'
	}
};

const REPO_CANISTER_IDS = JSON.parse(
	readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../../../../canister_ids.json'), 'utf-8')
);

const CASALS_BACKEND_IDS = {
	test: 'qthgp-3yaaa-aaaae-agveq-cai',
	staging: 'th7fr-bqaaa-aaaan-q6n4q-cai',
	demo: 'jo3cj-faaaa-aaaac-bffea-cai'
};

const DEAD_CANISTER_PREFIXES = ['fdr7z', 'jj2e5', 'rbuam', 'fksuf', 'hznxf', 'gudtl', 'h6mrr', 'mcqbx'];

test('detectNetwork maps known hostnames', () => {
	assert.equal(detectNetwork('test.gos.earth'), 'test');
	assert.equal(detectNetwork('staging.gos.earth'), 'staging');
	assert.equal(detectNetwork('demo.gos.earth'), 'demo');
	assert.equal(detectNetwork('gos.earth'), 'ic');
	assert.equal(detectNetwork('registry.realmsgos.org'), 'ic');
	assert.equal(detectNetwork('localhost'), 'local');
	assert.equal(detectNetwork('127.0.0.1'), 'local');
	assert.equal(detectNetwork('realm_registry_frontend.localhost'), 'local');
});

test('detectNetwork defaults unknown hostnames to staging', () => {
	assert.equal(detectNetwork('unknown.example.com'), 'staging');
});

test('getCanisterId resolves from injected map by network', () => {
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'test.gos.earth',
			canisterIdsMap: CANISTER_MAP
		}),
		'yhw3g-fyaaa-aaaas-qgorq-cai'
	);
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'staging.gos.earth',
			canisterIdsMap: CANISTER_MAP
		}),
		'snqhl-daaaa-aaaan-q6n3q-cai'
	);
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'demo.gos.earth',
			canisterIdsMap: CANISTER_MAP
		}),
		'rhw4p-gqaaa-aaaac-qbw7q-cai'
	);
});

test('getCanisterId falls back to env for local network', () => {
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'localhost',
			canisterIdsMap: CANISTER_MAP,
			envOverride: { CANISTER_ID_REALM_REGISTRY_BACKEND: 'local-canister-id' }
		}),
		'local-canister-id'
	);
});

test('getCanisterId returns undefined when nothing resolves', () => {
	assert.equal(
		getCanisterId('nonexistent_canister', {
			hostname: 'test.gos.earth',
			canisterIdsMap: CANISTER_MAP
		}),
		undefined
	);
	assert.equal(
		getCanisterId('file_registry', {
			hostname: 'demo.gos.earth',
			canisterIdsMap: CANISTER_MAP
		}),
		undefined
	);
});

test('detectNetwork resolves gaas-env domain to configured network', () => {
	const gaasEnv = { domain: 'partner.example', network: 'custom-net' };
	assert.equal(detectNetwork('partner.example', gaasEnv), 'custom-net');
	assert.equal(detectNetwork('localhost', gaasEnv), 'local');
	assert.equal(detectNetwork('test.gos.earth', gaasEnv), 'test');
});

test('getCanisterId resolves casals_backend from canister_ids.json on portal hostnames', () => {
	assert.equal(
		getCanisterId('casals_backend', {
			hostname: 'test.gos.earth',
			canisterIdsMap: REPO_CANISTER_IDS
		}),
		CASALS_BACKEND_IDS.test
	);
	assert.equal(
		getCanisterId('casals_backend', {
			hostname: 'staging.gos.earth',
			canisterIdsMap: REPO_CANISTER_IDS
		}),
		CASALS_BACKEND_IDS.staging
	);
	assert.equal(
		getCanisterId('casals_backend', {
			hostname: 'demo.gos.earth',
			canisterIdsMap: REPO_CANISTER_IDS
		}),
		CASALS_BACKEND_IDS.demo
	);
});

test('canister_ids.json bakes live casals_backend IDs and no known-dead prefixes', () => {
	assert.deepEqual(REPO_CANISTER_IDS.casals_backend, CASALS_BACKEND_IDS);
	const dumped = JSON.stringify(REPO_CANISTER_IDS.casals_backend);
	for (const prefix of DEAD_CANISTER_PREFIXES) {
		assert.equal(dumped.includes(prefix), false, `dead prefix ${prefix}`);
	}
});

test('portal bake injects every canister_ids.json entry including casals_backend', () => {
	const viteSource = readFileSync(
		join(dirname(fileURLToPath(import.meta.url)), '../../vite.config.js'),
		'utf-8'
	);
	assert.match(viteSource, /for \(const \[canister, networks\] of Object\.entries\(allIds\)\)/);
	assert.match(viteSource, /CANISTER_ID_\$\{canister\.toUpperCase\(\)\}/);
	assert.match(viteSource, /'__CANISTER_IDS__'/);
	assert.ok(REPO_CANISTER_IDS.casals_backend);
});

test('getCanisterId prefers gaas-env canisters map when present', () => {
	const gaasEnv = {
		domain: 'partner.example',
		network: 'partner',
		canisters: {
			realm_registry_backend: {
				partner: 'gaas-canister-id'
			}
		}
	};
	assert.equal(
		getCanisterId('realm_registry_backend', {
			hostname: 'partner.example',
			canisterIdsMap: CANISTER_MAP,
			gaasEnvOverride: gaasEnv
		}),
		'gaas-canister-id'
	);
});
