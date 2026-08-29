/**
 * Personal assistants the registry panel can connect via the existing
 * Geister MCP connector. Only these three — do not add a fourth.
 */
export const PERSONAL_PROVIDER_IDS = Object.freeze(['chatgpt', 'claude', 'grok']);

/** @typedef {'chatgpt' | 'claude' | 'grok'} PersonalProviderId */

/**
 * @typedef {{
 *   id: PersonalProviderId,
 *   label: string,
 *   stepDefaults: [string, string, string],
 * }} PersonalProvider
 */

/** @type {readonly PersonalProvider[]} */
export const PERSONAL_PROVIDERS = Object.freeze([
  {
    id: 'chatgpt',
    label: 'ChatGPT',
    stepDefaults: [
      'In ChatGPT: Settings → Connectors → add a custom MCP connector.',
      'Paste the Realms MCP URL and continue.',
      'Sign in with Internet Identity and choose read-only or full access.',
    ],
  },
  {
    id: 'claude',
    label: 'Claude',
    stepDefaults: [
      'In Claude: Settings → Connectors → Add custom connector.',
      'Paste the Realms MCP URL and continue.',
      'Sign in with Internet Identity and choose read-only or full access.',
    ],
  },
  {
    id: 'grok',
    label: 'Grok',
    stepDefaults: [
      'In Grok: Settings → Connectors → add a custom MCP server.',
      'Paste the Realms MCP URL and continue.',
      'Sign in with Internet Identity and choose read-only or full access.',
    ],
  },
]);

/** @param {unknown} id */
export function isPersonalProviderId(id) {
  return typeof id === 'string' && PERSONAL_PROVIDER_IDS.includes(id);
}

/** @param {unknown} id */
export function getPersonalProvider(id) {
  if (!isPersonalProviderId(id)) return null;
  return PERSONAL_PROVIDERS.find((p) => p.id === id) || null;
}

/** @param {unknown} raw */
export function normalizeConnectedProviders(raw) {
  if (!Array.isArray(raw)) return [];
  const seen = new Set();
  /** @type {PersonalProviderId[]} */
  const out = [];
  for (const id of raw) {
    if (!isPersonalProviderId(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

/**
 * First-open / unconnected: offer ChatGPT, Claude, or Grok until the user
 * connects one or dismisses the suggestion. Built-in chat is unrelated.
 *
 * @param {{ connectedProviders?: unknown, dismissConnectSuggestion?: unknown }} prefs
 */
export function shouldOfferPersonalConnect(prefs = {}) {
  if (prefs.dismissConnectSuggestion === true) return false;
  return normalizeConnectedProviders(prefs.connectedProviders).length === 0;
}

/** @param {unknown} label */
export function providerLabelMentionsCloud(label) {
  return typeof label === 'string' && /\bcloud\b/i.test(label);
}
