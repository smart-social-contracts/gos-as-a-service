import assert from 'node:assert/strict';
import test from 'node:test';
import {
  FLOATING_FAB_GAP,
  FLOATING_MAX_HEIGHT,
  MIN_PANEL_HEIGHT,
  assistantPanelBoxStyle,
  computeAssistantPanelBox,
  cssLengthToPx,
} from './assistant-viewport.js';

test('desktop floating panel keeps CSS defaults when chrome does not overlap', () => {
  const box = computeAssistantPanelBox({
    docked: false,
    visualHeight: 900,
    visualOffsetTop: 0,
    layoutHeight: 900,
    layoutWidth: 1280,
  });
  assert.equal(box, null);
  assert.equal(assistantPanelBoxStyle(box), '');
});

test('docked iPhone panel fits the visual viewport so the composer is not under Safari chrome', () => {
  // Typical iPhone layout viewport vs visual viewport with the Safari toolbar showing.
  const box = computeAssistantPanelBox({
    docked: true,
    visualHeight: 668,
    visualOffsetTop: 0,
    layoutHeight: 844,
    layoutWidth: 390,
  });
  assert.ok(box);
  assert.equal(box.heightPx, 660);
  assert.equal(box.topPx, 0);
  assert.equal(box.bottomPx, null);
  assert.equal(assistantPanelBoxStyle(box), 'height: 660px; top: 0px; bottom: auto');
});

test('docked panel follows visualViewport offsetTop when the URL bar consumes the top', () => {
  const box = computeAssistantPanelBox({
    docked: true,
    visualHeight: 620,
    visualOffsetTop: 47,
    layoutHeight: 844,
    layoutWidth: 390,
  });
  assert.ok(box);
  assert.equal(box.heightPx, 612);
  assert.equal(box.topPx, 47);
});

test('phone-width floating panel stays above the brain FAB and inside the visual viewport', () => {
  const box = computeAssistantPanelBox({
    docked: false,
    visualHeight: 580,
    visualOffsetTop: 0,
    layoutHeight: 667,
    layoutWidth: 390,
  });
  assert.ok(box);
  assert.ok(box.heightPx >= MIN_PANEL_HEIGHT);
  assert.ok(box.heightPx <= FLOATING_MAX_HEIGHT);
  assert.ok(box.bottomPx >= FLOATING_FAB_GAP);
  assert.ok(box.heightPx + box.bottomPx <= 667);
  assert.match(assistantPanelBoxStyle(box), /height: \d+px; bottom: \d+px/);
});

test('floating panel lifts above overlapping mobile browser chrome', () => {
  const box = computeAssistantPanelBox({
    docked: false,
    visualHeight: 700,
    visualOffsetTop: 0,
    layoutHeight: 844,
    layoutWidth: 1024,
  });
  assert.ok(box);
  assert.equal(box.bottomPx, 160);
});

test('docked height never collapses below the minimum usable panel', () => {
  const box = computeAssistantPanelBox({
    docked: true,
    visualHeight: 80,
    visualOffsetTop: 0,
    layoutHeight: 844,
    layoutWidth: 390,
  });
  assert.ok(box);
  assert.equal(box.heightPx, MIN_PANEL_HEIGHT);
});

test('cssLengthToPx understands rem and px banner offsets', () => {
  assert.equal(cssLengthToPx('2.75rem', 16), 44);
  assert.equal(cssLengthToPx('44px'), 44);
  assert.equal(cssLengthToPx('0px'), 0);
  assert.equal(cssLengthToPx(''), 0);
});

test('docked panel sits below the test-mode banner instead of under it', () => {
  const box = computeAssistantPanelBox({
    docked: true,
    visualHeight: 900,
    visualOffsetTop: 0,
    layoutHeight: 900,
    layoutWidth: 1280,
    bannerHeight: 44,
  });
  assert.ok(box);
  assert.equal(box.topPx, 44);
  assert.equal(box.heightPx, 856);
  assert.equal(
    assistantPanelBoxStyle(box),
    'height: 856px; top: 44px; bottom: auto',
  );
});
