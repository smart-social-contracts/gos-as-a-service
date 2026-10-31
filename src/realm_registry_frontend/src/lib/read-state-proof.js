import { Cbor, Expiry } from '@dfinity/agent';

/**
 * A "proof" shows the Geister servers (ggg-mcp, ggg-ai) which principal is asking: a read_state
 * request for the path `time`, signed with the user's Internet Identity and sent to them instead of
 * the IC. The server relays it to a replica, which checks the signature and the delegation chain.
 * See ggg-mcp/docs/browser-proof.md.
 *
 * Keep this inside the portal's own code. A proof lets whoever holds it act as the user on the Geister
 * servers, so never offer "sign this nonce" to iframes (realm frontends), extensions or a postMessage
 * bridge: each flow fetches its own challenge from the server URL it configures and signs only that.
 */

// The IC accepts an ingress expiry at most 5 minutes ahead.
const PROOF_VALIDITY_MS = 4 * 60 * 1000;

/**
 * @param {import('@dfinity/agent').SignIdentity} identity
 * @param {Uint8Array} nonce the server's challenge, at most 32 bytes
 * @returns {Promise<string>} base64 of the CBOR envelope
 */
export async function signProof(identity, nonce) {
  const content = {
    request_type: 'read_state',
    sender: identity.getPrincipal(),
    // Exactly this path: the servers reject any other.
    paths: [[new TextEncoder().encode('time')]],
    ingress_expiry: Expiry.fromDeltaInMilliseconds(PROOF_VALIDITY_MS),
    nonce,
  };
  const { body } = await identity.transformRequest({ endpoint: 'read_state', body: content });
  return btoa(String.fromCharCode(...Cbor.encode(body)));
}

/** @param {string} hex */
export function hexToBytes(hex) {
  return Uint8Array.from(hex.match(/../g) || [], (byte) => parseInt(byte, 16));
}

/**
 * The consent page's challenge is derived from the request, so there is nothing to fetch.
 * @param {string} requestId
 * @returns {Promise<Uint8Array>}
 */
export async function requestIdNonce(requestId) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(requestId));
  return new Uint8Array(digest);
}

/**
 * Fetch a one-use challenge from `challengeUrl` and sign it.
 * @param {import('@dfinity/agent').SignIdentity} identity
 * @param {string} challengeUrl
 * @returns {Promise<{ nonce: string, proof: string }>} the challenge (hex) and the proof for it
 */
export async function proveChallenge(identity, challengeUrl) {
  const res = await fetch(challengeUrl);
  if (!res.ok) throw new Error(`challenge: HTTP ${res.status}`);
  const { nonce } = await res.json();
  return { nonce, proof: await signProof(identity, hexToBytes(nonce)) };
}
