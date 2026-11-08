import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const LOCALES = ['en', 'es', 'de', 'fr', 'it', 'zh-CN'];
const load = (locale) =>
  JSON.parse(readFileSync(new URL(`./i18n/locales/${locale}.json`, import.meta.url), 'utf8'));
const locales = Object.fromEntries(LOCALES.map((locale) => [locale, load(locale)]));

const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

// Keys the page builds at run time: assistantDeploy.${...}
const DYNAMIC_KEYS = [
  'unavailable_body',
  'invalid_link',
  'load_error',
  'proof_failed',
  'action_error',
  'claim_busy',
  'claim_gone',
];

test('every portal language has the same assistantDeploy messages as English', () => {
  const english = Object.keys(locales.en.assistantDeploy);
  for (const locale of LOCALES) {
    assert.deepEqual(Object.keys(locales[locale].assistantDeploy), english, locale);
  }
});

test('a translation keeps the placeholders of the English message', () => {
  for (const [key, english] of Object.entries(locales.en.assistantDeploy)) {
    for (const locale of LOCALES) {
      assert.deepEqual(placeholders(locales[locale].assistantDeploy[key]), placeholders(english), `${locale}.${key}`);
    }
  }
});

test('no translation is left empty or copied from English by mistake', () => {
  for (const locale of LOCALES.filter((l) => l !== 'en')) {
    const same = Object.entries(locales[locale].assistantDeploy)
      .filter(([key, text]) => !text.trim() || (text === locales.en.assistantDeploy[key] && text.length > 24))
      .map(([key]) => key);
    assert.deepEqual(same, [], locale);
  }
});

test('the consent page sentence exists in every language', () => {
  for (const locale of LOCALES) {
    assert.ok(locales[locale].mcpConsent.prepare_desc.length > 10, locale);
  }
});

test('every assistantDeploy message the page and the card use exists', () => {
  const sources = ['../routes/deploy-gos/+page.svelte', './components/AssistantRequestCard.svelte'].map((path) =>
    readFileSync(new URL(path, import.meta.url), 'utf8'),
  );
  const used = new Set(DYNAMIC_KEYS);
  for (const source of sources) {
    for (const [, key] of source.matchAll(/assistantDeploy\.([a-z_]+)/g)) used.add(key);
  }
  const missing = [...used].filter((key) => !(key in locales.en.assistantDeploy));
  assert.deepEqual(missing, []);
});
