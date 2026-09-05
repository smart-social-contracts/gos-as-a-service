import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

/**
 * Test Mode banner X: Tab+Enter worked, mouse click did not.
 *
 * Same hit-testing class as realm host chrome: the dismiss control is a
 * native button, but the X is an SVG <path>. A leftover layer or a
 * delegated click whose target is the <path> leaves the button focused
 * (keyboard works) while elementFromPoint is not the button.
 *
 * Header chrome (hub / auth) must stay clickable. Banner z-index stays
 * above the header strip; the header itself is pointer-events: none so
 * only .header-zone hit targets receive clicks.
 */

const here = dirname(fileURLToPath(import.meta.url));
const banner = readFileSync(join(here, 'components/TestModeBanner.svelte'), 'utf8');
const header = readFileSync(join(here, 'components/RegistryHeader.svelte'), 'utf8');
const appHtml = readFileSync(join(here, '../app.html'), 'utf8');
const layout = readFileSync(join(here, '../routes/+layout.svelte'), 'utf8');
const home = readFileSync(join(here, '../routes/+page.svelte'), 'utf8');

test('dismiss is a native button wired to dismissBanner', () => {
	assert.match(banner, /<button[^>]*type="button"/);
	assert.match(banner, /on:click=\{dismissBanner\}/);
	assert.match(banner, /demo_banner\.dismiss_label/);
});

test('X svg/path are not the mouse hit target', () => {
	assert.match(banner, /\.dismiss svg[\s\S]*pointer-events:\s*none/);
	assert.match(banner, /\.dismiss path[\s\S]*pointer-events:\s*none/);
	assert.match(banner, /\.dismiss \{[\s\S]*pointer-events:\s*auto/);
});

test('banner stays above the header strip without covering hub/auth zones', () => {
	assert.match(banner, /z-index:\s*400/);
	assert.match(header, /z-index:\s*200/);
	assert.match(header, /\.registry-header \{[\s\S]*pointer-events:\s*none/);
	assert.match(header, /\.header-zone \{[\s\S]*pointer-events:\s*auto/);
	assert.match(header, /header-left/);
	assert.match(header, /header-right/);
	assert.match(header, /toggleHub/);
	assert.match(header, /showAuthMenu/);
});

test('viewport-fit=cover enables safe-area insets on iOS', () => {
	assert.match(appHtml, /viewport-fit=cover/);
	assert.match(appHtml, /initial-scale=1/);
});

test('globe home insets map shell below the fixed test banner', () => {
	assert.match(home, /\.registry-page \{[\s\S]*height:\s*100vh[\s\S]*height:\s*100dvh/);
	assert.match(home, /\.map-shell \{[\s\S]*top:\s*var\(--test-mode-banner-height,\s*0px\)/);
	assert.match(header, /top:\s*var\(--test-mode-banner-height,\s*0px\)/);
});

test('app shell uses dynamic viewport height without double banner padding on map routes', () => {
	assert.match(layout, /\.app-shell \{[\s\S]*min-height:\s*100vh[\s\S]*min-height:\s*100dvh/);
	assert.match(layout, /\.app-shell\.full-viewport \{[\s\S]*padding-top:\s*0/);
	assert.match(layout, /\.loading-screen \{[\s\S]*min-height:\s*100vh[\s\S]*min-height:\s*100dvh/);
});
