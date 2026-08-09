import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildRealmDeploymentManifest,
  slugify,
} from './deployment-manifest-core.js';

const TEST_CONFIG = {
  default_deploy_version: 'main',
  default_deploy_queue_network: 'staging',
  casals_section: 'Deployments',
  portal_base_url: 'https://staging.gos.earth',
};

test('buildRealmDeploymentManifest omits codex, token, and branding', () => {
  const manifest = buildRealmDeploymentManifest(
    {
      name: 'Test Realm',
      slug: 'test-realm',
      gos_implementation: 'realms-gos',
      deploy_version: '0.4.0',
      codex_package_name: 'syntropia',
      token_mode: 'new',
      token_name: 'Test Token',
      token_symbol: 'TST',
    },
    'staging',
    TEST_CONFIG,
    { deployVersion: '0.4.0', useCasals: false },
  );

  assert.equal(manifest.name, 'Test Realm');
  assert.equal(manifest.network, 'staging');
  assert.equal(manifest.deploy_version, '0.4.0');
  assert.equal(manifest.gos.implementation, 'realms-gos');
  assert.equal(manifest.realm.name, 'Test Realm');
  assert.equal(manifest.federation.slug, 'test-realm');
  assert.equal(manifest.realm.codex, undefined);
  assert.equal(manifest.realm.token, undefined);
  assert.equal(manifest.branding, undefined);
});

test('buildRealmDeploymentManifest slugifies custom slug for federation', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'My Realm', slug: 'Custom_Slug Name!' },
    'demo',
    TEST_CONFIG,
    { useCasals: false },
  );

  assert.equal(manifest.federation.slug, slugify('Custom_Slug Name!'));
});

test('casals wasm keys always pin the channel (main must not collapse to bare family)', () => {
  const mainManifest = buildRealmDeploymentManifest(
    { name: 'Main Realm', gos_implementation: 'realms-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: 'main', useCasals: true },
  );
  assert.equal(mainManifest.casals.backend_wasm_key, 'realm-backend@main');
  assert.equal(mainManifest.casals.frontend_wasm_key, 'realm-assets@main');

  const pinnedManifest = buildRealmDeploymentManifest(
    { name: 'Pinned Realm', gos_implementation: 'realms-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: '0.4.0', useCasals: true },
  );
  assert.equal(pinnedManifest.casals.backend_wasm_key, 'realm-backend@0.4.0');
  assert.equal(pinnedManifest.casals.frontend_wasm_key, 'realm-assets@0.4.0');
});
