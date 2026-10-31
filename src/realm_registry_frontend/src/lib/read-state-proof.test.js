import assert from 'node:assert/strict';
import test from 'node:test';
import { Cbor } from '@dfinity/agent';
import { Ed25519KeyIdentity } from '@dfinity/identity';

import { hexToBytes, proveChallenge, requestIdNonce, signProof } from './read-state-proof.js';

const decodeEnvelope = (proof) => Cbor.decode(Uint8Array.from(atob(proof), (c) => c.charCodeAt(0)));

test('signProof signs a read_state request for the path "time" carrying the nonce', async () => {
  const identity = Ed25519KeyIdentity.generate();
  const nonce = Uint8Array.from([1, 2, 3, 4]);

  const envelope = decodeEnvelope(await signProof(identity, nonce));

  assert.equal(envelope.content.request_type, 'read_state');
  assert.deepEqual(new Uint8Array(envelope.content.sender), identity.getPrincipal().toUint8Array());
  assert.deepEqual(envelope.content.paths.map((path) => path.map((label) => new TextDecoder().decode(label))), [
    ['time'],
  ]);
  assert.deepEqual(new Uint8Array(envelope.content.nonce), nonce);
  assert.deepEqual(new Uint8Array(envelope.sender_pubkey), new Uint8Array(identity.getPublicKey().toDer()));
  assert.ok(envelope.sender_sig.byteLength > 0);
});

test('signProof expires within the 5 minutes the IC accepts', async () => {
  const identity = Ed25519KeyIdentity.generate();

  const { content } = decodeEnvelope(await signProof(identity, new Uint8Array(1)));

  const expiresInMs = Number(BigInt(content.ingress_expiry) / 1_000_000n) - Date.now();
  assert.ok(expiresInMs > 0 && expiresInMs <= 5 * 60 * 1000, `expires in ${expiresInMs} ms`);
});

test('hexToBytes decodes a hex challenge', () => {
  assert.deepEqual(hexToBytes('00ff10'), Uint8Array.from([0, 255, 16]));
});

test('requestIdNonce is the SHA-256 of the request id', async () => {
  const nonce = await requestIdNonce('abc');

  assert.equal(
    Buffer.from(nonce).toString('hex'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  );
});

test('proveChallenge signs the challenge the server issued', async (t) => {
  const identity = Ed25519KeyIdentity.generate();
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url, 'https://ai.example/api/auth/challenge');
    return { ok: true, json: async () => ({ nonce: '0a0b' }) };
  });

  const { nonce, proof } = await proveChallenge(identity, 'https://ai.example/api/auth/challenge');

  assert.equal(nonce, '0a0b');
  assert.deepEqual(new Uint8Array(decodeEnvelope(proof).content.nonce), Uint8Array.from([10, 11]));
});

test('proveChallenge fails when the server refuses a challenge', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 429 }));

  await assert.rejects(
    proveChallenge(Ed25519KeyIdentity.generate(), 'https://ai.example/api/auth/challenge'),
    /HTTP 429/,
  );
});
