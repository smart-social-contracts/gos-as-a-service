import { building } from '$app/environment';
import { CONFIG } from './config.js';
import { getCanisterId } from './network.js';

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

  const resolvedCanisterId =
    CONFIG.casals_backend_canister_id || getCanisterId('casals_backend');
  if (!resolvedCanisterId) {
    throw new Error('Could not load available subnets');
  }

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

function parseSubnetId(entry) {
  if (typeof entry === 'string') return entry.trim();
  if (entry && typeof entry === 'object') {
    const id =
      entry.id ?? entry.subnet_id ?? entry.subnetId ?? entry.principal ?? entry.subnet;
    if (typeof id === 'string') return id.trim();
  }
  return '';
}

export function parseSubnetList(raw) {
  let data = raw;
  if (typeof raw === 'string') {
    try {
      data = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(data)) return [];
  return [...new Set(data.map(parseSubnetId).filter(Boolean))];
}

export async function listSubnets() {
  const actor = await getActorPromise();
  const raw = await actor.list_subnets();
  return parseSubnetList(raw);
}
