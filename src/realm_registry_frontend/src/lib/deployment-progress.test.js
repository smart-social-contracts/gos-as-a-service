import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildExtensionInstallGroups,
  buildExtensionSubSteps,
  buildProvisionSubSteps,
  computeDeploymentPercent,
  computeDeploymentUnits,
  deploymentFinishedWithErrors,
  getDeploymentProgress,
  isAutoRetryingJob,
  isPermissionBlockedError,
  isStalledJob,
  withLiveProgressTiming,
} from './deployment-progress.js';

test('completed job is 100%', () => {
  assert.equal(
    computeDeploymentPercent({ status: 'completed', raw_status: 'completed' }, null),
    100,
  );
});

// A partially installed realm still reaches status 'completed' — the installer
// registers it and records the failure in `error`. Reporting that as a finished
// deployment is how a realm shipped without any of its dashboards.
const PARTIAL_JOB = {
  status: 'completed',
  raw_status: 'completed',
  backend_canister_id: 'icuo5-5aaaa-aaaac-bfrxa-cai',
  frontend_canister_id: 'ifvij-qyaaa-aaaac-bfrxq-cai',
  assets_verified: 1,
  wasm_verified: 1,
  expected_step_count: 18,
  error: "partial extension install (1 failed): syntropia: module 'ast' has no attribute 'parse'",
};

const PARTIAL_TASK = { total_count: 18, completed_count: 17, steps: [] };

test('deploymentFinishedWithErrors distinguishes a clean completion from a partial one', () => {
  assert.equal(deploymentFinishedWithErrors(PARTIAL_JOB), true);
  assert.equal(
    deploymentFinishedWithErrors({ status: 'completed', raw_status: 'completed', error: '' }),
    false,
  );
  assert.equal(
    deploymentFinishedWithErrors({ status: 'extensions', raw_status: 'extensions', error: 'x' }),
    false,
  );
});

test('completed job with a failed step is not 100%', () => {
  const percent = computeDeploymentPercent(PARTIAL_JOB, PARTIAL_TASK);
  assert.ok(percent < 100, `expected under 100%, got ${percent}%`);
  assert.ok(percent > 50, `expected most of the work counted, got ${percent}%`);
});

test('completed job with a failed step reports as failed, not complete', () => {
  const progress = getDeploymentProgress(PARTIAL_JOB, { deployTask: PARTIAL_TASK });

  assert.equal(progress.isComplete, false);
  assert.equal(progress.isFailed, true);
  assert.equal(progress.currentLabel, 'Failed');
  assert.match(progress.currentDescription, /syntropia/);
  assert.equal(progress.stages.find((s) => s.id === 'complete')?.state, 'upcoming');
});

test('completed job with a failed step blames the stage that actually failed', () => {
  const progress = getDeploymentProgress(PARTIAL_JOB, { deployTask: PARTIAL_TASK });

  assert.equal(progress.stages.find((s) => s.id === 'extensions')?.state, 'failed');
  assert.equal(progress.stages.find((s) => s.id === 'verify')?.state, 'done');
});

test('cleanly completed job is still reported as complete', () => {
  const progress = getDeploymentProgress(
    { ...PARTIAL_JOB, error: '' },
    { deployTask: { total_count: 18, completed_count: 18, steps: [] } },
  );

  assert.equal(progress.isComplete, true);
  assert.equal(progress.isFailed, false);
  assert.equal(progress.percent, 100);
  assert.equal(progress.stages.find((s) => s.id === 'complete')?.state, 'done');
});

test('provisioning with backend only is well below old fixed 28%', () => {
  const job = {
    status: 'provisioning',
    raw_status: 'provisioning',
    backend_canister_id: 'epc7x-syaaa-aaaac-bfq3q-cai',
    frontend_canister_id: '',
    assets_verified: 0,
    wasm_verified: 1,
    expected_step_count: 33,
  };
  const percent = computeDeploymentPercent(job, null);
  assert.ok(percent < 20, `expected under 20%, got ${percent}%`);
});

test('provisioning with backend and frontend is mid provision range', () => {
  const job = {
    status: 'provisioning',
    raw_status: 'provisioning',
    backend_canister_id: 'abc',
    frontend_canister_id: 'def',
    assets_verified: 0,
    expected_step_count: 10,
  };
  const percent = computeDeploymentPercent(job, null);
  assert.ok(percent >= 20 && percent <= 32, `expected 20-32%, got ${percent}%`);
});

test('provisioning with assets verified scores higher than canisters-only', () => {
  const base = {
    status: 'provisioning',
    raw_status: 'provisioning',
    backend_canister_id: 'abc',
    frontend_canister_id: 'def',
    expected_step_count: 10,
  };
  const withoutAssets = computeDeploymentPercent({ ...base, assets_verified: 0 }, null);
  const withAssets = computeDeploymentPercent(
    { ...base, assets_verified: 1, wasm_verified: 1 },
    null,
  );
  assert.ok(withAssets > withoutAssets);
});

