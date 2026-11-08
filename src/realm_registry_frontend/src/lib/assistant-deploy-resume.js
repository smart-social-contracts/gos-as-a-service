/**
 * A request is "claimed" from the moment the user clicks Launch. If the page never saw the end of it
 * (a reload, a closed tab, a report that did not get through) the link must not open as a fresh wizard:
 * a second Launch would pay for a second realm. Look for the job the first click started instead.
 */

const ATTEMPT_KEY = 'assistant_deploy_attempt:';
// A request lives an hour, so any job it started is younger than that.
const JOB_MAX_AGE_MS = 60 * 60 * 1000;

/**
 * Keep what this tab is about to deploy, to find the job again after a reload: the user may have
 * changed the name, and the job is named after the final one.
 * @param {Storage} storage
 * @param {string} requestId
 * @param {{ name: string, specHash: string }} attempt
 */
export function rememberAttempt(storage, requestId, attempt) {
  try {
    storage.setItem(ATTEMPT_KEY + requestId, JSON.stringify(attempt));
  } catch {
    /* private window, full storage: the original name is the fallback */
  }
}

function recallAttempt(storage, requestId) {
  try {
    const attempt = JSON.parse(storage.getItem(ATTEMPT_KEY + requestId));
    return typeof attempt?.name === 'string' && typeof attempt?.specHash === 'string' ? attempt : null;
  } catch {
    return null;
  }
}

/**
 * @param {{
 *   request: { id: string, specHash: string, leaseExpiresAt: number, spec: { name: string } },
 *   principalText: string,
 *   storage: Storage,
 *   findJob: (query: { callerPrincipal: string, realmName: string, maxAgeMs: number }) => Promise<{ job_id: string } | null>,
 *   report: (jobId: string, specHash: string) => Promise<void>,
 *   nowMs?: number,
 * }} deps
 * @returns {Promise<{ phase: 'used', jobId: string } | { phase: 'claimed' } | { phase: 'wizard' }>}
 *   `used`: the job exists (it has been reported); `claimed`: another click holds the request or we
 *   cannot tell; `wizard`: nothing was started and the claim has lapsed, so the user may launch.
 */
export async function resumeClaimedRequest({ request, principalText, storage, findJob, report, nowMs = Date.now() }) {
  const attempt = recallAttempt(storage, request.id);
  const names = [...new Set([attempt?.name, request.spec.name].filter(Boolean))];
  let job = null;
  try {
    for (const realmName of names) {
      job = await findJob({ callerPrincipal: principalText, realmName, maxAgeMs: JOB_MAX_AGE_MS });
      if (job) break;
    }
  } catch {
    return { phase: 'claimed' };
  }
  if (job) {
    await report(job.job_id, attempt?.specHash || request.specHash);
    return { phase: 'used', jobId: job.job_id };
  }
  const lapsed = request.leaseExpiresAt > 0 && nowMs >= request.leaseExpiresAt * 1000;
  return { phase: lapsed ? 'wizard' : 'claimed' };
}
