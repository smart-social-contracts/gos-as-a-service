import assert from 'node:assert/strict';
import test from 'node:test';
import { Ed25519KeyIdentity } from '@dfinity/identity';

import { createAiSession, SignInRequiredError } from './session.js';

const ORIGIN = 'https://ai.example';

/** A ggg-ai that issues session tokens `token-1`, `token-2`, … and accepts the latest. */
function fakeServer(t, identity, { expiresIn = 3600 } = {}) {
  const server = { sessionsOpened: 0, calls: [], validToken: null };
  t.mock.method(globalThis, 'fetch', async (url, init = {}) => {
    server.calls.push(url);
    if (url === `${ORIGIN}/api/auth/challenge`) return { ok: true, json: async () => ({ nonce: '0a0b' }) };
    if (url === `${ORIGIN}/api/auth/session`) {
      server.sessionsOpened += 1;
      server.validToken = `token-${server.sessionsOpened}`;
      const principal = identity.getPrincipal().toText();
      return { ok: true, json: async () => ({ token: server.validToken, principal, expires_in: expiresIn }) };
    }
    const accepted = init.headers.Authorization === `Bearer ${server.validToken}`;
    return { ok: accepted, status: accepted ? 200 : 401 };
  });
  return server;
}

const sessionFor = (identity) => createAiSession({ origin: ORIGIN, getIdentity: async () => identity });

test('signed out: throws SignInRequiredError without calling the server', async (t) => {
  const server = fakeServer(t, null);

  await assert.rejects(sessionFor(null)(`${ORIGIN}/api/ask`), SignInRequiredError);

  assert.deepEqual(server.calls, []);
});

test('signs in once and sends the Bearer token on every call', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const server = fakeServer(t, identity);
  const aiFetch = sessionFor(identity);

  await aiFetch(`${ORIGIN}/api/conversations`);
  await aiFetch(`${ORIGIN}/api/suggestions`);

  assert.equal(server.sessionsOpened, 1);
  assert.equal(fetch.mock.calls.at(-1).arguments[1].headers.Authorization, 'Bearer token-1');
});

test('calls that start together share one sign-in', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const server = fakeServer(t, identity);
  const aiFetch = sessionFor(identity);

  await Promise.all([aiFetch(`${ORIGIN}/api/conversations`), aiFetch(`${ORIGIN}/api/suggestions`)]);

  assert.equal(server.sessionsOpened, 1);
});

test('renews a token that is about to expire', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const server = fakeServer(t, identity, { expiresIn: 30 });
  const aiFetch = sessionFor(identity);

  await aiFetch(`${ORIGIN}/api/conversations`);
  await aiFetch(`${ORIGIN}/api/conversations`);

  assert.equal(server.sessionsOpened, 2);
});

test('on a 401, signs in again and retries once', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const server = fakeServer(t, identity);
  const aiFetch = sessionFor(identity);
  await aiFetch(`${ORIGIN}/api/conversations`);
  server.validToken = 'forgotten-by-the-server';

  const res = await aiFetch(`${ORIGIN}/api/conversations`);

  assert.equal(res.status, 200);
  assert.equal(server.sessionsOpened, 2);
});

test('a 401 that survives the retry is returned to the caller', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const principal = identity.getPrincipal().toText();
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (url.endsWith('/challenge')) return { ok: true, json: async () => ({ nonce: '0a0b' }) };
    if (url.endsWith('/session')) return { ok: true, json: async () => ({ token: 't', principal, expires_in: 3600 }) };
    return { ok: false, status: 401 };
  });

  const res = await sessionFor(identity)(`${ORIGIN}/api/conversations`);

  assert.equal(res.status, 401);
});
