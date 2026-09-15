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

test('deploy-gos invitation gate links to Tally, not OpenChat', () => {
	const source = readFileSync(join(here, '../routes/deploy-gos/+page.svelte'), 'utf8');
	assert.match(source, /ALPHA_INVITE_REQUEST_URL/);
	assert.match(source, /Request Invite/);
	assert.doesNotMatch(source, /oc\.app\/community\/x2nkd-waaaa-aaaar-bhh4q-cai/);
});
