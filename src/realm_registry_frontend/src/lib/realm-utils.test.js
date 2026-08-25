import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  acceptSplashLogoUrl,
  brandingLogoUrls,
  BRANDING_LOGO_PATHS,
  isLeftoverBrandingBytes,
  isLeftoverPlatformLogoPath,
  LEFTOVER_BRANDING_SHA256,
  pathnameFromAssetUrl,
  sha256Hex,
  splashLogoCandidates,
} from './realm-utils.js';

const testdata = join(dirname(fileURLToPath(import.meta.url)), 'testdata');

test('brandingLogoUrls is empty without a frontend canister', () => {
  assert.deepEqual(brandingLogoUrls(''), []);
  assert.deepEqual(brandingLogoUrls(null), []);
  assert.deepEqual(brandingLogoUrls(undefined), []);
});

test('brandingLogoUrls probes custom logo then root logo', () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  assert.deepEqual(brandingLogoUrls(id), [
    `https://${id}.icp0.io/custom/logo.png`,
    `https://${id}.icp0.io/logo.png`,
  ]);
  assert.deepEqual(BRANDING_LOGO_PATHS, ['/custom/logo.png', '/logo.png']);
});

test('leftover platform paths include clover and GOS planet, not /custom/logo.png', () => {
  assert.equal(isLeftoverPlatformLogoPath('/images/logo.png'), true);
  assert.equal(isLeftoverPlatformLogoPath('/images/logo_sphere_only.svg'), true);
  assert.equal(
    isLeftoverPlatformLogoPath('https://abcde-aaaaa-aaaan-aaaaq-cai.icp0.io/images/logo.png'),
    true
  );
  assert.equal(isLeftoverPlatformLogoPath('/custom/logo.png'), false);
  assert.equal(pathnameFromAssetUrl('https://example.icp0.io/custom/logo.png'), '/custom/logo.png');
});

test('known leftover file hashes stay pinned (Syntropia demo + clover)', () => {
  assert.ok(LEFTOVER_BRANDING_SHA256.has('ad61a953728bad3317cec825379f8b00022cda8f48572be34df74f4f65cc70a2'));
  assert.ok(LEFTOVER_BRANDING_SHA256.has('85bf3e1f45bce760e07987764c7435c2c0744db49092d5721cb7a33c25c40898'));
});

test('splashLogoCandidates prefers configured logo_url and skips leftover paths', () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  assert.deepEqual(
    splashLogoCandidates({
      frontendCanisterId: id,
      configuredLogoUrl: '/images/logo_sphere_only.svg',
    }),
    [`https://${id}.icp0.io/custom/logo.png`, `https://${id}.icp0.io/logo.png`]
  );
  assert.deepEqual(
    splashLogoCandidates({
      frontendCanisterId: id,
      configuredLogoUrl: 'https://files.example/real-brand.png',
    }),
    [
      'https://files.example/real-brand.png',
      `https://${id}.icp0.io/custom/logo.png`,
      `https://${id}.icp0.io/logo.png`,
    ]
  );
  assert.deepEqual(splashLogoCandidates({ frontendCanisterId: '', configuredLogoUrl: '' }), []);
});

test('leftover Syntropia and clover PNGs are rejected as splash brands', async () => {
  const syntropia = readFileSync(join(testdata, 'leftover-syntropia-logo.png'));
  const clover = readFileSync(join(testdata, 'leftover-clover-logo.png'));
  assert.equal(await isLeftoverBrandingBytes(syntropia), true);
  assert.equal(await isLeftoverBrandingBytes(clover), true);
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/custom/logo.png', async () => ({
      ok: true,
      arrayBuffer: async () => syntropia.buffer.slice(syntropia.byteOffset, syntropia.byteOffset + syntropia.byteLength),
    })),
    false
  );
});

test('acceptSplashLogoUrl rejects leftover paths / failed fetches and accepts a real mark', async () => {
  const real = new Uint8Array([1, 2, 3, 4, 5]);
  assert.equal(await isLeftoverBrandingBytes(real), false);
  assert.ok((await sha256Hex(real)).length === 64);

  const accepted = await acceptSplashLogoUrl('https://realm.example/custom/logo.png', async () => ({
    ok: true,
    headers: { get: () => 'image/png' },
    arrayBuffer: async () => real.buffer,
  }));
  assert.equal(accepted, true);

  assert.equal(
    await acceptSplashLogoUrl('/images/logo.png', async () => ({
      ok: true,
      arrayBuffer: async () => real.buffer,
    })),
    false
  );
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/custom/logo.png', async () => ({ ok: false })),
    false
  );

  const html = new TextEncoder().encode('<!doctype html><html><body>SPA</body></html>');
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/logo.png', async () => ({
      ok: true,
      headers: { get: () => 'text/html' },
      arrayBuffer: async () => html.buffer,
    })),
    false
  );
});
