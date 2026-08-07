import assert from 'node:assert/strict';
import test from 'node:test';
import { brandingAssetsFromManifest } from './deployment-manifest-view.js';

const manifest = {
  branding: {
    namespace: 'branding-testsyntropia1-abc12345',
    file_registry_canister_id: 'fr-canister',
    files: {
      '/custom/logo.png': 'logo.png',
      '/custom/background.png': 'background.png',
    },
  },
};

test('branding prefers registry URLs while extensions are running', () => {
  const assets = brandingAssetsFromManifest(manifest, {
    frontendCanisterId: 'fe-canister',
    rawStatus: 'extensions',
  });
  assert.equal(assets.length, 2);
  assert.match(assets[0].primaryUrl, /^https:\/\/fr-canister/);
  assert.equal(assets[0].primarySource, 'registry');
});

test('branding prefers realm URLs after registration', () => {
  const assets = brandingAssetsFromManifest(manifest, {
    frontendCanisterId: 'fe-canister',
    rawStatus: 'completed',
  });
  assert.match(assets[0].primaryUrl, /^https:\/\/fe-canister/);
  assert.equal(assets[0].primarySource, 'realm');
});
