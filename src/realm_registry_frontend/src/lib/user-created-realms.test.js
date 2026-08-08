import assert from 'node:assert/strict';
import test from 'node:test';
import {
  effectiveListingStatus,
  isRealmInSetup,
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
