/**
 * Deterministic test identities for II-bypass mode.
 *
 * Seed layout (32 bytes): [0xED, 0x57, index₀, index₁, index₂, index₃, 0, …]
 *
 * Optional deploy-time overrides (via /canister_ids.js):
 *   - globalThis.__TEST_IDENTITY_PEms = string[] — PEM strings used for login
 *
 * Reference roster (indices 0–9): config/deterministic-test-identity-principals.json
 */

import { Ed25519KeyIdentity, Secp256k1KeyIdentity } from '@dfinity/identity';

export const TEST_IDENTITY_SESSION_KEY = 'test_identity_index';
export const TEST_IDENTITY_MAGIC = [0xed, 0x57];
/** Indices 0–1 shown as fixed cards in the picker (Identity 1–2). */
export const TEST_IDENTITY_FIXED_PICKER_MAX_INDEX = 1;
/** @deprecated alias for fixed picker cards */
export const TEST_IDENTITY_PICKER_MAX_INDEX = TEST_IDENTITY_FIXED_PICKER_MAX_INDEX;
/** Highest supported identity index (human Identity number = index + 1). */
export const TEST_IDENTITY_MAX_INDEX = 0xffffffff;

export function testIdentityNumber(index) {
  return index + 1;
}

export function testIdentityLabel(index) {
  if (index === 0) return 'Identity 1 (Creator)';
  return `Identity ${index + 1}`;
}

/** @param {number} index */
export function testIdentitySeed(index) {
  const seed = new Uint8Array(32);
  seed[0] = TEST_IDENTITY_MAGIC[0];
  seed[1] = TEST_IDENTITY_MAGIC[1];
  seed[2] = index & 0xff;
  seed[3] = (index >>> 8) & 0xff;
  seed[4] = (index >>> 16) & 0xff;
  seed[5] = (index >>> 24) & 0xff;
  return seed;
}

/** @param {string} raw */
function decodePem(raw) {
  const trimmed = String(raw || '').trim();
  if (!trimmed) return '';
  if (trimmed.includes('BEGIN')) return trimmed;
  try {
    return atob(trimmed.replace(/-/g, '+').replace(/_/g, '/'));
  } catch {
    return trimmed;
  }
}

function expectedPrincipal(index) {
  const principals = globalThis.__TEST_IDENTITY_PRINCIPALS;
  if (!Array.isArray(principals) || !principals[index]) return '';
  return String(principals[index]);
}

/** @param {number} index */
export function createTestIdentityFromIndex(index) {
  const pems = globalThis.__TEST_IDENTITY_PEms;
  const pemRaw = Array.isArray(pems) && pems[index] ? String(pems[index]) : '';
  if (pemRaw) {
    const pem = decodePem(pemRaw);
    const identity = Secp256k1KeyIdentity.fromPem(pem);
    const expected = expectedPrincipal(index);
    if (expected && identity.getPrincipal().toText() !== expected) {
      throw new Error(
        `${testIdentityLabel(index)} PEM principal ${identity.getPrincipal().toText()} does not match configured ${expected}`,
      );
    }
    return identity;
  }
  return Ed25519KeyIdentity.generate(testIdentitySeed(index));
}

/** @param {number} index */
export function testIdentityPrincipal(index) {
  return createTestIdentityFromIndex(index).getPrincipal().toText();
}

/** @param {string} principal */
export function shortPrincipal(principal) {
  if (!principal || principal.length < 12) return principal || '';
  return `${principal.slice(0, 8)}…${principal.slice(-8)}`;
}

/** @param {number} index */
export function normalizeTestIdentityIndex(index) {
  const parsed = Math.floor(Number(index));
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(TEST_IDENTITY_MAX_INDEX, parsed));
}

/** @param {number} identityNumber 1-based human identity number */
export function identityNumberToIndex(identityNumber) {
  return normalizeTestIdentityIndex(Number(identityNumber) - 1);
}

/** @param {number} identityNumber 1-based human identity number */
export function isValidCustomIdentityNumber(identityNumber) {
  const parsed = Math.floor(Number(identityNumber));
  if (!Number.isFinite(parsed)) return false;
  const minCustom = testIdentityNumber(TEST_IDENTITY_FIXED_PICKER_MAX_INDEX + 1);
  const maxCustom = testIdentityNumber(TEST_IDENTITY_MAX_INDEX);
  return parsed >= minCustom && parsed <= maxCustom;
}

/**
 * @param {number} index
 * @returns {{ index: number, label: string, principal: string, loginPrincipal: string, description: string, hasPem: boolean }}
 */
export function getTestIdentityPersona(index) {
  const normalized = normalizeTestIdentityIndex(index);
  const pems = globalThis.__TEST_IDENTITY_PEms;
  const hasPem = Array.isArray(pems) && !!pems[normalized];
  const configured = expectedPrincipal(normalized);
  let loginPrincipal = '';
  try {
    loginPrincipal = testIdentityPrincipal(normalized);
  } catch {
    loginPrincipal = '';
  }
  return {
    index: normalized,
    label: testIdentityLabel(normalized),
    principal: configured || loginPrincipal,
    loginPrincipal,
    hasPem,
    description:
      normalized === 0
        ? 'Default registry persona (Identity 1)'
        : `Deterministic test member ${testIdentityNumber(normalized)}`,
  };
}

export function getStoredTestIdentityIndex() {
  if (typeof sessionStorage === 'undefined') return 0;
  const raw = sessionStorage.getItem(TEST_IDENTITY_SESSION_KEY);
  if (raw == null) return 0;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return 0;
  return normalizeTestIdentityIndex(parsed);
}

export function setStoredTestIdentityIndex(index) {
  if (typeof sessionStorage === 'undefined') return;
  sessionStorage.setItem(TEST_IDENTITY_SESSION_KEY, String(normalizeTestIdentityIndex(index)));
}

export function clearStoredTestIdentityIndex() {
  if (typeof sessionStorage === 'undefined') return;
  sessionStorage.removeItem(TEST_IDENTITY_SESSION_KEY);
}

/**
 * Fixed picker cards (Identity 1–2 by default).
 * @returns {{ index: number, label: string, principal: string, loginPrincipal: string, description: string, hasPem: boolean }[]}
 */
export function listTestIdentities(maxIndex = TEST_IDENTITY_FIXED_PICKER_MAX_INDEX) {
  const items = [];
  for (let index = 0; index <= maxIndex; index++) {
    items.push(getTestIdentityPersona(index));
  }
  return items;
}
