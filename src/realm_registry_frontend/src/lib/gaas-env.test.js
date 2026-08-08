import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
	buildIcDomainsContent,
	buildIiAlternativeOriginsContent,
	generateWellKnownFiles,
	getGaasEnvViteDefine,
	loadGaasEnvFromFile,
	normalizeGaasEnv
} from '../../scripts/gaas-env.js';

test('normalizeGaasEnv requires domain', () => {
	assert.throws(() => normalizeGaasEnv({ name: 'test' }), /requires domain/);
});

test('normalizeGaasEnv maps optional fields', () => {
	const env = normalizeGaasEnv({
		name: 'test',
		domain: 'test.gos.earth',
		network: 'test',
		services: {
			billing_url: 'https://billing.example.test',
			deploy_url: 'https://deploy.example.test'
		},
		gos: [
			{
				implementation: 'realms-gos',
				version: 'v0.3.1',
				loader_profile: 'realms-iframe-v1',
				available: true
			}
		],
		ii_alternative_origins: ['https://extra.example.test']
	});

	assert.equal(env.domain, 'test.gos.earth');
	assert.equal(env.network, 'test');
	assert.equal(env.services?.billing_url, 'https://billing.example.test');
	assert.equal(env.services?.deploy_url, 'https://deploy.example.test');
	assert.equal(env.gos?.[0]?.implementation, 'realms-gos');
	assert.deepEqual(env.ii_alternative_origins, ['https://extra.example.test']);
});

test('buildIcDomainsContent writes configured domain', () => {
	const content = buildIcDomainsContent({ domain: 'partner.example' });
	assert.equal(content, 'partner.example\n');
});

test('buildIiAlternativeOriginsContent includes domain origin and extras', () => {
	const content = buildIiAlternativeOriginsContent({
		domain: 'partner.example',
		ii_alternative_origins: ['https://alt.example', 'https://partner.example']
	});
	const parsed = JSON.parse(content);
	assert.deepEqual(parsed.alternativeOrigins, [
		'https://partner.example',
		'https://alt.example'
	]);
});

test('generateWellKnownFiles writes static assets', () => {
	const dir = mkdtempSync(join(tmpdir(), 'gaas-env-'));
	const staticDir = join(dir, 'static');
	try {
		generateWellKnownFiles(
			{
				domain: 'partner.example',
				ii_alternative_origins: ['https://alt.example']
			},
			staticDir
		);

		assert.equal(
			readFileSync(join(staticDir, '.well-known/ic-domains'), 'utf-8'),
			'partner.example\n'
		);
		const iiOrigins = JSON.parse(
			readFileSync(join(staticDir, '.well-known/ii-alternative-origins'), 'utf-8')
		);
		assert.deepEqual(iiOrigins.alternativeOrigins, [
			'https://partner.example',
			'https://alt.example'
		]);
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});

test('getGaasEnvViteDefine returns empty object when env absent', () => {
	assert.deepEqual(getGaasEnvViteDefine(null), {});
	assert.deepEqual(getGaasEnvViteDefine(undefined), {});
});

test('getGaasEnvViteDefine serializes gaas-env for Vite define', () => {
	const define = getGaasEnvViteDefine({ domain: 'partner.example', network: 'test' });
	assert.equal(define.__GAAS_ENV__, JSON.stringify({ domain: 'partner.example', network: 'test' }));
});

test('loadGaasEnvFromFile reads repo-root gaas-env.json', () => {
	const dir = mkdtempSync(join(tmpdir(), 'gaas-env-file-'));
	try {
		writeFileSync(
			join(dir, 'gaas-env.json'),
			JSON.stringify({ domain: 'file.example', network: 'staging' })
		);
		const env = loadGaasEnvFromFile(dir);
		assert.equal(env?.domain, 'file.example');
		assert.equal(env?.network, 'staging');
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});
