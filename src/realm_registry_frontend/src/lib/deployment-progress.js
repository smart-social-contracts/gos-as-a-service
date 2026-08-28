import { uniqueErrorText } from './deployment-attempt-memory.js';

/** Pipeline stages shown to users (order matters). */
export const DEPLOYMENT_PIPELINE = [
  {
    id: 'queue',
    label: 'Queued',
    description: 'Your deployment request is in the queue.',
  },
  {
    id: 'provision',
    label: 'Creating canisters',
    description: 'Provisioning backend and frontend canisters on the Internet Computer.',
  },
  {
    id: 'verify',
    label: 'Verifying software',
    description: 'Checking that installed software matches the authorized release.',
  },
  {
    id: 'extensions',
    label: 'Installing extensions',
    description: 'Deploying codex, extensions, and realm configuration.',
  },
  {
    id: 'register',
    label: 'Registering realm',
    description: 'Recording your realm in the on-chain registry.',
  },
  {
    id: 'complete',
    label: 'Complete',
    description: 'Your realm is live.',
  },
];

const STATUS_STAGE_INDEX = {
  pending: 0,
  provisioning: 1,
  deploying: 1,
  verifying: 2,
  extensions: 3,
  registering: 4,
  completed: 5,
  failed: 5,
  failed_verification: 2,
  cancelled: 0,
};

const TERMINAL_STATUSES = new Set([
  'completed',
  'failed',
  'failed_verification',
  'cancelled',
]);

const FAILED_STATUSES = new Set(['failed', 'failed_verification', 'cancelled']);

/**
 * Failures nobody can retry their way out of: the installer was refused a
 * permission it cannot grant itself, so the deployment is waiting on a fix to
 * the platform's canister topology, not on another attempt.
 */
const PERMISSION_BLOCK_PATTERNS = [
  'managepermissions',
  'does not hold commit',
  'grant_permission failed',
  'is not a controller',
];

/**
 * True when an error means the deployment is blocked on a permission the
 * installer cannot obtain. Such a job must never be dressed up as
 * "Retrying automatically" — that hid a real permission hole for hours.
 *
 * @param {string} [error]
 * @returns {boolean}
 */
export function isPermissionBlockedError(error) {
  const text = (error || '').toLowerCase();
  if (!text) return false;
  return PERMISSION_BLOCK_PATTERNS.some((pattern) => text.includes(pattern));
}

/** True when the same job_id was reopened after a failure (heartbeat / retry). */
export function isAutoRetryingJob(job, memory = null) {
  const status = (job?.raw_status || job?.status || '').toLowerCase();
  if (!status || FAILED_STATUSES.has(status) || status === 'completed') return false;
  if (memory?.autoRetrying || memory?.lastError) return true;
  return Boolean(toTimestampMs(job?.completed_at));
}

const EXTENSIONS_STAGE_INDEX = DEPLOYMENT_PIPELINE.findIndex((s) => s.id === 'extensions');

/**
 * True when the installer finished the run but some step failed.
 *
 * A partially installed realm still reaches status `completed`: its canisters
 * exist and it is registered, so it keeps its dashboard entry and visit link.
 * The installer records what went wrong in `error` (e.g. a codex that failed
 * to install, which leaves the realm without its core extensions), and that
 * must not be presented as a finished deployment.
 *
 * @param {object} job
 * @returns {boolean}
 */
export function deploymentFinishedWithErrors(job) {
  const status = (job?.raw_status || job?.status || '').toLowerCase();
  return status === 'completed' && Boolean((job?.error || '').trim());
}

/** Relative effort per pipeline stage (queue → register). Used when we lack live observations. */
const STAGE_DURATION_WEIGHTS = [1, 3, 2, 4, 3];

/** Weighted work units for percent calculation (not wall-clock). */
const UNITS = {
  queue: 1,
  provisionBackend: 2,
  provisionFrontend: 2,
  provisionFinalize: 1,
  verify: 1,
  register: 2,
  extensionStep: 1,
};

/**
 * @param {object} job
 * @param {object|null|undefined} deployTask
 * @returns {{ completed: number, total: number, extensionTotal: number, extensionCompleted: number }}
 */
