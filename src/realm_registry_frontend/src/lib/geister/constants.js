import { CONFIG } from '$lib/config.js';

export const PRODUCTION_API_HOST = 'https://geister-api.realmsgos.dev/';
export const API_URL = `${PRODUCTION_API_HOST}api/ask`;
export const SUGGESTIONS_API_URL = `${PRODUCTION_API_HOST}suggestions`;
export const ASSISTANTS_API_URL = `${PRODUCTION_API_HOST}api/personas/assistants`;
export const CONVERSATIONS_API_URL = `${PRODUCTION_API_HOST}api/conversations`;
export const CHAT_REQUEST_TIMEOUT_MS = 360_000;

/** Geister network for this registry deploy. */
export function geisterNetwork() {
  return CONFIG.default_deploy_queue_network || 'staging';
}
