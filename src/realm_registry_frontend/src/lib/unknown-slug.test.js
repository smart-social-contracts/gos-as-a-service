import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  findJobForSlug,
  isUnknownSlugError,
  jobMatchesSlug,
  unknownSlugView,
} from './unknown-slug.js';

test('isUnknownSlugError matches resolve_slug copy', () => {
  assert.equal(isUnknownSlugError(new Error("Unknown slug 'realmtest6'"), 'realmtest6'), true);
  assert.equal(isUnknownSlugError(new Error('network down'), 'realmtest6'), false);
});

test('jobMatchesSlug uses slugified realm name', () => {
  assert.equal(jobMatchesSlug({ realm_name: 'RealmTest6' }, 'realmtest6'), true);
  assert.equal(jobMatchesSlug({ realm_name: 'Agora' }, 'realmtest6'), false);
});

test('findJobForSlug returns newest matching job', () => {
  const jobs = [
    { job_id: 'new', realm_name: 'RealmTest6', status: 'registering' },
    { job_id: 'old', realm_name: 'RealmTest6', status: 'failed' },
  ];
  assert.equal(findJobForSlug(jobs, 'realmtest6').job_id, 'new');
});

test('unknownSlugView creating / failed / missing', () => {
  const creating = unknownSlugView('realmtest6', {
    job_id: 'job_1',
    realm_name: 'RealmTest6',
    status: 'registering',
  });
  assert.equal(creating.kind, 'creating');
  assert.match(creating.title, /still being created/);
  assert.equal(creating.href, '/my-dashboard/deployments?job=job_1');

  const failed = unknownSlugView('realmtest6', {
    job_id: 'job_2',
    realm_name: 'RealmTest6',
    status: 'failed',
  });
  assert.equal(failed.kind, 'failed');
  assert.match(failed.title, /failed/i);

  const missing = unknownSlugView('realmtest6', null);
  assert.equal(missing.kind, 'missing');
  assert.match(missing.title, /No realm named realmtest6/);
});
