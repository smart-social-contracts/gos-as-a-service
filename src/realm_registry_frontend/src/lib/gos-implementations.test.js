import assert from 'node:assert/strict';
import test from 'node:test';
import {
  GOS_IMPLEMENTATIONS,
  buildGosManifestBlock,
  getGosImplementation,
  normalizeGosDeployVersion,
  visibleWizardSteps,
  WIZARD_STEPS,
} from './gos-implementations.js';

test('registry includes realms-gos as available with realms-iframe-v1 loader', () => {
  const realms = GOS_IMPLEMENTATIONS.find((impl) => impl.id === 'realms-gos');
  assert.ok(realms);
  assert.equal(realms.available, true);
  assert.equal(realms.loaderProfile, 'realms-iframe-v1');
  assert.equal(realms.gggConformance, '1.0');
});

test('registry includes chora-gos as unavailable', () => {
  const chora = GOS_IMPLEMENTATIONS.find((impl) => impl.id === 'chora-gos');
  assert.ok(chora);
  assert.equal(chora.available, false);
  assert.equal(chora.loaderProfile, null);
  assert.equal(chora.gggConformance, null);
});

test('getGosImplementation returns matching entry or undefined', () => {
  assert.equal(getGosImplementation('realms-gos')?.name, 'Realms GOS');
  assert.equal(getGosImplementation('chora-gos')?.available, false);
  assert.equal(getGosImplementation('unknown'), undefined);
  assert.equal(getGosImplementation(), undefined);
});

test('visibleWizardSteps omits Realms-only steps for other implementations', () => {
  const realmsSteps = visibleWizardSteps('realms-gos');
  assert.deepEqual(
    realmsSteps.map((s) => s.id),
    WIZARD_STEPS.map((s) => s.id),
  );

  const choraSteps = visibleWizardSteps('chora-gos');
  assert.deepEqual(choraSteps.map((s) => s.id), [
    'platform',
    'basics',
    'branding',
    'deploy',
  ]);
});

test('buildGosManifestBlock includes correct fields for realms-gos', () => {
  const block = buildGosManifestBlock('realms-gos', '0.4.0');
  assert.equal(block.implementation, 'realms-gos');
  assert.equal(block.version, '0.4.0');
  assert.equal(block.ggg_conformance, '1.0');
  assert.equal(block.loader_profile, 'realms-iframe-v1');
});

test('buildGosManifestBlock version reflects deploy_version', () => {
  assert.equal(buildGosManifestBlock('realms-gos', '1.2.3').version, '1.2.3');
  assert.equal(buildGosManifestBlock('realms-gos', 'v0.5.1').version, '0.5.1');
  assert.equal(buildGosManifestBlock('realms-gos', 'main').version, 'main');
});

test('normalizeGosDeployVersion strips leading v and maps latest to main', () => {
  assert.equal(normalizeGosDeployVersion('v0.5.1'), '0.5.1');
  assert.equal(normalizeGosDeployVersion('latest'), 'main');
});
