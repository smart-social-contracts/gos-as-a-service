import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { architectureHref } from './architecture-link.js';

const here = dirname(fileURLToPath(import.meta.url));
const headerSource = readFileSync(
	join(here, 'components/RegistryHeader.svelte'),
	'utf-8'
);
const pageSource = readFileSync(join(here, '../routes/+page.svelte'), 'utf-8');
const idsSource = readFileSync(join(here, '../../../../canister_ids.json'), 'utf-8');

test('architectureHref returns the provided Casals URL', () => {
	assert.equal(
		architectureHref('https://qic2k-baaaa-aaaae-agvga-cai.icp0.io'),
		'https://qic2k-baaaa-aaaae-agvga-cai.icp0.io'
	);
});

test('empty casalsUrl does not navigate to a canister URL', () => {
	assert.equal(architectureHref(''), '');
	assert.equal(architectureHref('   '), '');
	assert.equal(architectureHref(undefined), '');
	assert.equal(architectureHref(null), '');
	assert.ok(!architectureHref('').includes('.icp0.io'));
	assert.ok(!architectureHref('').includes('-cai'));
});

test('RegistryHeader has no fdr7z fallback and no hardcoded canister URL', () => {
	assert.equal(headerSource.includes('fdr7z'), false);
	assert.equal(headerSource.includes('CASALS_FALLBACK'), false);
	assert.equal(headerSource.includes('.icp0.io'), false);
	assert.match(headerSource, /architectureHref\(casalsUrl\)/);
	assert.match(headerSource, /data-architecture-unavailable/);
	assert.match(headerSource, /\{#if architectureUrl\}/);
});

test('portal source and canister_ids no longer mention fdr7z', () => {
	assert.equal(pageSource.includes('fdr7z'), false);
	assert.equal(idsSource.includes('fdr7z'), false);
	assert.match(idsSource, /to4on-xyaaa-aaaan-q6n5a-cai/);
	assert.match(idsSource, /qic2k-baaaa-aaaae-agvga-cai/);
});

test('frontend prebuild does not generate casals_backend', () => {
	const pkg = JSON.parse(readFileSync(join(here, '../../package.json'), 'utf-8'));
	assert.equal((pkg.scripts?.prebuild || '').includes('casals_backend'), false);
	assert.match(pkg.scripts.prebuild, /dfx generate realm_registry_backend/);
	assert.match(pkg.scripts.prebuild, /dfx generate realm_installer/);
});
