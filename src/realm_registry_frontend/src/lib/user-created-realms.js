/**
 * Resolve realms created by a user on the registry canister.
 *
 * Registry realm IDs are backend canister IDs (set during deploy registration),
 * not the user's Internet Identity principal.
 */

function realmVisitUrl(record) {
  const url = (record.url || record.backend_url || '').trim();
  if (url) return url.replace(/\/+$/, '') + '/';
  const fe = (record.frontend_canister_id || '').trim();
  if (fe) return `https://${fe}.icp0.io/`;
  return '';
}

function recordToRow(record) {
  return {
    id: record.id,
    name: record.name || record.id,
    url: realmVisitUrl(record),
    frontend_canister_id: record.frontend_canister_id || '',
  };
}

/** Collect backend canister IDs from completed deployment jobs owned by the user. */
export function backendIdsFromDeployments(deployments, principalText) {
  const ids = new Set();
  for (const d of deployments || []) {
    if ((d.caller_principal || '') !== principalText) continue;
    if ((d.raw_status || d.status || '').toLowerCase() !== 'completed') continue;
    const backendId = (d.backend_canister_id || '').trim();
    if (backendId) ids.add(backendId);
  }
  return ids;
}

/**
 * @param {string} principalText
 * @param {object[]} [deployments] - optional preloaded deployment rows
 * @returns {Promise<object[]>}
 */
export async function fetchCreatedRealmsForUser(principalText, deployments = null) {
  if (!principalText) return [];

  const { backend } = await import('$lib/canisters.js');
  const realmIds = new Set();

  // Legacy installs used the caller principal as realm id.
  realmIds.add(principalText);

  let rows = deployments;
  if (rows == null) {
    const { fetchDeploymentJobsFromInstaller } = await import('$lib/installer-queue.js');
    const jobs = await fetchDeploymentJobsFromInstaller();
    rows = jobs.filter((j) => (j.caller_principal || '') === principalText);
  }

  for (const id of backendIdsFromDeployments(rows, principalText)) {
    realmIds.add(id);
  }

  const found = new Map();
  for (const realmId of realmIds) {
    try {
      const result = await backend.get_realm(realmId);
      if (result?.Ok) {
        const row = recordToRow(result.Ok);
        found.set(row.id, row);
      }
    } catch {
      /* skip missing ids */
    }
  }

  return [...found.values()].sort((a, b) =>
    (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
  );
}

/** @returns {Map<string, object>} backend canister id → registry row */
export function indexCreatedRealmsByBackend(realms) {
  const map = new Map();
  for (const realm of realms || []) {
    const id = (realm.id || '').trim();
    if (id) map.set(id, realm);
  }
  return map;
}

/** Registry row for a deployment job, if the realm is listed on-chain. */
export function registryEntryForDeployment(deployment, registryByBackend) {
  const backend = (deployment?.backend_canister_id || '').trim();
  if (!backend || !registryByBackend) return null;
  return registryByBackend.get(backend) || null;
}

/** Prefer federation portal URL from registry; fall back to deployment icp0 link. */
export function preferredVisitUrl(deployment, registryEntry) {
  const fromRegistry = (registryEntry?.url || '').trim();
  if (fromRegistry) return fromRegistry.replace(/\/+$/, '') + '/';
  const fromJob = (deployment?.realm_url || '').trim();
  return fromJob || null;
}
