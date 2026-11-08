import assert from 'node:assert/strict';
import test from 'node:test';
import { rememberFinalSpecHash, resumeClaimedRequest } from './assistant-deploy-resume.js';

const NOW_S = 1_800_000_000;
const NOW_MS = NOW_S * 1000;
const CLAIMED_AT = NOW_S - 60; // the user clicked Launch a minute ago
const USER = 'user-principal-abc';

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
  };
}

function claimedRequest(overrides = {}) {
  return {
    id: 'req-1',
    specHash: 'original-hash',
    claimedAt: CLAIMED_AT,
    leaseExpiresAt: CLAIMED_AT + 180,
    ...overrides,
  };
}

const job = (jobId, createdAt, overrides = {}) => ({
  job_id: jobId,
  caller_principal: USER,
  realm_name: 'Riverside Commons',
  created_at: createdAt,
  ...overrides,
});

function recorder() {
  const reports = [];
  return { reports, report: async (jobId, specHash) => void reports.push({ jobId, specHash }) };
}

const run = (overrides) =>
  resumeClaimedRequest({
    request: claimedRequest(),
    principalText: USER,
    storage: memoryStorage(),
    listJobs: async () => [],
    report: recorder().report,
    nowMs: NOW_MS,
    ...overrides,
  });

test('a reload after Launch finds the job and reports it instead of offering a second Launch', async () => {
  const storage = memoryStorage();
  rememberFinalSpecHash(storage, 'req-1', 'final-hash');
  const { reports, report } = recorder();

  const outcome = await run({ storage, listJobs: async () => [job('job_1', CLAIMED_AT + 2)], report });

  assert.deepEqual(outcome, { phase: 'used', jobId: 'job_1' });
  assert.deepEqual(reports, [{ jobId: 'job_1', specHash: 'final-hash' }]);
});

test('a renamed realm is found from a fresh tab with nothing in storage', async () => {
  const { reports, report } = recorder();
  const renamed = job('job_2', CLAIMED_AT + 2, { realm_name: 'Beta' }); // the request said "Alpha"

  const outcome = await run({ listJobs: async () => [renamed], report });

  assert.deepEqual(outcome, { phase: 'used', jobId: 'job_2' });
  assert.deepEqual(reports, [{ jobId: 'job_2', specHash: 'original-hash' }]);
});

test('an older job with the same name is not this request\'s', async () => {
  const older = job('job_old', CLAIMED_AT - 61);
  const { reports, report } = recorder();

  const outcome = await run({ listJobs: async () => [older], report });

  assert.deepEqual(outcome, { phase: 'claimed' });
  assert.deepEqual(reports, []);
});

test('with the claim lapsed and only an older job, the user may launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_S - 1 });

  assert.deepEqual(await run({ request, listJobs: async () => [job('job_old', CLAIMED_AT - 3600)] }), { phase: 'wizard' });
});

test('a job up to 60 s older than the claim still counts, as ggg-mcp accepts its report', async () => {
  assert.deepEqual(await run({ listJobs: async () => [job('job_3', CLAIMED_AT - 60)] }), { phase: 'used', jobId: 'job_3' });
  assert.deepEqual(await run({ listJobs: async () => [job('job_3', CLAIMED_AT - 61)] }), { phase: 'claimed' });
});

test('the newest job since the claim is the one reported', async () => {
  const jobs = [job('job_a', CLAIMED_AT + 1), job('job_c', CLAIMED_AT + 30), job('job_b', CLAIMED_AT + 10)];

  assert.deepEqual(await run({ listJobs: async () => jobs }), { phase: 'used', jobId: 'job_c' });
});

test('another user\'s job is not this user\'s', async () => {
  const theirs = job('job_x', CLAIMED_AT + 2, { caller_principal: 'someone-else' });

  assert.deepEqual(await run({ listJobs: async () => [theirs] }), { phase: 'claimed' });
});

test('no job and a live claim: the page says the user already clicked Launch', async () => {
  const { reports, report } = recorder();

  assert.deepEqual(await run({ report }), { phase: 'claimed' });
  assert.deepEqual(reports, []);
});

test('no job and a lapsed claim: the user may launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_S - 1 });

  assert.deepEqual(await run({ request }), { phase: 'wizard' });
});

test('a lapsed claim with a job is still the job: never a second Launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_S - 600 });

  assert.deepEqual(await run({ request, listJobs: async () => [job('job_5', CLAIMED_AT + 3)] }), {
    phase: 'used',
    jobId: 'job_5',
  });
});

test('an unknown lease counts as live', async () => {
  assert.deepEqual(await run({ request: claimedRequest({ leaseExpiresAt: 0 }) }), { phase: 'claimed' });
});

test('without the claim time nothing is matched and the user is not offered a second Launch', async () => {
  const request = claimedRequest({ claimedAt: 0, leaseExpiresAt: NOW_S - 600 });
  let asked = false;
  const listJobs = async () => {
    asked = true;
    return [job('job_6', NOW_S)];
  };

  assert.deepEqual(await run({ request, listJobs }), { phase: 'claimed' });
  assert.equal(asked, false, 'it does not guess from a list it cannot tell apart');
});

test('when the installer cannot be asked the user is not offered a second Launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_S - 600 });
  const listJobs = async () => {
    throw new Error('installer unreachable');
  };

  assert.deepEqual(await run({ request, listJobs }), { phase: 'claimed' });
});

test('storage that is broken or holds nothing falls back to the original spec hash', async () => {
  const broken = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  };
  rememberFinalSpecHash(broken, 'req-1', 'x'); // does not throw

  for (const storage of [broken, memoryStorage()]) {
    const { reports, report } = recorder();
    const outcome = await run({ storage, listJobs: async () => [job('job_7', CLAIMED_AT + 1)], report });
    assert.deepEqual(outcome, { phase: 'used', jobId: 'job_7' });
    assert.deepEqual(reports, [{ jobId: 'job_7', specHash: 'original-hash' }]);
  }
});
