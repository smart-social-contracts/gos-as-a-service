import { fileURLToPath, URL } from 'url';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import environment from 'vite-plugin-environment';
import dotenv from 'dotenv';
import { readFileSync, existsSync } from 'fs';
import { dirname, join } from 'path';
import { getBuildTimeValues } from './scripts/build-info.js';
import {
  generateWellKnownFiles,
  getGaasEnvViteDefine,
  loadGaasEnv,
} from './scripts/gaas-env.js';
import {
  assertCasalsFrontendLiveForBake,
  assertInstallerLiveForBake,
} from './scripts/assert-canister-live.js';

dotenv.config({ path: '../../.env' });

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '../..');
const staticDir = join(dirname(fileURLToPath(import.meta.url)), 'static');

function getGaasEnvConfig() {
  try {
    return loadGaasEnv(repoRoot);
  } catch (e) {
    console.warn(e.message);
    return null;
  }
}

const gaasEnv = getGaasEnvConfig();
if (gaasEnv) {
  generateWellKnownFiles(gaasEnv, staticDir);
  console.log(`gaas-env: loaded deployment descriptor for ${gaasEnv.domain}`);
}

function getBuildValues() {
  return getBuildTimeValues(repoRoot);
}

// Resolve canister IDs from canister_ids.json for the active DFX_NETWORK.
// Injects IDs directly into Vite's define block (build-time constants) AND
// into process.env so vite-plugin-environment can also pick them up.
// This bypasses plugin ordering/timing issues and works in both local dev and CI.
function getCanisterIdDefines() {
  const network = process.env.DFX_NETWORK;
  if (!network) {
    console.warn('DFX_NETWORK is not set — canister IDs will not be injected at build time.');
    return {};
  }

  const idsPath = join(repoRoot, 'canister_ids.json');
  const defines = {};

  if (!existsSync(idsPath)) return defines;

  try {
    const allIds = JSON.parse(readFileSync(idsPath, 'utf-8'));
    for (const [canister, networks] of Object.entries(allIds)) {
      const id = networks[network] || '';
      if (id) {
        const envKey = `CANISTER_ID_${canister.toUpperCase()}`;
        defines[`import.meta.env.${envKey}`] = JSON.stringify(id);
        process.env[envKey] = id;
      }
    }
  } catch (e) {
    console.warn('Failed to read canister_ids.json:', e.message);
    return defines;
  }

  assertInstallerLiveForBake(defines['import.meta.env.CANISTER_ID_REALM_INSTALLER']
    ? JSON.parse(defines['import.meta.env.CANISTER_ID_REALM_INSTALLER'])
    : '', network, { repoRoot });
  assertCasalsFrontendLiveForBake(
    defines['import.meta.env.CANISTER_ID_CASALS_FRONTEND']
      ? JSON.parse(defines['import.meta.env.CANISTER_ID_CASALS_FRONTEND'])
      : '',
    network,
    { repoRoot }
  );

  return defines;
}

// Inject the full canister_ids.json map for runtime resolution (single tarball, multi-env deploy).
function getCanisterIdsDefine() {
  const idsPath = join(repoRoot, 'canister_ids.json');
  if (!existsSync(idsPath)) return {};

  try {
    const allIds = JSON.parse(readFileSync(idsPath, 'utf-8'));
    // Only the staging SPA bake must refuse a dead staging installer id.
    // test/demo `gaas new --network ic` still writes the full map into
    // __CANISTER_IDS__, but must not require staging.gos.earth to be live.
    if (process.env.GAAS_ENV === 'staging' || process.env.DFX_NETWORK === 'staging') {
      assertInstallerLiveForBake(allIds.realm_installer?.staging || '', 'staging', {
        repoRoot,
      });
      for (const [net, id] of Object.entries(allIds.casals_frontend || {})) {
        assertCasalsFrontendLiveForBake(id || '', net, { repoRoot });
      }
    }
    return { '__CANISTER_IDS__': JSON.stringify(allIds) };
  } catch (e) {
    if (String(e.message || '').includes('CANISTER_ID_REALM_INSTALLER')) {
      throw e;
    }
    console.warn('Failed to read canister_ids.json for __CANISTER_IDS__:', e.message);
    return {};
  }
}

const buildValues = getBuildValues();
const canisterDefines = getCanisterIdDefines();
const canisterIdsDefine = getCanisterIdsDefine();
const gaasEnvDefine = getGaasEnvViteDefine(gaasEnv);

export default defineConfig({
  build: {
    emptyOutDir: true,
  },
  ssr: {
    noExternal: [
      'svelte-i18n',
      'intl-messageformat',
      '@formatjs/icu-messageformat-parser',
      '@formatjs/icu-skeleton-parser',
      '@formatjs/fast-memoize',
    ],
  },
  define: {
    '__BUILD_VERSION__': JSON.stringify(buildValues.version),
    '__BUILD_COMMIT__': JSON.stringify(buildValues.commitHash),
    '__BUILD_TIME__': JSON.stringify(buildValues.buildTime),
    ...canisterIdsDefine,
    ...canisterDefines,
    ...gaasEnvDefine,
  },
  optimizeDeps: {
    include: ['maplibre-gl', 'h3-js'],
    esbuildOptions: {
      define: {
        global: "globalThis",
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:4943",
        changeOrigin: true,
      },
    },
  },
  plugins: [
    sveltekit(),
    environment("all", { prefix: "CANISTER_" }),
    environment("all", { prefix: "DFX_" }),
    environment("all", { prefix: "VITE_" }),
  ],
  resolve: {
    alias: [
      {
        find: "declarations",
        replacement: fileURLToPath(
          new URL("../declarations", import.meta.url)
        ),
      },
      { find: '@icp-sdk/core/agent', replacement: '@dfinity/agent' },
      { find: '@icp-sdk/core/principal', replacement: '@dfinity/principal' },
      { find: '@icp-sdk/core/candid', replacement: '@dfinity/candid' },
    ],
    dedupe: ['@dfinity/agent', 'maplibre-gl'],
  },
});
