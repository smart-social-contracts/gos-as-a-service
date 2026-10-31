import { getIdentity } from '$lib/auth.js';
import { GEISTER_API_ORIGIN } from './constants.js';
import { createAiSession } from './session.js';

/** `fetch` for ggg-ai: adds the signed-in user's session token. */
export const aiFetch = createAiSession({ origin: GEISTER_API_ORIGIN, getIdentity });
