import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isAmbiguousDeploymentRequestError,
  matchRecentDeploymentJob,
} from './deployment-request-recovery.js';

const CALLER = 'aaaaa-aa';
const REALM = 'My Test Realm';
const NOW_MS = 1_700_000_000_000;
const RECENT_CREATED = BigInt(Math.floor(NOW_MS / 1000) - 60);
const OLD_CREATED = BigInt(Math.floor(NOW_MS / 1000) - 600);

function job(overrides = {}) {
  return {
    job_id: 'job-1',
    realm_name: REALM,
    caller_principal: CALLER,
    created_at: RECENT_CREATED,
    ...overrides,
  };
}

test('isAmbiguousDeploymentRequestError matches agent-js undefined reply errors', () => {
  assert.equal(
    isAmbiguousDeploymentRequestError(
      new Error(
        'Call was returned undefined. We cannot determine if the call was successful or not.',
      ),
    ),
    true,
  );
  assert.equal(isAmbiguousDeploymentRequestError(new Error('Network timeout')), false);
});

test('matchRecentDeploymentJob finds a recent same-name job', () => {
  const match = matchRecentDeploymentJob([job()], {
    callerPrincipal: CALLER,
    realmName: REALM,
    nowMs: NOW_MS,
  });
  assert.equal(match?.job_id, 'job-1');
});

test('matchRecentDeploymentJob ignores an old same-name job', () => {
  const match = matchRecentDeploymentJob([job({ created_at: OLD_CREATED })], {
    callerPrincipal: CALLER,
    realmName: REALM,
    nowMs: NOW_MS,
  });
  assert.equal(match, null);
});

test('matchRecentDeploymentJob ignores a job from a different caller', () => {
  const match = matchRecentDeploymentJob(
    [job({ caller_principal: 'bbbbb-bb' })],
    {
      callerPrincipal: CALLER,
      realmName: REALM,
      nowMs: NOW_MS,
    },
  );
  assert.equal(match, null);
});