export function computeDeploymentUnits(job, deployTask) {
  const status = (job.raw_status || job.status || '').toLowerCase();
  let completed = 0;
  let total = 0;

  total += UNITS.queue;
  if (status !== 'pending') completed += UNITS.queue;

  total += UNITS.provisionBackend + UNITS.provisionFrontend + UNITS.provisionFinalize;
  if ((job.backend_canister_id || '').trim()) completed += UNITS.provisionBackend;
  if ((job.frontend_canister_id || '').trim()) completed += UNITS.provisionFrontend;
  if (Number(job.assets_verified)) completed += UNITS.provisionFinalize;

  total += UNITS.verify;
  if (Number(job.wasm_verified) && Number(job.assets_verified)) {
    completed += UNITS.verify;
  } else if (['extensions', 'registering', 'completed'].includes(status)) {
    completed += UNITS.verify;
  }

  const extensionTotal = Math.max(
    Number(deployTask?.total_count ?? 0),
    Number(job.expected_step_count ?? 0),
    Array.isArray(deployTask?.steps) ? deployTask.steps.length : 0,
  );
  total += extensionTotal * UNITS.extensionStep;

  let extensionCompleted = Number(deployTask?.completed_count ?? 0);
  if (!deployTask && ['registering', 'completed'].includes(status)) {
    extensionCompleted = extensionTotal;
  }
  extensionCompleted = Math.min(extensionCompleted, extensionTotal);
  completed += extensionCompleted * UNITS.extensionStep;

  total += UNITS.register;
  if (status === 'completed') {
    completed += UNITS.register;
  } else if (status === 'registering') {
    completed += Math.ceil(UNITS.register / 2);
  }

  return { completed, total, extensionTotal, extensionCompleted };
}

function shortId(id) {
  const s = (id || '').trim();
  return s.length > 8 ? `${s.slice(0, 5)}…` : s;
}

/**
 * Phase-based percent: each pipeline stage owns a slice of 0–100 so long
 * provisioning/extension work is visible instead of being drowned out by the
 * extension step count in the denominator.
 */
const PHASE = {
  queue: { from: 0, to: 5 },
  provision: { from: 5, to: 35 },
  verify: { from: 35, to: 42 },
  extensions: { from: 42, to: 92 },
  register: { from: 92, to: 99 },
};

function lerpPhase(phaseKey, fraction) {
  const phase = PHASE[phaseKey];
  const t = Math.max(0, Math.min(1, fraction));
  return Math.round(phase.from + t * (phase.to - phase.from));
}

/**
 * @param {object} job
 * @returns {Array<{ label: string, state: string, detail: string|null }>}
 */
export function buildProvisionSubSteps(job) {
  const backend = (job.backend_canister_id || '').trim();
  const frontend = (job.frontend_canister_id || '').trim();
  const assets = Number(job.assets_verified) === 1;
  const status = (job.raw_status || job.status || '').toLowerCase();
  const inProvision =
    status === 'provisioning' ||
    status === 'deploying' ||
    (status === 'pending' && (backend || frontend)) ||
    (!assets && !['extensions', 'registering', 'completed'].includes(status));

  const specs = [
    {
      id: 'backend',
      label: 'Backend canister',
      done: Boolean(backend),
      detail: backend ? shortId(backend) : null,
    },
    {
      id: 'frontend',
      label: 'Frontend canister & assets',
      done: Boolean(frontend) && assets,
      detail: frontend ? shortId(frontend) : null,
    },
    {
      id: 'finalize',
      label: 'Stand configuration',
      done: assets && Boolean(backend),
      detail: null,
    },
  ];

  let activeAssigned = false;
  return specs.map((spec) => {
    let state = 'upcoming';
    if (spec.done) {
      state = 'done';
    } else if (inProvision && !activeAssigned) {
      state = 'active';
      activeAssigned = true;
    }
    return {
      label: spec.label,
      state,
      detail: spec.detail,
    };
  });
}

/**
 * @param {object} job
 * @param {object|null|undefined} deployTask
 * @returns {number}
 */
