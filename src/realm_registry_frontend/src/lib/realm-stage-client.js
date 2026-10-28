/** Fetch lifecycle stage from a deployed realm backend canister. */
import { fetchRealmInfo } from './realm-gos-client.js';

/**
 * @param {string} backendCanisterId
 * @returns {Promise<string|null>} stage id (e.g. alpha) or null on failure
 */
export async function fetchRealmStage(backendCanisterId) {
  return (await fetchRealmInfo(backendCanisterId))?.stage ?? null;
}

/**
 * @param {object[]} deployments
 * @returns {Promise<Record<string, string>>} job_id -> stage
 */
export async function fetchDeploymentRealmStages(deployments) {
  /** @type {Record<string, string>} */
  const stages = {};
  const completed = (deployments || []).filter(
    (d) => (d.raw_status || d.status || '').toLowerCase() === 'completed' && d.backend_canister_id,
  );

  await Promise.all(
    completed.map(async (d) => {
      const stage = await fetchRealmStage(d.backend_canister_id);
      if (stage) stages[d.deployment_id] = stage;
    }),
  );

  return stages;
}
