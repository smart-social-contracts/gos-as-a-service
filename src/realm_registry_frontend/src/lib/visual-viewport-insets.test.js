import assert from 'node:assert/strict';
import test from 'node:test';
import { readTestModeBannerHeightPx } from './visual-viewport-insets.js';

test('readTestModeBannerHeightPx reads inline root style first', () => {
  const doc = {
    documentElement: {
      style: { getPropertyValue: () => '52px' },
    },
  };
  assert.equal(readTestModeBannerHeightPx(doc), 52);
});
