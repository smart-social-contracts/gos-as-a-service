import { building } from '$app/environment';
import { CONFIG } from './config.js';
import { getCanisterId } from './network.js';
import { parseSubnetList, requireCasalsBackendCanisterId } from './subnet-list-parse.js';

export { parseSubnetList, requireCasalsBackendCanisterId };

function isBuildingOrTesting() {
  const mode = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.MODE : '';
  return building || mode === 'test';
}

function isLocalDevelopment() {
  if (typeof window === 'undefined') return false;
  return (
    window.location.hostname.includes('localhost') ||
    window.location.hostname.includes('127.0.0.1')
  );
}

let actorPromise = null;

async function createCasalsActor() {
  if (isBuildingOrTesting()) {
    return { list_subnets: async () => '[]' };
  }

  const resolvedCanisterId = requireCasalsBackendCanisterId(
    CONFIG.casals_backend_canister_id || getCanisterId('casals_backend')
  );

  const { createActor } = await import('declarations/casals_backend');
  const { HttpAgent } = await import('@dfinity/agent');

  const agent = new HttpAgent();
  if (isLocalDevelopment()) {
    try {
      await agent.fetchRootKey();
    } catch (e) {
      console.warn('fetchRootKey failed:', e);
    }
  }

  return createActor(resolvedCanisterId, { agent });
}

function getActorPromise() {
  if (!actorPromise) {
    actorPromise = createCasalsActor().catch((err) => {
      actorPromise = null;
      throw err;
    });
  }
  return actorPromise;
}

export async function listSubnets() {
  const actor = await getActorPromise();
  const raw = await actor.list_subnets();
  return parseSubnetList(raw);
}
