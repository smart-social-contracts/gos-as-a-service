import { fileURLToPath, URL } from 'url';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import environment from 'vite-plugin-environment';
import dotenv from 'dotenv';
import { execSync } from 'child_process';
import { readFileSync, existsSync } from 'fs';

dotenv.config({ path: '../../.env' });

function getBuildTimeValues() {
  let version = 'dev';
  let commitHash = 'local';
  const buildTime = new Date().toISOString().replace('T', ' ').substring(0, 19);
  
  try {
    version = readFileSync('../../version.txt', 'utf-8').trim();
  } catch (e) {
    // version.txt not found, use default
  }
  
  try {
    commitHash = execSync('git rev-parse --short HEAD', { encoding: 'utf-8' }).trim();
  } catch (e) {
    // git not available, use default
  }
  
  return { version, commitHash, buildTime };
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

  const idsPath = '../../canister_ids.json';
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
  }

  return defines;
}

const buildValues = getBuildTimeValues();
const canisterDefines = getCanisterIdDefines();

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
    ...canisterDefines,
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
