import { building } from '$app/environment';
import { CONFIG } from './config.js';
import { detectNetwork, getCanisterId } from './network.js';
import { parseSubnetList } from './subnet-list-parse.js';

export { parseSubnetList } from './subnet-list-parse.js';

function isBuildingOrTesting() {
  return building || process.env.NODE_ENV === 'test';
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

  const network = detectNetwork();
  if (network !== 'ic') {
    throw new Error('list_subnets is only available on the ic network');
  }

  const { createActor, canisterId: declaredCanisterId } = await import(
    'declarations/casals_backend'
  );
  const { HttpAgent } = await import('@dfinity/agent');

  const resolvedCanisterId =
    CONFIG.casals_backend_canister_id ||
    getCanisterId('casals_backend') ||
    declaredCanisterId;
  if (!resolvedCanisterId) {
    throw new Error('casals_backend canister ID is not set');
  }

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
  if (!actorPromise) actorPromise = createCasalsActor();
  return actorPromise;
}

export async function listSubnets() {
  const actor = await getActorPromise();
  const raw = await actor.list_subnets();
  return parseSubnetList(raw);
}
