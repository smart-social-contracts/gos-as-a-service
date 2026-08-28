import assert from 'node:assert/strict';
import test from 'node:test';
import { rememberJobAttempt, uniqueErrorText } from './deployment-attempt-memory.js';

const RATE_LIMIT =
  'Casals create_canister rate-limited: too many requests in the last window, retry later.';

function mockSession() {
  const data = Object.create(null);
  globalThis.sessionStorage = {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    setItem(key, value) {
      data[key] = String(value);
    },
    removeItem(key) {
      delete data[key];
    },
  };
  return data;
}

test('uniqueErrorText collapses a paragraph-duplicated error', () => {
  assert.equal(uniqueErrorText(`${RATE_LIMIT}\n\n${RATE_LIMIT}`), RATE_LIMIT);
});

test('uniqueErrorText collapses an exact concatenated error', () => {
  assert.equal(uniqueErrorText(`${RATE_LIMIT}${RATE_LIMIT}`), RATE_LIMIT);
});

test('uniqueErrorText leaves two different errors intact', () => {
  const text = `${RATE_LIMIT}\n\nSomething else failed.`;
  assert.equal(uniqueErrorText(text), text);
});

test('rememberJobAttempt stores the last failure and marks a reopen as auto-retry', () => {
  mockSession();
  const jobId = 'job_20260828111300_abc';
  const createdAt = 1_700_000_000;
  const failedAt = 1_700_003_360;
  const failed = rememberJobAttempt(
    jobId,
    {
      raw_status: 'failed',
      error: `${RATE_LIMIT}\n\n${RATE_LIMIT}`,
      created_at: createdAt,
      completed_at: failedAt,
    },
    failedAt * 1000,
  );

  assert.equal(failed?.autoRetrying, false);
  assert.equal(failed?.lastError, RATE_LIMIT);
  assert.equal(failed?.attemptStartedAtMs, createdAt * 1000);

  const reopenAt = failedAt * 1000 + 600_000;
  const retry = rememberJobAttempt(
    jobId,
    {
      raw_status: 'provisioning',
      error: RATE_LIMIT,
      created_at: createdAt,
      completed_at: failedAt,
    },
    reopenAt,
  );

  assert.equal(retry?.autoRetrying, true);
  assert.equal(retry?.lastError, RATE_LIMIT);
  assert.equal(retry?.attemptStartedAtMs, reopenAt);

  const stillRetrying = rememberJobAttempt(
    jobId,
    {
      raw_status: 'provisioning',
      error: RATE_LIMIT,
      created_at: createdAt,
      completed_at: failedAt,
    },
    reopenAt + 8000,
  );
  assert.equal(stillRetrying?.attemptStartedAtMs, reopenAt);
});

test('rememberJobAttempt keeps last error when installer cleared it on reopen', () => {
  mockSession();
  const jobId = 'job_same_id';
  rememberJobAttempt(
    jobId,
    {
      raw_status: 'failed',
      error: RATE_LIMIT,
      created_at: 1_700_000_000,
      completed_at: 1_700_000_080,
    },
    1_700_000_080_000,
  );
  const retry = rememberJobAttempt(
    jobId,
    {
      raw_status: 'provisioning',
      error: '',
      created_at: 1_700_000_000,
      completed_at: 1_700_000_080,
    },
    1_700_000_140_000,
  );
  assert.equal(retry?.autoRetrying, true);
  assert.equal(retry?.lastError, RATE_LIMIT);
});
