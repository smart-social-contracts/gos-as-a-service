import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { applyIntroLinks, INTRO_LINKS } from './intro-links.js';

const here = dirname(fileURLToPath(import.meta.url));
const tour = readFileSync(join(here, 'components/RegistryTour.svelte'), 'utf8');
const en = JSON.parse(readFileSync(join(here, 'i18n/locales/en.json'), 'utf8'));

test('intro destinations match the public GGG / Realms / ICP sites', () => {
  assert.equal(INTRO_LINKS.ggg, 'https://github.com/smart-social-contracts/ggg');
  assert.equal(INTRO_LINKS.realm, 'https://github.com/smart-social-contracts/ggg');
  assert.equal(INTRO_LINKS.ssc, 'https://smartsocialcontracts.org');
  assert.equal(INTRO_LINKS.ic, 'https://internetcomputer.org');
});

test('applyIntroLinks wraps tokens as new-tab anchors', () => {
  const html = applyIntroLinks('See [[ggg]] and a [[realm]].', {
    ggg: { href: INTRO_LINKS.ggg, label: 'Generalized Global Governance (GGG)' },
    realm: { href: INTRO_LINKS.realm, label: 'realm' },
  });
  assert.match(html, /href="https:\/\/github\.com\/smart-social-contracts\/ggg"/);
  assert.equal((html.match(/href="https:\/\/github\.com\/smart-social-contracts\/ggg"/g) || []).length, 2);
  assert.match(html, /target="_blank"/g);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, />Generalized Global Governance \(GGG\)</);
  assert.match(html, />realm</);
});

test('applyIntroLinks escapes untrusted template text', () => {
  const html = applyIntroLinks('<script>x</script> [[ggg]]', {
    ggg: { href: INTRO_LINKS.ggg, label: '<b>GGG</b>' },
  });
  assert.match(html, /&lt;script&gt;x&lt;\/script&gt;/);
  assert.match(html, /&lt;b&gt;GGG&lt;\/b&gt;/);
});

test('English intro copy uses link tokens for GGG and realm', () => {
  assert.match(en.tour.intro_lead, /\[\[ggg\]\]/);
  assert.match(en.tour.intro_body, /\[\[realm\]\]/);
  assert.equal(en.tour.intro_ggg, 'Generalized Global Governance (GGG)');
  assert.equal(en.tour.intro_realm, 'realm');
  assert.equal(en.tour.intro_link_ssc, 'smartsocialcontracts.org');
  assert.equal(en.tour.intro_link_ic, 'internetcomputer.org');
});

test('intro dialog wires GGG, realm, SSC, and ICP links to new tabs', () => {
	assert.match(tour, /INTRO_LINKS\.ggg/);
	assert.match(tour, /INTRO_LINKS\.realm/);
	assert.match(tour, /INTRO_LINKS\.ssc/);
	assert.match(tour, /INTRO_LINKS\.ic/);
	assert.match(tour, /target="_blank"/);
	assert.match(tour, /rel="noopener noreferrer"/);
});

test('intro footer is a single centered Next control; X still dismisses', () => {
	assert.match(tour, /tour\.intro_continue/);
	assert.match(en.tour.intro_continue, /^Next$/);
	assert.match(tour, /\.intro-actions \{[\s\S]*justify-content:\s*center/);
	assert.doesNotMatch(tour, /intro-btn-secondary/);
	assert.match(tour, /class="intro-close"/);
	assert.match(tour, /on:click=\{closeIntro\}/);
});
