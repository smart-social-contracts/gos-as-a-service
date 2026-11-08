import assert from 'node:assert/strict';
import test from 'node:test';
import { Cbor } from '@dfinity/agent';
import { Ed25519KeyIdentity } from '@dfinity/identity';

import { AssistantRequestError, createAssistantDeployClient } from './assistant-deploy-client.js';

const ORIGIN = 'https://mcp.example';
const ID = 'k3JrXz0aQ1m9Wv2nTt8bYp5dHc7LsEuA';
const client = createAssistantDeployClient({ origin: ORIGIN });

const replyBody = {
  id: ID,
  status: 'pending',
  client_name: 'Claude',
  delegate_principal: 'aaaaa-aa',
  note: null,
  expires_at: 1_900_000_000,
  spec_hash: 'ab'.repeat(32),
  spec: {
    name: 'Riverside Commons',
    slug: 'riverside-commons',
    platform: { gos: 'realms-gos', version: 'latest' },
    subnet: { choice: 'automatic' },
    manifesto: 'M',
    welcome_message: 'W',
  },
};

/** Answers the challenge, then the call; records both. */
function mockServer(t, { status = 200, body = { ok: true } } = {}) {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url, init });
    if (String(url).includes('/api/mcp/challenge')) {
      return { ok: true, status: 200, json: async () => ({ nonce: '0a0b' }) };
    }
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  });
  return calls;
}

const envelopeNonce = (proof) =>
  new Uint8Array(Cbor.decode(Uint8Array.from(atob(proof), (c) => c.charCodeAt(0))).content.nonce);

for (const [method, operation] of [
  ['load', 'read'],
  ['claim', 'claim'],
  ['report', 'report'],
  ['cancel', 'cancel'],
]) {
  test(`${method} proves the user with a challenge issued for deploy_request_${operation} and this request`, async (t) => {
    const identity = Ed25519KeyIdentity.generate();
    const calls = mockServer(t, { body: method === 'load' ? replyBody : { ok: true } });

    await client[method](identity, ID, { jobId: 'job_1', specHash: 'cd' });

    assert.equal(
      calls[0].url,
      `${ORIGIN}/api/mcp/challenge?operation=deploy_request_${operation}&request_id=${ID}`,
    );
    assert.equal(calls[1].url, `${ORIGIN}/api/mcp/deploy-requests/${ID}/${operation}`);
    assert.equal(calls[1].init.method, 'POST');
    const body = JSON.parse(calls[1].init.body);
    assert.equal(body.nonce, '0a0b');
    assert.deepEqual(envelopeNonce(body.proof), Uint8Array.from([10, 11]));
  });
}

test('load, claim and cancel send nothing but the proof', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const calls = mockServer(t, { body: replyBody });

  await client.load(identity, ID);
  await client.claim(identity, ID);
  await client.cancel(identity, ID);

  for (const post of calls.filter((c) => c.init)) {
    assert.deepEqual(Object.keys(JSON.parse(post.init.body)).sort(), ['nonce', 'proof']);
  }
});

test('report sends the job id and the hash of the final spec', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  const calls = mockServer(t);

  await client.report(identity, ID, { jobId: 'job_20261108_ab12', specHash: 'cd'.repeat(32) });

  const body = JSON.parse(calls[1].init.body);
  assert.deepEqual(Object.keys(body).sort(), ['job_id', 'nonce', 'proof', 'spec_hash']);
  assert.equal(body.job_id, 'job_20261108_ab12');
  assert.equal(body.spec_hash, 'cd'.repeat(32));
});

test('load returns the request cleaned up', async (t) => {
  mockServer(t, { body: { ...replyBody, extra: 'ignored' } });

  const request = await client.load(Ed25519KeyIdentity.generate(), ID);

  assert.equal(request.clientName, 'Claude');
  assert.equal(request.extra, undefined);
});

test('the request id is escaped in both URLs', async (t) => {
  const calls = mockServer(t);

  await client.cancel(Ed25519KeyIdentity.generate(), 'a/b?c');

  assert.match(calls[0].url, /request_id=a%2Fb%3Fc$/);
  assert.equal(calls[1].url, `${ORIGIN}/api/mcp/deploy-requests/a%2Fb%3Fc/cancel`);
});

test('a refusal carries its status and body', async (t) => {
  mockServer(t, { status: 409, body: { error: 'already claimed', status: 'claimed' } });

  await assert.rejects(
    () => client.claim(Ed25519KeyIdentity.generate(), ID),
    (err) => {
      assert.ok(err instanceof AssistantRequestError);
      assert.equal(err.status, 409);
      assert.equal(err.body.status, 'claimed');
      assert.equal(err.message, 'already claimed');
      return true;
    },
  );
});

test('a refusal without a JSON body still says its status', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) =>
    String(url).includes('/api/mcp/challenge')
      ? { ok: true, status: 200, json: async () => ({ nonce: '0a' }) }
      : { ok: false, status: 502, json: async () => Promise.reject(new Error('not json')) },
  );

  await assert.rejects(() => client.cancel(Ed25519KeyIdentity.generate(), ID), { status: 502, message: 'HTTP 502' });
});

test('no call is made when the challenge is refused', async (t) => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url) => {
    calls.push(url);
    return { ok: false, status: 429, json: async () => ({}) };
  });

  await assert.rejects(() => client.cancel(Ed25519KeyIdentity.generate(), ID), /challenge: HTTP 429/);
  assert.equal(calls.length, 1);
});
