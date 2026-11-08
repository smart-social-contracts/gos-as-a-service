import assert from 'node:assert/strict';
import test from 'node:test';
import { rememberAttempt, resumeClaimedRequest } from './assistant-deploy-resume.js';

const NOW_MS = 1_800_000_000_000;
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
    leaseExpiresAt: NOW_MS / 1000 + 120, // the claim is live for two more minutes
    spec: { name: 'Riverside Commons' },
    ...overrides,
  };
}

/** The installer's job list, as findJob sees it; records what was asked. */
function jobs(...existing) {
  const asked = [];
  const findJob = async (query) => {
    asked.push(query);
    return existing.find((job) => job.realm_name === query.realmName) ?? null;
  };
  return { findJob, asked };
}

function recorder() {
  const reports = [];
  return { reports, report: async (jobId, specHash) => void reports.push({ jobId, specHash }) };
}

const run = (overrides) =>
  resumeClaimedRequest({ request: claimedRequest(), principalText: USER, storage: memoryStorage(), nowMs: NOW_MS, ...overrides });

test('a reload after Launch finds the job and reports it instead of offering a second Launch', async () => {
  const storage = memoryStorage();
  rememberAttempt(storage, 'req-1', { name: 'Riverside Commons', specHash: 'final-hash' });
  const { findJob } = jobs({ realm_name: 'Riverside Commons', job_id: 'job_1' });
  const { reports, report } = recorder();

  const outcome = await run({ storage, findJob, report });

  assert.deepEqual(outcome, { phase: 'used', jobId: 'job_1' });
  assert.deepEqual(reports, [{ jobId: 'job_1', specHash: 'final-hash' }]);
});

test('the job is looked for under the name the user gave it, then under the original name', async () => {
  const storage = memoryStorage();
  rememberAttempt(storage, 'req-1', { name: 'River Co-op', specHash: 'final-hash' });
  const { findJob, asked } = jobs({ realm_name: 'River Co-op', job_id: 'job_2' });

  const outcome = await run({ storage, findJob, report: recorder().report });

  assert.deepEqual(outcome, { phase: 'used', jobId: 'job_2' });
  assert.deepEqual(asked.map((q) => q.realmName), ['River Co-op']);

  const second = jobs({ realm_name: 'Riverside Commons', job_id: 'job_3' });
  const again = await run({ storage, findJob: second.findJob, report: recorder().report });
  assert.deepEqual(again, { phase: 'used', jobId: 'job_3' });
  assert.deepEqual(second.asked.map((q) => q.realmName), ['River Co-op', 'Riverside Commons']);
});

test('from another tab nothing is remembered: the original name and hash are used', async () => {
  const { findJob, asked } = jobs({ realm_name: 'Riverside Commons', job_id: 'job_4' });
  const { reports, report } = recorder();

  const outcome = await run({ findJob, report });

  assert.deepEqual(outcome, { phase: 'used', jobId: 'job_4' });
  assert.deepEqual(reports, [{ jobId: 'job_4', specHash: 'original-hash' }]);
  assert.equal(asked[0].callerPrincipal, USER);
  assert.ok(asked[0].maxAgeMs >= 60 * 60 * 1000, 'it looks back over the whole life of the request');
});

test('no job and a live claim: the page says the user already clicked Launch', async () => {
  const { reports, report } = recorder();

  const outcome = await run({ findJob: jobs().findJob, report });

  assert.deepEqual(outcome, { phase: 'claimed' });
  assert.deepEqual(reports, []);
});

test('no job and a lapsed claim: the user may launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_MS / 1000 - 1 });

  assert.deepEqual(await run({ request, findJob: jobs().findJob, report: recorder().report }), { phase: 'wizard' });
});

test('a lapsed claim with a job is still the job: never a second Launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_MS / 1000 - 600 });
  const { findJob } = jobs({ realm_name: 'Riverside Commons', job_id: 'job_5' });

  assert.deepEqual(await run({ request, findJob, report: recorder().report }), { phase: 'used', jobId: 'job_5' });
});

test('an unknown lease counts as live', async () => {
  const request = claimedRequest({ leaseExpiresAt: 0 });

  assert.deepEqual(await run({ request, findJob: jobs().findJob, report: recorder().report }), { phase: 'claimed' });
});

test('when the installer cannot be asked the user is not offered a second Launch', async () => {
  const request = claimedRequest({ leaseExpiresAt: NOW_MS / 1000 - 600 });
  const findJob = async () => {
    throw new Error('installer unreachable');
  };

  assert.deepEqual(await run({ request, findJob, report: recorder().report }), { phase: 'claimed' });
});

test('a job of another realm is not this request', async () => {
  const { findJob } = jobs({ realm_name: 'Some Other Realm', job_id: 'job_6' });

  assert.deepEqual(await run({ findJob, report: recorder().report }), { phase: 'claimed' });
});

test('storage that is broken or holds garbage falls back to the original name', async () => {
  const garbage = { getItem: () => '{not json', setItem: () => {} };
  const broken = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  };
  rememberAttempt(broken, 'req-1', { name: 'x', specHash: 'y' }); // does not throw

  for (const storage of [garbage, broken]) {
    const { findJob } = jobs({ realm_name: 'Riverside Commons', job_id: 'job_7' });
    assert.deepEqual(await run({ storage, findJob, report: recorder().report }), { phase: 'used', jobId: 'job_7' });
  }
});
