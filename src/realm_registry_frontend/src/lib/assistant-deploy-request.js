/**
 * A realm that an AI assistant prepared for its user (ggg-mcp `request_realm_deployment`).
 *
 * The assistant never sends a manifest. ggg-mcp keeps the wizard's answers (the "spec") for one
 * hour; the deploy wizard loads them into its form and the user's own session deploys. These
 * functions turn that spec into form data and back, and nothing else: whatever else a reply
 * carries is dropped here, so only the six fields below ever reach the form.
 */
import { realmTexts, slugify } from './deployment-manifest-core.js';
import { getGosImplementation } from './gos-implementations.js';

export const ASSISTANT_REQUEST_PARAM = 'assistant_request';

// 24 random bytes in URL-safe text: exactly 32 characters. ggg-mcp refuses any other length.
const REQUEST_ID = /^[A-Za-z0-9_-]{32}$/;
const SUBNET_CHOICES = ['automatic', 'european', 'other'];
const STATUSES = ['pending', 'claimed', 'deployed'];

// The assistant picks its own name and note, so what the page shows of them is capped, and stripped of
// the characters that could reorder or hide what the user reads next to them: control characters, the
// bidirectional and zero-width "format" characters, line and paragraph separators.
const MAX_CLIENT_NAME = 64;
const MAX_NOTE = 500;
const INVISIBLE = /[\p{Cc}\p{Cf}\u2028\u2029]/gu;
const INVISIBLE_BUT_NEWLINES = /[\p{Cf}\u2028\u2029]|(?![\n\t])\p{Cc}/gu;
// A principal is lowercase letters, digits and dashes.
const PRINCIPAL = /^[a-z0-9-]{1,100}$/;

/**
 * @param {URLSearchParams} searchParams
 * @returns {{ active: boolean, id: string }} `active` when the link names a request at all;
 *   `id` is empty when that name is not an id (the page then says the link is not valid).
 */
export function parseAssistantRequestParam(searchParams) {
  const raw = searchParams.get(ASSISTANT_REQUEST_PARAM);
  if (raw === null) return { active: false, id: '' };
  const id = raw.trim();
  return { active: true, id: REQUEST_ID.test(id) ? id : '' };
}

function isText(value) {
  return typeof value === 'string';
}

/** At most `max` characters of `text` without the invisible ones. */
function shown(text, pattern, max) {
  return Array.from(text.replace(pattern, '').trim()).slice(0, max).join('');
}

function readSpec(raw) {
  const { name, slug, platform, subnet, manifesto, welcome_message } = raw || {};
  const valid =
    [name, slug, manifesto, welcome_message, platform?.gos, platform?.version].every(isText) &&
    getGosImplementation(platform.gos)?.available === true &&
    SUBNET_CHOICES.includes(subnet?.choice) &&
    (subnet.choice !== 'other' || isText(subnet.subnet_id));
  if (!valid) throw new Error('The assistant request is malformed.');
  return {
    name,
    slug,
    platform: { gos: platform.gos, version: platform.version },
    subnet: subnet.choice === 'other' ? { choice: 'other', subnet_id: subnet.subnet_id } : { choice: subnet.choice },
    manifesto,
    welcome_message,
  };
}

/**
 * Keep only the fields the page uses, checked and capped.
 * @param {any} raw the JSON ggg-mcp answered to a read
 */
export function readAssistantRequest(raw) {
  if (!raw || !isText(raw.id) || !STATUSES.includes(raw.status) || !Number.isFinite(raw.expires_at)) {
    throw new Error('The assistant request is malformed.');
  }
  return {
    id: raw.id,
    status: raw.status,
    clientName: shown(isText(raw.client_name) ? raw.client_name : '', INVISIBLE, MAX_CLIENT_NAME),
    delegatePrincipal: isText(raw.delegate_principal) && PRINCIPAL.test(raw.delegate_principal) ? raw.delegate_principal : '',
    note: shown(isText(raw.note) ? raw.note : '', INVISIBLE_BUT_NEWLINES, MAX_NOTE),
    expiresAt: raw.expires_at,
    // When the user's Launch took the request, and until when that claim holds; 0 when ggg-mcp did not say.
    claimedAt: Number.isFinite(raw.claimed_at) ? raw.claimed_at : 0,
    leaseExpiresAt: Number.isFinite(raw.lease_expires_at) ? raw.lease_expires_at : 0,
    specHash: isText(raw.spec_hash) ? raw.spec_hash : '',
    jobId: isText(raw.job_id) ? raw.job_id : '',
    spec: readSpec(raw.spec),
  };
}

/** @param {number} expiresAt unix seconds */
export function isExpired(expiresAt, nowMs = Date.now()) {
  return nowMs >= expiresAt * 1000;
}

const withoutV = (version) => version.trim().replace(/^v/, '');

/**
 * The catalog option for `version`, however either side spells it ("0.8.0" or "v0.8.0"); "" when there
 * is none. ggg-mcp turns "latest" into a concrete version when it files the request, so a literal
 * "latest" matches nothing and the user is sent to pick a version.
 * @param {Array<{ value: string }>} options the wizard's version options
 */
export function matchDeployVersion(options, version) {
  return options.find((option) => withoutV(option.value) === withoutV(version))?.value ?? '';
}

/**
 * The form as the spec asks for it. `deploy_version` is the spec's spelling: the page swaps it for the
 * catalog option that matches (matchDeployVersion).
 * @param {ReturnType<typeof readAssistantRequest>['spec']} spec
 */
export function formDataFromSpec(spec) {
  return {
    gos_implementation: spec.platform.gos,
    name: spec.name,
    slug: spec.slug,
    deploy_version: spec.platform.version,
    subnet_choice: spec.subnet.choice,
    subnet_id: spec.subnet.choice === 'other' ? spec.subnet.subnet_id : '',
    manifesto: spec.manifesto,
    welcome_message: spec.welcome_message,
  };
}

/**
 * What the form will deploy, in the spec's shape. A version the user did not change keeps the
 * spelling the assistant used, so an untouched form has the original's hash.
 */
export function specFromFormData(formData, original) {
  const name = (formData.name || '').trim();
  const version =
    withoutV(formData.deploy_version) === withoutV(original.platform.version)
      ? original.platform.version
      : formData.deploy_version;
  const choice = formData.subnet_choice;
  return {
    name,
    slug: slugify((formData.slug || '').trim() || name),
    platform: { gos: formData.gos_implementation, version },
    subnet: choice === 'other' ? { choice, subnet_id: (formData.subnet_id || '').trim() } : { choice },
    ...realmTexts(formData),
  };
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sortKeys(value[key])]),
    );
  }
  return value;
}

/**
 * Hex sha256 of the spec's JSON with sorted keys and no spaces, UTF-8. ggg-mcp hashes the original
 * the same way (Python: json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)),
 * and tells the assistant "deployed, with your changes" when the two hashes differ.
 */
export async function specHash(spec) {
  const bytes = new TextEncoder().encode(JSON.stringify(sortKeys(spec)));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
