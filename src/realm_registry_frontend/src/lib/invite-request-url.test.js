import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { ALPHA_INVITE_REQUEST_URL } from './invite-request-url.js';

const here = dirname(fileURLToPath(import.meta.url));

test('alpha invite request URL is the production Tally form', () => {
	assert.equal(ALPHA_INVITE_REQUEST_URL, 'https://tally.so/r/GxQ8QL');
});

test('deploy-gos invitation gate shows the Alpha notice, which links to Tally, not OpenChat', () => {
	const gate = readFileSync(join(here, '../routes/deploy-gos/+page.svelte'), 'utf8');
	const notice = readFileSync(join(here, 'components/AlphaAccessNotice.svelte'), 'utf8');
	assert.match(gate, /<AlphaAccessNotice \/>/);
	assert.match(notice, /ALPHA_INVITE_REQUEST_URL/);
	assert.doesNotMatch(gate, /oc\.app\/community\/x2nkd-waaaa-aaaar-bhh4q-cai/);
});

test('the landing page shows the Alpha notice to visitors who are not signed in', () => {
	const landing = readFileSync(join(here, '../routes/+page.svelte'), 'utf8');
	assert.match(landing, /<AlphaAccessNotice \/>/);
});
