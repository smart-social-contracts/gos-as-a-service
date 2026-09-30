import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { MAINTAINER_CONTACT_URL, MAINTAINER_ORIGIN } from './maintainer.js';

const here = dirname(fileURLToPath(import.meta.url));
const LOCALES = ['en.json', 'es.json', 'de.json', 'fr.json', 'it.json', 'zh-CN.json'];

test('contact for this portal is the realmsgos.org about page', () => {
	assert.equal(MAINTAINER_ORIGIN, 'https://realmsgos.org');
	assert.equal(MAINTAINER_CONTACT_URL, 'https://realmsgos.org/about#contact');
});

test('about copy names realmsgos.org and points at its contact link', () => {
	const page = readFileSync(join(here, '../routes/about/+page.svelte'), 'utf-8');
	assert.match(page, /MAINTAINER_CONTACT_URL/);
	assert.match(page, /about\.body_before/);
	assert.match(page, /about\.link/);
	const header = readFileSync(join(here, 'components/RegistryHeader.svelte'), 'utf-8');
	assert.match(header, /href="\/about"/);
	const footer = readFileSync(join(here, 'components/RegistryFooter.svelte'), 'utf-8');
	assert.match(footer, /MAINTAINER_CONTACT_URL/);
	assert.match(footer, /about\.footer/);
	for (const file of LOCALES) {
		const loc = JSON.parse(readFileSync(join(here, 'i18n/locales', file), 'utf-8'));
		assert.equal(loc.about.link, 'realmsgos.org', file);
		assert.match(loc.about.body_before, /\S/);
		assert.match(loc.about.body_after, /\S/);
		assert.match(loc.about.footer, /realmsgos\.org/);
		assert.ok(loc.hub.about, file);
	}
	const en = JSON.parse(readFileSync(join(here, 'i18n/locales/en.json'), 'utf-8'));
	assert.equal(
		en.about.body_before + en.about.link + en.about.body_after,
		'This website is built and maintained by realmsgos.org. Follow that link to get in touch.'
	);
});