export function computeDeploymentPercent(job, deployTask) {
  const status = (job.raw_status || job.status || '').toLowerCase();
  if (status === 'completed' && !deploymentFinishedWithErrors(job)) return 100;

  const backend = Boolean((job.backend_canister_id || '').trim());
  const frontend = Boolean((job.frontend_canister_id || '').trim());
  const assets = Number(job.assets_verified) === 1;
  const verified = Number(job.wasm_verified) && assets;
  const { extensionTotal, extensionCompleted } = computeDeploymentUnits(job, deployTask);

  let percent;

  if (status === 'pending' && !backend) {
    percent = lerpPhase('queue', 0.6);
  } else if (
    status === 'provisioning' ||
    status === 'deploying' ||
    (status === 'pending' && backend) ||
    (!assets && !['extensions', 'registering', 'completed', 'failed', 'failed_verification', 'cancelled'].includes(status))
  ) {
    let fraction = 0.05;
    if (backend) fraction += 0.3;
    if (frontend) fraction += 0.35;
    if (assets) fraction += 0.3;
    percent = lerpPhase('provision', fraction);
  } else if (status === 'verifying' || status === 'failed_verification') {
    percent = lerpPhase('verify', verified ? 1 : 0.4);
  } else if (status === 'extensions' || extensionTotal > 0) {
    const doneFrac = extensionTotal > 0 ? extensionCompleted / extensionTotal : 0;
    percent = lerpPhase('extensions', doneFrac);
  } else if (status === 'registering') {
    percent = lerpPhase('register', 0.55);
  } else if (verified) {
    percent = PHASE.verify.to;
  } else {
    percent = lerpPhase('queue', 1);
  }

  if (FAILED_STATUSES.has(status) || deploymentFinishedWithErrors(job)) {
    return Math.max(PHASE.queue.from, Math.min(percent, 99));
  }
  return Math.max(0, Math.min(percent, 99));
}

export function toTimestampMs(value) {
  if (value == null || value === '') return null;
  const n = typeof value === 'bigint' ? Number(value) : Number(value);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n > 1e12 ? n : n * 1000;
}

