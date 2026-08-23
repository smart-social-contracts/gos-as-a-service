import assert from 'node:assert/strict';
import test from 'node:test';
import { brandingLogoUrls, BRANDING_LOGO_PATHS } from './realm-utils.js';

test('brandingLogoUrls is empty without a frontend canister', () => {
  assert.deepEqual(brandingLogoUrls(''), []);
  assert.deepEqual(brandingLogoUrls(null), []);
  assert.deepEqual(brandingLogoUrls(undefined), []);
});

test('brandingLogoUrls probes custom logo then root logo', () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  assert.deepEqual(brandingLogoUrls(id), [
    `https://${id}.icp0.io/custom/logo.png`,
    `https://${id}.icp0.io/logo.png`
  ]);
  assert.deepEqual(BRANDING_LOGO_PATHS, ['/custom/logo.png', '/logo.png']);
});
