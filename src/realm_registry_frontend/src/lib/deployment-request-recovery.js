const RECENT_DEPLOYMENT_JOB_MAX_AGE_MS = 5 * 60 * 1000;
const RECENT_DEPLOYMENT_JOB_POLL_ATTEMPTS = 8;
const RECENT_DEPLOYMENT_JOB_POLL_INTERVAL_MS = 2500;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** agent-js sync `/api/v3/call` can return HTTP 200 with request_status `processing`. */
export function isAmbiguousDeploymentRequestError(err) {
  const msg = String(err?.message || err || '');
  return /returned undefined|cannot determine if the call was successful/i.test(msg);
}

/**
 * Match a deployment job created recently by this caller with this realm name.
 *
 * @param {object[]} jobs
 * @param {{ callerPrincipal: string, realmName: string, maxAgeMs?: number, nowMs?: number }} options
 * @returns {object|null}
 */
export function matchRecentDeploymentJob(
  jobs,
  {
    callerPrincipal,
    realmName,
    maxAgeMs = RECENT_DEPLOYMENT_JOB_MAX_AGE_MS,
    nowMs = Date.now(),
  } = {},
) {
  const caller = (callerPrincipal || '').trim();
  const name = (realmName || '').trim();
  if (!caller || !name) return null;

  const cutoffSec = (nowMs - maxAgeMs) / 1000;
  let best = null;
  let bestCreated = 0;

  for (const job of jobs || []) {
    if ((job.caller_principal || '') !== caller) continue;
    if ((job.realm_name || '') !== name) continue;
    const created = Number(job.created_at || 0);
    if (created < cutoffSec) continue;
    if (created >= bestCreated) {
      best = job;
      bestCreated = created;
    }
  }

  return best;
}

/**
 * Poll installer jobs after request_deployment returns an ambiguous agent-js reply.
 *
 * @param {{
 *   callerPrincipal: string,
 *   realmName: string,
 *   fetchJobs: () => Promise<object[]>,
 *   maxAttempts?: number,
 *   intervalMs?: number,
 *   maxAgeMs?: number,
 *   sleepFn?: (ms: number) => Promise<void>,
 * }} options
 * @returns {Promise<object|null>}
 */
export async function pollRecentDeploymentJob({
  callerPrincipal,
  realmName,
  fetchJobs,
  maxAttempts = RECENT_DEPLOYMENT_JOB_POLL_ATTEMPTS,
  intervalMs = RECENT_DEPLOYMENT_JOB_POLL_INTERVAL_MS,
  maxAgeMs = RECENT_DEPLOYMENT_JOB_MAX_AGE_MS,
  sleepFn = sleep,
}) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const jobs = await fetchJobs();
    const match = matchRecentDeploymentJob(jobs, {
      callerPrincipal,
      realmName,
      maxAgeMs,
    });
    if (match) return match;
    if (attempt < maxAttempts - 1) {
      await sleepFn(intervalMs);
    }
  }
  return null;
}
