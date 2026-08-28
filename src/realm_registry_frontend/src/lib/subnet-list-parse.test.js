import assert from 'node:assert/strict';
import test from 'node:test';
import { parseSubnetList, requireCasalsBackendCanisterId } from './subnet-list-parse.js';

const SUBNET_A = '4ecnw-byqwz-dtgss-ua2mh-pfvs7-c3lct-gtf4e-hnu75-j7eek-iifqm-sqe';
const SUBNET_B = '4utr6-xo2fz-v7fsb-t3wsg-k7sfl-cj2ba-ghdnd-kcrfo-xavdb-ebean-mqe';

const LIVE_SUBNETS = Array.from(
	{ length: 27 },
	(_, i) => `subnet-${String(i + 1).padStart(2, '0')}`
);

const LIVE_CASALS_ENVELOPE = {
	ok: true,
	whitelist_active: false,
	subnets: LIVE_SUBNETS,
	creatable_subnets: LIVE_SUBNETS
};

test('parseSubnetList accepts a bare JSON array of subnet ids', () => {
	assert.deepEqual(parseSubnetList(JSON.stringify([SUBNET_A, SUBNET_B])), [
		SUBNET_A,
		SUBNET_B
	]);
	assert.deepEqual(parseSubnetList([SUBNET_A, SUBNET_B]), [SUBNET_A, SUBNET_B]);
});

test('parseSubnetList accepts the live Casals {ok, subnets, creatable_subnets} envelope', () => {
	const parsed = parseSubnetList(JSON.stringify(LIVE_CASALS_ENVELOPE));
	assert.equal(parsed.length, 27);
	assert.deepEqual(parsed, LIVE_SUBNETS);
	assert.deepEqual(parseSubnetList(LIVE_CASALS_ENVELOPE), LIVE_SUBNETS);
});

test('parseSubnetList prefers subnets when creatable_subnets differs', () => {
	assert.deepEqual(
		parseSubnetList({
			ok: true,
			subnets: [SUBNET_A],
			creatable_subnets: [SUBNET_B]
		}),
		[SUBNET_A]
	);
});

test('parseSubnetList ignores ok:false error envelopes even when subnets is present', () => {
	assert.deepEqual(
		parseSubnetList({
			ok: false,
			subnets: [SUBNET_A],
			creatable_subnets: [SUBNET_A]
		}),
		[]
	);
	assert.deepEqual(parseSubnetList(JSON.stringify({ ok: false })), []);
});

test('parseSubnetList accepts object entries with id fields', () => {
	assert.deepEqual(
		parseSubnetList({
			subnets: [{ id: SUBNET_A }, { subnet_id: SUBNET_B }]
		}),
		[SUBNET_A, SUBNET_B]
	);
});

test('parseSubnetList returns empty list for invalid or empty payloads', () => {
	assert.deepEqual(parseSubnetList('not-json'), []);
	assert.deepEqual(parseSubnetList(JSON.stringify({ ok: true })), []);
	assert.deepEqual(parseSubnetList({}), []);
	assert.deepEqual(parseSubnetList(null), []);
});

test('requireCasalsBackendCanisterId throws when the conductor ID is missing', () => {
	assert.throws(() => requireCasalsBackendCanisterId(''), /Could not load available subnets/);
	assert.throws(() => requireCasalsBackendCanisterId('   '), /Could not load available subnets/);
	assert.throws(() => requireCasalsBackendCanisterId(undefined), /Could not load available subnets/);
	assert.throws(() => requireCasalsBackendCanisterId(null), /Could not load available subnets/);
	assert.equal(
		requireCasalsBackendCanisterId('qthgp-3yaaa-aaaae-agveq-cai'),
		'qthgp-3yaaa-aaaae-agveq-cai'
	);
});
