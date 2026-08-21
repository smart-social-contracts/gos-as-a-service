import assert from 'node:assert/strict';
import test from 'node:test';

import {
	classifyCountry,
	countryCodeFromRegion,
	countryCodeToFlag,
	orderCountryCodes,
	regionFlagGroups,
	shortSubnetId,
	subnetShortLabel,
	subnetTypeLabel,
} from './subnet-geo.js';

test('countryCodeToFlag maps ISO codes to regional-indicator emoji', () => {
	assert.equal(countryCodeToFlag('RO'), '🇷🇴');
	assert.equal(countryCodeToFlag('us'), '🇺🇸');
	assert.equal(countryCodeToFlag('X'), '');
});

test('countryCodeFromRegion parses IC dashboard region strings', () => {
	assert.equal(countryCodeFromRegion('Europe,RO,Bucharest'), 'RO');
	assert.equal(countryCodeFromRegion('North America,US,San Jose'), 'US');
	assert.equal(countryCodeFromRegion('nope'), '');
});

test('classifyCountry groups known codes', () => {
	assert.equal(classifyCountry('DE'), 'EU');
	assert.equal(classifyCountry('US'), 'USA');
	assert.equal(classifyCountry('JP'), 'APAC');
	assert.equal(classifyCountry('AE'), 'MidEast');
	assert.equal(classifyCountry('ZZ'), 'Other');
});

test('orderCountryCodes sorts by region then name', () => {
	const ordered = orderCountryCodes(['JP', 'DE', 'US']);
	assert.deepEqual(
		ordered.map((c) => c.code),
		['US', 'DE', 'JP'],
	);
});

test('subnetTypeLabel prettifies dashboard types', () => {
	assert.equal(subnetTypeLabel('VERIFIED_APPLICATION'), 'Verified Application');
	assert.equal(subnetTypeLabel('application'), 'Application');
});

test('regionFlagGroups keeps region order', () => {
	const groups = regionFlagGroups(orderCountryCodes(['JP', 'DE', 'US']));
	assert.deepEqual(
		groups.map((g) => g.region),
		['USA', 'EU', 'APAC'],
	);
});

test('subnet labels stay short', () => {
	const id = '4ecnw-byqwz-dtgss-ua2mh-pfvs7-c3lct-gtf4e-hnu75-j7eek-iifqm-sqe';
	assert.equal(subnetShortLabel(id), '4ecnw');
	assert.equal(shortSubnetId(id), '4ecnw…m-sqe');
});
