import { browser } from '$app/environment';

const STORAGE_KEY = 'realms_deployment_stage_times';

/** @returns {Record<string, { createdAt?: number, stages: Record<number, number> }>} */
function loadStore() {
  if (!browser) return {};
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveStore(store) {
  if (!browser) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* quota / private mode */
  }
}

export function toTimestampMs(value) {
  if (value == null || value === '') return null;
  const n = typeof value === 'bigint' ? Number(value) : Number(value);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n > 1e12 ? n : n * 1000;
}

/** Record when we first see each pipeline stage index during live polling. */
export function recordDeploymentStageObservation(jobId, row) {
  if (!browser || !jobId || !row) return;
  const stageIndex = row.progress?.stageIndex;
  if (stageIndex == null) return;

  const store = loadStore();
  const createdAt = toTimestampMs(row.created_at);
  const entry = store[jobId] || { stages: {} };
  if (createdAt && !entry.createdAt) entry.createdAt = createdAt;
  if (!entry.stages[stageIndex]) {
    entry.stages[stageIndex] = Date.now();
  }
  if (stageIndex > 0 && !entry.stages[0]) {
    entry.stages[0] = createdAt || Date.now();
  }
  store[jobId] = entry;
  saveStore(store);
}

/**
 * Build per-stage start timestamps from session observations.
 * @returns {Record<number, number>|null}
 */
export function getObservedStageStarts(jobId, createdAtMs) {
  if (!browser || !jobId) return null;
  const entry = loadStore()[jobId];
  if (!entry?.stages) return null;

  const starts = { ...entry.stages };
  if (createdAtMs && !starts[0]) starts[0] = createdAtMs;
  return Object.keys(starts).length ? starts : null;
}

export function clearDeploymentStageObservation(jobId) {
  if (!browser || !jobId) return;
  const store = loadStore();
  delete store[jobId];
  saveStore(store);
}
