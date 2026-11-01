import { aiFetch } from './ai-fetch.js';
import { SUGGESTIONS_API_URL } from './constants.js';

// Suggestions are optional: give up rather than keep the panel on "Loading suggestions…".
const SUGGESTIONS_TIMEOUT_MS = 20_000;

/**
 * @param {{ contextRealm?: string, persona?: string }} opts
 * @returns {Promise<string[]>}
 */
export async function fetchSuggestions(opts = {}) {
  const params = new URLSearchParams({ persona: opts.persona || 'ashoka' });
  // Geister still accepts realm_principal; also send context_realm for newer APIs.
  if (opts.contextRealm) {
    params.set('realm_principal', opts.contextRealm);
    params.set('context_realm', opts.contextRealm);
  }
  const response = await aiFetch(`${SUGGESTIONS_API_URL}?${params}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(SUGGESTIONS_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  return Array.isArray(data.suggestions) ? data.suggestions : [];
}
