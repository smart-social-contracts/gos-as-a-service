import assert from 'node:assert/strict';
import test from 'node:test';
import { parseSubnetList } from './subnet-list-parse.js';

const SUBNET_A = '4ecnw-byqwz-dtgss-ua2mh-pfvs7-c3lct-gtf4e-hnu75-j7eek-iifqm-sqe';
const SUBNET_B = '4utr6-xo2fz-v7fsb-t3wsg-k7sfl-cj2ba-ghdnd-kcrfo-xavdb-ebean-mqe';

test('parseSubnetList accepts a bare JSON array of subnet ids', () => {
  const raw = JSON.stringify([SUBNET_A, SUBNET_B]);
  assert.deepEqual(parseSubnetList(raw), [SUBNET_A, SUBNET_B]);
});

test('parseSubnetList accepts Casals object payload with subnets key', () => {
  const raw = JSON.stringify({
    subnets: [SUBNET_A, SUBNET_B],
    creatable_subnets: [SUBNET_A, SUBNET_B],
    whitelist_active: false,
    ok: true,
  });
  assert.deepEqual(parseSubnetList(raw), [SUBNET_A, SUBNET_B]);
});

test('parseSubnetList prefers creatable_subnets when present', () => {
  const raw = JSON.stringify({
    subnets: [SUBNET_A, 'ignored-subnet'],
    creatable_subnets: [SUBNET_B],
    ok: true,
  });
  assert.deepEqual(parseSubnetList(raw), [SUBNET_B]);
});

test('parseSubnetList accepts object entries with id fields', () => {
  const raw = JSON.stringify({
    subnets: [{ id: SUBNET_A }, { subnet_id: SUBNET_B }],
  });
  assert.deepEqual(parseSubnetList(raw), [SUBNET_A, SUBNET_B]);
});

test('parseSubnetList returns empty list for invalid JSON', () => {
  assert.deepEqual(parseSubnetList('not-json'), []);
});

test('parseSubnetList returns empty list for non-array object without subnets', () => {
  assert.deepEqual(parseSubnetList(JSON.stringify({ ok: true })), []);
});
