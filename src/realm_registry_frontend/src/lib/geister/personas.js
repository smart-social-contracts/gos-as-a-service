import { ASSISTANTS_API_URL } from './constants.js';

/**
 * @typedef {{ id: string, name: string, emoji?: string, description?: string }} AssistantPersona
 */

/**
 * @returns {Promise<AssistantPersona[]>}
 */
export async function fetchAssistants() {
  const response = await fetch(ASSISTANTS_API_URL, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  return Array.isArray(data.assistants) ? data.assistants : [];
}

/**
 * @returns {Promise<'online'|'offline'>}
 */
export async function checkApiStatus() {
  try {
    const res = await fetch(ASSISTANTS_API_URL, {
      method: 'HEAD',
      signal: AbortSignal.timeout(5000),
    });
    return res.ok ? 'online' : 'offline';
  } catch {
    return 'offline';
  }
}
