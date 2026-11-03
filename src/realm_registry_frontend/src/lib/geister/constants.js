import { CONFIG } from '$lib/config.js';

export const GEISTER_API_ORIGIN = 'http://localhost:8733';
export const PRODUCTION_API_HOST = `${GEISTER_API_ORIGIN}/`;
export const API_URL = `${PRODUCTION_API_HOST}api/ask`;
export const SUGGESTIONS_API_URL = `${PRODUCTION_API_HOST}suggestions`;
export const ASSISTANTS_API_URL = `${PRODUCTION_API_HOST}api/personas/assistants`;
export const CONVERSATIONS_API_URL = `${PRODUCTION_API_HOST}api/conversations`;
/** Same Geister MCP connector URL used by Connect Claude (and any MCP client). */
export const MCP_URL = 'http://localhost:8732/mcp';
export const CHAT_REQUEST_TIMEOUT_MS = 360_000;

/** Geister network for this registry deploy. */
export function geisterNetwork() {
  return CONFIG.default_deploy_queue_network || '';
}