/** @param {number} ms */
export function formatDuration(ms) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return '<1s';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return remSec > 0 ? `${min}m ${remSec}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  return remMin > 0 ? `${hr}h ${remMin}m` : `${hr}h`;
}

function stageIndexForJob(job) {
  const status = (job.raw_status || job.status || '').toLowerCase();
  let index = STATUS_STAGE_INDEX[status] ?? 0;

  if (status === 'pending' && (job.backend_canister_id || job.frontend_canister_id)) {
    index = Math.max(index, 1);
  }

  return { status, index };
}

/** @param {string} state */
export function extensionStatusLabel(state) {
  switch (state) {
    case 'done':
      return 'Installed';
    case 'active':
      return 'In progress';
    case 'failed':
      return 'Failed';
    default:
      return 'Pending';
  }
}

/** @param {object} step */
function withStatusLabel(step) {
  return {
    ...step,
    statusLabel: extensionStatusLabel(step.state),
  };
}

/**
 * @param {object|null|undefined} deployTask
 * @param {string[]} [codexDependencies]
 */
export function buildExtensionSubSteps(deployTask, codexDependencies = []) {
  const steps = deployTask?.steps;
  const fromTask = !Array.isArray(steps) || !steps.length
    ? []
    : steps.map((step, index) => {
        const st = (step.status || '').toLowerCase();
        let state = 'upcoming';
        if (st === 'completed') state = 'done';
        else if (st === 'failed') state = 'failed';
        else if (st === 'running') state = 'active';

        const kind = (step.kind || '').toLowerCase();
        let label = step.label || step.kind || 'step';
        let group = 'setup';

        if (kind === 'configure_canister_ids') {
          label = 'Configure canister IDs';
        } else if (kind === 'grant_frontend_access') {
          label = 'Grant frontend access';
        } else if (kind === 'extension') {
          label = step.label || 'unknown';
          group = 'extension';
        } else if (kind === 'codex') {
          label = step.label || 'unknown';
          group = 'codex';
        }

        return withStatusLabel({
          id: `${kind}:${label}:${index}`,
          label,
          kind,
          group,
          status: st,
          error: (step.error || '').trim() || null,
          state,
        });
      });

  const hasExtensionSteps = fromTask.some((step) => step.group === 'extension');
  if (hasExtensionSteps || !codexDependencies.length) {
    return fromTask;
  }

  const codexStep = fromTask.find((step) => step.group === 'codex');
  const codexState = codexStep?.state || 'upcoming';
  const bundled = codexDependencies.map((depId, index) => {
    let state = 'upcoming';
    if (codexState === 'done') state = 'done';
    else if (codexState === 'failed') state = 'failed';
    else if (codexState === 'active') state = 'active';

    return withStatusLabel({
      id: `bundled:${depId}:${index}`,
      label: depId,
      kind: 'extension',
      group: 'extension',
      status: state === 'done' ? 'completed' : state === 'active' ? 'running' : state === 'failed' ? 'failed' : 'pending',
      error: codexStep?.error || null,
      state,
      bundled: true,
    });
  });

  const setupSteps = fromTask.filter((step) => step.group === 'setup');
  const codexSteps = fromTask.filter((step) => step.group === 'codex');
  return [...setupSteps, ...bundled, ...codexSteps];
}

/**
 * Group extension-install sub-steps for expandable UI (setup / extensions / codex).
 *
 * @param {object|null|undefined} deployTask
 * @param {string[]} [codexDependencies]
 */
export function buildExtensionInstallGroups(deployTask, codexDependencies = []) {
  const subSteps = buildExtensionSubSteps(deployTask, codexDependencies);
  if (!subSteps.length) return [];

  /** @type {Record<string, { id: string, label: string, steps: typeof subSteps }>} */
  const byGroup = {
    setup: { id: 'setup', label: 'Setup', steps: [] },
    extension: { id: 'extension', label: 'Extensions', steps: [] },
    codex: { id: 'codex', label: 'Codex', steps: [] },
  };

  for (const step of subSteps) {
    const bucket = byGroup[step.group] || byGroup.setup;
    bucket.steps.push(step);
  }

  return Object.values(byGroup)
    .filter((group) => group.steps.length > 0)
    .map((group) => ({
      ...group,
      completed: group.steps.filter((step) => step.state === 'done').length,
      total: group.steps.length,
      active: group.steps.some((step) => step.state === 'active'),
      failed: group.steps.some((step) => step.state === 'failed'),
    }));
}

function stageDescription(status, job, stage, deployTask) {
  const backend = (job.backend_canister_id || '').trim();
  const frontend = (job.frontend_canister_id || '').trim();
  const { extensionTotal, extensionCompleted } = computeDeploymentUnits(job, deployTask);

  if (status === 'provisioning') {
    const parts = [];
    if (backend) parts.push(`backend ${shortId(backend)} ready`);
    if (frontend) parts.push(`frontend ${shortId(frontend)} ready`);
    if (parts.length) {
      const tail = Number(job.assets_verified)
        ? 'Finalizing stand configuration…'
        : frontend
          ? 'Uploading frontend assets and verifying…'
          : 'Creating frontend canister…';
      return `${parts.join(', ')}. ${tail}`;
    }
    return 'Provisioning canisters via Casals on the Internet Computer.';
  }

  if (status === 'pending' && !backend && !frontend) {
    return stage.description;
  }

  if (status === 'pending' || status === 'deploying') {
    const parts = [];
    if (backend) parts.push(`backend ${shortId(backend)}`);
    if (frontend) parts.push(`frontend ${shortId(frontend)}`);
    if (parts.length) {
      return `${stage.description} (${parts.join(', ')})`;
    }
  }

  if (status === 'extensions') {
    if (extensionTotal > 0) {
      return `Installing extensions and codex (${extensionCompleted}/${extensionTotal} steps complete).`;
    }
    return 'Installing codex, extensions, and realm configuration.';
  }

  if (status === 'registering') {
    return 'Finalizing registration and settling credits.';
  }

  if (status === 'failed_verification') {
    return 'Software verification failed — the installed build did not match the expected release.';
  }

  return stage.description;
}

/**
 * @param {Array<{ id: string, state: string }>} stages
 * @param {number} totalMs
 * @param {number} terminalStageIndex - last stage that ran (inclusive)
 */
function estimateStageDurationsMs(stages, totalMs, terminalStageIndex) {
  const indices = stages
    .map((stage, i) => ({ stage, i }))
    .filter(
      ({ stage, i }) =>
        stage.id !== 'complete' &&
        i <= terminalStageIndex &&
        (stage.state === 'done' || stage.state === 'failed' || stage.state === 'active'),
    );

  if (!indices.length || totalMs <= 0) return {};

  const weights = indices.map(({ i }) => STAGE_DURATION_WEIGHTS[i] ?? 1);
  const weightSum = weights.reduce((a, b) => a + b, 0);
  const out = {};
  indices.forEach(({ i }, idx) => {
    out[i] = Math.max(0, Math.round((totalMs * weights[idx]) / weightSum));
  });
  return out;
}

/**
 * @param {Array<{ id: string, state: string }>} stages
 * @param {number} startMs
 * @param {number} endMs
 * @param {Record<number, number>|null} observedStarts - stage index → timestamp ms
 */
function resolveStageDurationsMs(stages, startMs, endMs, observedStarts) {
  const durations = {};
  const pipelineStages = stages.filter((s) => s.id !== 'complete');

  if (observedStarts && Object.keys(observedStarts).length > 0) {
    const sorted = pipelineStages
      .map((stage, i) => ({ stage, i }))
      .filter(({ stage }) => stage.state !== 'upcoming');

    for (let k = 0; k < sorted.length; k++) {
      const { i, stage } = sorted[k];
      const stageStart = observedStarts[i] ?? (k === 0 ? startMs : observedStarts[sorted[k - 1].i]);
      let stageEnd;
      if (stage.state === 'active') {
        stageEnd = endMs;
      } else {
        const next = sorted[k + 1];
        stageEnd = next ? (observedStarts[next.i] ?? endMs) : endMs;
      }
      if (stageStart && stageEnd && stageEnd >= stageStart) {
        durations[i] = stageEnd - stageStart;
      }
    }
    if (Object.keys(durations).length) return { durations, estimated: false };
  }

  const terminalStageIndex = pipelineStages.reduce(
    (max, stage, i) =>
      stage.state === 'done' || stage.state === 'failed' || stage.state === 'active'
        ? Math.max(max, i)
        : max,
    0,
  );
  return {
    durations: estimateStageDurationsMs(stages, Math.max(0, endMs - startMs), terminalStageIndex),
    estimated: true,
  };
}

/**
 * @param {object} job - installer job view or deployment row
 * @param {{ observedStageStarts?: Record<number, number>|null, deployTask?: object|null }} [options]
 * @returns {object} progress view model for UI
 */
export function getDeploymentProgress(job, options = {}) {
  const deployTask = options?.deployTask ?? null;
  const codexDependencies = options?.codexDependencies ?? [];
  const memory = options?.attemptMemory ?? null;
  const { status, index: stageIndex } = stageIndexForJob(job);
  const isTerminal = TERMINAL_STATUSES.has(status);
  const finishedWithErrors = deploymentFinishedWithErrors(job);
  const isFailed = FAILED_STATUSES.has(status) || finishedWithErrors;
  const isComplete = status === 'completed' && !finishedWithErrors;
  const lastError = uniqueErrorText(
    job.last_error || job.previous_error || job.error || memory?.lastError || '',
  );
  const isBlocked = !isComplete && isPermissionBlockedError(lastError);
  const isAutoRetrying =
    !isFailed && !isComplete && !isBlocked && isAutoRetryingJob(job, memory);

  // A run that finished with errors stalled where the work actually failed —
  // the extension/codex phase — not at the registration it went on to do.
  const activeIndex = isComplete
    ? DEPLOYMENT_PIPELINE.length - 1
    : finishedWithErrors
      ? EXTENSIONS_STAGE_INDEX
      : isFailed
        ? Math.min(stageIndex, DEPLOYMENT_PIPELINE.length - 2)
        : stageIndex;

  const currentStage = DEPLOYMENT_PIPELINE[activeIndex] || DEPLOYMENT_PIPELINE[0];
  const percent = computeDeploymentPercent(job, deployTask);
  const { extensionTotal, extensionCompleted } = computeDeploymentUnits(job, deployTask);
  const subSteps = buildExtensionSubSteps(deployTask, codexDependencies);
  const extensionInstallGroups = buildExtensionInstallGroups(deployTask, codexDependencies);
  const provisionSubSteps = buildProvisionSubSteps(job);

  const stages = DEPLOYMENT_PIPELINE.map((stage, i) => {
    let state = 'upcoming';
    if (isComplete) {
      state = 'done';
    } else if (isFailed && i === activeIndex) {
      state = 'failed';
    } else if (i < activeIndex) {
      state = 'done';
    } else if (i === activeIndex) {
      state = isFailed ? 'failed' : 'active';
    }
    return { ...stage, state };
  });

  const startedAtMs = toTimestampMs(job.created_at);
  const attemptStartedAtMs =
    options?.attemptStartedAtMs ||
    memory?.attemptStartedAtMs ||
    (isAutoRetrying ? toTimestampMs(job.completed_at) || startedAtMs : startedAtMs);
  const finishedAtMs = isFailed || isComplete ? toTimestampMs(job.completed_at) ?? Date.now() : null;
  const endMs = finishedAtMs ?? Date.now();
  const totalDurationMs =
    attemptStartedAtMs && endMs >= attemptStartedAtMs ? endMs - attemptStartedAtMs : null;

  const { durations: stageDurationMs, estimated: durationsEstimated } =
    attemptStartedAtMs != null
      ? resolveStageDurationsMs(stages, attemptStartedAtMs, endMs, options?.observedStageStarts ?? null)
      : { durations: {}, estimated: true };

  const stagesWithTiming = stages.map((stage, i) => {
    const durationMs = stageDurationMs[i];
    return {
      ...stage,
      durationMs: durationMs ?? null,
      durationLabel: durationMs != null ? formatDuration(durationMs) : '',
      durationEstimated: durationsEstimated,
    };
  });

  return {
    status,
    stageIndex: activeIndex,
    currentLabel: isComplete
      ? 'Complete'
      : isFailed
        ? 'Failed'
        : isBlocked
          ? 'Blocked'
          : isAutoRetrying
            ? 'Retrying automatically'
            : currentStage.label,
    currentDescription: isFailed || isBlocked
      ? lastError || 'Deployment failed.'
      : isAutoRetrying
        ? lastError || currentStage.description
        : stageDescription(status, job, currentStage, deployTask),
    percent,
    stages: stagesWithTiming,
    subSteps,
    extensionInstallGroups,
    provisionSubSteps,
    extensionTotal,
    extensionCompleted,
    isTerminal,
    isFailed,
    isComplete,
    isAutoRetrying,
    isBlocked,
    isActive: !isFailed && !isComplete,
    error: lastError || null,
    backendCanisterId: (job.backend_canister_id || '').trim() || null,
    frontendCanisterId: (job.frontend_canister_id || '').trim() || null,
    startedAtMs,
    attemptStartedAtMs,
    finishedAtMs,
    totalDurationMs,
    totalDurationLabel: totalDurationMs != null ? formatDuration(totalDurationMs) : '',
    durationsEstimated,
  };
}

export function getDeploymentStatusLabel(status) {
  const progress = getDeploymentProgress({ status, raw_status: status });
  if (progress.isComplete) return 'Completed';
  if (progress.isFailed) return 'Failed';
  if (progress.isActive) return progress.currentLabel;
  return status || 'Unknown';
}

/**
 * Recompute duration labels using a live clock (for ticking UI while polling).
 *
 * @param {object} progress - output of getDeploymentProgress
 * @param {number} nowMs
 * @param {Record<number, number>|null} [observedStageStarts]
 * @returns {object}
 */
export function withLiveProgressTiming(progress, nowMs, observedStageStarts = null) {
  if (!progress) return progress;

  const startedAtMs = progress.attemptStartedAtMs || progress.startedAtMs;
  const endMs = progress.finishedAtMs ?? nowMs;
  const totalDurationMs =
    startedAtMs && endMs >= startedAtMs ? endMs - startedAtMs : progress.totalDurationMs;

  const stages = (progress.stages || []).map((stage, i) => {
    if (stage.state !== 'active' && stage.state !== 'done') {
      return stage;
    }

    const stageStart =
      observedStageStarts?.[i] ??
      (i === 0 ? startedAtMs : observedStageStarts?.[i - 1]) ??
      startedAtMs;

    if (stage.state === 'active' && stageStart) {
      const durationMs = Math.max(0, nowMs - stageStart);
      return {
        ...stage,
        durationMs,
        durationLabel: formatDuration(durationMs),
        durationEstimated: false,
      };
    }

    if (stage.state === 'done' && stage.durationMs != null && !stage.durationEstimated) {
      return stage;
    }

    return stage;
  });

  return {
    ...progress,
    stages,
    totalDurationMs: totalDurationMs ?? progress.totalDurationMs,
    totalDurationLabel:
      totalDurationMs != null ? formatDuration(totalDurationMs) : progress.totalDurationLabel,
  };
}

export function getDeploymentStatusColor(status) {
  switch ((status || '').toLowerCase()) {
    case 'completed':
      return '#22c55e';
    case 'failed':
    case 'failed_verification':
    case 'cancelled':
      return '#ef4444';
    case 'pending':
      return '#f59e0b';
    default:
      return '#3b82f6';
  }
}
