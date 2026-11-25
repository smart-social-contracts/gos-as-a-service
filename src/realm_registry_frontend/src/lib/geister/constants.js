import { CONFIG } from '$lib/config.js';
import { resolveGeisterApiOrigin } from '$lib/config-resolvers.js';
import { runtimeCanisterIds } from '$lib/network.js';

const viteEnv = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {};

/** The Geister API this deployment's assistant talks to; "" when it has none (a local stack). */
export const GEISTER_API_ORIGIN = resolveGeisterApiOrigin(
  viteEnv,
  runtimeCanisterIds(),
  CONFIG.deploy_queue_network,
);
/** False when there is no Geister API: the assistant then makes no request at all. */
export const GEISTER_API_AVAILABLE = GEISTER_API_ORIGIN !== '';
export const GEISTER_API_UNAVAILABLE_MESSAGE =
  'This deployment has no assistant service: its /canister_ids.js declares no geister_api_url.';
const API_HOST = `${GEISTER_API_ORIGIN}/`;
export const API_URL = `${API_HOST}api/ask`;
export const SUGGESTIONS_API_URL = `${API_HOST}suggestions`;
export const ASSISTANTS_API_URL = `${API_HOST}api/personas/assistants`;
export const CONVERSATIONS_API_URL = `${API_HOST}api/conversations`;
/** Same Geister MCP connector URL used by Connect Claude (and any MCP client). */
export const MCP_URL = 'https://geister-mcp.realmsgos.dev/mcp';
/** The Geister MCP server's origin. A local end-to-end build sets VITE_GEISTER_MCP_ORIGIN to a local one. */
export const MCP_ORIGIN =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_GEISTER_MCP_ORIGIN) ||
  'https://geister-mcp.realmsgos.dev';
export const CHAT_REQUEST_TIMEOUT_MS = 360_000;

/** Geister network for this registry deploy. */
export function geisterNetwork() {
  return CONFIG.default_deploy_queue_network || '';
}
