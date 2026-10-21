import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const here = dirname(fileURLToPath(import.meta.url));
const LOCALES = ['en.json', 'es.json', 'de.json', 'fr.json', 'it.json', 'zh-CN.json'];
const header = readFileSync(join(here, 'components/RegistryHeader.svelte'), 'utf-8');

test('"What is this?" opens the presentation in a new tab', () => {
	assert.match(header, /WHAT_IS_THIS_URL = '\/what-is-this\/index\.html'/);
	const link = header.match(/<a\s[^>]*data-what-is-this[^>]*>/)?.[0] ?? '';
	assert.match(link, /href=\{WHAT_IS_THIS_URL\}/);
	assert.match(link, /target="_blank"/);
	const deck = join(here, '../../static/what-is-this');
	assert.ok(existsSync(join(deck, 'index.html')));
	for (const src of readFileSync(join(deck, 'index.html'), 'utf-8').matchAll(/src="(assets\/[^"]+)"/g)) {
		assert.ok(existsSync(join(deck, src[1])), src[1]);
	}
});

test('"Tutorial" starts the walkthrough', () => {
	assert.match(header, /<button[^>]*data-tutorial[^>]*on:click=\{openTour\}/);
	assert.match(header, /hub\.tutorial/);
	assert.doesNotMatch(header, /hub\.tour_title|href="\/about"/);
});

test('every locale names both menu entries', () => {
	for (const file of LOCALES) {
		const { hub } = JSON.parse(readFileSync(join(here, 'i18n/locales', file), 'utf-8'));
		assert.match(hub.what_is_this, /\S/, file);
		assert.match(hub.tutorial, /\S/, file);
		assert.equal(hub.tour_title, undefined, file);
	}
});
