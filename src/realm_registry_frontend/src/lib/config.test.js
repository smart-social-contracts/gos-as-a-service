import assert from 'node:assert/strict';
import test from 'node:test';
import {
	resolveBillingServiceUrl,
	resolveDeployServiceUrl,
	resolvePortalBaseUrl
} from './config-resolvers.js';

test('resolveBillingServiceUrl falls back to default without gaas-env', () => {
	assert.equal(resolveBillingServiceUrl({}, undefined), 'https://billing.realmsgos.dev');
});

test('resolveBillingServiceUrl returns null when gaas-env omits billing_url', () => {
	assert.equal(
		resolveBillingServiceUrl({}, { domain: 'partner.example', network: 'test' }),
		null
	);
});

test('resolveBillingServiceUrl prefers VITE override', () => {
	assert.equal(
		resolveBillingServiceUrl(
			{ VITE_BILLING_SERVICE_URL: 'https://billing.override.test' },
			{ domain: 'partner.example', services: { billing_url: 'https://billing.example.test' } }
		),
		'https://billing.override.test'
	);
});

test('resolveDeployServiceUrl returns null when gaas-env omits deploy_url', () => {
	assert.equal(
		resolveDeployServiceUrl({}, { domain: 'partner.example', network: 'test' }),
		null
	);
});

test('resolvePortalBaseUrl takes the conductor-written portal_url first', () => {
	assert.equal(
		resolvePortalBaseUrl({}, { domain: 'partner.example' }, { portal_url: 'https://gos.earth/' }),
		'https://gos.earth'
	);
});

test('resolvePortalBaseUrl falls back to the gaas-env domain origin', () => {
	assert.equal(
		resolvePortalBaseUrl({}, { domain: 'partner.example', network: 'test' }, {}),
		'https://partner.example'
	);
});

test('resolvePortalBaseUrl is empty when this deployment declares no portal', () => {
	assert.equal(resolvePortalBaseUrl({}, undefined, {}), '');
	assert.equal(resolvePortalBaseUrl({}, undefined, undefined), '');
});
