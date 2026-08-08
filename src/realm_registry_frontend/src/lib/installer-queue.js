import { browser, building } from '$app/environment';
import { CONFIG } from '$lib/config.js';
import { getDeploymentProgress } from '$lib/deployment-progress.js';
import { getObservedStageStarts, toTimestampMs } from '$lib/deployment-stage-timing.js';
import { pollRecentDeploymentJob } from './deployment-request-recovery.js';

export { isAmbiguousDeploymentRequestError, matchRecentDeploymentJob } from './deployment-request-recovery.js';

const buildingOrTesting = building || process.env.NODE_ENV === 'test';

/** Matches realm_installer ``_LIST_JOBS_MAX`` (one query page). */
export const LIST_JOBS_PAGE_SIZE = 50;

const DELETABLE_DEPLOYMENT_STATUSES = new Set(['failed', 'failed_verification', 'cancelled']);

function isLocalDevelopment() {
  if (!browser || typeof window === 'undefined') return false;
  return (
    window.location.hostname.includes('localhost') ||
    window.location.hostname.includes('127.0.0.1')
  );
}

function resultOk(raw) {
  if (raw == null) return null;
  if (typeof raw === 'object' && 'Ok' in raw) return raw.Ok;
  return null;
}

async function createInstallerActor() {
  const { createActor, canisterId } = await import('declarations/realm_installer');
  const { HttpAgent } = await import('@dfinity/agent');
  const agent = new HttpAgent();
  if (isLocalDevelopment()) {
    try {
      await agent.fetchRootKey();
    } catch (_) {
      /* non-fatal */
    }
  }
  const id = CONFIG.realm_installer_canister_id || canisterId;
  if (!id) {
    throw new Error('realm_installer canister id is not configured');
  }
  return createActor(id, { agent });
}

async function createAuthenticatedInstallerActor() {
  const { getIdentity } = await import('$lib/auth.js');
  const identity = await getIdentity();
  if (!identity) {
    throw new Error('Not authenticated');
  }
  const { createActor, canisterId } = await import('declarations/realm_installer');
  const { HttpAgent } = await import('@dfinity/agent');
  const agent = new HttpAgent({ identity });
  if (isLocalDevelopment()) {
    try {
      await agent.fetchRootKey();
    } catch (_) {
      /* non-fatal */
    }
  }
  const id = CONFIG.realm_installer_canister_id || canisterId;
  if (!id) {
    throw new Error('realm_installer canister id is not configured');
  }
  return createActor(id, { agent });
}

export function isDeletableDeployment(deployment) {
  const st = (deployment?.raw_status || deployment?.status || '').toLowerCase();
  return DELETABLE_DEPLOYMENT_STATUSES.has(st);
}

function deploymentRowPriority(row) {
  const st = (row?.raw_status || row?.status || '').toLowerCase();
  if (isActiveQueueStatus(st) || st === 'in_progress') return 100;
  if (st === 'completed') return 50;
  if (st === 'failed' || st === 'failed_verification') return 20;
  if (st === 'cancelled') return 10;
  return 15;
}

function deploymentGroupKey(row) {
  const backend = (row?.backend_canister_id || '').trim();
  if (backend) return `backend:${backend}`;
  const name = (row?.realm_name || row?.deployment_id || '').trim().toLowerCase();
  if (name) return `name:${name}`;
  return `job:${row?.deployment_id || ''}`;
}

/** @typedef {{ deployment_id: string, realm_name: string, raw_status: string, status: string, created_at: number, error: string | null }} DeploymentJobHistoryEntry */

/** @param {object} row */
function toJobHistoryEntry(row) {
  return {
    deployment_id: row.deployment_id || '',
    realm_name: row.realm_name || row.deployment_id || '',
    raw_status: row.raw_status || row.status || '',
    status: row.status || '',
    created_at: Number(row.created_at || 0),
    error: row.error || null,
  };
}

/**
 * Collapse repeated redeploys to the same backend canister. Keeps the most
 * relevant job (active > completed > failed) and records older jobs for expansion.
 *
 * @param {object[]} rows - output of ``installerJobToDeploymentRow``
 * @returns {object[]}
 */
