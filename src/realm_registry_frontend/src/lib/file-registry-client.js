// Browser-side client for the file_registry canister — adapted for the
// realm_registry_frontend auth module.
//
// Handles uploading images (logo, background) in chunks and publishing
// the namespace so the realm_installer can later read them on-chain.

import { Actor, HttpAgent } from '@dfinity/agent';
import { IDL } from '@dfinity/candid';
import { Principal } from '@dfinity/principal';
import { initializeAuthClient } from './auth';

// Match CLI publish limits (extension.py): keep raw chunks at 64 KiB so JSON +
// base64 decode stays under the WASI Python per-message instruction budget.
const CHUNK_BYTES = 64 * 1024;

const fileRegistryIdlFactory = ({ IDL: idl }) =>
  idl.Service({
    store_file_chunk: idl.Func([idl.Text], [idl.Text], []),
    finalize_chunked_file_step: idl.Func([idl.Text], [idl.Text], []),
    publish_namespace: idl.Func([idl.Text], [idl.Text], []),
    list_codices: idl.Func([], [idl.Text], ['query']),
    get_file: idl.Func([idl.Text], [idl.Text], ['query']),
  });

async function getRegistryActor(canisterId) {
  const client = await initializeAuthClient();
  const identity = client.getIdentity();
  const agent = new HttpAgent({ identity });
  if (
    typeof window !== 'undefined' &&
    (window.location.hostname.includes('localhost') ||
      window.location.hostname.includes('127.0.0.1'))
  ) {
    try { await agent.fetchRootKey(); } catch (e) { /* local dev */ }
  }
  return Actor.createActor(fileRegistryIdlFactory, {
    agent,
    canisterId: Principal.fromText(canisterId),
  });
}

/** Read-only actor: queries need no signature, so skip the auth client. */
async function getQueryActor(canisterId) {
  const agent = new HttpAgent({});
  if (
    typeof window !== 'undefined' &&
    (window.location.hostname.includes('localhost') ||
      window.location.hostname.includes('127.0.0.1'))
  ) {
    try { await agent.fetchRootKey(); } catch (e) { /* local dev */ }
  }
  return Actor.createActor(fileRegistryIdlFactory, {
    agent,
    canisterId: Principal.fromText(canisterId),
  });
}

/**
 * Fetch a codex package manifest from the file registry — the package that a
 * new realm will actually install, unlike the codices git repo which may be
 * ahead of (or behind) what is published.
 *
 * @param {string} canisterId file_registry canister id
 * @param {string} codexId lowercase package id (e.g. "syntropia")
 * @returns {Promise<object|null>} parsed manifest.json, or null when unavailable
 */
export async function fetchCodexManifest(canisterId, codexId) {
  const actor = await getQueryActor(canisterId);
  const listing = JSON.parse(String(await actor.list_codices()));
  const entry = Array.isArray(listing)
    ? listing.find((c) => c.codex_id === codexId)
    : null;
  if (!entry?.latest) return null;
  // Unified codex packages (kind: codex, issue #244) live under ext/;
  // legacy packages under codex/. list_codices tells us which.
  const prefix = entry.namespace_prefix || 'codex';
  const resp = JSON.parse(
    String(
      await actor.get_file(
        JSON.stringify({
          namespace: `${prefix}/${codexId}/${entry.latest}`,
          path: 'manifest.json',
        }),
      ),
    ),
  );
  if (resp?.error || !resp?.content_b64) return null;
  return JSON.parse(atob(resp.content_b64));
}

function arrayBufferToBase64(buf) {
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)));
  }
  return typeof btoa === 'function'
    ? btoa(binary)
    : Buffer.from(binary, 'binary').toString('base64');
}

async function sha256HexFromBlob(file) {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function guessContentType(path, fileType) {
  if (fileType) return fileType;
  const lower = path.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.svg')) return 'image/svg+xml';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.gif')) return 'image/gif';
  return 'application/octet-stream';
}

/**
 * Upload one file (small or chunked) to a file_registry namespace.
 * @param {string} canisterId
 * @param {{namespace: string, path: string, file: File|Blob}} payload
 * @param {(p: {path: string, uploaded: number, total: number, status: string, error?: string}) => void} [onProgress]
 */
export async function uploadFile(canisterId, payload, onProgress) {
  const { namespace, path, file } = payload;
  const total = file.size;
  const ct = guessContentType(path, file.type);
  const actor = await getRegistryActor(canisterId);

  onProgress?.({ path, uploaded: 0, total, status: 'queued' });
  onProgress?.({ path, uploaded: 0, total, status: 'hashing' });
  const sha256 = await sha256HexFromBlob(file);
  const totalChunks = Math.max(1, Math.ceil(total / CHUNK_BYTES));

  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_BYTES;
    const end = Math.min(start + CHUNK_BYTES, total);
    const slice = file.slice(start, end);
    const buf = await slice.arrayBuffer();
    const args = JSON.stringify({
      namespace,
      path,
      chunk_index: i,
      total_chunks: totalChunks,
      data_b64: arrayBufferToBase64(buf),
      content_type: ct,
    });
    const resp = await actor.store_file_chunk(args);
    const parsed = JSON.parse(String(resp));
    if (parsed?.error) throw new Error(`store_file_chunk[${i}]: ${parsed.error}`);
    onProgress?.({ path, uploaded: Math.min(end, total), total, status: 'uploading' });
  }

  onProgress?.({ path, uploaded: total, total, status: 'finalizing' });
  let firstCall = true;
  while (true) {
    const args = JSON.stringify(
      firstCall
        ? { namespace, path, expected_sha256: sha256, batch_size: 1 }
        : { namespace, path, batch_size: 1 },
    );
    firstCall = false;
    const resp = await actor.finalize_chunked_file_step(args);
    const parsed = JSON.parse(String(resp));
    if (parsed?.error) throw new Error(`finalize: ${parsed.error}`);
    if (parsed?.done) break;
  }

  onProgress?.({ path, uploaded: total, total, status: 'done' });
}

/**
 * Upload files to a namespace and then publish the namespace.
 * @param {string} canisterId
 * @param {string} namespace
 * @param {{path: string, file: File|Blob}[]} files
 * @param {Function} [onProgress]
 */
export async function uploadAndPublish(canisterId, namespace, files, onProgress) {
  for (const item of files) {
    await uploadFile(canisterId, { namespace, path: item.path, file: item.file }, onProgress);
  }
  const actor = await getRegistryActor(canisterId);
  const resp = await actor.publish_namespace(JSON.stringify({ namespace }));
  const parsed = JSON.parse(String(resp));
  if (parsed?.error) throw new Error(`publish_namespace: ${parsed.error}`);
}
