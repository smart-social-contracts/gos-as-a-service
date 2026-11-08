/**
 * A request is "claimed" from the moment the user clicks Launch. If the page never saw the end of it
 * (a reload, a closed tab, a report that did not get through) the link must not open as a fresh wizard:
 * a second Launch would pay for a second realm. Look for the job the first click started instead.
 *
 * The job is the user's newest one created since the claim. It is not looked up by realm name: the user
 * may have renamed the realm, and this tab's memory is gone when the link is opened in another tab.
 */

const HASH_KEY = 'assistant_deploy_final_spec_hash:';
// ggg-mcp refuses a report for a job created more than this long before the claim.
const REPORT_SLACK_S = 60;

/**
 * Keep the hash of what this tab deployed, to report it if the page is reloaded before it reports.
 * @param {Storage} storage
 * @param {string} requestId
 * @param {string} specHash
 */
export function rememberFinalSpecHash(storage, requestId, specHash) {
  try {
    storage.setItem(HASH_KEY + requestId, specHash);
  } catch {
    /* private window, full storage: the original spec's hash is the fallback */
  }
}

function recallFinalSpecHash(storage, requestId) {
  try {
    return storage.getItem(HASH_KEY + requestId) || '';
  } catch {
    return '';
  }
}

/** The newest of the user's jobs created at or after `sinceSec`, or null. */
function newestJobSince(jobs, principalText, sinceSec) {
  let newest = null;
  for (const job of jobs) {
    if ((job.caller_principal || '') !== principalText) continue;
    const created = Number(job.created_at || 0);
    if (created < sinceSec) continue;
    if (!newest || created >= Number(newest.created_at)) newest = job;
  }
  return newest;
}

/**
 * @param {{
 *   request: { id: string, specHash: string, claimedAt: number, leaseExpiresAt: number },
 *   principalText: string,
 *   storage: Storage,
 *   listJobs: () => Promise<Array<{ job_id: string, caller_principal: string, created_at: number }>>,
 *   report: (jobId: string, specHash: string) => Promise<void>,
 *   nowMs?: number,
 * }} deps `listJobs` throws when the installer cannot be asked.
 * @returns {Promise<{ phase: 'used', jobId: string } | { phase: 'claimed' } | { phase: 'wizard' }>}
 *   `used`: the job exists (it has been reported); `claimed`: another click holds the request or we
 *   cannot tell; `wizard`: nothing was started and the claim has lapsed, so the user may launch.
 */
export async function resumeClaimedRequest({ request, principalText, storage, listJobs, report, nowMs = Date.now() }) {
  // Without the claim time there is no telling this request's job from an older one.
  if (!(request.claimedAt > 0)) return { phase: 'claimed' };
  let job;
  try {
    job = newestJobSince(await listJobs(), principalText, request.claimedAt - REPORT_SLACK_S);
  } catch {
    return { phase: 'claimed' };
  }
  if (job) {
    await report(job.job_id, recallFinalSpecHash(storage, request.id) || request.specHash);
    return { phase: 'used', jobId: job.job_id };
  }
  const lapsed = request.leaseExpiresAt > 0 && nowMs >= request.leaseExpiresAt * 1000;
  return { phase: lapsed ? 'wizard' : 'claimed' };
}
