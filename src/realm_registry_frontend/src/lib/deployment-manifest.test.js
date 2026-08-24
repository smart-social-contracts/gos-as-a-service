import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildRealmDeploymentManifest,
  networkInfra,
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

test('monad-gos casals wasm keys use monad artifact families', () => {
  const mainManifest = buildRealmDeploymentManifest(
    { name: 'Monad GOS Realm', gos_implementation: 'monad-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: 'main', useCasals: true },
  );
  assert.equal(mainManifest.gos.implementation, 'monad-gos');
  assert.equal(mainManifest.gos.loader_profile, 'monad-iframe-v1');
  assert.equal(mainManifest.gos.ggg_conformance, '1.0');
  assert.equal(mainManifest.casals.backend_wasm_key, 'monad-backend@main');
  assert.equal(mainManifest.casals.frontend_wasm_key, 'monad-assets@main');

  const pinnedManifest = buildRealmDeploymentManifest(
    { name: 'Monad GOS Pinned', gos_implementation: 'monad-gos' },
    'staging',
    TEST_CONFIG,
    { deployVersion: '0.4.0', useCasals: true },
  );
  assert.equal(pinnedManifest.casals.backend_wasm_key, 'monad-backend@0.4.0');
  assert.equal(pinnedManifest.casals.frontend_wasm_key, 'monad-assets@0.4.0');
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

test('staging still gets test_flags when can_test_mode is true', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Staging Realm', gos_implementation: 'realms-gos' },
    'staging',
    { ...TEST_CONFIG, can_test_mode: true },
    { useCasals: false },
  );
  assert.equal(manifest.can_test_mode, true);
  assert.equal(manifest.test_flags.test_mode, true);
  assert.equal(manifest.test_flags.ii_bypass, false);
});

test('staging still gets test_flags when can_test_mode is undefined', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Compat Realm', gos_implementation: 'realms-gos' },
    'staging',
    TEST_CONFIG,
    { useCasals: false },
  );
  assert.equal(manifest.can_test_mode, undefined);
  assert.equal(manifest.test_flags.test_mode, true);
});

test('production GaaS omits test_flags when can_test_mode is false', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Prod Realm', gos_implementation: 'realms-gos' },
    'staging',
    { ...TEST_CONFIG, can_test_mode: false },
    { useCasals: false },
  );
  assert.equal(manifest.test_flags, undefined);
});

test('test network gets full test flag set when can_test_mode is true', () => {
  const manifest = buildRealmDeploymentManifest(
    { name: 'Test Realm', gos_implementation: 'realms-gos' },
    'test',
    { ...TEST_CONFIG, can_test_mode: true },
    { useCasals: false },
  );
  assert.equal(manifest.can_test_mode, true);
  assert.equal(manifest.test_flags.test_mode, true);
  assert.equal(manifest.test_flags.user_self_registration, true);
  assert.equal(manifest.test_flags.demo_data, true);
  assert.equal(manifest.test_flags.ii_bypass, true);
  assert.equal(manifest.test_flags.skip_terms, true);
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
