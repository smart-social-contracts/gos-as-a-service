import assert from 'node:assert/strict';
import test from 'node:test';
import { LEGAL_CONTACT_EMAIL } from './legal-info.js';
import { PRIVACY } from './privacy.js';
import { TERMS } from './terms.js';

const MAX_WORDS_PER_PAGE = 900;

function wordCount(text) {
  return text.sections
    .flatMap((section) => [section.heading, ...section.paragraphs])
    .join(' ')
    .split(/\s+/).length;
}

for (const [name, texts] of [['terms', TERMS], ['privacy', PRIVACY]]) {
  test(`${name}: Spanish has the same sections as English`, () => {
    assert.equal(texts.es.sections.length, texts.en.sections.length);
  });

  test(`${name}: each text stays short and names the contact address`, () => {
    for (const text of Object.values(texts)) {
      assert.ok(wordCount(text) <= MAX_WORDS_PER_PAGE);
      assert.ok(JSON.stringify(text).includes(LEGAL_CONTACT_EMAIL));
    }
  });
}
