import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  acceptBrandingAssetUrl,
  acceptSplashLogoUrl,
  brandingLogoUrls,
  BRANDING_LOGO_PATHS,
  clearSplashBrandHint,
  firstSplashLogoUrl,
  HOST_SPLASH_MARK_PATH,
  isLeftoverBrandingBytes,
  isLeftoverPlatformLogoPath,
  isRealmBrandLogoPath,
  LEFTOVER_BRANDING_SHA256,
  pathnameFromAssetUrl,
  readSplashBrandHint,
  resolveAcceptedSplashLogoUrl,
  sha256Hex,
  splashLogoCandidates,
  splashLogoInputFromPortal,
  SPLASH_BRAND_HINT_STORAGE_KEY,
  writeSplashBrandHint,
} from './realm-utils.js';

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (key) => (Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null),
    setItem: (key, value) => {
      data[key] = String(value);
    },
    removeItem: (key) => {
      delete data[key];
    },
  };
}

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
  assert.equal(isRealmBrandLogoPath('/custom/logo.png'), true);
  assert.equal(isRealmBrandLogoPath('https://example.icp0.io/custom/logo.png'), true);
  assert.equal(pathnameFromAssetUrl('https://example.icp0.io/custom/logo.png'), '/custom/logo.png');
});

test('host splash mark is the GOS orb under /images/, never leftover /custom/logo.png', () => {
  assert.equal(HOST_SPLASH_MARK_PATH, '/images/logo_sphere_only.svg');
  assert.equal(isLeftoverPlatformLogoPath(HOST_SPLASH_MARK_PATH), true);
  assert.equal(isRealmBrandLogoPath(HOST_SPLASH_MARK_PATH), false);
});

test('leftover hashes include clover, shipped Syntropia DNA, and shipped city background', () => {
  assert.ok(LEFTOVER_BRANDING_SHA256.has('85bf3e1f45bce760e07987764c7435c2c0744db49092d5721cb7a33c25c40898'));
  assert.ok(LEFTOVER_BRANDING_SHA256.has('ad61a953728bad3317cec825379f8b00022cda8f48572be34df74f4f65cc70a2'));
  assert.ok(LEFTOVER_BRANDING_SHA256.has('a2852f05b5ae66b26f169d8efc128326fcdb64dee2915d251e66df477881fed4'));
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

test('firstSplashLogoUrl is /custom/logo.png as soon as the frontend canister is known', () => {
  const id = 'wumyk-tiaaa-aaaae-agz6q-cai';
  assert.equal(firstSplashLogoUrl({ frontendCanisterId: id }), `https://${id}.icp0.io/custom/logo.png`);
  assert.equal(
    firstSplashLogoUrl({ frontendCanisterId: id, configuredLogoUrl: '/custom/logo.png' }),
    `https://${id}.icp0.io/custom/logo.png`
  );
  assert.equal(firstSplashLogoUrl({ frontendCanisterId: '', configuredLogoUrl: '/custom/logo.png' }), '');
});

test('splash brand hint persists slug → frontend canister for the first splash frame', () => {
  const storage = memoryStorage();
  const id = 'wumyk-tiaaa-aaaae-agz6q-cai';
  assert.equal(readSplashBrandHint('RealmTest6', storage), null);
  writeSplashBrandHint(
    'RealmTest6',
    { frontendCanisterId: id, configuredLogoUrl: '/custom/logo.png' },
    storage
  );
  const hint = readSplashBrandHint('realmtest6', storage);
  assert.deepEqual(hint, {
    frontendCanisterId: id,
    configuredLogoUrl: '/custom/logo.png',
  });
  assert.equal(firstSplashLogoUrl(hint), `https://${id}.icp0.io/custom/logo.png`);
  assert.equal(
    firstSplashLogoUrl(splashLogoInputFromPortal({ splashHint: hint })),
    `https://${id}.icp0.io/custom/logo.png`
  );
  assert.match(storage.getItem(SPLASH_BRAND_HINT_STORAGE_KEY), /wumyk-tiaaa-aaaae-agz6q-cai/);
  clearSplashBrandHint('realmtest6', storage);
  assert.equal(readSplashBrandHint('realmtest6', storage), null);
});

test('splashLogoInputFromPortal prefers resolved realm over splash hint', () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  assert.deepEqual(
    splashLogoInputFromPortal({
      splashHint: { frontendCanisterId: 'old-id', configuredLogoUrl: '/custom/logo.png' },
      realm: { frontendCanisterId: id, logoUrl: 'https://files.example/brand.png' },
    }),
    { frontendCanisterId: id, configuredLogoUrl: 'https://files.example/brand.png' }
  );
  assert.equal(
    firstSplashLogoUrl(
      splashLogoInputFromPortal({
        splashHint: { frontendCanisterId: id, configuredLogoUrl: '' },
      })
    ),
    `https://${id}.icp0.io/custom/logo.png`
  );
});

test('resolveAcceptedSplashLogoUrl walks candidates and skips leftovers / 404s', async () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  const real = new Uint8Array([1, 2, 3, 4, 5]);
  const fetchImpl = async (url) => {
    const u = String(url);
    if (u.includes('/custom/logo.png')) return { ok: false };
    if (u.includes('/logo.png')) {
      return {
        ok: true,
        headers: { get: () => 'image/png' },
        arrayBuffer: async () => real.buffer,
      };
    }
    return { ok: false };
  };

  assert.equal(
    await resolveAcceptedSplashLogoUrl({ frontendCanisterId: id, configuredLogoUrl: '' }, fetchImpl),
    `https://${id}.icp0.io/logo.png`
  );
  assert.equal(
    await resolveAcceptedSplashLogoUrl(
      { frontendCanisterId: id, configuredLogoUrl: '/images/logo_sphere_only.svg' },
      fetchImpl
    ),
    `https://${id}.icp0.io/logo.png`
  );
  assert.equal(await resolveAcceptedSplashLogoUrl({ frontendCanisterId: id }, async () => ({ ok: false })), '');
});

