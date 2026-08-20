import assert from 'node:assert/strict';
import test from 'node:test';
import {
  GOS_IMPLEMENTATIONS,
  buildGosImplementationsFromEnv,
  buildGosManifestBlock,
  getGosImplementation,
  normalizeGosDeployVersion,
  resolveGosImplementations,
  shouldShowVersionPicker,
  soleDeployVersionOption,
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

test('registry includes chora-gos as available with chora-iframe-v1 loader', () => {
  const chora = GOS_IMPLEMENTATIONS.find((impl) => impl.id === 'chora-gos');
  assert.ok(chora);
  assert.equal(chora.available, true);
  assert.equal(chora.loaderProfile, 'chora-iframe-v1');
  assert.equal(chora.gggConformance, '1.0');
});

test('getGosImplementation returns matching entry or undefined', () => {
  assert.equal(getGosImplementation('realms-gos')?.name, 'Realms GOS');
  assert.equal(getGosImplementation('chora-gos')?.available, true);
  assert.equal(getGosImplementation('unknown'), undefined);
  assert.equal(getGosImplementation(), undefined);
});

test('visibleWizardSteps returns platform-only wizard flow', () => {
  const steps = visibleWizardSteps('realms-gos');
  assert.deepEqual(steps.map((s) => s.id), ['platform', 'basics', 'deploy']);

  const choraSteps = visibleWizardSteps('chora-gos');
  assert.deepEqual(choraSteps.map((s) => s.id), ['platform', 'basics', 'deploy']);
});

test('buildGosManifestBlock includes correct fields for realms-gos', () => {
  const block = buildGosManifestBlock('realms-gos', '0.4.0');
  assert.equal(block.implementation, 'realms-gos');
  assert.equal(block.version, '0.4.0');
  assert.equal(block.ggg_conformance, '1.0');
  assert.equal(block.loader_profile, 'realms-iframe-v1');
});

test('buildGosManifestBlock includes correct fields for chora-gos', () => {
  const block = buildGosManifestBlock('chora-gos', '0.4.0');
  assert.equal(block.implementation, 'chora-gos');
  assert.equal(block.version, '0.4.0');
  assert.equal(block.ggg_conformance, '1.0');
  assert.equal(block.loader_profile, 'chora-iframe-v1');
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

test('shouldShowVersionPicker is true only when multiple options exist', () => {
  assert.equal(shouldShowVersionPicker([]), false);
  assert.equal(shouldShowVersionPicker([{ value: 'main', label: 'main' }]), false);
  assert.equal(
    shouldShowVersionPicker([
      { value: 'main', label: 'main' },
      { value: '0.4.0', label: '0.4.0' },
    ]),
    true,
  );
  assert.equal(shouldShowVersionPicker(null), false);
});

test('soleDeployVersionOption returns the single option or null', () => {
  const only = { value: 'main', label: 'main (latest from file registry)' };
  assert.deepEqual(soleDeployVersionOption([only]), only);
  assert.equal(soleDeployVersionOption([]), null);
  assert.equal(
    soleDeployVersionOption([
      { value: 'main', label: 'main' },
      { value: '0.4.0', label: '0.4.0' },
    ]),
    null,
  );
});

test('buildGosImplementationsFromEnv maps gaas-env gos entries', () => {
  const list = buildGosImplementationsFromEnv([
    {
      implementation: 'realms-gos',
      version: 'v0.3.1',
      loader_profile: 'realms-iframe-v1',
      available: true,
    },
  ]);
  assert.equal(list.length, 1);
  assert.equal(list[0].id, 'realms-gos');
  assert.equal(list[0].available, true);
  assert.equal(list[0].loaderProfile, 'realms-iframe-v1');
});

test('resolveGosImplementations falls back to defaults without gaas-env', () => {
  const list = resolveGosImplementations(undefined);
  assert.equal(list.length, 2);
  assert.ok(list.some((impl) => impl.id === 'realms-gos'));
  assert.ok(list.some((impl) => impl.id === 'chora-gos'));
});