test('extension steps increase percent proportionally', () => {
  const job = {
    status: 'extensions',
    raw_status: 'extensions',
    backend_canister_id: 'abc',
    frontend_canister_id: 'def',
    assets_verified: 1,
    wasm_verified: 1,
    expected_step_count: 10,
  };
  const early = computeDeploymentPercent(job, { total_count: 10, completed_count: 2, steps: [] });
  const later = computeDeploymentPercent(job, { total_count: 10, completed_count: 8, steps: [] });
  assert.ok(later > early);
  assert.ok(early >= 42 && later <= 92);
});

test('withLiveProgressTiming ticks total and active stage duration', () => {
  const now = 1_700_000_000_000;
  const progress = getDeploymentProgress(
    {
      status: 'provisioning',
      raw_status: 'provisioning',
      created_at: (now - 125000) / 1000,
      backend_canister_id: 'abc',
    },
    null,
  );
  const live = withLiveProgressTiming(progress, now, { 1: now - 45000 });
  assert.equal(live.totalDurationLabel, '2m 5s');
  const activeStage = live.stages.find((s) => s.state === 'active');
  assert.equal(activeStage?.durationLabel, '45s');
});

test('getDeploymentProgress exposes provision and extension sub-steps', () => {
  const progress = getDeploymentProgress(
    {
      status: 'provisioning',
      raw_status: 'provisioning',
      backend_canister_id: 'abc',
      frontend_canister_id: '',
      assets_verified: 0,
    },
    null,
  );
  assert.ok(progress.provisionSubSteps.length >= 3);
  assert.equal(progress.provisionSubSteps[0].state, 'done');
  assert.equal(progress.provisionSubSteps[1].state, 'active');

  const extProgress = getDeploymentProgress(
    {
      status: 'extensions',
      raw_status: 'extensions',
      backend_canister_id: 'abc',
      frontend_canister_id: 'def',
      assets_verified: 1,
      wasm_verified: 1,
    },
    {
      deployTask: {
        total_count: 2,
        completed_count: 1,
        steps: [
          { idx: 0, kind: 'grant_frontend_access', label: 'grant_frontend_access', status: 'completed' },
          { idx: 1, kind: 'extension', label: 'public_dashboard', status: 'running' },
        ],
      },
    },
  );
  assert.equal(extProgress.extensionTotal, 2);
  assert.equal(extProgress.extensionCompleted, 1);
  assert.equal(extProgress.subSteps.length, 2);
  assert.match(extProgress.currentDescription, /1\/2/);
});

test('ui in_progress status does not mask raw extensions stage', () => {
  const progress = getDeploymentProgress(
    {
      status: 'in_progress',
      raw_status: 'extensions',
      backend_canister_id: 'abc',
      frontend_canister_id: 'def',
      assets_verified: 1,
      wasm_verified: 1,
      expected_step_count: 18,
    },
    {
      deployTask: { total_count: 18, completed_count: 2, steps: [] },
    },
  );
  assert.equal(progress.currentLabel, 'Installing extensions');
  assert.notEqual(progress.stages[0].state, 'active');
  assert.equal(progress.stages.find((s) => s.id === 'extensions')?.state, 'active');
});

test('buildExtensionInstallGroups separates setup, extensions, and codex', () => {
  const groups = buildExtensionInstallGroups({
    steps: [
      { kind: 'configure_canister_ids', label: 'configure_canister_ids', status: 'completed' },
      { kind: 'grant_frontend_access', label: 'grant_frontend_access', status: 'completed' },
      { kind: 'extension', label: 'public_dashboard', status: 'completed' },
      { kind: 'extension', label: 'member_dashboard', status: 'running' },
      { kind: 'codex', label: 'syntropia', status: 'pending' },
    ],
  });

  assert.equal(groups.length, 3);
  assert.equal(groups[0].label, 'Setup');
  assert.equal(groups[0].completed, 2);
  assert.equal(groups[1].label, 'Extensions');
  assert.equal(groups[1].completed, 1);
  assert.equal(groups[1].steps[1].label, 'member_dashboard');
  assert.equal(groups[1].steps[1].statusLabel, 'In progress');
  assert.equal(groups[2].label, 'Codex');
  assert.equal(groups[2].steps[0].label, 'syntropia');
});

