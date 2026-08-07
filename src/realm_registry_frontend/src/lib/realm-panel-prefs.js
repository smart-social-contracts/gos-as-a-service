const WIDTH_KEY = 'mundus_realm_panel_width';

/**
 * @param {number} fallback
 * @returns {number}
 */
export function loadRealmPanelWidth(fallback = 360) {
  try {
    const n = Number(localStorage.getItem(WIDTH_KEY));
    if (Number.isFinite(n) && n >= 280) return n;
  } catch {
    /* private mode */
  }
  return fallback;
}

/** @param {number} width */
export function saveRealmPanelWidth(width) {
  try {
    localStorage.setItem(WIDTH_KEY, String(width));
  } catch {
    /* private mode */
  }
}
