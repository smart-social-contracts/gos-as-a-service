// vite.config.js
import { fileURLToPath, URL } from "url";
import { sveltekit } from "file:///srv/dev/gos-as-a-service/node_modules/@sveltejs/kit/src/exports/vite/index.js";
import { defineConfig } from "file:///srv/dev/gos-as-a-service/node_modules/vite/dist/node/index.js";
import environment from "file:///srv/dev/gos-as-a-service/node_modules/vite-plugin-environment/dist/index.js";
import dotenv from "file:///srv/dev/gos-as-a-service/node_modules/dotenv/lib/main.js";
import { execSync } from "child_process";
import { readFileSync, existsSync } from "fs";
var __vite_injected_original_import_meta_url = "file:///srv/dev/gos-as-a-service/src/realm_registry_frontend/vite.config.js";
dotenv.config({ path: "../../.env" });
function getBuildTimeValues() {
  let version = "dev";
  let commitHash = "local";
  const buildTime = (/* @__PURE__ */ new Date()).toISOString().replace("T", " ").substring(0, 19);
  try {
    version = readFileSync("../../version.txt", "utf-8").trim();
  } catch (e) {
  }
  try {
    commitHash = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim();
  } catch (e) {
  }
  return { version, commitHash, buildTime };
}
function getCanisterIdDefines() {
  const network = process.env.DFX_NETWORK;
  if (!network) {
    console.warn("DFX_NETWORK is not set \u2014 canister IDs will not be injected at build time.");
    return {};
  }
  const idsPath = "../../canister_ids.json";
  const defines = {};
  if (!existsSync(idsPath)) return defines;
  try {
    const allIds = JSON.parse(readFileSync(idsPath, "utf-8"));
    for (const [canister, networks] of Object.entries(allIds)) {
      const id = networks[network] || "";
      if (id) {
        const envKey = `CANISTER_ID_${canister.toUpperCase()}`;
        defines[`import.meta.env.${envKey}`] = JSON.stringify(id);
        process.env[envKey] = id;
      }
    }
  } catch (e) {
    console.warn("Failed to read canister_ids.json:", e.message);
  }
  return defines;
}
function getCanisterIdsDefine() {
  const idsPath = "../../canister_ids.json";
  if (!existsSync(idsPath)) return {};
  try {
    const allIds = JSON.parse(readFileSync(idsPath, "utf-8"));
    return { "__CANISTER_IDS__": JSON.stringify(allIds) };
  } catch (e) {
    console.warn("Failed to read canister_ids.json for __CANISTER_IDS__:", e.message);
    return {};
  }
}
var buildValues = getBuildTimeValues();
var canisterDefines = getCanisterIdDefines();
var canisterIdsDefine = getCanisterIdsDefine();
var vite_config_default = defineConfig({
  build: {
    emptyOutDir: true
  },
  ssr: {
    noExternal: [
      "svelte-i18n",
      "intl-messageformat",
      "@formatjs/icu-messageformat-parser",
      "@formatjs/icu-skeleton-parser",
      "@formatjs/fast-memoize"
    ]
  },
  define: {
    "__BUILD_VERSION__": JSON.stringify(buildValues.version),
    "__BUILD_COMMIT__": JSON.stringify(buildValues.commitHash),
    "__BUILD_TIME__": JSON.stringify(buildValues.buildTime),
    ...canisterIdsDefine,
    ...canisterDefines
  },
  optimizeDeps: {
    include: ["maplibre-gl", "h3-js"],
    esbuildOptions: {
      define: {
        global: "globalThis"
      }
    }
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:4943",
        changeOrigin: true
      }
    }
  },
  plugins: [
    sveltekit(),
    environment("all", { prefix: "CANISTER_" }),
    environment("all", { prefix: "DFX_" }),
    environment("all", { prefix: "VITE_" })
  ],
  resolve: {
    alias: [
      {
        find: "declarations",
        replacement: fileURLToPath(
          new URL("../declarations", __vite_injected_original_import_meta_url)
        )
      },
      { find: "@icp-sdk/core/agent", replacement: "@dfinity/agent" },
      { find: "@icp-sdk/core/principal", replacement: "@dfinity/principal" },
      { find: "@icp-sdk/core/candid", replacement: "@dfinity/candid" }
    ],
    dedupe: ["@dfinity/agent", "maplibre-gl"]
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc3J2L2Rldi9nb3MtYXMtYS1zZXJ2aWNlL3NyYy9yZWFsbV9yZWdpc3RyeV9mcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nydi9kZXYvZ29zLWFzLWEtc2VydmljZS9zcmMvcmVhbG1fcmVnaXN0cnlfZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nydi9kZXYvZ29zLWFzLWEtc2VydmljZS9zcmMvcmVhbG1fcmVnaXN0cnlfZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgeyBmaWxlVVJMVG9QYXRoLCBVUkwgfSBmcm9tICd1cmwnO1xuaW1wb3J0IHsgc3ZlbHRla2l0IH0gZnJvbSAnQHN2ZWx0ZWpzL2tpdC92aXRlJztcbmltcG9ydCB7IGRlZmluZUNvbmZpZyB9IGZyb20gJ3ZpdGUnO1xuaW1wb3J0IGVudmlyb25tZW50IGZyb20gJ3ZpdGUtcGx1Z2luLWVudmlyb25tZW50JztcbmltcG9ydCBkb3RlbnYgZnJvbSAnZG90ZW52JztcbmltcG9ydCB7IGV4ZWNTeW5jIH0gZnJvbSAnY2hpbGRfcHJvY2Vzcyc7XG5pbXBvcnQgeyByZWFkRmlsZVN5bmMsIGV4aXN0c1N5bmMgfSBmcm9tICdmcyc7XG5cbmRvdGVudi5jb25maWcoeyBwYXRoOiAnLi4vLi4vLmVudicgfSk7XG5cbmZ1bmN0aW9uIGdldEJ1aWxkVGltZVZhbHVlcygpIHtcbiAgbGV0IHZlcnNpb24gPSAnZGV2JztcbiAgbGV0IGNvbW1pdEhhc2ggPSAnbG9jYWwnO1xuICBjb25zdCBidWlsZFRpbWUgPSBuZXcgRGF0ZSgpLnRvSVNPU3RyaW5nKCkucmVwbGFjZSgnVCcsICcgJykuc3Vic3RyaW5nKDAsIDE5KTtcbiAgXG4gIHRyeSB7XG4gICAgdmVyc2lvbiA9IHJlYWRGaWxlU3luYygnLi4vLi4vdmVyc2lvbi50eHQnLCAndXRmLTgnKS50cmltKCk7XG4gIH0gY2F0Y2ggKGUpIHtcbiAgICAvLyB2ZXJzaW9uLnR4dCBub3QgZm91bmQsIHVzZSBkZWZhdWx0XG4gIH1cbiAgXG4gIHRyeSB7XG4gICAgY29tbWl0SGFzaCA9IGV4ZWNTeW5jKCdnaXQgcmV2LXBhcnNlIC0tc2hvcnQgSEVBRCcsIHsgZW5jb2Rpbmc6ICd1dGYtOCcgfSkudHJpbSgpO1xuICB9IGNhdGNoIChlKSB7XG4gICAgLy8gZ2l0IG5vdCBhdmFpbGFibGUsIHVzZSBkZWZhdWx0XG4gIH1cbiAgXG4gIHJldHVybiB7IHZlcnNpb24sIGNvbW1pdEhhc2gsIGJ1aWxkVGltZSB9O1xufVxuXG4vLyBSZXNvbHZlIGNhbmlzdGVyIElEcyBmcm9tIGNhbmlzdGVyX2lkcy5qc29uIGZvciB0aGUgYWN0aXZlIERGWF9ORVRXT1JLLlxuLy8gSW5qZWN0cyBJRHMgZGlyZWN0bHkgaW50byBWaXRlJ3MgZGVmaW5lIGJsb2NrIChidWlsZC10aW1lIGNvbnN0YW50cykgQU5EXG4vLyBpbnRvIHByb2Nlc3MuZW52IHNvIHZpdGUtcGx1Z2luLWVudmlyb25tZW50IGNhbiBhbHNvIHBpY2sgdGhlbSB1cC5cbi8vIFRoaXMgYnlwYXNzZXMgcGx1Z2luIG9yZGVyaW5nL3RpbWluZyBpc3N1ZXMgYW5kIHdvcmtzIGluIGJvdGggbG9jYWwgZGV2IGFuZCBDSS5cbmZ1bmN0aW9uIGdldENhbmlzdGVySWREZWZpbmVzKCkge1xuICBjb25zdCBuZXR3b3JrID0gcHJvY2Vzcy5lbnYuREZYX05FVFdPUks7XG4gIGlmICghbmV0d29yaykge1xuICAgIGNvbnNvbGUud2FybignREZYX05FVFdPUksgaXMgbm90IHNldCBcdTIwMTQgY2FuaXN0ZXIgSURzIHdpbGwgbm90IGJlIGluamVjdGVkIGF0IGJ1aWxkIHRpbWUuJyk7XG4gICAgcmV0dXJuIHt9O1xuICB9XG5cbiAgY29uc3QgaWRzUGF0aCA9ICcuLi8uLi9jYW5pc3Rlcl9pZHMuanNvbic7XG4gIGNvbnN0IGRlZmluZXMgPSB7fTtcblxuICBpZiAoIWV4aXN0c1N5bmMoaWRzUGF0aCkpIHJldHVybiBkZWZpbmVzO1xuXG4gIHRyeSB7XG4gICAgY29uc3QgYWxsSWRzID0gSlNPTi5wYXJzZShyZWFkRmlsZVN5bmMoaWRzUGF0aCwgJ3V0Zi04JykpO1xuICAgIGZvciAoY29uc3QgW2NhbmlzdGVyLCBuZXR3b3Jrc10gb2YgT2JqZWN0LmVudHJpZXMoYWxsSWRzKSkge1xuICAgICAgY29uc3QgaWQgPSBuZXR3b3Jrc1tuZXR3b3JrXSB8fCAnJztcbiAgICAgIGlmIChpZCkge1xuICAgICAgICBjb25zdCBlbnZLZXkgPSBgQ0FOSVNURVJfSURfJHtjYW5pc3Rlci50b1VwcGVyQ2FzZSgpfWA7XG4gICAgICAgIGRlZmluZXNbYGltcG9ydC5tZXRhLmVudi4ke2VudktleX1gXSA9IEpTT04uc3RyaW5naWZ5KGlkKTtcbiAgICAgICAgcHJvY2Vzcy5lbnZbZW52S2V5XSA9IGlkO1xuICAgICAgfVxuICAgIH1cbiAgfSBjYXRjaCAoZSkge1xuICAgIGNvbnNvbGUud2FybignRmFpbGVkIHRvIHJlYWQgY2FuaXN0ZXJfaWRzLmpzb246JywgZS5tZXNzYWdlKTtcbiAgfVxuXG4gIHJldHVybiBkZWZpbmVzO1xufVxuXG4vLyBJbmplY3QgdGhlIGZ1bGwgY2FuaXN0ZXJfaWRzLmpzb24gbWFwIGZvciBydW50aW1lIHJlc29sdXRpb24gKHNpbmdsZSB0YXJiYWxsLCBtdWx0aS1lbnYgZGVwbG95KS5cbmZ1bmN0aW9uIGdldENhbmlzdGVySWRzRGVmaW5lKCkge1xuICBjb25zdCBpZHNQYXRoID0gJy4uLy4uL2NhbmlzdGVyX2lkcy5qc29uJztcbiAgaWYgKCFleGlzdHNTeW5jKGlkc1BhdGgpKSByZXR1cm4ge307XG5cbiAgdHJ5IHtcbiAgICBjb25zdCBhbGxJZHMgPSBKU09OLnBhcnNlKHJlYWRGaWxlU3luYyhpZHNQYXRoLCAndXRmLTgnKSk7XG4gICAgcmV0dXJuIHsgJ19fQ0FOSVNURVJfSURTX18nOiBKU09OLnN0cmluZ2lmeShhbGxJZHMpIH07XG4gIH0gY2F0Y2ggKGUpIHtcbiAgICBjb25zb2xlLndhcm4oJ0ZhaWxlZCB0byByZWFkIGNhbmlzdGVyX2lkcy5qc29uIGZvciBfX0NBTklTVEVSX0lEU19fOicsIGUubWVzc2FnZSk7XG4gICAgcmV0dXJuIHt9O1xuICB9XG59XG5cbmNvbnN0IGJ1aWxkVmFsdWVzID0gZ2V0QnVpbGRUaW1lVmFsdWVzKCk7XG5jb25zdCBjYW5pc3RlckRlZmluZXMgPSBnZXRDYW5pc3RlcklkRGVmaW5lcygpO1xuY29uc3QgY2FuaXN0ZXJJZHNEZWZpbmUgPSBnZXRDYW5pc3Rlcklkc0RlZmluZSgpO1xuXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICBidWlsZDoge1xuICAgIGVtcHR5T3V0RGlyOiB0cnVlLFxuICB9LFxuICBzc3I6IHtcbiAgICBub0V4dGVybmFsOiBbXG4gICAgICAnc3ZlbHRlLWkxOG4nLFxuICAgICAgJ2ludGwtbWVzc2FnZWZvcm1hdCcsXG4gICAgICAnQGZvcm1hdGpzL2ljdS1tZXNzYWdlZm9ybWF0LXBhcnNlcicsXG4gICAgICAnQGZvcm1hdGpzL2ljdS1za2VsZXRvbi1wYXJzZXInLFxuICAgICAgJ0Bmb3JtYXRqcy9mYXN0LW1lbW9pemUnLFxuICAgIF0sXG4gIH0sXG4gIGRlZmluZToge1xuICAgICdfX0JVSUxEX1ZFUlNJT05fXyc6IEpTT04uc3RyaW5naWZ5KGJ1aWxkVmFsdWVzLnZlcnNpb24pLFxuICAgICdfX0JVSUxEX0NPTU1JVF9fJzogSlNPTi5zdHJpbmdpZnkoYnVpbGRWYWx1ZXMuY29tbWl0SGFzaCksXG4gICAgJ19fQlVJTERfVElNRV9fJzogSlNPTi5zdHJpbmdpZnkoYnVpbGRWYWx1ZXMuYnVpbGRUaW1lKSxcbiAgICAuLi5jYW5pc3Rlcklkc0RlZmluZSxcbiAgICAuLi5jYW5pc3RlckRlZmluZXMsXG4gIH0sXG4gIG9wdGltaXplRGVwczoge1xuICAgIGluY2x1ZGU6IFsnbWFwbGlicmUtZ2wnLCAnaDMtanMnXSxcbiAgICBlc2J1aWxkT3B0aW9uczoge1xuICAgICAgZGVmaW5lOiB7XG4gICAgICAgIGdsb2JhbDogXCJnbG9iYWxUaGlzXCIsXG4gICAgICB9LFxuICAgIH0sXG4gIH0sXG4gIHNlcnZlcjoge1xuICAgIHByb3h5OiB7XG4gICAgICBcIi9hcGlcIjoge1xuICAgICAgICB0YXJnZXQ6IFwiaHR0cDovLzEyNy4wLjAuMTo0OTQzXCIsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSxcbiAgcGx1Z2luczogW1xuICAgIHN2ZWx0ZWtpdCgpLFxuICAgIGVudmlyb25tZW50KFwiYWxsXCIsIHsgcHJlZml4OiBcIkNBTklTVEVSX1wiIH0pLFxuICAgIGVudmlyb25tZW50KFwiYWxsXCIsIHsgcHJlZml4OiBcIkRGWF9cIiB9KSxcbiAgICBlbnZpcm9ubWVudChcImFsbFwiLCB7IHByZWZpeDogXCJWSVRFX1wiIH0pLFxuICBdLFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IFtcbiAgICAgIHtcbiAgICAgICAgZmluZDogXCJkZWNsYXJhdGlvbnNcIixcbiAgICAgICAgcmVwbGFjZW1lbnQ6IGZpbGVVUkxUb1BhdGgoXG4gICAgICAgICAgbmV3IFVSTChcIi4uL2RlY2xhcmF0aW9uc1wiLCBpbXBvcnQubWV0YS51cmwpXG4gICAgICAgICksXG4gICAgICB9LFxuICAgICAgeyBmaW5kOiAnQGljcC1zZGsvY29yZS9hZ2VudCcsIHJlcGxhY2VtZW50OiAnQGRmaW5pdHkvYWdlbnQnIH0sXG4gICAgICB7IGZpbmQ6ICdAaWNwLXNkay9jb3JlL3ByaW5jaXBhbCcsIHJlcGxhY2VtZW50OiAnQGRmaW5pdHkvcHJpbmNpcGFsJyB9LFxuICAgICAgeyBmaW5kOiAnQGljcC1zZGsvY29yZS9jYW5kaWQnLCByZXBsYWNlbWVudDogJ0BkZmluaXR5L2NhbmRpZCcgfSxcbiAgICBdLFxuICAgIGRlZHVwZTogWydAZGZpbml0eS9hZ2VudCcsICdtYXBsaWJyZS1nbCddLFxuICB9LFxufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQWlWLFNBQVMsZUFBZSxXQUFXO0FBQ3BYLFNBQVMsaUJBQWlCO0FBQzFCLFNBQVMsb0JBQW9CO0FBQzdCLE9BQU8saUJBQWlCO0FBQ3hCLE9BQU8sWUFBWTtBQUNuQixTQUFTLGdCQUFnQjtBQUN6QixTQUFTLGNBQWMsa0JBQWtCO0FBTnlLLElBQU0sMkNBQTJDO0FBUW5RLE9BQU8sT0FBTyxFQUFFLE1BQU0sYUFBYSxDQUFDO0FBRXBDLFNBQVMscUJBQXFCO0FBQzVCLE1BQUksVUFBVTtBQUNkLE1BQUksYUFBYTtBQUNqQixRQUFNLGFBQVksb0JBQUksS0FBSyxHQUFFLFlBQVksRUFBRSxRQUFRLEtBQUssR0FBRyxFQUFFLFVBQVUsR0FBRyxFQUFFO0FBRTVFLE1BQUk7QUFDRixjQUFVLGFBQWEscUJBQXFCLE9BQU8sRUFBRSxLQUFLO0FBQUEsRUFDNUQsU0FBUyxHQUFHO0FBQUEsRUFFWjtBQUVBLE1BQUk7QUFDRixpQkFBYSxTQUFTLDhCQUE4QixFQUFFLFVBQVUsUUFBUSxDQUFDLEVBQUUsS0FBSztBQUFBLEVBQ2xGLFNBQVMsR0FBRztBQUFBLEVBRVo7QUFFQSxTQUFPLEVBQUUsU0FBUyxZQUFZLFVBQVU7QUFDMUM7QUFNQSxTQUFTLHVCQUF1QjtBQUM5QixRQUFNLFVBQVUsUUFBUSxJQUFJO0FBQzVCLE1BQUksQ0FBQyxTQUFTO0FBQ1osWUFBUSxLQUFLLGdGQUEyRTtBQUN4RixXQUFPLENBQUM7QUFBQSxFQUNWO0FBRUEsUUFBTSxVQUFVO0FBQ2hCLFFBQU0sVUFBVSxDQUFDO0FBRWpCLE1BQUksQ0FBQyxXQUFXLE9BQU8sRUFBRyxRQUFPO0FBRWpDLE1BQUk7QUFDRixVQUFNLFNBQVMsS0FBSyxNQUFNLGFBQWEsU0FBUyxPQUFPLENBQUM7QUFDeEQsZUFBVyxDQUFDLFVBQVUsUUFBUSxLQUFLLE9BQU8s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
