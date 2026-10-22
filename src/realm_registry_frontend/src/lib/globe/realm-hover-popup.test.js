import test from 'node:test';
import assert from 'node:assert/strict';

import { buildMarkerHoverPopupHtml } from './realm-hover-popup.js';

const translate = (key) => key;
const point = { realmName: 'Harbour Commons', stage: 'alpha', users: 12, location: 'North Quay' };

test('the popup shows the realm photo and its credit on top', () => {
  const html = buildMarkerHoverPopupHtml(point, translate, {
    url: 'https://fr.icp0.io/listings/harbour-commons/background.jpg?v=abc&x=1',
    credit: 'Photo: A. <Author>, CC BY 4.0, Wikimedia Commons',
  });
  assert.match(html, /class="realm-hover-card has-photo"/);
  assert.match(html, /<img class="realm-hover-photo" src="https:\/\/fr\.icp0\.io\/listings\/harbour-commons\/background\.jpg\?v=abc&amp;x=1" alt="" \/>/);
  assert.match(html, /Photo: A\. &lt;Author&gt;, CC BY 4\.0/);
  assert.ok(html.indexOf('realm-hover-photo') < html.indexOf('realm-hover-title'));
});

test('the popup counts the realm\'s users in total, not those in the zone', () => {
  const html = buildMarkerHoverPopupHtml({ ...point, users: 12, totalUsers: 4200 }, (key, opts) =>
    `${key}:${opts?.values?.count ?? ''}`
  );
  assert.match(html, /globe\.popup_total_users:4,?200/);
  assert.doesNotMatch(html, /users_in_zone/);
});

test('the popup has no photo without an https one', () => {
  for (const photo of [null, { url: '' }, { url: 'http://fr.icp0.io/a.jpg' }, { url: 'javascript:alert(1)' }]) {
    const html = buildMarkerHoverPopupHtml(point, translate, photo);
    assert.doesNotMatch(html, /realm-hover-photo|has-photo|<img/);
    assert.match(html, /Harbour Commons/);
  }
});
