import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { DEPLOY_GOS_PATH, draftResumeUrl } from './wizard-draft-utils.js';

const here = dirname(fileURLToPath(import.meta.url));

test('draftResumeUrl uses /deploy-gos and keeps draft query params', () => {
	assert.equal(DEPLOY_GOS_PATH, '/deploy-gos');
	assert.equal(draftResumeUrl({}), '/deploy-gos');
	assert.equal(draftResumeUrl({ id: 'draft-1' }), '/deploy-gos?draft=draft-1');
	assert.equal(draftResumeUrl({ id: 'draft-1' }, 6), '/deploy-gos?draft=draft-1&step=6');
});

test('create-realm load redirects to /deploy-gos with the same search string', () => {
	const redirectSource = readFileSync(
		join(here, '../routes/create-realm/+page.js'),
		'utf-8'
	);
	assert.match(redirectSource, /prerender = false/);
	assert.match(redirectSource, /redirect\(308,\s*`\/deploy-gos\$\{url\.search\}`\)/);
});

test('deploy-gos page uses the locked heading and tab title', () => {
	const pageSource = readFileSync(join(here, '../routes/deploy-gos/+page.svelte'), 'utf-8');
	assert.match(pageSource, /<title>Launch a new realm \| Realms<\/title>/);
	assert.match(pageSource, /<h1>Launch a new realm<\/h1>/);
	assert.match(pageSource, /Follow the steps to launch your new realm\./);
	assert.match(pageSource, /Choose your GOS/);
	assert.match(pageSource, /Realm Identification/);
	assert.match(pageSource, /This is the URL of your realm's portal:/);
	assert.match(pageSource, /The Internet Computer runs on computers around the world/);
	assert.match(pageSource, /Confirm these settings, then launch your realm\./);
	assert.match(pageSource, /codex-detail-label">GOS</);
	assert.match(pageSource, /Launch realm/);
	assert.equal(pageSource.includes('Basic Information'), false);
	assert.equal(pageSource.includes('Create Your Realm'), false);
	assert.equal(pageSource.includes('Deploy your GOS'), false);
	assert.equal(pageSource.includes('Manual Deployment'), false);
	assert.equal(pageSource.includes('pip install realms-gos'), false);
	assert.equal(pageSource.includes('Deploy via Casals'), false);
	assert.equal(pageSource.includes('governance system'), false);
});
