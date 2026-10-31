import { proveChallenge } from '../read-state-proof.js';

// Renew a little early so a token never expires between the check and the request.
const RENEW_MARGIN_MS = 60_000;

export const SIGN_IN_REQUIRED_MESSAGE = 'Sign in to use the assistant.';

export class SignInRequiredError extends Error {
  constructor() {
    super(SIGN_IN_REQUIRED_MESSAGE);
    this.name = 'SignInRequiredError';
  }
}

/**
 * ggg-ai only answers a user who holds a session token, which it issues for a proof of the
 * user's principal (ggg-ai/docs/browser-proof.md). This keeps one token per signed-in user and
 * renews it when it expires.
 *
 * @param {{ origin: string, getIdentity: () => Promise<import('@dfinity/agent').SignIdentity | null> }} deps
 */
export function createAiSession({ origin, getIdentity }) {
  /** @type {{ token: string, principal: string, expiresAt: number } | null} */
  let session = null;
  /** @type {Promise<void> | null} */
  let opening = null;

  async function open(identity) {
    const { nonce, proof } = await proveChallenge(identity, `${origin}/api/auth/challenge`);
    const res = await fetch(`${origin}/api/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nonce, proof }),
    });
    if (!res.ok) throw new Error(`Could not sign in to the assistant (HTTP ${res.status}).`);
    const { token, principal, expires_in } = await res.json();
    session = { token, principal, expiresAt: Date.now() + expires_in * 1000 };
  }

  async function token(identity) {
    const usable =
      session &&
      session.principal === identity.getPrincipal().toText() &&
      Date.now() < session.expiresAt - RENEW_MARGIN_MS;
    if (!usable) {
      // Calls that start together (history, suggestions) share one sign-in.
      opening ??= open(identity).finally(() => (opening = null));
      await opening;
    }
    return session.token;
  }

  /**
   * `fetch` with the session token. Signed out: throws SignInRequiredError.
   * @param {string} url
   * @param {RequestInit} [init]
   */
  async function aiFetch(url, init = {}) {
    const identity = await getIdentity();
    if (!identity) throw new SignInRequiredError();
    const send = async () =>
      fetch(url, {
        ...init,
        headers: { ...init.headers, Authorization: `Bearer ${await token(identity)}` },
      });
    const res = await send();
    if (res.status !== 401) return res;
    // The server dropped the session (expired, or it restarted): sign in once more.
    session = null;
    return send();
  }

  return aiFetch;
}
