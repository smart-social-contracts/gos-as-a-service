# Platform layer split — `gaas new` / `realms seed` / `realms new`

**Status:** proposal (not implemented). Recorded 2026-08-31.

Today `gaas new` deploys three unrelated concerns in one command: the GaaS platform
(registry + installer + portal), the Realms product surface (marketplace, extension
catalog), and a Casals conductor shared between them. This document splits those
concerns across three commands, each owning a disjoint set of canisters.

The on-chain separation already exists — the split is about **command ownership**, not
rewiring canisters. A single `gaas new` run on demo already uploads GOS binaries to
`casals_file_registry` (341 chunk calls) and extension/codex packages to `file_registry`
(212 chunk calls); they are simply owned by the same command today.

## The three layers

| Command | Deploys | Scope |
|---|---|---|
| `gaas new` | One GOS-as-a-Service instance (`*.gos.earth`) | Per instance; self-contained |
| `realms seed` | Realms GOS product infrastructure (`*.realmsgos.org`) | Per network (demo / staging / test) |
| `realms new` | One realm | Per realm |

Each of the first two owns its **own** Casals stack. This is deliberate: the Realms GOS
team maintains and upgrades marketplace infrastructure independently of any GaaS
operator, and both benefit from Casals' snapshot → install → verify → rollback path.

## Canister ownership

### `gaas new` — one GaaS instance

| Canister | Contents / role |
|---|---|
| `gaas_realm_registry_backend` | Realm catalog, credits, `request_deployment` |
| `gaas_realm_registry_frontend` | Wizard + portal (DNS-mapped, e.g. `demo.gos.earth`) |
| `gaas_realm_installer` | Deployment queue; provisions realm stands via Casals |
| `gaas_casals_backend` | Orchestrates every canister in this GaaS instance, including provisioned GOS canisters and their baton canisters |
| `gaas_casals_frontend` | Casals UI |
| `gaas_casals_multisig` | Orchestra root control |
| `gaas_casals_file_registry_backend` | Supported GOS WASMs (Realms GOS, Monad GOS — backend + frontend/asset), plus the baton WASM |
| `gaas_casals_file_registry_frontend` | File registry admin UI |

A GaaS instance is **GOS-agnostic**: it holds no Realms-specific state. It does not own
a marketplace, and it does not hold the extension/codex catalog.

### `realms seed` — Realms GOS infrastructure (per network)

| Canister | Contents / role |
|---|---|
| `realmsgos_marketplace_frontend` | Marketplace SPA; also the Realms GOS landing site (DNS-mapped, e.g. `demo.realmsgos.org`) |
| `realmsgos_marketplace_backend` | Marketplace logic |
| `realmsgos_casals_backend` | Orchestrates the Realms product canisters |
| `realmsgos_casals_frontend` | Casals UI |
| `realmsgos_casals_multisig` | Orchestra root control |
| `realmsgos_casals_file_registry_backend` | Extensions, codices, branding — the packages shown in the marketplace. **Not** Realms GOS WASMs |
| `realmsgos_casals_file_registry_frontend` | File registry admin UI |

This layer also **publishes** the extension/codex catalog. Neither `gaas new` nor
`realms new` writes packages into it.

### `realms new` — one realm

Selected by `--deploy-mode=gaas|standalone`.

| Mode | Behaviour | Canisters |
|---|---|---|
| `gaas` | Calls `gaas_realm_installer` / `gaas_realm_registry_backend` to spin up a Realms GOS instance inside that GaaS | `realm_backend`, `realm_frontend`, + orchestration baton |
| `standalone` | Deploys a standalone Realms GOS instance, not registered with any GaaS | `realm_backend`, `realm_frontend` |

Extensions and codices are pulled from `realmsgos_casals_file_registry_backend` in both
modes, so a standalone realm still depends on `realms seed` having run on that network.
Token canisters are referenced, never minted (see `--token-canister`).

## Artifact sources

All WASMs come from **GitHub releases**. Nothing is built from source at deploy time,
and nothing installs from an on-chain "master WASM store" canister.