test('buildExtensionSubSteps expands codex dependencies when no extension steps exist', () => {
  const steps = buildExtensionSubSteps(
    {
      steps: [
        { kind: 'grant_frontend_access', label: 'grant_frontend_access', status: 'completed' },
        { kind: 'codex', label: 'syntropia', status: 'completed' },
      ],
    },
    ['access_manager', 'member_manager', 'zone_selector'],
  );

  const extensions = steps.filter((step) => step.group === 'extension');
  assert.equal(extensions.length, 3);
  assert.equal(extensions[0].label, 'access_manager');
  assert.equal(extensions[0].statusLabel, 'Installed');
  assert.equal(extensions[2].statusLabel, 'Installed');
});

const RATE_LIMIT =
  'Casals create_canister rate-limited: too many requests in the last window, retry later.';

test('failed job headline is Failed and is not mid-progress healthy', () => {
  const duplicated = `${RATE_LIMIT}${RATE_LIMIT}`;
  const progress = getDeploymentProgress({
    status: 'failed',
    raw_status: 'failed',
    created_at: 1_700_000_000,
    completed_at: 1_700_000_080,
    backend_canister_id: 'abc',
    frontend_canister_id: 'def',
    assets_verified: 1,
    wasm_verified: 1,
    expected_step_count: 10,
    error: duplicated,
  });

  assert.equal(progress.currentLabel, 'Failed');
  assert.equal(progress.isFailed, true);
  assert.equal(progress.isActive, false);
  assert.equal(progress.isAutoRetrying, false);
  assert.equal(progress.error, RATE_LIMIT);
  assert.equal(progress.currentDescription, RATE_LIMIT);
  assert.equal(progress.percent, 42);
});

test('auto-reopened job says Retrying automatically and keeps one copy of the last error', () => {
  const createdAt = 1_700_000_000;
  const failedAt = 1_700_003_360;
  const attemptStart = 1_700_003_360_000;
  const now = attemptStart + 8000;
  const realNow = Date.now;
  Date.now = () => now;
  try {
    const job = {
      status: 'provisioning',
      raw_status: 'provisioning',
      created_at: createdAt,
      completed_at: failedAt,
      error: `${RATE_LIMIT}\n\n${RATE_LIMIT}`,
      backend_canister_id: '',
      frontend_canister_id: '',
    };
    const progress = getDeploymentProgress(job, {
      attemptMemory: {
        lastError: RATE_LIMIT,
        failedAtMs: failedAt * 1000,
        attemptStartedAtMs: attemptStart,
        autoRetrying: true,
      },
      attemptStartedAtMs: attemptStart,
    });

    assert.equal(isAutoRetryingJob(job, { autoRetrying: true, lastError: RATE_LIMIT }), true);
    assert.equal(progress.currentLabel, 'Retrying automatically');
    assert.equal(progress.isAutoRetrying, true);
    assert.equal(progress.isFailed, false);
    assert.equal(progress.isActive, true);
    assert.equal(progress.error, RATE_LIMIT);
    assert.equal(progress.currentDescription, RATE_LIMIT);
    assert.equal(progress.startedAtMs, createdAt * 1000);
    assert.equal(progress.attemptStartedAtMs, attemptStart);
    assert.equal(progress.totalDurationLabel, '8s');
    const queue = progress.stages.find((s) => s.id === 'queue');
    assert.ok(queue?.durationMs != null);
    assert.ok(queue.durationMs <= 8000, `queue duration should be this attempt, got ${queue.durationMs}`);
  } finally {
    Date.now = realNow;
  }
});

test('auto-retry is detected from leftover completed_at on the same job_id', () => {
  const job = {
    status: 'provisioning',
    raw_status: 'provisioning',
    created_at: 1_700_000_000,
    completed_at: 1_700_003_360,
    error: RATE_LIMIT,
  };
  assert.equal(isAutoRetryingJob(job), true);
  const progress = getDeploymentProgress(job);
  assert.equal(progress.currentLabel, 'Retrying automatically');
  assert.equal(progress.startedAtMs, 1_700_000_000_000);
});

test('withLiveProgressTiming uses this-attempt start, not first enqueue', () => {
  const now = 1_700_000_008_000;
  const progress = getDeploymentProgress(
    {
      status: 'provisioning',
      raw_status: 'provisioning',
      created_at: (now - 56 * 60 * 1000) / 1000,
      completed_at: (now - 8000) / 1000,
      error: RATE_LIMIT,
    },
    { attemptStartedAtMs: now - 8000 },
  );
  const live = withLiveProgressTiming(progress, now, { 1: now - 8000 });
  assert.equal(live.totalDurationLabel, '8s');
  const activeStage = live.stages.find((s) => s.state === 'active');
  assert.equal(activeStage?.durationLabel, '8s');
});

