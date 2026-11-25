// src/lib/auth.js - Internet Identity authentication module
import { AuthClient } from '@icp-sdk/auth/client';
import { CONFIG, getTestModeIIBypass } from '$lib/config.js';
import { clearAuthSession, setAuthSession } from '$lib/stores/authSession.js';
import {
  createTestIdentityFromIndex,
  getStoredTestIdentityIndex,
  normalizeTestIdentityIndex,
  setStoredTestIdentityIndex,
  testIdentityLabel,
  testIdentityPrincipal,
} from '$lib/test-identities.js';

const II_URL = CONFIG.internet_identity_url;

console.log(`Using Identity Provider: ${II_URL}`);

const DERIVATION_ORIGIN = CONFIG.ii_derivation_origin || '';
if (DERIVATION_ORIGIN) {
  console.log(`Using II derivationOrigin: ${DERIVATION_ORIGIN}`);
}

/** Default II session: 8 hours (DFINITY recommendation for typical apps). */
const SESSION_DEFAULT_TTL_NS = BigInt(8 * 60 * 60 * 1_000_000_000);
/** Remember-me II session: 7 days. */
const SESSION_REMEMBER_TTL_NS = BigInt(7 * 24 * 60 * 60 * 1_000_000_000);

// Internet Identity's backend canister has this id on mainnet and on icp-cli's
// local network (`ii: true`) alike.
const II_BACKEND_CANISTER_ID = 'rdmx6-jaaaa-aaaaa-aaadq-cai';

/**
 * Where @icp-sdk/auth signs in. Every mainnet II domain is served by the
 * library's default (id.ai); a local II renders its sign-in at `/authorize` and
 * mints through the local replica, whose root key must be fetched.
 */
function identityProviderOptions(iiUrl) {
  const host = new URL(iiUrl).hostname;
  if (!host.endsWith('localhost') && host !== '127.0.0.1') return {};
  return {
    identityProvider: { authorizeUrl: new URL('/authorize', iiUrl).href, canisterId: II_BACKEND_CANISTER_ID },
    agentOptions: { host: window.location.origin, shouldFetchRootKey: true },
  };
}

const REMEMBER_ME_KEY = 'portal:remember_me';

function getRememberMe() {
  try {
    return localStorage.getItem(REMEMBER_ME_KEY) === '1';
  } catch {
    return false;
  }
}

function setRememberMe(value) {
  try {
    localStorage.setItem(REMEMBER_ME_KEY, value ? '1' : '0');
  } catch {
    // storage unavailable
  }
}

let authClient;

let _testIdentity = null;
let _testLoggedIn = false;
let _testIdentityIndex = null;
let _ensureTestAuthPromise = null;

function _normalizeIdentityIndex(index) {
  if (index == null || index === '') return getStoredTestIdentityIndex();
  return normalizeTestIdentityIndex(index);
}

function _readIdentityIndexFromUrl() {
  if (typeof window === 'undefined') return null;
  const raw = new URLSearchParams(window.location.search).get('ti');
  if (raw == null || raw === '') return null;
  return _normalizeIdentityIndex(raw);
}