| Artifact | Consumed by | Source |
|---|---|---|
| Realms GOS / Monad GOS backend + frontend | `gaas new` → `gaas_casals_file_registry_backend` | GitHub release of the respective GOS repo |
| `realm_backend` / `realm_frontend` for a standalone realm | `realms new --deploy-mode=standalone` | GitHub release (`smart-social-contracts/realms`) |
| Casals backend / frontend / file registry | `gaas new`, `realms seed` | GitHub release (`smart-social-contracts/casals`) |
| Orchestration baton, orchestration multisig | `gaas new`, `realms seed` | GitHub release (`smart-social-contracts/casals`) |

An existing GaaS instance picks up a newly released GOS version via `gaas seed`, not a
redeploy.

## Prerequisite: Casals must publish release assets

**Casals `v0.3.0` publishes zero release assets** (`gh release view --json assets` returns
`{"assets":[]}`). Every Casals-side artifact is currently built from a source checkout —
hence `resolve_casals_src()` and the `--casals-src` flag in the `gaas` CLI.

The consumer side already expects release-style filenames, so no naming decisions are
needed — only a release workflow in the Casals repo publishing:

- `casals_backend.wasm.gz` — expected by `known.py` (`CASALS_BACKEND_WASM_ASSET`)
- `casals_frontend.tar.gz` — expected by `known.py` (`CASALS_FRONTEND_ARCHIVE`)
- `file_registry.wasm.gz` — expected by `known.py` (`CASALS_FILE_REGISTRY_WASM_ASSETS`)
- `orchestration-baton@<ver>.wasm.gz` — expected by `conductor_seed.py`
- `orchestration-multisig@<ver>.wasm.gz` — expected by `conductor_seed.py`

Until that workflow exists, `gaas new` and `realms seed` cannot drop their source-build
path.

## Deltas from today

| Area | Today | After the split |
|---|---|---|
| `gaas new` canisters | 9 named, including `file_registry`, `file_registry_frontend`, `marketplace_backend` | 8 named; marketplace and the package catalog move to `realms seed` |
| Extension/codex catalog | Seeded by `gaas new` phase 6 | Seeded by `realms seed` |
| Installer config | Init args include `file_registry_id` and `marketplace_id` | Both removed. The Realms GOS WASM knows its own registry, so the installer stays GOS-agnostic |
| `realms new` standalone | **Does not exist** — `--gaas-config` is hard-required in three places in `commands/new.py` | New code path; the command is currently built entirely around the registry/installer queue (credits check, `request_deployment`, job polling) |
| `realms env deploy` | Deploys the per-env product stack | Absorbed by `realms seed`, which is a superset (product stack + Casals stack + catalog seeding) |
| Multisig | Minted from the Casals pool by `deploy_sheet` with an auto-assigned ID | Named and tracked in `canister_ids.json` |
| Casals per network | One conductor doing both jobs | Two independent stacks, one per layer |

## Consequences

**Canister count roughly doubles: 9 → 15.** At the 1T-per-create default that is ~15T for
a full two-stack rebuild versus ~9T today. The two stacks rebuild independently, so both
are rarely paid for at once.

**Dependency order is `realms seed` → `gaas new` → `realms new`, but only loosely.**
`gaas new` does not depend on `realms seed` at all, since GOS WASMs come from GitHub. A
Realms GOS realm does depend on a seeded catalog on its network, in both deploy modes.

**Naming collision to resolve before implementation.** `gaas seed` already exists and means
"re-seed GOS artifacts and conductor authorization on an existing environment." A
`realms seed` that *deploys* infrastructure is a second, unrelated meaning of the same
verb.

**Tracking the multisig matters more than it looks.** An auto-ID canister absent from
`canister_ids.json` is exactly what gets orphaned during a destroy/recreate cycle, with its
cycles stranded.

## Related

- [`GAAS_CLI.md`](GAAS_CLI.md) — current `gaas new` / `gaas seed` reference
- [`../AGENTS.md`](../AGENTS.md) — canister IDs, deploy paths
- [`../environments/`](../environments/) — per-environment descriptors
