import assert from 'node:assert/strict';
import test from 'node:test';
import {
	DEFAULT_GEISTER_API_ORIGIN,
	resolveBillingServiceUrl,
	resolveDeployServiceUrl,
	resolveGeisterApiOrigin,
	resolveInternetIdentityUrl,
	resolvePortalBaseUrl
} from './config-resolvers.js';

test('resolveGeisterApiOrigin: a local network has no assistant service unless it names one', () => {
	assert.equal(resolveGeisterApiOrigin({}, { network: 'local' }, 'local'), '');
	assert.equal(resolveGeisterApiOrigin({}, undefined, 'local'), '');
	assert.equal(
		resolveGeisterApiOrigin({}, { network: 'local', geister_api_url: 'http://geister.localhost:8000/' }, 'local'),
		'http://geister.localhost:8000'
	);
});

test('resolveGeisterApiOrigin: every other deployment keeps the host it has always used', () => {
	for (const network of ['ic', 'production', 'staging', 'demo', 'test', '']) {
		assert.equal(resolveGeisterApiOrigin({}, { network }, network), DEFAULT_GEISTER_API_ORIGIN);
	}
	assert.equal(resolveGeisterApiOrigin({}, undefined, 'ic'), 'https://geister-api.realmsgos.dev');
});

test('resolveGeisterApiOrigin: a deployment can declare another host, or none with an empty one', () => {
	assert.equal(
		resolveGeisterApiOrigin({}, { geister_api_url: ' https://geister.example.test/ ' }, 'ic'),
		'https://geister.example.test'
	);
	assert.equal(resolveGeisterApiOrigin({}, { geister_api_url: '' }, 'ic'), '');
});

test('resolveGeisterApiOrigin: the VITE override wins, as for the other services', () => {
	assert.equal(
		resolveGeisterApiOrigin(
			{ VITE_GEISTER_API_ORIGIN: 'http://localhost:9000' },
			{ geister_api_url: 'https://geister.example.test' },
			'local'
		),
		'http://localhost:9000'
	);
});

test('resolveInternetIdentityUrl is the mainnet one when the deployment names none', () => {
	assert.equal(resolveInternetIdentityUrl({}, undefined), 'https://identity.ic0.app/');
	assert.equal(resolveInternetIdentityUrl({}, { network: 'ic', internet_identity: ' ' }), 'https://identity.ic0.app/');
});

test('resolveInternetIdentityUrl takes the one the conductor wrote in /canister_ids.js', () => {
	const local = 'http://identity.localhost:8000';
	assert.equal(resolveInternetIdentityUrl({}, { network: 'local', internet_identity: local }), local);
});

test('resolveInternetIdentityUrl prefers the VITE override', () => {
	assert.equal(
		resolveInternetIdentityUrl(
			{ VITE_INTERNET_IDENTITY_URL: 'http://localhost:4943/?canisterId=ii' },
			{ internet_identity: 'http://identity.localhost:8000' }
		),
		'http://localhost:4943/?canisterId=ii'
	);
});

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