function _clearIdentityIndexFromUrl() {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (!url.searchParams.has('ti')) return;
  url.searchParams.delete('ti');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

function _publishTestAuth(identity, index) {
  const principal = identity.getPrincipal();
  setAuthSession({
    loading: false,
    isLoggedIn: true,
    principal,
    identityIndex: index,
  });
}

async function _createTestIdentity({ identityIndex = null } = {}) {
  const idx = _normalizeIdentityIndex(identityIndex);
  _testIdentity = createTestIdentityFromIndex(idx);
  _testIdentityIndex = idx;
  setStoredTestIdentityIndex(idx);
  console.log(`[TEST MODE] ${testIdentityLabel(idx)}: ${_testIdentity.getPrincipal().toText()}`);
  return _testIdentity;
}

function _testSessionMatchesIndex(index) {
  if (!_testLoggedIn || !_testIdentity || _testIdentityIndex !== index) return false;
  try {
    return _testIdentity.getPrincipal().toText() === testIdentityPrincipal(index);
  } catch {
    return false;
  }
}

function _createTestAuthClientMock() {
  return {
    isAuthenticated: async () => _testLoggedIn,
    getIdentity: () => _testIdentity,
    logout: async () => {
      _testLoggedIn = false;
      _testIdentity = null;
      _testIdentityIndex = null;
    },
  };
}

export function getTestIdentityIndex() {
  if (_testIdentityIndex != null) return _testIdentityIndex;
  return getStoredTestIdentityIndex();
}

export async function ensureTestAuth() {
  if (!getTestModeIIBypass()) return null;
  if (_ensureTestAuthPromise) return _ensureTestAuthPromise;

  _ensureTestAuthPromise = (async () => {
    const urlIndex = _readIdentityIndexFromUrl();
    if (urlIndex != null) {
      setStoredTestIdentityIndex(urlIndex);
      _clearIdentityIndexFromUrl();
    }
    const index = getStoredTestIdentityIndex();
    if (_testSessionMatchesIndex(index)) {
      _publishTestAuth(_testIdentity, index);
      return { identity: _testIdentity, principal: _testIdentity.getPrincipal() };
    }
    return login({ identityIndex: index });
  })().finally(() => {
    _ensureTestAuthPromise = null;
  });

  return _ensureTestAuthPromise;
}

export async function switchTestIdentity(identityIndex) {
  _ensureTestAuthPromise = null;
  const idx = _normalizeIdentityIndex(identityIndex);
  setStoredTestIdentityIndex(idx);
  _testLoggedIn = false;
  _testIdentity = null;
  _testIdentityIndex = null;
  authClient = null;
  return login({ identityIndex: idx });
}

export function initializeAuthClient() {
  if (getTestModeIIBypass()) {
    if (!authClient) {
      authClient = _createTestAuthClientMock();
      console.log('[TEST MODE] Auth client initialized (mock)');
    }
    return authClient;
  }
  if (!authClient) {
    authClient = new AuthClient({
      ...identityProviderOptions(II_URL),
      // The federation portal signs in on its own origin; only a non-portal
      // build pins the derivation origin, exactly as before.
      ...(!CONFIG.federation_portal && DERIVATION_ORIGIN ? { derivationOrigin: DERIVATION_ORIGIN } : {}),
    });
  }
  return authClient;
}

export async function login({ identityIndex = null, rememberMe = null } = {}) {
  if (getTestModeIIBypass()) {
    const urlParams = new URLSearchParams(window.location.search);
    const asParam = urlParams.get('as');
    const pemParam = urlParams.get('pem');

    let identity;
    let index = getTestIdentityIndex();

    if (asParam && pemParam) {
      const { Secp256k1KeyIdentity } = await import('@icp-sdk/core/identity/secp256k1');
      const decodedPem = decodeURIComponent(pemParam);
      identity = Secp256k1KeyIdentity.fromPem(decodedPem);
      _testIdentity = identity;
      _testIdentityIndex = null;
      console.log(`[TEST MODE] Logged in as ${asParam} with Secp256k1 PEM: ${identity.getPrincipal().toText()}`);
    } else {
      if (asParam) {
        console.warn(`[TEST MODE] ?as=${asParam} present but ?pem= missing — using test identity index`);
      }
      identity = await _createTestIdentity({ identityIndex });
      index = _testIdentityIndex ?? index;
    }

    _testLoggedIn = true;
    authClient = _createTestAuthClientMock();
    const principal = identity.getPrincipal();
    console.log(`[TEST MODE] Logged in with principal: ${principal.toText()}`);
    _publishTestAuth(identity, index);
    return { identity, principal };
  }

  // @icp-sdk/auth opens the Internet Identity window only in the tick of the
  // click that asked for it, and refuses once anything has been awaited: so
  // nothing on the way to signIn() awaits, and callers call login() straight
  // from their click handler.
  const client = initializeAuthClient();

  // Persist remember-me choice so subsequent logins default to it.
  if (rememberMe !== null) {
    setRememberMe(rememberMe);
  }
  const ttl = getRememberMe() ? SESSION_REMEMBER_TTL_NS : SESSION_DEFAULT_TTL_NS;

  try {
    const identity = await client.signIn({ maxTimeToLive: ttl });
    const principal = identity.getPrincipal();
    console.log(`Logged in with principal: ${principal.toText()}`);
    setAuthSession({ loading: false, isLoggedIn: true, principal, identityIndex: 0 });
    return { identity, principal };
  } catch (error) {
    console.error('Login failed:', error);
    return { identity: null, principal: null };
  }
}

export async function logout() {
  if (getTestModeIIBypass()) {
    _testLoggedIn = false;
    _testIdentity = null;
    _testIdentityIndex = null;
    clearAuthSession();
    console.log('[TEST MODE] Logged out');
    return;
  }
  try {
    // Ends the session at Internet Identity, not only in this browser.
    await initializeAuthClient().signOut();
  } catch (error) {
    // This browser is signed out either way; the session at II lasts until it expires.
    console.error('Internet Identity did not end the session:', error);
  }
  clearAuthSession();
}

export async function isAuthenticated() {
  if (getTestModeIIBypass()) {
    return _testLoggedIn;
  }
  return (await getIdentity()) !== null;
}

export async function getPrincipal() {
  return (await getIdentity())?.getPrincipal() ?? null;
}

/**
 * The identity this tab can act as, or null. Signed in means holding an
 * identity: a stored record naming an account this tab cannot act for
 * (expired, revoked at II, held only by another tab) is signed out.
 * @returns {Promise<import('@icp-sdk/core/agent').Identity | null>}
 */
export async function getIdentity() {
  if (getTestModeIIBypass()) {
    return _testLoggedIn && _testIdentity ? _testIdentity : null;
  }
  try {
    const identity = await initializeAuthClient().getIdentity();
    return identity.getPrincipal().isAnonymous() ? null : identity;
  } catch (error) {
    console.warn('[auth] stored session is not usable:', error);
    return null;
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted || !getTestModeIIBypass()) return;
    void ensureTestAuth();
  });
}
