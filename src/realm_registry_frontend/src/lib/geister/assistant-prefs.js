const PREFS_KEY = 'mundus_assistant_prefs';
const WIDTH_KEY = 'mundus_assistant_width';

/**
 * @typedef {{ defaultAssistant: string, showSuggestions: boolean, sharePageContext: boolean }} AssistantPrefs
 */

/** @returns {AssistantPrefs} */
export function loadPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    return {
      defaultAssistant: typeof raw.defaultAssistant === 'string' ? raw.defaultAssistant : '',
      showSuggestions: raw.showSuggestions !== false,
      sharePageContext: raw.sharePageContext !== false,
    };
  } catch {
    return { defaultAssistant: '', showSuggestions: true, sharePageContext: true };
  }
}

/** @param {Partial<AssistantPrefs>} prefs */
export function savePrefs(prefs) {
  try {
    const current = loadPrefs();
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...current, ...prefs }));
  } catch {
    /* private mode */
  }
}

/**
 * @param {number} fallback
 * @returns {number}
 */
export function loadPanelWidth(fallback = 380) {
  try {
    const n = Number(localStorage.getItem(WIDTH_KEY));
    if (Number.isFinite(n) && n >= 280) return n;
  } catch {
    /* private mode */
  }
  return fallback;
}

/** @param {number} width */
export function savePanelWidth(width) {
  try {
    localStorage.setItem(WIDTH_KEY, String(width));
  } catch {
    /* private mode */
  }
}
