import { SUGGESTIONS_API_URL } from './constants.js';

/**
 * @param {{ userPrincipal?: string, contextRealm?: string, persona?: string }} opts
 * @returns {Promise<string[]>}
 */
export async function fetchSuggestions(opts = {}) {
  const params = new URLSearchParams({
    user_principal: opts.userPrincipal || '',
    persona: opts.persona || 'ashoka',
  });
  // Geister still accepts realm_principal; also send context_realm for newer APIs.
  if (opts.contextRealm) {
    params.set('realm_principal', opts.contextRealm);
    params.set('context_realm', opts.contextRealm);
  }
  const response = await fetch(`${SUGGESTIONS_API_URL}?${params}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  return Array.isArray(data.suggestions) ? data.suggestions : [];
}
