# Three-command deployment architecture — `gaas new` / `realms seed` / `realms new`

Status: **design agreed, not implemented**. Locked decisions recorded below came
out of the demo rebuild postmortem (2026-08-31, `gaas-new-demo_20260831_152825.log`).

Scope: [smart-social-contracts/gos-as-a-service](https://github.com/smart-social-contracts/gos-as-a-service),
[smart-social-contracts/realms](https://github.com/smart-social-contracts/realms),
[smart-social-contracts/casals](https://github.com/smart-social-contracts/casals).

## Why

Today `gaas new` does three jobs at once: it stands up a GaaS platform
(registry + installer + portal), it creates and seeds the Realms product
infrastructure (Casals, file registries, marketplace), and it publishes the
Realms extension/codex catalog. The result is a 15-phase deploy where Realms
packages are seeded into a GaaS-owned registry, ownership is ambiguous, and a
cycles miscalculation in any phase kills the whole run.

The target is three commands with non-overlapping ownership:

| Command | Stands up | Does **not** do |
|---|---|---|
| `gaas new` | One GaaS platform instance (`*.gos.earth`) | Seed Realms packages, create realms |
| `realms seed` | Shared Realms GOS infrastructure (`*.realmsgos.org`) | Create a GaaS, create realms |
| `realms new` | One realm (GaaS-queued or standalone) | Publish catalogs, touch platform infra |

## Target canister ownership

### `gaas new` — one GaaS instance

| Canister | Role |
|---|---|
| `gaas_realm_registry_backend` | Realm catalog, credits, `request_deployment` |
| `gaas_realm_registry_frontend` | Wizard + portal (DNS: `<env>.gos.earth`) |
| `gaas_realm_installer` | Deployment queue; drives the gaas Casals |
| `gaas_casals_backend` | Conductor for **all** gaas canisters, including every deployed GOS instance and its baton |
| `gaas_casals_frontend` | Casals UI |
| `gaas_casals_multisig` | Root governance for the gaas orchestra (minted via `deploy_sheet`) |
| `gaas_casals_file_registry_backend` | **GOS binaries only**: Realms GOS and Monad GOS backend/frontend(asset) WASMs, plus baton and multisig template WASMs |
| `gaas_casals_file_registry_frontend` | Admin UI for the binary registry |

### `realms seed` — shared Realms infrastructure

| Canister | Role |
|---|---|
| `realmsgos_marketplace_frontend` | Marketplace SPA **and** Realms GOS landing page (DNS: `<env>.realmsgos.org`) |
| `realmsgos_marketplace_backend` | Marketplace API |
| `realmsgos_casals_backend` | Conductor for the Realms product stack |
| `realmsgos_casals_frontend` | Casals UI |
| `realmsgos_casals_multisig` | Root governance for the realmsgos orchestra |
| `realmsgos_casals_file_registry_backend` | **Package catalog**: extensions, codices, branding — what the marketplace displays. Explicitly **no** GOS WASMs |
| `realmsgos_casals_file_registry_frontend` | Admin UI for the catalog |

### `realms new --deploy-mode=gaas|standalone` — one realm

Both modes create exactly two canisters:

| Canister | Role |
|---|---|
| `realms_backend` | Realm logic; extensions/codices live as files inside it |
| `realms_frontend` | Asset canister (`/ext/…` bundles, `/custom/` branding) |

- **`gaas` mode**: queues via `gaas_realm_installer` / `gaas_realm_registry_backend`.
  Realm WASM pulled from `gaas_casals_file_registry_backend`; extensions/codices
  from `realmsgos_casals_file_registry_backend`. Baton created by the installer
  (`create_stand_baton`). Registered in the GaaS.
- **`standalone` mode**: direct canister create + install from **Realms GitHub
  release artifacts** (`realm_backend.wasm.gz`, `realm_frontend.tar.gz` — already
  published by `release.yml`). No registry, no installer, no credits. Not
  registered in any GaaS.
- Token/NFT canisters are **referenced, never minted** (v1:
  `--token-canister` required when `--token-symbol` is set).

## Locked decisions

1. **Standalone WASM source = Realms GitHub release.** The realmsgos catalog
   excludes GOS WASMs by design, and a standalone realm touches no GaaS, so
   release artifacts are the only remaining source.
2. **Two full Casals stacks per environment** (`gaas_casals_*` +
   `realmsgos_casals_*`). Deliberate duplication: GaaS platform ops are isolated
   from Realms product ops. Cost is roughly double the conductor/multisig/
   registry canisters versus today's single-conductor model — accepted.
3. **Both file registries carry the orchestration templates** (baton +
   multisig WASMs). Each Casals must be able to `deploy_sheet` and provision
   batons self-sufficiently.

## Gaps / work items

### W1 — Casals GitHub release for orchestration template WASMs (blocker)

Today `seed_orchestration_templates` (`cli/gaas/conductor_seed.py`) resolves
`orchestration-baton@1.3.0.wasm.gz` and `orchestration-multisig@1.2.0.wasm.gz`
from a **local Casals source checkout** (`--casals-src`, `CASALS_SRC`, or the
hardcoded `/srv/dev/Casals` fallback), building them via
`scripts/build_orchestration_templates.sh` when absent. There is no release
fetch.

Required:

- A Casals release workflow that publishes both template WASMs as release
  assets (versioned: `orchestration-baton@<ver>.wasm.gz`,
  `orchestration-multisig@<ver>.wasm.gz`).
- CLI support to fetch them from a pinned Casals release (same pattern as
  `fetch_gos_artifacts.py` for GOS WASMs), replacing the local-checkout
  dependency.

### W2 — `realms seed` command (new)

Does not exist. Closest current code is `realms env deploy` (product stack:
file_registry pair + marketplace pair) plus the Casals/multisig/template
phases inside `gaas new` that must move out. `realms seed` owns:

- Create + configure `realmsgos_casals_*` stack (backend, frontend, multisig
  via `deploy_sheet`, file-registry pair with templates uploaded + authorized).
- Create + configure marketplace pair; wire `*.realmsgos.org` DNS.
- Publish the extension/codex/branding catalog into
  `realmsgos_casals_file_registry_backend`.

### W3 — Slim `gaas new`

Remove from its phase list: extension/codex catalog seeding (today phase 6,
`seed_codex_catalog`), marketplace creation, and the `*.realmsgos.org` surface.
Keep: registry pair, installer, `gaas_casals_*` stack, GOS WASM seeding
(Realms GOS + Monad GOS) into `gaas_casals_file_registry_backend`.
`gaas new` takes a pointer to already-seeded Realms infra (realmsgos
file-registry id) and writes it into installer/registry config so realm
provisioning can resolve extension/codex packages.

### W4 — `realms new --deploy-mode`

Today `realms new` hard-requires `--gaas-config` (registry + installer IDs).
Add `--deploy-mode=gaas|standalone` (default `gaas` when `--gaas-config` is
present). Standalone path: direct `dfx canister create` ×2, install realm
backend/frontend from the pinned Realms GitHub release, write
`canister_ids.js`, optional branding upload. No registry call, no credits, no
installer job.

### W5 — Canister naming migration

Adopt the `gaas_*` / `realmsgos_*` prefixes in descriptors, `known.py`
(`PLATFORM_CANISTER_NAMES`), `canister_ids.json`, and environment JSONs.
Cosmetic but wide-ranging; do it as part of W2/W3, not as a standalone rename.

## What already matches

The registry content split is **de facto true today** — verified on the
2026-08-31 demo rebuild: 341 chunk uploads went to `casals_file_registry`
(GOS WASMs + baton + multisig templates), 212 to `file_registry`
(extensions/codices). `_gos_binary_registry_id` already prefers
`casals_file_registry` for GOS binaries. The design names and formalizes a
separation the code half-implements.

## Build order

1. **W1** — Casals release workflow (unblocks both seeds).
2. **W2** — `realms seed`.
3. **W3** — slim `gaas new` (consumes W1, points at W2 output).
4. **W4** — `realms new --deploy-mode`.

## Explicit non-goals

- **No shared single Casals** per environment (decision 2).
- **No GOS WASMs in the realmsgos catalog** — the marketplace displays
  packages, not platform binaries.
- **No token/NFT minting** in `realms new` v1 — existing canister references
  only.
- **No realm creation in `gaas new` or `realms seed`** — realms come only
  from `realms new` (or the equivalent wizard path against a running GaaS).