export function dedupeDeploymentRows(rows) {
  const groups = new Map();

  for (const row of rows || []) {
    const key = deploymentGroupKey(row);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  const deduped = [];
  for (const group of groups.values()) {
    const sorted = [...group].sort((a, b) => {
      const priorityDiff = deploymentRowPriority(b) - deploymentRowPriority(a);
      if (priorityDiff !== 0) return priorityDiff;
      return Number(b.created_at || 0) - Number(a.created_at || 0);
    });
    const canonical = sorted[0];
    const earlier = sorted.slice(1).map(toJobHistoryEntry);
    deduped.push({
      ...canonical,
      earlier_deploy_count: earlier.length,
      earlier_jobs: earlier,
    });
  }

  deduped.sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
  return deduped;
}

/** Fetch every deployment job page for the authenticated caller. */
export async function fetchDeploymentJobsFromInstaller() {
  if (buildingOrTesting || !browser) return [];
  const actor = await createAuthenticatedInstallerActor();
  const pageSize = LIST_JOBS_PAGE_SIZE;
  const all = [];
  let offset = 0;

  for (;;) {
    const offsetArg = offset > 0 ? [offset] : [];
    const raw = await actor.list_deployment_jobs(offsetArg, [pageSize]);
    if (raw == null) break;
    if (typeof raw === 'object' && 'Err' in raw) break;
    const ok = resultOk(raw);
    if (!ok) break;

    const jobs = ok.jobs || [];
    all.push(...jobs);
    if (jobs.length < pageSize) break;
    offset += jobs.length;
    if (offset > 5000) break;
  }

  return all;
}

/** Poll installer jobs after request_deployment returns an ambiguous agent-js reply. */
export async function findRecentDeploymentJob(options = {}) {
  return pollRecentDeploymentJob({
    ...options,
    fetchJobs: options.fetchJobs ?? fetchDeploymentJobsFromInstaller,
  });
}

/**
 * Filter, map, and dedupe installer jobs for the dashboard Realms tab.
 *
 * @returns {{ rawJobs: object[], deployments: object[], totalJobCount: number }}
 */
export function prepareDashboardDeploymentRows(jobs, principalText) {
  const mine = (jobs || []).filter((j) => (j.caller_principal || '') === principalText);
  const rows = mine.map(installerJobToDeploymentRow);
  const deployments = dedupeDeploymentRows(rows);
  return {
    rawJobs: mine,
    deployments,
    totalJobCount: mine.length,
  };
}

/** @returns {Promise<object|null>} */
export async function fetchDeploymentJobStatus(jobId) {
  if (buildingOrTesting || !browser || !jobId) return null;
  const actor = await createInstallerActor();
  const raw = await actor.get_deployment_job_status(jobId);
  if (raw == null) return null;
  if (typeof raw === 'object' && 'Err' in raw) return null;
  return resultOk(raw);
}

/** @returns {Promise<object|null>} extension/codex install steps for a job */
export async function fetchDeployTaskStatus(jobId) {
  if (buildingOrTesting || !browser || !jobId) return null;
  const actor = await createInstallerActor();
  if (typeof actor.get_deploy_task_status !== 'function') return null;
  const raw = await actor.get_deploy_task_status(jobId);
  if (raw == null) return null;
  if (typeof raw === 'object' && 'Err' in raw) return null;
  const ok = resultOk(raw);
  if (!ok) return null;
  return {
    ...ok,
    total_count: Number(ok.total_count ?? 0),
    completed_count: Number(ok.completed_count ?? 0),
    steps: (ok.steps || []).map((step) => ({
      ...step,
      idx: Number(step.idx ?? 0),
    })),
  };
}

/** @returns {Promise<string|null>} manifest JSON for owner-authenticated caller */
export async function fetchDeploymentManifest(jobId) {
  if (buildingOrTesting || !browser || !jobId) return null;
  const actor = await createAuthenticatedInstallerActor();
  const raw = await actor.get_deployment_manifest(jobId);
  if (raw == null) return null;
  if (typeof raw === 'object' && 'Err' in raw) {
    throw new Error(raw.Err?.message || raw.Err || 'Failed to load manifest');
  }
  return resultOk(raw);
}

/** Delete a terminal failed deployment job (owner only). */
export async function deleteDeploymentJob(jobId) {
  if (buildingOrTesting || !browser || !jobId) {
    throw new Error('Cannot delete deployment job');
  }
  const actor = await createAuthenticatedInstallerActor();
  const raw = await actor.delete_deployment_job(jobId);
  if (raw == null) {
    throw new Error('No response from installer');
  }
  if (typeof raw === 'object' && 'Err' in raw) {
    throw new Error(raw.Err?.message || raw.Err || 'Delete failed');
  }
  return resultOk(raw);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Destroy can take minutes (Casals drains every stand canister). Agent-js may report undefined. */
function isAmbiguousDestroyError(err) {
  const msg = String(err?.message || err || '');
  return (
    msg.includes('Call was returned undefined') ||
    msg.includes('Cannot determine if the call was successful') ||
    msg.includes('No response from installer') ||
    msg.includes('ERR_NETWORK')
  );
}

/** Retry-safe: realm/job already gone after a successful earlier attempt. */
function isBenignDestroyError(message) {
  const msg = String(message || '');
  return (
    msg.includes('unknown job_id') ||
    /Realm '[^']+' not found/i.test(msg) ||
    msg.includes('Canister has no update method') ||
    msg.includes('Canister not found')
  );
}

/**
 * Poll until the installer drops the job record (destroy finished) or timeout.
 * @returns {Promise<object>}
 */
export async function waitForRealmDestroy(jobId, { timeoutMs = 180000, intervalMs = 3000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await fetchDeploymentJobStatus(jobId);
    if (!status) {
      return { job_id: jobId, status: 'destroyed', noop: false };
    }
    await sleep(intervalMs);
  }
  throw new Error(
    'Destroy is still running on-chain. Wait a minute, refresh the dashboard, and check Casals treasury.',
  );
}

/**
 * Destroy an alpha-stage completed realm (owner only).
 * @param {string} jobId
 * @param {{ backendCanisterId?: string, onProgress?: (update: object) => void, pollIntervalMs?: number }} [options]
 */
export async function destroyRealmJob(jobId, options = {}) {
  if (buildingOrTesting || !browser || !jobId) {
    throw new Error('Cannot destroy realm');
  }
  const onProgress = options.onProgress;
  const pollIntervalMs = options.pollIntervalMs ?? 3000;
  const actor = await createAuthenticatedInstallerActor();

  onProgress?.({ stageIndex: 0 });

  let pollTimer = null;
  let pollStage = 0;
  const startPollProgress = () => {
    pollTimer = setInterval(() => {
      if (pollStage < 3) {
        pollStage += 1;
        onProgress?.({ stageIndex: pollStage });
      }
    }, pollIntervalMs);
  };

  const stopPollProgress = () => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  try {
    const raw = await actor.destroy_realm_job(jobId);
    if (raw == null) {
      startPollProgress();
      const result = await waitForRealmDestroy(jobId, { intervalMs: pollIntervalMs });
      onProgress?.({ stageIndex: 4, complete: true });
      return result;
    }
    if (typeof raw === 'object' && 'Err' in raw) {
      const msg = raw.Err?.message || raw.Err || 'Destroy failed';
      if (isBenignDestroyError(msg)) {
        startPollProgress();
        const result = await waitForRealmDestroy(jobId, { intervalMs: pollIntervalMs });
        onProgress?.({ stageIndex: 4, complete: true });
        return result;
      }
      throw new Error(msg);
    }
    onProgress?.({ stageIndex: 4, complete: true });
    return resultOk(raw);
  } catch (err) {
    if (isAmbiguousDestroyError(err) || isBenignDestroyError(err?.message)) {
      startPollProgress();
      const result = await waitForRealmDestroy(jobId, { intervalMs: pollIntervalMs });
      onProgress?.({ stageIndex: 4, complete: true });
      return result;
    }
    throw err;
  } finally {
    stopPollProgress();
  }
}

/**
 * Map installer job to the shape previously returned by the management HTTP API
 * so dashboard templates stay stable.
 */
export function installerJobToDeploymentRow(job, deployTask = null, options = {}) {
  const st = (job.status || '').toLowerCase();
  let uiStatus = st;
  if (
    st === 'deploying' ||
    st === 'verifying' ||
    st === 'extensions' ||
    st === 'registering' ||
    st === 'provisioning'
  ) {
    uiStatus = 'in_progress';
  }
  const frontend = job.frontend_canister_id || '';
  const realmUrl = frontend ? `https://${frontend}.icp0.io` : null;
  const row = {
    deployment_id: job.job_id,
    realm_name: job.realm_name || job.job_id,
    status: uiStatus,
    raw_status: st,
    created_at: Number(job.created_at || 0),
    completed_at: job.completed_at != null ? Number(job.completed_at) : null,
    realm_url: realmUrl,
    error: job.error || null,
    backend_canister_id: job.backend_canister_id || '',
    frontend_canister_id: job.frontend_canister_id || '',
    expected_step_count: Number(job.expected_step_count || 0),
    ext_deploy_task_id: job.ext_deploy_task_id || '',
    caller_principal: job.caller_principal || '',
    credits_charged: 0,
    earlier_deploy_count: 0,
    earlier_jobs: [],
  };
  row.progress = getDeploymentProgress(
    { ...job, raw_status: st },
    {
      deployTask,
      codexDependencies: options?.codexDependencies ?? [],
      observedStageStarts: getObservedStageStarts(
        job.job_id,
        toTimestampMs(job.created_at),
      ),
    },
  );
  row.deployTask = deployTask || null;
  return row;
}

export function isActiveQueueStatus(status) {
  const s = (status || '').toLowerCase();
  return (
    s === 'pending' ||
    s === 'provisioning' ||
    s === 'deploying' ||
    s === 'verifying' ||
    s === 'extensions' ||
    s === 'registering'
  );
}
