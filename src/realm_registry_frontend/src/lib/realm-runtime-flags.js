/**
 * Fetch runtime flags from a realm backend canister (anonymous query).
 * @param {string} backendCanisterId
 * @returns {Promise<{ test_mode_ii_bypass?: boolean } | null>}
 */
export async function fetchRealmRuntimeFlags(backendCanisterId) {
  if (!backendCanisterId || typeof window === 'undefined') return null;
  try {
    const { HttpAgent, Actor } = await import('@dfinity/agent');
    const { IDL } = await import('@dfinity/candid');
    const idlFactory = ({ IDL: I }) => {
      return I.Service({
        get_runtime_flags: I.Func([], [I.Text], ['query']),
      });
    };
    const agent = new HttpAgent({ host: 'https://icp0.io' });
    const actor = Actor.createActor(idlFactory, { agent, canisterId: backendCanisterId });
    const raw = await actor.get_runtime_flags();
    const payload = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!payload?.success) return null;
    return payload;
  } catch (e) {
    console.warn('[portal] could not fetch realm runtime flags:', e);
    return null;
  }
}
