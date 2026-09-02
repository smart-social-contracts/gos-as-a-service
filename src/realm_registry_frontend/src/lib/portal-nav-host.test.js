import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));

test('portal nav:push uses SvelteKit replaceState so the address bar is not reverted', () => {
	const host = fs.readFileSync(path.join(dir, 'portal-bridge-host.js'), 'utf8');
	assert.match(host, /onNavPush/);
	const page = fs.readFileSync(
		path.join(dir, '../routes/r/[slug]/[...path]/+page.svelte'),
		'utf8',
	);
	assert.match(page, /replaceState\(href/);
	assert.match(page, /pushState\(href/);
	assert.match(page, /liveIframeSrc/);
	assert.match(page, /nav\.type !== 'popstate'/);
});
