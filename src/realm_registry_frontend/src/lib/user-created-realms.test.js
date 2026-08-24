import assert from 'node:assert/strict';
import test from 'node:test';
import {
  effectiveListingStatus,
  indexCreatedRealmsByBackend,
  isRealmInSetup,
  registryEntryForDeployment,
} from './user-created-realms.js';

test('effectiveListingStatus treats absent status as live', () => {
  assert.equal(effectiveListingStatus(null), 'live');
  assert.equal(effectiveListingStatus({}), 'live');
  assert.equal(effectiveListingStatus({ listing_status: '' }), 'live');
});

test('effectiveListingStatus recognizes setup', () => {
  assert.equal(effectiveListingStatus({ listing_status: 'setup' }), 'setup');
  assert.equal(effectiveListingStatus({ listing_status: 'SETUP' }), 'setup');
});

test('effectiveListingStatus maps unknown values to live', () => {
  assert.equal(effectiveListingStatus({ listing_status: 'pending' }), 'live');
});

test('isRealmInSetup is true only for setup listings', () => {
  assert.equal(isRealmInSetup({ listing_status: 'setup' }), true);
  assert.equal(isRealmInSetup({ listing_status: 'live' }), false);
  assert.equal(isRealmInSetup(undefined), false);
});

test('registryEntryForDeployment joins by backend_canister_id', () => {
  const backendId = 'backend-principal-abc';
  const registryByBackend = indexCreatedRealmsByBackend([
    {
      id: backendId,
      name: 'My Realm',
      url: 'https://portal.example/r/my-realm/',
      frontend_canister_id: 'frontend-principal',
      listing_status: 'setup',
    },
  ]);
  const deployment = {
    deployment_id: 'job-1',
    backend_canister_id: backendId,
    raw_status: 'completed',
    status: 'completed',
  };
  const entry = registryEntryForDeployment(deployment, registryByBackend);
  assert.ok(entry);
  assert.equal(entry.id, backendId);
  assert.equal(entry.listing_status, 'setup');
  assert.equal(isRealmInSetup(entry), true);
});

test('completed deployment without registry row is not in setup', () => {
  const deployment = {
    deployment_id: 'job-2',
    backend_canister_id: 'missing-backend',
    raw_status: 'completed',
  };
  const entry = registryEntryForDeployment(deployment, indexCreatedRealmsByBackend([]));
  assert.equal(entry, null);
  assert.equal(isRealmInSetup(entry), false);
});
