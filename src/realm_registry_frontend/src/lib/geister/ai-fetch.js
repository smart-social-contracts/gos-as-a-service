import { getIdentity } from '$lib/auth.js';
import { GEISTER_API_AVAILABLE, GEISTER_API_ORIGIN, GEISTER_API_UNAVAILABLE_MESSAGE } from './constants.js';
import { createAiSession } from './session.js';

/**
 * `fetch` for ggg-ai: adds the signed-in user's session token. With no Geister API it refuses, rather
 * than let a relative url reach the portal's own origin.
 */
export const aiFetch = GEISTER_API_AVAILABLE
  ? createAiSession({ origin: GEISTER_API_ORIGIN, getIdentity })
  : async () => {
      throw new Error(GEISTER_API_UNAVAILABLE_MESSAGE);
    };
