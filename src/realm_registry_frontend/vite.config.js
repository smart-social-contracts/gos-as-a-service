import { fileURLToPath, URL } from 'url';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import environment from 'vite-plugin-environment';
import dotenv from 'dotenv';
import { dirname, join } from 'path';
import { getBuildTimeValues } from './scripts/build-info.js';
import {
  generateWellKnownFiles,
  getGaasEnvViteDefine,
  loadGaasEnv,
} from './scripts/gaas-env.js';

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

// Canister ids, the network and the portal origin are NOT baked into the
// bundle: the conductor writes /canister_ids.js into the deployed asset
// canister (casals.json, realm-registry-frontend `files`), and a local replica
// supplies CANISTER_ID_* through dfx's env (vite-plugin-environment below).
// One dist serves every environment.

const buildValues = getBuildValues();
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
