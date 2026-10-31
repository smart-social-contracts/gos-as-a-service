import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveRealmDelegationTargets } from './delegation-targets.js';

const platform = ['registry-id', 'installer-id'];

/** Each canister's own claim about its capital; '' is a canister that reports none. */
function resolve(backend, reported, capitals, options = {}) {
	return resolveRealmDelegationTargets(backend, platform, {
		fetchQuarterIds: async () => reported,
		fetchCapital: async (id) => capitals[id] ?? '',
		timeoutMs: 50,
		...options
	});
}

test.beforeEach((t) => t.mock.method(console, 'warn', () => {}));

test('delegates to the backend and the quarters that name it as their capital', async () => {
	const targets = await resolve('realm', ['q1', 'q2', 'q1'], { q1: 'realm', q2: 'realm' });
	assert.deepEqual(targets, ['realm', 'q1', 'q2']);
});

test('delegates to the backend alone when the realm reports no quarters', async () => {
	assert.deepEqual(await resolve('realm', [], {}), ['realm']);
});

test("drops another realm's backend, which reports no capital", async () => {
	assert.deepEqual(await resolve('realm', ['other-realm'], {}), ['realm']);
});

test('drops a quarter of another federation', async () => {
	assert.deepEqual(await resolve('realm', ['q9'], { q9: 'other-realm' }), ['realm']);
});

test('drops platform canisters without asking them', async () => {
	const asked = [];
	const targets = await resolve('realm', ['registry-id', 'q1'], { q1: 'realm' }, {
		fetchCapital: async (id) => {
			asked.push(id);
			return 'realm';
		}
	});
	assert.deepEqual(targets, ['realm', 'q1']);
	assert.deepEqual(asked, ['q1']);
});

test('checks at most 500 reported quarters', async () => {
	const reported = Array.from({ length: 501 }, (_, i) => `q${i}`);
	const asked = [];
	const targets = await resolve('realm', reported, {}, {
		fetchCapital: async (id) => {
			asked.push(id);
			return 'realm';
		}
	});
	assert.equal(asked.length, 500);
	assert.equal(targets.length, 501);
	assert.ok(!targets.includes('q500'));
});

test('refuses a platform canister recorded as the backend', async () => {
	await assert.rejects(resolve('installer-id', [], {}), /platform canister installer-id/);
});

test('drops a quarter that fails or does not answer in time, keeping the others', async () => {
	const targets = await resolve('realm', ['broken', 'slow', 'q1'], { q1: 'realm' }, {
		fetchCapital: (id) => {
			if (id === 'broken') return Promise.reject(new Error('IC0301'));
			if (id === 'slow') return new Promise(() => {});
			return Promise.resolve('realm');
		}
	});
	assert.deepEqual(targets, ['realm', 'q1']);
});

test('delegates to the backend alone when the realm cannot list its quarters', async () => {
	const failing = await resolve('realm', [], {}, { fetchQuarterIds: () => Promise.reject(new Error('down')) });
	const hanging = await resolve('realm', [], {}, { fetchQuarterIds: () => new Promise(() => {}) });
	assert.deepEqual(failing, ['realm']);
	assert.deepEqual(hanging, ['realm']);
});
