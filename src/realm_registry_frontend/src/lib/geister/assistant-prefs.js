import { normalizeConnectedProviders } from './assistant-providers.js';

const PREFS_KEY = 'mundus_assistant_prefs';
const WIDTH_KEY = 'mundus_assistant_width';

/**
 * @typedef {{
 *   defaultAssistant: string,
 *   showSuggestions: boolean,
 *   sharePageContext: boolean,
 *   connectedProviders: import('./assistant-providers.js').PersonalProviderId[],
 *   dismissConnectSuggestion: boolean,
 * }} AssistantPrefs
 */

/** @returns {AssistantPrefs} */
export function defaultPrefs() {
  return {
    defaultAssistant: '',
    showSuggestions: true,
    sharePageContext: true,
    connectedProviders: [],
    dismissConnectSuggestion: false,
  };
}

/** @returns {AssistantPrefs} */
export function loadPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    return {
      defaultAssistant: typeof raw.defaultAssistant === 'string' ? raw.defaultAssistant : '',
      showSuggestions: raw.showSuggestions !== false,
      sharePageContext: raw.sharePageContext !== false,
      connectedProviders: normalizeConnectedProviders(raw.connectedProviders),
      dismissConnectSuggestion: raw.dismissConnectSuggestion === true,
    };
  } catch {
    return defaultPrefs();
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

/** @param {import('./assistant-providers.js').PersonalProviderId} id */
export function markProviderConnected(id) {
  const current = loadPrefs();
  const connectedProviders = normalizeConnectedProviders([...current.connectedProviders, id]);
  savePrefs({ connectedProviders });
  return connectedProviders;
}

/** @param {import('./assistant-providers.js').PersonalProviderId} id */
export function markProviderDisconnected(id) {
  const current = loadPrefs();
  const connectedProviders = current.connectedProviders.filter((p) => p !== id);
  savePrefs({ connectedProviders });
  return connectedProviders;
}

export function dismissConnectSuggestion() {
  savePrefs({ dismissConnectSuggestion: true });
}
