/** Floating card max height (matches `.assistant-panel` CSS). */
export const FLOATING_MAX_HEIGHT = 560;
/** Space reserved for the host brain FAB when the panel is undocked. */
export const FLOATING_FAB_GAP = 88;
export const FLOATING_TOP_GAP = 16;
export const MIN_PANEL_HEIGHT = 220;
export const PHONE_BREAKPOINT = 768;

/**
 * Keep the assistant panel (and its composer) inside the *visible* viewport.
 *
 * iOS Safari's `100vh` includes the area behind the browser chrome, so a
 * docked `height: 100vh` panel draws the message input under the toolbar.
 * Size from `visualViewport` instead.
 *
 * @param {{
 *   docked: boolean,
 *   visualHeight: number,
 *   visualOffsetTop?: number,
 *   layoutHeight: number,
 *   layoutWidth: number,
 * }} input
 * @returns {{ heightPx: number, topPx: number | null, bottomPx: number | null } | null}
 *   `null` means CSS defaults are fine (wide desktop, no chrome overlap).
 */
export function computeAssistantPanelBox(input) {
  const {
    docked,
    visualHeight,
    visualOffsetTop = 0,
    layoutHeight,
    layoutWidth,
  } = input;

  const hiddenBelow = Math.max(0, layoutHeight - visualOffsetTop - visualHeight);
  const phone = layoutWidth < PHONE_BREAKPOINT;
  const chromeHidesBottom = hiddenBelow >= 24;

  if (!docked && !phone && !chromeHidesBottom) {
    return null;
  }

  if (docked) {
    const chromeGap = phone || chromeHidesBottom ? 8 : 0;
    return {
      heightPx: Math.max(MIN_PANEL_HEIGHT, Math.round(visualHeight) - chromeGap),
      topPx: Math.round(visualOffsetTop),
      bottomPx: null,
    };
  }

  const bottomPx = Math.round(Math.max(FLOATING_FAB_GAP, hiddenBelow + 16));
  const usedBelowVisual = Math.max(0, bottomPx - hiddenBelow);
  const usable = visualHeight - usedBelowVisual - FLOATING_TOP_GAP;
  return {
    heightPx: Math.min(FLOATING_MAX_HEIGHT, Math.max(MIN_PANEL_HEIGHT, Math.round(usable))),
    topPx: null,
    bottomPx,
  };
}

/**
 * @param {{ heightPx: number, topPx: number | null, bottomPx: number | null } | null} box
 * @returns {string}
 */
export function assistantPanelBoxStyle(box) {
  if (!box) return '';
  const parts = [`height: ${box.heightPx}px`];
  if (box.topPx !== null) {
    parts.push(`top: ${box.topPx}px`, 'bottom: auto');
  }
  if (box.bottomPx !== null) {
    parts.push(`bottom: ${box.bottomPx}px`);
  }
  return parts.join('; ');
}
