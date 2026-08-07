/** Teardown pipeline shown on dashboard cards while a realm is destroyed. */

export const DESTROY_PIPELINE = [
  {
    id: 'start',
    label: 'Starting teardown',
    description: 'Sending the destroy request to the realm installer.',
  },
  {
    id: 'drain',
    label: 'Reclaiming cycles',
    description: 'Casals is draining each canister balance back into its treasury.',
  },
  {
    id: 'delete',
    label: 'Deleting canisters',
    description: 'Removing backend, frontend, baton, and extension canisters.',
  },
  {
    id: 'registry',
    label: 'Removing from registry',
    description: 'Dropping the realm from the on-chain registry.',
  },
  {
    id: 'complete',
    label: 'Destroyed',
    description: 'Teardown complete. Cycles were returned to Casals when possible.',
  },
];

const STAGE_PERCENT = [12, 40, 68, 88, 100];

/** Advance stages during long polls (drain/delete dominate wall time). */
const STAGE_ADVANCE_MS = [4000, 35000, 70000, 110000];

/**
 * @param {{ stageIndex?: number, isComplete?: boolean, isFailed?: boolean, error?: string, backendCanisterId?: string, frontendCanisterId?: string, startedAt?: number }} opts
 */
export function getDestroyProgress(opts = {}) {
  const isFailed = !!opts.isFailed;
  const isComplete = !!opts.isComplete;
  let stageIndex = Number(opts.stageIndex ?? 0);

  if (isComplete) {
    stageIndex = DESTROY_PIPELINE.length - 1;
  } else if (!isFailed && opts.startedAt) {
    const elapsed = Date.now() - opts.startedAt;
    let inferred = 0;
    for (let i = STAGE_ADVANCE_MS.length - 1; i >= 0; i--) {
      if (elapsed >= STAGE_ADVANCE_MS[i]) {
        inferred = i + 1;
        break;
      }
    }
    stageIndex = Math.max(stageIndex, Math.min(inferred, DESTROY_PIPELINE.length - 2));
  }

  stageIndex = Math.max(0, Math.min(stageIndex, DESTROY_PIPELINE.length - 1));
  const current = DESTROY_PIPELINE[stageIndex];
  const percent = isFailed
    ? STAGE_PERCENT[Math.min(stageIndex, STAGE_PERCENT.length - 2)]
    : STAGE_PERCENT[stageIndex];

  const stages = DESTROY_PIPELINE.map((stage, i) => {
    let state = 'upcoming';
    if (isFailed && i === stageIndex) state = 'failed';
    else if (isComplete && i <= stageIndex) state = 'done';
    else if (!isComplete && !isFailed && i < stageIndex) state = 'done';
    else if (!isComplete && !isFailed && i === stageIndex) state = 'active';
    return { ...stage, state };
  });

  return {
    currentLabel: isFailed ? 'Destroy failed' : current.label,
    currentDescription: isFailed
      ? opts.error || 'Something went wrong while destroying this realm.'
      : current.description,
    percent,
    isComplete,
    isFailed,
    isActive: !isComplete && !isFailed,
    error: opts.error || null,
    stages,
    backendCanisterId: opts.backendCanisterId || '',
    frontendCanisterId: opts.frontendCanisterId || '',
  };
}

/**
 * @param {object} deployment
 * @param {number} [destroyedAtMs]
 */
export function deploymentToDestroyRecord(deployment, destroyedAtMs = Date.now()) {
  return {
    job_id: deployment.deployment_id || '',
    realm_name: deployment.realm_name || deployment.deployment_id || '',
    backend_canister_id: deployment.backend_canister_id || '',
    frontend_canister_id: deployment.frontend_canister_id || '',
    created_at: Number(deployment.created_at || 0),
    destroyed_at: destroyedAtMs,
  };
}

/**
 * @param {object} record
 * @param {object[]} installerRows
 * @param {Record<string, object>} activeDestroys
 */
export function buildDashboardDeploymentCards(installerRows, destroyRecords, activeDestroys) {
  /** @type {object[]} */
  const cards = [];
  const seen = new Set();

  for (const [jobId, active] of Object.entries(activeDestroys || {})) {
    if (!jobId || !active?.deployment) continue;
    seen.add(jobId);
    const dep = active.deployment;
    const isFailed = !!active.error;
    const isComplete = !!active.complete;
    cards.push({
      ...dep,
      cardKind: isFailed ? 'destroy_failed' : isComplete ? 'destroyed' : 'destroying',
      destroyProgress: getDestroyProgress({
        stageIndex: active.stageIndex,
        isComplete,
        isFailed,
        error: active.error,
        startedAt: active.startedAt,
        backendCanisterId: dep.backend_canister_id,
        frontendCanisterId: dep.frontend_canister_id,
      }),
      destroyError: active.error || null,
    });
  }

  for (const rec of destroyRecords || []) {
    const jobId = rec.job_id || '';
    if (!jobId || seen.has(jobId)) continue;
    seen.add(jobId);
    cards.push({
      deployment_id: jobId,
      realm_name: rec.realm_name || jobId,
      backend_canister_id: rec.backend_canister_id || '',
      frontend_canister_id: rec.frontend_canister_id || '',
      created_at: rec.created_at || rec.destroyed_at || 0,
      destroyed_at: rec.destroyed_at || 0,
      raw_status: 'destroyed',
      status: 'destroyed',
      cardKind: 'destroyed',
      destroyProgress: getDestroyProgress({
        isComplete: true,
        backendCanisterId: rec.backend_canister_id,
        frontendCanisterId: rec.frontend_canister_id,
      }),
    });
  }

  for (const dep of installerRows || []) {
    const jobId = dep.deployment_id || '';
    if (!jobId || seen.has(jobId)) continue;
    cards.push({ ...dep, cardKind: 'live' });
  }

  cards.sort((a, b) => {
    const aTs = Number(a.destroyed_at || a.created_at || 0);
    const bTs = Number(b.destroyed_at || b.created_at || 0);
    return bTs - aTs;
  });

  return cards;
}
