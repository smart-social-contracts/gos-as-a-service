import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildRealmDeploymentManifest,
  networkInfra,
  slugify,
} from './deployment-manifest-core.js';

// CONFIG as resolved from the conductor-written /canister_ids.js of one deployment.
const TEST_CONFIG = {
  default_deploy_version: 'main',
  default_deploy_queue_network: 'local',
  casals_section: 'Deployments',
  portal_base_url: 'http://portal.localhost:8000',
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

test('casals block names the stand only (WASMs come from the stand_template)', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Main Realm', gos_implementation: 'realms-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: 'main', useCasals: true },
  );
  assert.deepEqual(manifest.casals, { section: 'Deployments', stand: 'main-realm' });
  assert.equal(manifest.deploy_version, 'main');
});

test('monad-gos still carries its gos block without casals wasm keys', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Monad GOS Realm', gos_implementation: 'monad-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: '0.4.0', useCasals: true },
  );
  assert.equal(manifest.gos.implementation, 'monad-gos');
  assert.equal(manifest.gos.loader_profile, 'monad-iframe-v1');
  assert.equal(manifest.gos.ggg_conformance, '1.0');
  assert.equal(manifest.deploy_version, '0.4.0');
  assert.equal(manifest.casals.backend_wasm_key, undefined);
  assert.equal(manifest.casals.frontend_wasm_key, undefined);
});

test('networkInfra returns null without GaaS-owned infra fields', () => {
  assert.equal(networkInfra('test', {}), null);
  assert.equal(networkInfra('staging', {}), null);
  assert.equal(networkInfra('demo', {}), null);
});

test('networkInfra includes ii_derivation_origin when configured', () => {
  const infra = networkInfra('test', { ii_derivation_origin: 'https://test.gos.earth' });
  assert.deepEqual(infra, { ii_derivation_origin: 'https://test.gos.earth' });
  assert.equal(infra.file_registry_canister_id, undefined);
  assert.equal(infra.marketplace_canister_id, undefined);
});

test('casals block omits subnet keys by default', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Auto Realm', gos_implementation: 'realms-gos', subnet_choice: 'automatic' },
    'ic',
    TEST_CONFIG,
    { useCasals: true },
  );
  assert.equal(manifest.casals.subnet, undefined);
  assert.equal(manifest.casals.subnet_type, undefined);
});

test('casals block emits subnet_type european', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'EU Realm', gos_implementation: 'realms-gos', subnet_choice: 'european' },
    'ic',
    TEST_CONFIG,
    { useCasals: true },
  );
  assert.equal(manifest.casals.subnet_type, 'european');
  assert.equal(manifest.casals.subnet, undefined);
});

test('casals block emits explicit subnet id', () => {
  const manifest = buildRealmDeploymentManifest(
    {
      name: 'Pinned Subnet Realm',
      gos_implementation: 'realms-gos',
      subnet_choice: 'other',
      subnet_id: 'abc12-xyz34-abcde-abcdef-abc',
    },
    'ic',
    TEST_CONFIG,
    { useCasals: true },
  );
  assert.equal(manifest.casals.subnet, 'abc12-xyz34-abcde-abcdef-abc');
  assert.equal(manifest.casals.subnet_type, undefined);
});

test('casals block never emits empty subnet strings', () => {
  const manifest = buildRealmDeploymentManifest(
    {
      name: 'Empty Subnet Realm',
      gos_implementation: 'realms-gos',
      subnet_choice: 'other',
      subnet_id: '   ',
    },
    'ic',
    TEST_CONFIG,
    { useCasals: true },
  );
  assert.equal(manifest.casals.subnet, undefined);
  assert.equal(manifest.casals.subnet_type, undefined);
});

test('the wizard sends no test_flags of its own — the registry stamps the environment\'s', () => {
  for (const [network, config] of [
    ['local', { ...TEST_CONFIG, can_test_mode: true }],
    ['local', TEST_CONFIG],
    ['ic', { ...TEST_CONFIG, can_test_mode: false }],
    ['staging', { ...TEST_CONFIG, can_test_mode: true }],
    ['test', { ...TEST_CONFIG, can_test_mode: true }],
  ]) {
    const manifest = buildRealmDeploymentManifest(
      { name: 'Any Realm', gos_implementation: 'realms-gos' },
      network,
      config,
      { useCasals: false },
    );
    assert.equal(manifest.test_flags, undefined, network);
    assert.equal(manifest.can_test_mode, config.can_test_mode === true ? true : undefined);
  }
});

test('federation.portal_url comes from the configured portal, never a host table', () => {
  const withPortal = buildRealmDeploymentManifest(
    { name: 'Portal Realm', slug: 'portal-realm' },
    'ic',
    { ...TEST_CONFIG, portal_base_url: 'https://gos.earth/' },
    { useCasals: false },
  );
  assert.equal(withPortal.federation.portal_url, 'https://gos.earth/r/portal-realm');

  const withoutPortal = buildRealmDeploymentManifest(
    { name: 'Portal Realm', slug: 'portal-realm' },
    'staging',
    { ...TEST_CONFIG, portal_base_url: '' },
    { useCasals: false },
  );
  assert.equal(withoutPortal.federation.portal_url, '');
  assert.equal(withoutPortal.network, 'staging');
});

test('an unknown network stays empty rather than becoming an environment', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'No Net Realm' },
    '',
    TEST_CONFIG,
    { useCasals: false },
  );
  assert.equal(manifest.network, '');
});

test('buildRealmDeploymentManifest includes founder from formData', () => {
  const manifest = buildRealmDeploymentManifest(
    {
      name: 'Founder Realm',
      gos_implementation: 'realms-gos',
      founder: 'aaaaa-aa',
    },
    'staging',
    TEST_CONFIG,
    { useCasals: false },
  );
  assert.equal(manifest.founder, 'aaaaa-aa');
});

test('buildRealmDeploymentManifest omits founder when blank', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'No Founder Realm', gos_implementation: 'realms-gos' },
    'staging',
    TEST_CONFIG,
    { useCasals: false, founder: '' },
  );
  assert.equal(manifest.founder, undefined);
});
