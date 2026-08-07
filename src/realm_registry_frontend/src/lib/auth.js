// src/lib/auth.js - Internet Identity authentication module
import { AuthClient } from '@dfinity/auth-client';
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

export async function initializeAuthClient() {
  if (getTestModeIIBypass()) {
    if (!authClient) {
      authClient = _createTestAuthClientMock();
      console.log('[TEST MODE] Auth client initialized (mock)');
    }
    return authClient;
  }
  if (!authClient) {
    authClient = await AuthClient.create();
  }
  return authClient;
}

export async function login({ identityIndex = null } = {}) {
  if (getTestModeIIBypass()) {
    const urlParams = new URLSearchParams(window.location.search);
    const asParam = urlParams.get('as');
    const pemParam = urlParams.get('pem');

    let identity;
    let index = getTestIdentityIndex();

    if (asParam && pemParam) {
      const { Secp256k1KeyIdentity } = await import('@dfinity/identity');
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

  const client = await initializeAuthClient();

  return new Promise((resolve) => {
    const loginOpts = {
      identityProvider: II_URL,
      onSuccess: () => {
        const identity = client.getIdentity();
        const principal = identity.getPrincipal();
        console.log(`Logged in with principal: ${principal.toText()}`);
        setAuthSession({ loading: false, isLoggedIn: true, principal, identityIndex: 0 });
        resolve({ identity, principal });
      },
      onError: (error) => {
        console.error('Login failed:', error);
        resolve({ identity: null, principal: null });
      },
    };
    if (!CONFIG.federation_portal && DERIVATION_ORIGIN) {
      loginOpts.derivationOrigin = DERIVATION_ORIGIN;
    }
    client.login(loginOpts);
  });
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
  const client = await initializeAuthClient();
  await client.logout();
  clearAuthSession();
}

export async function isAuthenticated() {
  if (getTestModeIIBypass()) {
    return _testLoggedIn;
  }
  const client = await initializeAuthClient();
  return client.isAuthenticated();
}

export async function getPrincipal() {
  const client = await initializeAuthClient();
  if (getTestModeIIBypass()) {
    return _testLoggedIn && _testIdentity ? _testIdentity.getPrincipal() : null;
  }
  if (await client.isAuthenticated()) {
    return client.getIdentity().getPrincipal();
  }
  return null;
}

/** @returns {Promise<import('@dfinity/agent').Identity | null>} */
export async function getIdentity() {
  if (getTestModeIIBypass()) {
    return _testLoggedIn && _testIdentity ? _testIdentity : null;
  }
  const client = await initializeAuthClient();
  if (await client.isAuthenticated()) {
    return client.getIdentity();
  }
  return null;
}

if (typeof window !== 'undefined') {
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted || !getTestModeIIBypass()) return;
    void ensureTestAuth();
  });
}
