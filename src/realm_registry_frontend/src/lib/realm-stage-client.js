/** Fetch lifecycle stage from a deployed realm backend canister. */

function isLocalDevelopment() {
  if (typeof window === 'undefined') return false;
  return (
    window.location.hostname.includes('localhost') ||
    window.location.hostname.includes('127.0.0.1')
  );
}

/**
 * @param {string} backendCanisterId
 * @returns {Promise<string|null>} stage id (e.g. alpha) or null on failure
 */
export async function fetchRealmStage(backendCanisterId) {
  const cid = (backendCanisterId || '').trim();
  if (!cid) return null;

  try {
    const { Actor, HttpAgent } = await import('@dfinity/agent');
    const { Principal } = await import('@dfinity/principal');
    const { IDL } = await import('@dfinity/candid');

    const idlFactory = ({ IDL: Idl }) =>
      Idl.Service({
        get_runtime_flags: Idl.Func([], [Idl.Text], ['query']),
      });

    const agent = new HttpAgent({ host: isLocalDevelopment() ? undefined : 'https://icp0.io' });
    if (isLocalDevelopment()) {
      try {
        await agent.fetchRootKey();
      } catch {
        /* non-fatal */
      }
    }

    const actor = Actor.createActor(idlFactory, {
      agent,
      canisterId: Principal.fromText(cid),
    });

    const raw = await actor.get_runtime_flags();
    const data = typeof raw === 'string' ? JSON.parse(raw) : null;
    if (!data?.success) return null;
    return (data.realm_stage || 'alpha').trim().toLowerCase();
  } catch (err) {
    const message = err?.message || String(err);
    if (/not found|IC0301/i.test(message)) return null;
    console.warn('fetchRealmStage failed:', cid, err);
    return null;
  }
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