test('resolveAcceptedSplashLogoUrl never falls back to the retired clover at /images/logo.png', async () => {
  const id = 'abcde-aaaaa-aaaan-aaaaq-cai';
  const clover = readFileSync(join(testdata, 'leftover-clover-logo.png'));
  const fetchImpl = async (url) => {
    const u = String(url);
    if (u.includes('/custom/logo.png')) return { ok: false };
    if (u.endsWith('.icp0.io/logo.png')) return { ok: false };
    if (u.includes('/images/logo.png')) {
      return {
        ok: true,
        headers: { get: () => 'image/png' },
        arrayBuffer: async () => bufferOf(clover),
      };
    }
    return { ok: false };
  };

  assert.equal(await resolveAcceptedSplashLogoUrl({ frontendCanisterId: id }, fetchImpl), '');
  assert.equal(
    await acceptSplashLogoUrl(`https://${id}.icp0.io/images/logo.png`, fetchImpl),
    false
  );
});

function bufferOf(fileBytes) {
  return fileBytes.buffer.slice(fileBytes.byteOffset, fileBytes.byteOffset + fileBytes.byteLength);
}

function okPngFetch(fileBytes) {
  const buf = bufferOf(fileBytes);
  return async () => ({
    ok: true,
    headers: { get: () => 'image/png' },
    arrayBuffer: async () => buf,
  });
}

test('shipped Syntropia DNA and city bytes are leftover; clover leftover is still rejected', async () => {
  const syntropia = readFileSync(join(testdata, 'syntropia-realm-logo.png'));
  const city = readFileSync(join(testdata, 'leftover-city-background.png'));
  const clover = readFileSync(join(testdata, 'leftover-clover-logo.png'));

  assert.equal(await sha256Hex(syntropia), 'ad61a953728bad3317cec825379f8b00022cda8f48572be34df74f4f65cc70a2');
  assert.equal(await sha256Hex(city), 'a2852f05b5ae66b26f169d8efc128326fcdb64dee2915d251e66df477881fed4');
  assert.equal(await isLeftoverBrandingBytes(syntropia), true);
  assert.equal(await isLeftoverBrandingBytes(city), true);
  assert.equal(await isLeftoverBrandingBytes(clover), true);
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/custom/logo.png', okPngFetch(syntropia)),
    false
  );
  assert.equal(
    await acceptBrandingAssetUrl('https://realm.example/custom/background.png', okPngFetch(city)),
    false
  );
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/images/logo.png', okPngFetch(clover)),
    false
  );
});

test('a founder-uploaded mark at /custom/logo.png is still accepted', async () => {
  const uploaded = readFileSync(join(testdata, 'leftover-clover-logo.png'));
  const uploadedCopy = Buffer.from(uploaded);
  uploadedCopy[uploadedCopy.length - 1] ^= 0xff;

  assert.equal(await isLeftoverBrandingBytes(uploadedCopy), false);
  assert.equal(
    await acceptSplashLogoUrl('https://realm.example/custom/logo.png', okPngFetch(uploadedCopy)),
    true
  );
  assert.equal(
    await acceptBrandingAssetUrl('https://realm.example/custom/background.png', okPngFetch(uploadedCopy)),
    true
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
