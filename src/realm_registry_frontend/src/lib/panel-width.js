/** Expanded side panel width as a fraction of the viewport. */
export const PANEL_WIDTH_RATIO = 0.45;

export const PANEL_MIN_WIDTH = 280;

/** SSR-safe default panel width in px. */
export function defaultPanelWidth() {
  if (typeof window === 'undefined') {
    return Math.round(1280 * PANEL_WIDTH_RATIO);
  }
  return Math.floor(window.innerWidth * PANEL_WIDTH_RATIO);
}

/** @param {number} w */
export function clampPanelWidth(w) {
  if (typeof window === 'undefined') return w;
  const max = Math.floor(window.innerWidth * PANEL_WIDTH_RATIO);
  return Math.max(PANEL_MIN_WIDTH, Math.min(max, Math.round(w)));
}