// job_20260828152332_870e on test.gos.earth: the installer was refused
// `grant_permission` on the realm's asset canister (it holds no
// ManagePermissions there, by design), the heartbeat reopened the job, and the
// card said "Retrying automatically" while every retry failed the same way.
const PERMISSION_BLOCK_ERROR =
  'realm bootstrap failed (1 failed): grant_frontend_access: realm backend ' +
  'pxip5-cyaaa-aaaae-ag3dq-cai does not hold Commit on frontend asset canister ' +
  'o2glt-nqaaa-aaaae-ag3ea-cai, and the installer cannot grant it: it holds no ' +
  'ManagePermissions there.';

test('a permission-blocked job is never labelled Retrying automatically', () => {
  const job = {
    status: 'provisioning',
    raw_status: 'provisioning',
    created_at: 1_700_000_000,
    completed_at: 1_700_003_360,
    backend_canister_id: 'pxip5-cyaaa-aaaae-ag3dq-cai',
    frontend_canister_id: 'o2glt-nqaaa-aaaae-ag3ea-cai',
    error: PERMISSION_BLOCK_ERROR,
  };

  assert.equal(isPermissionBlockedError(PERMISSION_BLOCK_ERROR), true);
  const progress = getDeploymentProgress(job, {
    attemptMemory: { lastError: PERMISSION_BLOCK_ERROR, autoRetrying: true },
  });
  assert.equal(progress.isBlocked, true);
  assert.equal(progress.isAutoRetrying, false);
  assert.equal(progress.currentLabel, 'Blocked');
  assert.equal(progress.currentDescription, PERMISSION_BLOCK_ERROR);
});

test('a failed permission-blocked job still reads as failed', () => {
  const progress = getDeploymentProgress({
    status: 'failed',
    raw_status: 'failed',
    created_at: 1_700_000_000,
    completed_at: 1_700_003_360,
    error: PERMISSION_BLOCK_ERROR,
  });
  assert.equal(progress.currentLabel, 'Failed');
  assert.equal(progress.isFailed, true);
  assert.equal(progress.isBlocked, true);
});

test('a transient failure is still retryable and not blocked', () => {
  const job = {
    status: 'provisioning',
    raw_status: 'provisioning',
    created_at: 1_700_000_000,
    completed_at: 1_700_003_360,
    error: RATE_LIMIT,
  };
  const progress = getDeploymentProgress(job);
  assert.equal(isPermissionBlockedError(RATE_LIMIT), false);
  assert.equal(progress.isBlocked, false);
  assert.equal(progress.currentLabel, 'Retrying automatically');
});

test('a clean run is not blocked', () => {
  const progress = getDeploymentProgress({ status: 'extensions', raw_status: 'extensions' });
  assert.equal(progress.isBlocked, false);
});

// Live zombie shape: job_20260828152332_870e sat in `extensions` with a
// leftover completed_at because its deploy task had been hijacked by another
// realm's task of the same name. Nothing was re-driving it, yet the card read
// "Retrying automatically 42%".
const STRANDED_JOB = {
  status: 'extensions',
  raw_status: 'extensions',
  created_at: 1_787_930_619,
  completed_at: 1_787_931_998,
  backend_canister_id: 'pxip5-cyaaa-aaaae-ag3dq-cai',
  frontend_canister_id: 'o2glt-nqaaa-aaaae-ag3ea-cai',
  assets_verified: 1,
  wasm_verified: 1,
  expected_step_count: 3,
  error: '',
};

test('a job stranded past provisioning reads as stalled, not retrying', () => {
  assert.equal(isStalledJob(STRANDED_JOB), true);
  assert.equal(isAutoRetryingJob(STRANDED_JOB), false);

  const progress = getDeploymentProgress(STRANDED_JOB);
  assert.equal(progress.isStalled, true);
  assert.equal(progress.isAutoRetrying, false);
  assert.equal(progress.currentLabel, 'Stalled');
  assert.match(progress.currentDescription, /not retrying/);
});

test('session memory cannot resurrect "Retrying automatically" for a stalled job', () => {
  const progress = getDeploymentProgress(STRANDED_JOB, {
    attemptMemory: { autoRetrying: true, lastError: RATE_LIMIT },
  });
  assert.equal(progress.isAutoRetrying, false);
  assert.equal(progress.currentLabel, 'Stalled');
});

test('a job still in a re-drivable phase keeps the retry label', () => {
  const job = { ...STRANDED_JOB, status: 'provisioning', raw_status: 'provisioning' };
  assert.equal(isStalledJob(job), false);
  assert.equal(isAutoRetryingJob(job), true);
  assert.equal(getDeploymentProgress(job).currentLabel, 'Retrying automatically');
});

test('a first-attempt job in extensions is neither stalled nor retrying', () => {
  const job = { ...STRANDED_JOB, completed_at: 0 };
  assert.equal(isStalledJob(job), false);
  const progress = getDeploymentProgress(job);
  assert.equal(progress.isStalled, false);
  assert.equal(progress.currentLabel, 'Installing extensions');
});
