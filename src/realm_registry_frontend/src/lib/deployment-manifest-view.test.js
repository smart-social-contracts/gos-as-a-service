import assert from 'node:assert/strict';
import test from 'node:test';
import { brandingAssetsFromManifest, summarizeManifest } from './deployment-manifest-view.js';

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

test('summarizeManifest exposes GOS implementation and version', () => {
  const summary = summarizeManifest({
    name: 'Test',
    deploy_version: '0.4.0',
    gos: {
      implementation: 'realms-gos',
      version: '0.4.0',
      ggg_conformance: '1.0',
      loader_profile: 'realms-iframe-v1',
    },
  });

  assert.equal(summary.gosImplementation, 'realms-gos');
  assert.equal(summary.gosVersion, '0.4.0');
});
