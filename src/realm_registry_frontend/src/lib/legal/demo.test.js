import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { isDemoEnvironment } from '../demo-environment.js';
import { demoPrivacy, demoTerms } from './demo.js';
import { PRIVACY } from './privacy.js';
import { TERMS } from './terms.js';

const here = dirname(fileURLToPath(import.meta.url));
const text = (texts) => JSON.stringify(texts);

test('the demo texts are shown on the demo portal and on staging, which shares its data, never in production', () => {
  assert.ok(isDemoEnvironment('demo'));
  assert.ok(isDemoEnvironment(' Staging '));
  assert.ok(!isDemoEnvironment('production'));
  assert.ok(!isDemoEnvironment(''));
  assert.ok(!isDemoEnvironment(undefined));
});

test('the demo privacy policy adds the demo section last, in English and Spanish', () => {
  const production = text(PRIVACY);
  const privacy = demoPrivacy(PRIVACY);
  assert.equal(text(PRIVACY), production, 'the production text is unchanged');
  for (const [locale, heading] of [['en', '7. Demo environment'], ['es', '7. Entorno de demostración']]) {
    const sections = privacy[locale].sections;
    assert.equal(sections.length, PRIVACY[locale].sections.length + 1);
    assert.equal(sections.at(-1).heading, heading);
  }
  const en = text(privacy.en);
  for (const named of ['Google Fonts', 'unpkg.com', 'OpenStreetMap', 'OpenFreeMap', 'GitHub', 'DiceBear', 'Cloudflare']) {
    assert.ok(en.includes(named), `${named} is listed`);
  }
  assert.ok(en.includes('can be read by anyone'), 'the public logs are stated');
  assert.ok(en.includes('at least once every three months'));
  assert.equal(privacy.en.lastUpdated, '2026-11-27', 'a demo page carries the date of its additions');
  assert.equal(PRIVACY.en.lastUpdated, undefined);
});

test('the demo terms open with the addendum and drop "access is by invitation"', () => {
  const terms = demoTerms(TERMS);
  assert.equal(terms.en.sections[0].heading, 'Public demo');
  assert.equal(terms.es.sections[0].heading, 'Demo pública');
  assert.ok(!text(terms.en).includes('Access is by invitation'));
  assert.ok(!text(terms.es).includes('El acceso es por invitación'));
  assert.ok(text(TERMS.en).includes('Access is by invitation'), 'production keeps it');
  assert.ok(text(terms.en).includes('You sign in with Internet Identity'), 'the rest of the paragraph stays');
});

test('the demo banner can be folded but never dismissed', () => {
  const banner = readFileSync(join(here, '../components/DemoDataBanner.svelte'), 'utf8');
  assert.match(banner, /aria-expanded=\{!collapsed\}/);
  assert.equal(banner.match(/<button/g).length, 1, 'the fold button is its only button');
  assert.doesNotMatch(banner, /dismissBanner|dismiss_label|\{#if !dismissed/);
  assert.match(banner, /href="\/privacy"/);
  assert.match(banner, /href="\/terms"/);
  assert.match(banner, /mailto:\{LEGAL_CONTACT_EMAIL\}/);
  assert.match(banner, /use:topBannerInset/, 'the page lays itself out below it');
});

test('the layout shows the demo banner instead of the test-mode one on a demo environment', () => {
  const layout = readFileSync(join(here, '../../routes/+layout.svelte'), 'utf8');
  assert.match(layout, /\{#if demoEnvironment\}\s*<DemoDataBanner \/>\s*\{:else\}\s*<TestModeBanner \/>/);
});
