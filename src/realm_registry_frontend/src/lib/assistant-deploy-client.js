import { proveChallenge } from './read-state-proof.js';
import { readAssistantRequest } from './assistant-deploy-request.js';

/** A refusal from ggg-mcp. `status` is the HTTP status; `body` is its JSON, when it sent any. */
export class AssistantRequestError extends Error {
  constructor(status, message, body = {}) {
    super(message);
    this.name = 'AssistantRequestError';
    this.status = status;
    this.body = body;
  }
}

/**
 * The portal's side of ggg-mcp's `/api/mcp/deploy-requests/<id>/…` routes. Every call proves the
 * user's principal first: it fetches a one-use challenge issued for that operation and request,
 * and signs it with the user's Internet Identity. ggg-mcp answers only the user the request is
 * bound to, so a link opened by anyone else leads nowhere.
 *
 * @param {{ origin: string }} deps the ggg-mcp server, e.g. https://geister-mcp.realmsgos.dev
 */
export function createAssistantDeployClient({ origin }) {
  async function call(identity, id, operation, body = {}) {
    const challenge = `${origin}/api/mcp/challenge?operation=deploy_request_${operation}&request_id=${encodeURIComponent(id)}`;
    const { nonce, proof } = await proveChallenge(identity, challenge);
    const res = await fetch(`${origin}/api/mcp/deploy-requests/${encodeURIComponent(id)}/${operation}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nonce, proof, ...body }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new AssistantRequestError(res.status, data?.error || `HTTP ${res.status}`, data);
    return data;
  }

  return {
    /** The request, for the principal in `identity`. */
    async load(identity, id) {
      return readAssistantRequest(await call(identity, id, 'read'));
    },

    /** Take the request for this deployment. Refused (409) while another page holds it. */
    claim(identity, id) {
      return call(identity, id, 'claim');
    },

    /** Tell the assistant which job the user started, and with which final spec. */
    report(identity, id, { jobId, specHash }) {
      return call(identity, id, 'report', { job_id: jobId, spec_hash: specHash });
    },

    /** The user declines the request. */
    cancel(identity, id) {
      return call(identity, id, 'cancel');
    },
  };
}
