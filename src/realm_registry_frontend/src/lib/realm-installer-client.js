// Browser-side client for the realm_installer canister.
//
// The on-chain `deploy_realm` / `get_deploy_status` API was removed. Use
// the registry `enqueue_deployment` flow and `get_deployment_job_status`
// instead. These stubs remain only for backward compatibility in unused code.

import { Actor, HttpAgent } from '@dfinity/agent';
import { Principal } from '@dfinity/principal';
import { initializeAuthClient } from './auth';

let _cachedActor = null;
let _cachedCanisterId = null;

async function getInstallerActor(canisterId) {
  if (_cachedActor && _cachedCanisterId === canisterId) return _cachedActor;

  const { idlFactory } = await import('declarations/realm_installer');
  const client = await initializeAuthClient();
  const identity = client.getIdentity();
  const agent = new HttpAgent({ identity });
  if (
    typeof window !== 'undefined' &&
    (window.location.hostname.includes('localhost') ||
      window.location.hostname.includes('127.0.0.1'))
  ) {
    try { await agent.fetchRootKey(); } catch (e) { /* local dev */ }
  }
  _cachedActor = Actor.createActor(idlFactory, {
    agent,
    canisterId: Principal.fromText(canisterId),
  });
  _cachedCanisterId = canisterId;
  return _cachedActor;
}

/**
 * @deprecated deploy_realm was removed. Use the registry queue + job status.
 */
export async function deployRealm(_installerCanisterId, _manifest) {
  return {
    success: false,
    error: 'deploy_realm was removed; use registry enqueue / deployment job status',
  };
}

/**
 * @deprecated get_deploy_status was removed.
 */
export async function getDeployStatus(_installerCanisterId, _taskId) {
  return {
    success: false,
    error: 'get_deploy_status was removed; use get_deployment_job_status',
  };
}
