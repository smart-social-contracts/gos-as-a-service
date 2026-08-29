# GaaS CLI — descriptor-driven environment deployment

The **gaas** CLI deploys a complete GOS-as-a-Service (GaaS) environment from a single JSON **descriptor**: platform canisters, file registry seeding, frontend builds, DNS wiring, and smoke checks. It is the user-facing entry point for [one-command, descriptor-driven GaaS environment deployment](https://github.com/smart-social-contracts/gos-as-a-service/issues/1).

Dogfood descriptors for our live fleets live in [`environments/`](../environments/) (`test.json`, `staging.json`, `demo.json`).

## Operator output and run logs

During `gaas new` and `gaas seed`, gaas keeps the terminal focused on progress: stage headers (`[N/13]`), one-line status per build/deploy step, tables (cycles plan, seed summary, deployment summary), warnings/errors, and intentional interactive prompts.

Verbose subprocess output (npm/vite builds, `dfx deploy`/`install`, git clone noise) is appended to a per-invocation log file instead of the console:

```
~/.gaas/logs/<environment-name>-<UTC-timestamp>.log
```

Example: `~/.gaas/logs/test-20260809-201530.log` for environment `test`.

gaas prints `Full logs: <path>` immediately after preflight succeeds and again when the run finishes (success or failure). On command failure, the last ~40 lines of that command's output are also printed to the console so you can debug without opening the log.

## Single confirmation point

Mutating deploy steps — including IC asset-canister reinstalls for `realm_registry_frontend` and `casals_frontend` (which wipe existing frontend state) — are covered by a single upfront confirmation:

- Interactive wizard: **Deploy now?** (enhanced message listing asset reinstalls on IC)
- Descriptor mode on a TTY: same confirmation before the pipeline starts
- `--yes`: skip all confirmations; gaas passes `--yes` to `dfx` for install/reinstall operations so no mid-run `dfx` prompts appear

The only mid-run interactive prompts that remain are intentional gaas flows (for example, granting Casals commander principals at the end of deploy).

## Install

```bash
cd cli
python3 -m venv .venv
.venv/bin/pip install -e .
gaas --help
```

## Quickstart A — interactive wizard

Run without arguments to start the wizard:

```bash
gaas new
```

The wizard prompts for:

1. Environment name (slug)
2. Domain (hostname for the registry frontend / portal)
3. Network (`ic` or `local`)
4. dfx identity
5. GOS implementation(s) and version(s)
6. Existing canister IDs (leave blank to create new ones)
7. Casals version
8. Optional billing and deploy service URLs
9. Descriptor output path

It writes a descriptor JSON file, prints it for review, and asks **Deploy now?** If you confirm, the deploy pipeline runs immediately. Otherwise it prints the resume command:

```bash
gaas new my-env.gaas.json --identity deployer --network ic
```

## Quickstart B — descriptor file

Deploy from a checked-in or hand-authored descriptor:

```bash
gaas new environments/test.json --identity deployer --network ic
```

### Wiping backends (`--reinstall-backends`)

By default, backend canisters (`realm_registry_backend`, `realm_installer`, `casals_backend`,
`casals_file_registry`) are **upgraded in place** — their state survives. Frontend asset
canisters are always reinstalled (wiped and rebuilt from source).

Pass `--reinstall-backends` to wipe backends via `--mode reinstall` on the same canister IDs
(nothing is destroyed, no new canisters are created):

```bash
gaas new environments/test.json --identity deployer --network ic --reinstall-backends
```

The pipeline re-seeds platform state afterwards (file registry artifacts, conductor orchestra,
codex catalog, multisig, commanders), but **registry user data — realms, credits, slugs — is
permanently reset** and not restored. Never use this against a live environment (e.g. staging)
unless a full clean slate is intended.

### Rebuild except DNS-mapped frontends (`--destroy-except-realm-registry-frontend`)

By default (and with `--reinstall-backends`), platform canisters keep the **same IDs** — backends are
upgraded or reinstalled in place; only Casals-managed realm stands are drain-deleted via `gaas destroy`.

Pass `--destroy-except-realm-registry-frontend` when DNS-mapped frontends must stay on-chain but
everything else — including other frontends such as `casals_frontend` — should be recreated:

- **`realm_registry_frontend`** — required; `*.gos.earth` (e.g. staging `77243-aqaaa-aaaau-aggza-cai`)
- **`marketplace_frontend`** — preserved when present in the descriptor; `*.realmsgos.org`

```bash
gaas new environments/staging.json --identity deployer --network ic --yes --destroy-except-realm-registry-frontend
```

This **first phase**:

1. Drain-destroys every orchestra/registry/platform canister except DNS-mapped frontends
2. Converts leftover ICP in the Casals treasury
3. Evacuates cycles to your **cycles wallet** (not the frontends — asset canisters cannot fund creates). If `dfx identity get-wallet` is unset, gaas creates a temporary holding canister from the cycles ledger (1T; IC create fee is 0.5T), evacuates onto it, then deletes that canister so the cycles refund to the identity's cycles ledger (the account `create --no-wallet` spends from). Set `GAAS_CYCLES_HOLDING=<canister-id>` to reuse a leftover holding canister after a failed destroy instead of paying the create fee again. If Casals is frozen (`IC0207`), gaas tops it up from the cycles ledger and retries the destroy call once.
4. Dust-deletes the Casals conductor when balance ≤ 500B cycles
5. Clears destroyed IDs from the descriptor (DNS-mapped frontend IDs kept)

Then the normal pipeline runs: create/install/seed backends and **adopts** the existing DNS-mapped frontends.
Compatible with `--reinstall-backends` (new backends are empty anyway).

| Mode | Canister IDs | DNS frontends | Other frontends | User/registry data |
|---|---|---|---|---|
| default | same | reinstalled in place | reinstalled in place | kept |
| `--reinstall-backends` | same | reinstalled | reinstalled | wiped (re-seeded platform state) |
| `--destroy-except-realm-registry-frontend` | new (except DNS frontends) | adopted | destroyed, then new | wiped |

Never run raw `dfx canister delete` — it burns leftover cycles.

### Annotated example

```json
{
  "version": 1,
  "name": "test",
  "domain": "test.gos.earth",
  "gos": [
    {
      "implementation": "realms-gos",
      "version": "v0.4.0",
      "release_repo": "smart-social-contracts/realms",
      "artifacts": {
        "backend_wasm_key": "realm-backend",
        "frontend_wasm_key": "realm-assets"
      },
      "loader_profile": "realms-iframe-v1"
    }
  ],
  "canisters": {
    "realm_registry_backend": "yhw3g-fyaaa-aaaas-qgorq-cai",
    "realm_registry_frontend": "qtank-3qaaa-aaaaa-qhb6q-cai",
    "realm_installer": "fltjm-tyaaa-aaaap-qunhq-cai",
    "file_registry": "uq2mu-kaaaa-aaaah-avqcq-cai",
    "file_registry_frontend": "2no7h-xqaaa-aaaad-qlxeq-cai",
    "casals_backend": "qthgp-3yaaa-aaaae-agveq-cai",
    "casals_frontend": "qic2k-baaaa-aaaae-agvga-cai"
  },
  "casals": {
    "version": "v0.3.0",
    "release_repo": "smart-social-contracts/Casals"
  },
  "services": {
    "billing_url": "https://billing.realmsgos.dev",
    "deploy_url": "https://deploy.realmsgos.dev"
  },
  "dns": {
    "provider": "manual"
  }
}
```

| Field | Meaning |
|---|---|
| `version` | Descriptor schema version; must be `1`. |
| `name` | Environment slug (lowercase alphanumeric + hyphens). |
| `domain` | Portal hostname (e.g. `test.gos.earth`). |
| `gos[]` | GOS implementations to seed into the file registry. |
| `canisters` | Existing canister IDs; omit a key to let gaas create that canister. |
| `casals` | Casals release used when provisioning realms via the installer. |
| `services` | Off-chain service URLs baked into the registry frontend build. |
| `dns` | DNS provider hint; only `manual` is supported today. |

## Descriptor reference

Schema is enforced by `cli/gaas/descriptor.py` and `cli/gaas/known.py`.

### Top-level fields

| Field | Required | Default | Description |
|---|---|---|---|
| `version` | no | `1` | Descriptor schema version. Only `1` is supported. |
| `name` | **yes** | — | Slug-safe environment name (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`). |
| `domain` | **yes** | — | Hostname for the registry frontend / federation portal. Trailing dots are stripped; lowercased. |
| `gos` | **yes** | — | Non-empty list of GOS implementations to publish in the file registry. |
| `canisters` | no | `{}` | Map of known canister name → IC canister ID. Keys must be from the known list below. Values must match the IC principal format. |
| `casals` | **yes** | — | Casals release pin for realm provisioning. |
| `services` | no | `{}` | Off-chain service URLs for the registry frontend. |
| `dns` | no | `{"provider": "manual"}` | DNS configuration. |

### `gos[]` entries

| Field | Required | Default | Description |
|---|---|---|---|
| `implementation` | **yes** | — | GOS id. Known: `realms-gos`, `monad-gos` (both available in `known.py`; live env descriptors must list `monad-gos` before the wizard offers it). |
| `version` | **yes** | — | Release tag `vX.Y.Z` (e.g. `v0.4.0`), `latest` (newest GitHub release at deploy time), or `main` (build from upstream HEAD — unreproducible; recommended for test/local only). |
| `release_repo` | **yes** | — | GitHub repo slug (`owner/repo`) for release artifacts. |
| `artifacts.backend_wasm_key` | **yes** | — | File-registry namespace key for backend WASM. Default for `realms-gos`: `realm-backend`. |
| `artifacts.frontend_wasm_key` | **yes** | — | File-registry namespace key for frontend assets. Default for `realms-gos`: `realm-assets`. |
| `loader_profile` | **yes** | — | Portal embed profile. Default for `realms-gos`: `realms-iframe-v1`. |
| `catalog` | no | implementation default | Codex/extension catalog seeding. Omitted uses the known GOS default (`realms-gos` declares `realms-codices` / `realms-extensions` fallback repos). Set to `null` to skip seeding for this entry. Override with `{ "codices_repo_suffix": "…", "extensions_repo_suffix": "…" }` (repo name only, no `owner/` prefix — the owner is taken from `release_repo`). |

**Version pins:** Semver tags (`vX.Y.Z`) fetch fixed GitHub release assets and seed the file registry under the bare version (`0.4.0`). `latest` resolves the newest GitHub release at deploy time (cached for the process) and uses the resolved tag for fetching while catalog namespaces stay semver-clean. `main` shallow-clones upstream HEAD and builds WASM/frontend from source (mirroring each repo's release CI); artifacts are seeded under the `main` namespace. `main` and `latest` are accepted case-insensitively; semver tags are not. Prefer pinned semver tags for staging/production; use `main` only for test/local iteration.

During **seed file registry**, gaas uploads GOS realm WASM and frontend bundles to `casals_file_registry` when that canister is in the descriptor, otherwise to `file_registry`. It may also publish a GOS **codex catalog** and (best effort) **extension catalog** into the GaaS `file_registry` canister so realm creation can install packages such as `syntropia@latest`. Seeding runs only when the GOS implementation declares a catalog (see `known.py`) or the descriptor entry sets `catalog` to a non-null object. GOS implementations without a catalog (e.g. `monad-gos`) skip this step with a log note. For `realms-gos`, gaas resolves a Realms source checkout (reusing the clone from a `main` source build when available, otherwise shallow-cloning the pinned release tag). Codex packages are uploaded from `codices/codices/` when the Realms checkout includes that tree; if submodules were not initialized (typical for shallow clones), gaas shallow-clones the declared `codices_repo_suffix` repo (default `realms-codices`) at the same ref under the same org as `release_repo`. Unified codices (`kind: codex` with a `backend/` tree) publish to `ext/<id>/<manifest.version>/…` (manifest, `backend/**/*.py`, `backend/**/*.json`, optional frontend bundle/i18n). Legacy codices publish to the deprecated `codex/<id>/<manifest.version>/…` namespace. Extension bundles publish to `ext/<id>/<manifest.version>/…` from the Realms `extensions/` submodule when present, otherwise from a shallow clone of the declared `extensions_repo_suffix` repo (default `realms-extensions`); a missing extensions repo logs a warning and does not abort deploy, but codex publish failures do abort.

### `canisters` keys

Only these names are accepted:

| Key | Role |
|---|---|
| `realm_registry_backend` | Credits, slug claims, deployment requests |
| `realm_registry_frontend` | Create-realm wizard + federation portal |
| `realm_installer` | Deployment queue + Casals provisioning |
| `file_registry` | Realms-GOS package store (codices, extensions, marketplace approvals, version catalog). Created and installed by gaas from this repo's Basilisk `file_registry` WASM. |
| `file_registry_frontend` | File registry admin UI. Created and installed by gaas from the committed dist (release tarball when deploying a pinned platform version). |
| `marketplace_backend` | Realms marketplace backend. Created via the cycles ledger; WASM is Basilisk-built from a Realms checkout. |
| `marketplace_frontend` | **DNS-mapped adopt-only.** Realms marketplace SPA (`*.realmsgos.org`). gaas never mints a new ID; when the descriptor has this ID, gaas rebuilds the SPA and reinstalls assets onto it. |
| `casals_file_registry` | Casals-owned GOS binary store (realm WASM/frontend bundles, orchestration templates). Created on fresh deploy; omit from legacy descriptors to keep the single-`file_registry` layout. |
| `casals_backend` | Casals orchestrator backend (conductor) canister ID |
| `casals_frontend` | Casals orchestration UI (standalone assets canister) |

Leave a key out (or omit the entire `canisters` object) to create that canister during deploy. `casals_file_registry` and `marketplace_backend` are created via the cycles ledger (like `casals_backend`). `marketplace_frontend` is **never newly created** — it is DNS-mapped and only adopted when its ID is present in the descriptor.

**Two file registries:** gaas stores **GOS realm binaries** (backend WASM, frontend asset bundles) and seeds **orchestration templates** in `casals_file_registry` (falling back to `file_registry` on legacy single-registry descriptors). The GaaS `file_registry` receives the **Realms-GOS package catalog** seed (codices, extensions, marketplace namespace approvals). Casals `set_settings` receives `file_registry_canister_id` pointing at `casals_file_registry` when configured, otherwise `file_registry`.

### `casals`

| Field | Required | Default | Description |
|---|---|---|---|
| `version` | **yes** | — | Casals release tag `vX.Y.Z`, `latest`, or `main` (same semantics as `gos[].version`). Default pin: `v0.3.0`. |
| `release_repo` | no | `smart-social-contracts/Casals` | GitHub repo for Casals release artifacts. |
| `commanders` | no | `[]` | IC principals granted all-permissions section-commander rights on every orchestra section during conductor seeding (non-interactive). This unlocks the Casals web UI for those principals (the UI requires section- or stand-level commander access). You can also grant commanders interactively at the end of deploy — see [Granting Casals commanders (interactive)](#granting-casals-commanders-interactive). |

Example with extra UI admins:

```json
"casals": {
  "version": "v0.3.0",
  "commanders": [
    "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
    "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
  ]
}
```

### `cycles`

Unified cycle threshold for all platform canisters. When omitted, defaults to **2 TC** (2 trillion cycles).

| Field | Required | Default | Description |
|---|---|---|---|
| `threshold_tc` | no | `2` | Minimum/top-up threshold in teracycles (TC) for every platform canister. GaaS writes this into Casals via `set_settings` (`default_min_cycles`, `default_topup_cycles`, `treasury_reserve`, `create_cycles`) and into the realm installer via `configure` (`cycle_threshold_cycles`). |

Example:

```json
"cycles": {
  "threshold_tc": 2
}
```

### Granting Casals commanders (interactive)

After smoke checks and **before** controller topology, an interactive deploy prompts for Casals UI principals to grant as section commanders on every orchestra section. This works in production as well as test mode: the deployer identity is still a direct controller of the Casals backend until the final controller-topology phase hands control to the multisig.

The Casals UI principal is Internet-Identity-derived and depends on the frontend origin, so it cannot be known before the Casals frontend is deployed. When the prompt appears:

1. Open `https://<casals_frontend>.icp0.io` (gaas prints the URL from your descriptor).
2. Log in with Internet Identity.
3. If an access-denied modal appears, copy the principal it shows.
4. Paste each principal at the CLI prompt; press Enter on an empty line when done.

Each valid principal is granted commander rights via the conductor and appended to `casals.commanders` in the descriptor file (deduplicated). Invalid input is rejected with a warning; grant failures print an error and the prompt continues without aborting deploy.

Non-interactive runs (`--yes` or no TTY stdin) skip this step with a one-line note. Re-run `gaas new` interactively to grant commanders later (while the deployer still controls the Casals backend).

### `multisig`

Governance multisig canister for IC controller approvals (Casals backend/frontend, baton canisters, etc.). gaas deploys or adopts the canister during **Seeding conductor orchestra** (phase 6); **Configuring multisig signers** (phase 7) is a **mandatory** deploy step that calls the Motoko `configure` method on the live orchestra multisig **before** controller topology (phase 12). Every `gaas new` must leave the multisig configured as N-of-M with real signer principals — otherwise the Multisig UI shows **1-of-0** and logged-in users see **"not a signer"**.

When `backend_id` is omitted, gaas creates the multisig via the conductor sheet deploy and writes the ID back to the descriptor. On every run, gaas **reconciles** `backend_id` with the multisig canister ID in the live Casals conductor tree (`get_tree` → governance stand). A stale descriptor ID is overwritten with a warning; configuration always targets the live tree canister, not a dead or superseded ID.

| Field | Required | Default | Description |
|---|---|---|---|
| `backend_id` | no | `null` | Existing orchestration-multisig canister ID to adopt. Written back from the live conductor tree when it differs from the descriptor (e.g. after `--reinstall-backends` or a prior tree redeploy). |
| `signers` | no* | `[]` | List of IC principals who may approve governance proposals. **Required for finished governance** — set explicitly in test/demo/staging descriptors (e.g. one Internet Identity principal for 1-of-1). When empty, gaas falls back to the deployer identity as sole 1-of-1 (**legacy bootstrap only**; prefer setting signers explicitly). |
| `threshold` | no | `1` | Minimum approvals required per proposal (N in N-of-M). Must be ≤ `signers` length (after fallback). |

\*Empty `signers` is accepted but prints a deploy warning and uses the deployer; production and dogfood environments should always list real principals.

**`casals.commanders` ≠ `multisig.signers`:** `casals.commanders` grants **Casals web UI** section-commander access (orchestra dashboard, stand management). `multisig.signers` are the **IC governance** principals who approve on-chain multisig proposals (controller changes, upgrades, etc.). The same Internet Identity principal may appear in both lists, but they control different surfaces.

Example — 1-of-1 with a single Internet Identity principal:

```json
"multisig": {
  "backend_id": "rvkmh-liaaa-aaaae-agzoq-cai",
  "signers": [
    "3itd6-2sx7g-vefdk-xhebm-fucot-llay5-lhqd6-pkjac-m7mkf-vhwqq-fqe"
  ],
  "threshold": 1
}
```

Omit `backend_id` on a fresh deploy; gaas creates the multisig and persists the generated ID.

### `services`

| Field | Required | Default | Description |
|---|---|---|---|
| `billing_url` | no | `null` | Public HTTPS URL for the credits / Stripe billing service (not a secret). **When present, credits are enforced** unless `flags.can_test_mode` is set. When absent, the environment is derived **can test mode** (no credit gate). |
| `billing_service_principal` | no | `null` | IC principal allowed to call the registry's `add_credits` / `deduct_credits` (typically the realms-billing host deployer identity). When set, gaas passes it via registry `configure`; only that principal may mint credits on-chain. When unset, any caller is allowed (backward compat). |
| `deploy_url` | no | `null` | Public HTTPS URL for the off-chain deploy worker API. |
| `monitor_url` | no | `null` | Public HTTPS URL for the off-chain Casals cycles/health monitor service the conductor reports to. When set, gaas passes `monitor_service_url` and `monitor_enabled: true` to the conductor via `set_settings`. |
| `monitor_principal` | no | `null` | Public IC principal the monitor service uses (not a canister secret). When set, gaas also passes `monitor_principal` in the conductor `set_settings` payload. |

All service URLs must use `https://`. Empty strings are treated as absent. `monitor_principal` is only prompted in `gaas new` when a monitor URL is provided; `billing_service_principal` when a billing URL is provided.

The portal sends an Internet Identity delegation proof (`identity.publicKey` + `identity.delegations` from `DelegationIdentity.getDelegation().toJSON()`) and `registry_canister_id` on voucher redeem and Stripe checkout so realms-billing can verify the user (realms-billing#4).

`services.open_mode` is a deprecated alias for `flags.can_test_mode` (see [Can test mode vs billing](#can-test-mode-vs-billing)).

Our live environments use `https://billing.realmsgos.dev` and `https://deploy.realmsgos.dev` (confirmed in `src/realm_registry_frontend/src/lib/config-resolvers.js` defaults).

### Controller topology (final phase)

After smoke checks and the optional interactive commander-grant step, gaas applies IC controller sets (production vs test mode via `flags.can_test_mode`):

| Canister group | Production controllers | Test mode (`can_test_mode: true`) |
|---|---|---|
| `casals_backend`, `casals_frontend` | multisig | multisig + deployer identity |
| Infra (`realm_registry_*`, `realm_installer`, `casals_file_registry`, `file_registry`, `file_registry_frontend`, `marketplace_*` when present) | `casals_backend` | `casals_backend` + deployer |
| Baton / realm canisters (created by conductor) | baton / multisig per role | + deployer via conductor `extra_controller_principals` |

In production (no test mode), gaas loses IC control after this phase — it must remain last.

**Destroy paths (do not confuse with controller topology):**

| Path | Who | Flow |
|---|---|---|
| Portal / realm alpha teardown | `realm_installer` (Casals `delegated_destroy_principals`) | Direct Casals `destroy_stand` — **no** multisig vote |
| Casals Cycles ops (non-controller) | Multisig signers | Propose Motoko `DestroyStand` / `DestroyCanister` → threshold → multisig calls Casals |
| Casals Cycles emergency | Casals IC controllers | Direct `destroy_stand` / `destroy_canister` |

**`SetCanisterControllers` from the Multisig UI** only works when the multisig is already an IC controller of the target (true for Casals backend/frontend after this phase; **false** for infra, which is controlled by Casals). Change infra controllers **through Casals** while Casals remains a controller.

### `dns`

| Field | Required | Default | Description |
|---|---|---|---|
| `provider` | no | `"manual"` | DNS provider. Only `"manual"` is implemented; gaas prints records for you to add at your registrar. |

### Known GOS implementations (`known.py`)

| ID | Label | Default version | Release repo | Loader profile | Backend `wasm_type` |
|---|---|---|---|---|---|
| `realms-gos` | Realms GOS | `v0.3.1` | `smart-social-contracts/realms` | `realms-iframe-v1` | `basilisk` |
| `monad-gos` | Monad GOS | `v0.1.0` | `smart-social-contracts/monad-gos` | `monad-iframe-v1` | `motoko` |

Pinned versions download `monad_backend.wasm.gz` and `monad_frontend.tar.gz` from public `monad-gos` GitHub releases. `monad-gos` builds from source with `icp build monad_backend` when the descriptor pins `main`. Casals authorization uses each implementation's `wasm_type` for backend WASM (`basilisk` for Realms, `motoko` for Monad GOS). Live environment descriptors (`staging.json`, `demo.json`, `test.json`) must declare a `monad-gos` entry before the create-realm wizard can offer Monad GOS on that network.

### Cycles estimate (`known.py` / preflight)

Preflight on `--network ic` builds a **cycles plan** before deploy: wallet requirements for canisters not yet in the descriptor (creation fee + initial funding), plus minimum in-canister headroom for canisters already listed. It queries `dfx cycles balance` and `dfx canister status` for each adopted canister, prints a table, and fails with remediation commands when anything is short.

Example output (fresh deploy, all canisters missing):

```
                              Cycles plan
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Item     ┃ Required ┃ Available ┃ Shortfall ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ wallet   │   4.2 TC │    3.0 TC │    1.2 TC │
└──────────┴──────────┴───────────┴───────────┘
Suggested remediation:
  dfx cycles convert --amount=1.5 --network ic
```

Default wallet estimate per missing canister: **0.6 TC** (0.1T creation + 0.5T initial funding). Nine platform canisters are budgeted by default (`realm_registry_*`, `realm_installer`, `casals_backend`, `casals_frontend`, `casals_file_registry`, `file_registry`, `file_registry_frontend`, `marketplace_backend`). DNS-mapped `marketplace_frontend` is never cycle-budgeted for creation. Canister headrooms use the descriptor `cycles.threshold_tc` (default **2 TC**) for every platform canister. `casals_backend` additionally includes realm-provisioning budget and, when `multisig.backend_id` is unset, one extra threshold for multisig creation.

## Prerequisites

| Requirement | Notes |
|---|---|
| **dfx** | DFINITY SDK installed and on `PATH`. gaas sets `TERM=xterm` and `DFX_WARNING=-mainnet_plaintext_identity`. |
| **dfx identity** | Named identity with controller access to target canisters. Create with `dfx identity new <name>`. |
| **Cycles (IC mainnet)** | Preflight estimates wallet + canister requirements from the descriptor. Check balance: `dfx cycles balance --network ic`. Top up via the [cycles ledger](https://internetcomputer.org/docs/current/developer-docs/setup/cycles/cycles-wallet) or IC faucet for test principals. |
| **Local replica** | For `--network local`: `dfx start --background` before deploy. Preflight runs `dfx ping local`. |
| **Node.js / npm** | Required for the registry frontend build during the install-frontends phase. |
| **Casals checkout (fallback)** | If Casals release artifacts are unavailable, gaas may fall back to a local Casals repo checkout. Keep a clone of [smart-social-contracts/Casals](https://github.com/smart-social-contracts/Casals) handy. |

Validate a descriptor without deploying:

```bash
cd cli
.venv/bin/python -c "from gaas.descriptor import Descriptor; print(Descriptor.load('../environments/test.json'))"
```

## DNS guide

gaas wires a custom domain to the **registry frontend** canister (`realm_registry_frontend`). Run:

```bash
gaas dns-records environments/test.json
```

### Records gaas emits

For domain `test.gos.earth` and frontend canister `qtank-3qaaa-aaaaa-qhb6q-cai`:

| Type | Host | Value | Purpose |
|---|---|---|---|
| CNAME or ALIAS | `test.gos.earth` | `test.gos.earth.icp1.io` | Route traffic to the IC gateway |
| TXT | `_canister-id.test.gos.earth` | `qtank-3qaaa-aaaaa-qhb6q-cai` | Prove canister ownership to the IC |
| CNAME | `_acme-challenge.test.gos.earth` | `_acme-challenge.test.gos.earth.icp2.io` | Delegate ACME certificate challenge |

### Namecheap Advanced DNS walkthrough

1. Log in to Namecheap → **Domain List** → **Manage** → **Advanced DNS**.
2. **CNAME Record** (or **ALIAS** for apex): Host `@` or subdomain label (e.g. `test`), Value `test.gos.earth.icp1.io`, TTL Automatic.
3. **TXT Record**: Host `_canister-id.test` (Namecheap appends `.gos.earth`), Value the frontend canister ID.
4. **CNAME Record**: Host `_acme-challenge.test`, Value `_acme-challenge.test.gos.earth.icp2.io`.
5. Remove conflicting A/AAAA records on the same host.

### Verify loop

During the **domain wiring** phase, gaas polls public DNS every 10 seconds (default timeout 300 seconds) and checks:

- TXT at `_canister-id.<domain>` contains the frontend canister ID
- CNAME at `_acme-challenge.<domain>` points to `_acme-challenge.<domain>.icp2.io`
- CNAME/ALIAS at `<domain>` points to `<domain>.icp1.io`

### IC custom-domain registration

After DNS propagates, gaas registers the domain with the Internet Computer boundary nodes so HTTPS and canister routing work on your hostname.

### Re-run to resume

If DNS propagation times out, the pipeline pauses after the domain-wiring phase. Fix DNS at your registrar, wait for propagation, then re-run the same command:

```bash
gaas new environments/test.json --identity deployer --network ic
```

Completed phases are skipped; gaas resumes where it left off.

## Can test mode vs billing

Can test mode is resolved with this precedence (highest first):

| Setting | Effect |
|---|---|
| `flags.can_test_mode` (top level) | Explicit — always wins. Also settable via `gaas new --can-test-mode` or the wizard prompt. |
| `flags.open_mode` | Deprecated alias, still honored when `flags.can_test_mode` is absent. |
| `services.open_mode` | Deprecated alias, still honored when neither flag key is set. |
| _(neither set)_ | Derived: **can test** when `services.billing_url` is absent, **closed** (credits enforced) when a billing URL is present. |

The resolved value is always written explicitly into the registry's `configure` payload — the backend itself defaults to closed and only skips credit checks when `can_test_mode` is explicitly `true`.

When `can_test_mode` is true, gaas also calls the registry backend's `set_canister_config_json` with `test_flags: {test_mode: true, ii_bypass: true}` so the portal wizard authentication flow works without manual post-deploy steps. Production deployments (`can_test_mode` false or absent with billing) do not set these flags.

Deprecated aliases still work for backward compatibility: `flags.open_mode`, `services.open_mode`, configure/init JSON `"open_mode"`, stable storage key `env:open_mode`, CLI `--open-mode` (hidden), and settlement marker `skipped_open_mode` in older deployments.

`deploy_url` is independent: it points the registry frontend at an off-chain worker for legacy deploy paths. Omit both for fully self-contained environments.

## Third-party self-hosting

gaas descriptors are designed for **any domain** — nothing hardcodes `gos.earth` or `realmsgos.*` in the deploy pipeline. Set `domain`, `services`, and canister IDs to your own infrastructure.

**CSP caveats:**

- **Realm `frame-ancestors`:** Realms realm frontends ship with a restrictive Content-Security-Policy. The realm installer patches certified assets at provision time to add your portal origin (derived from the descriptor domain) to `frame-ancestors`, so realms embed correctly in your federation portal without manual CSP edits.
- **Casals `connect-src`:** The Casals SPA allowlists IC hosts only. When `services.monitor_url` is set, gaas merges that origin into the Casals frontend `.ic-assets.json5` `connect-src` (and keeps the existing Casals policy) so the Cycles page can reach the off-chain monitor. See [issue #19](https://github.com/smart-social-contracts/gos-as-a-service/issues/19).

## Troubleshooting

| Symptom | Cause | gaas mitigation |
|---|---|---|
| `dfx deploy` hits wrong canister / no-op | Stale `remote.id` in `dfx.json` silently redirects installs | gaas always passes **explicit canister IDs** from the descriptor to `dfx canister install`, bypassing remote.id |
| Frontend deploy fails after WASM module change | Certified-assets canisters need full reinstall, not upgrade | gaas uses `--mode reinstall` for frontend canisters |
| Realm deploy pulls wrong GOS version | Pin drift across repos | Single `gos[].version` pin in the descriptor; file registry seeded from that release |
| Empty `file_registry` canister ID | ID is assigned at first `dfx canister create` | Omit `file_registry` from `canisters` on fresh deploy; gaas writes the generated ID back to state |
| DNS verify loop times out | Registrar propagation delay or wrong host labels | Run `gaas dns-records <file>` and compare; re-run deploy after fixing records |
| Preflight: insufficient cycles | Wallet or canister below deploy estimate | Preflight prints a cycles plan table with `dfx cycles convert` / `dfx cycles top-up` remediation |
| Preflight: identity not found | Wrong `--identity` | `dfx identity list`; create or select the correct identity |
| Casals artifact fetch fails | Release missing or network error | Ensure `casals.version` tag exists on GitHub; keep a local Casals checkout as fallback |

## Command reference

```
gaas [OPTIONS] COMMAND [ARGS]...
```

Global: `--help` on any command.

### `gaas new`

Create or deploy a GaaS environment.

```
gaas new [DESCRIPTOR] [OPTIONS]
```

| Argument / flag | Description |
|---|---|
| `DESCRIPTOR` | Optional path to descriptor JSON. Omit to run the interactive wizard. |
| `--identity TEXT` | dfx identity name. Default: `default` (descriptor mode) or wizard prompt. |
| `--network [ic\|local]` | Target network. Default: `ic`. |
| `--yes` | Skip interactive confirmations (upfront deploy confirmation and Casals commander grant). gaas passes `--yes` to `dfx` for install/reinstall so no mid-run prompts appear. |

**Deploy phases** (when pipeline runs):

1. Validating descriptor, identity, cycles
2. Creating canisters
3. Installing backends
4. Configuring backends (registry, installer, casals `set_settings`)
5. Seeding file registry (GOS WASM/frontend bundles, version catalog entries, and codex/extension packages from the Realms source tree)
6. Seeding file-registry namespace approvals (`ext/` and `codex/` via marketplace `admin_approve_namespace`, after granting `_approvers`). Every successful `publish_namespace` of an `ext/` or `codex/` package also stamps immediately (republish restamps the new hash). The seed phase then force-restamps any leftover installable namespaces.
7. Seeding conductor orchestra (templates, authorized WASMs, sheet, multisig deploy)

   For each GOS entry, the conductor authorizes the **backend realm WASM** from `wasm/<backend_wasm_key>/<version>/` and the **frontend certified-assets canister WASM** (`realms-assetstorage.wasm.gz` under `wasm/realm-assetstorage/<version>/`). The frontend dist bundle remains in `frontend/<frontend_wasm_key>/<version>/` for the realm installer to sync after canister install; it is not registered as an installable WASM module.

   After the sheet and governance multisig are in place, gaas registers the platform canisters (realm registry, realm installer, GaaS file registry, Casals file registry when present — backends and frontends) under **Infra/platform** in the conductor orchestra. Only canisters tracked in the orchestra tree are monitored by the conductor's cycles autopilot; this registration ensures those platform canisters receive automatic cycle monitoring and top-ups. Cycle thresholds come from `set_settings` using `descriptor.cycles.threshold_tc` (default 2 TC) — one floor for every canister.

   Immediately afterward, gaas **primes the conductor cycles snapshot**: it reads `get_tree`, calls `refresh_canisters` in batches of up to three names, then verifies via `get_cycles_cached` that every orchestra canister appears in the persisted snapshot. Missing rows fail the deploy loudly; per-canister refresh errors produce warnings. This prevents a fresh deploy from leaving the Casals Orchestra dashboard at "Canisters: 0".
8. **Configuring multisig signers (mandatory)** — reconcile `multisig.backend_id` with the live Casals tree, then call Motoko `configure` with `multisig.signers` and `threshold` (default 1-of-N). Must complete before controller topology; without it the multisig shows 1-of-0 and UI users are not signers. Empty `signers` falls back to deployer-only 1-of-1 (legacy).
9. Building + installing frontends
10. Domain wiring (DNS verify + IC registration)
11. Smoke checks
12. Granting Casals commanders (interactive; skipped with `--yes` or non-TTY)
13. Applying controller topology (final — gaas may lose control in production)

If a phase is not yet implemented, the pipeline pauses and prints a resume command.

### `gaas seed`

Re-seed GOS realm artifacts and conductor WASM authorization on an **existing** environment — without creating canisters, running cycle preflight, deploying frontends, or wiring DNS.

Use this when iterating on realm backend/frontend builds against a test environment: rebuild from source, run `gaas seed`, and the file registry plus Casals conductor pick up the new WASM hashes (including `add_authorized_wasm` for the conductor).

```
gaas seed DESCRIPTOR --identity NAME [--network ic|local] [--yes] [--casals-src PATH]
```

| Argument / flag | Description |
|---|---|
| `DESCRIPTOR` | Path to descriptor JSON (required). |
| `--identity TEXT` | dfx identity name (required). |
| `--network [ic\|local]` | Target network. Default: `ic`. |
| `--yes` | Skip interactive confirmations. |
| `--casals-src PATH` | Local Casals checkout for orchestration template WASM. |

**Seed phases** (artifact pipeline only):

1. Validating descriptor and required canister IDs (`casals_backend`, platform canisters used by conductor seed, and at least one GOS binary registry — `casals_file_registry` preferred, `file_registry` as legacy fallback)
2. Seeding file registry (GOS WASM/frontend bundles to `casals_file_registry`; version catalog and codex/extension packages to `file_registry`)
3. Seeding file-registry namespace approvals (`ext/` and `codex/` only — grants marketplace approver ACL on `_approvers`, then force-calls `admin_approve_namespace` for each installable namespace so republished hashes are restamped; skipped when `file_registry` or `marketplace_backend` is absent from the descriptor)

### `gaas stamp-namespace-approvals`

Stamp (or restamp) marketplace approvals on file-registry `ext/` and `codex/` namespaces after a first-party publish. Routes through marketplace `admin_approve_namespace` so realms accept the stamp. **Refuses demo.**

```
gaas stamp-namespace-approvals DESCRIPTOR --identity NAME [--network ic|local] [--force|--no-force] [--namespace ext/foo/1.0.0]
```

Used by Test/staging file-publish pipelines. Realms `deploy-files.yml` must call this (or `scripts/stamp_namespace_approvals.sh -e test|staging`) after `realms files publish` so a new version cannot be born unapproved. On IC, `gaas` `publish_namespace` of an installable namespace fails closed if `marketplace_backend` is missing.
4. Seeding conductor orchestra (templates, authorized WASMs, sheet, multisig, platform stand registration for present canisters, and per-canister cycle policies)

The command prints a summary of uploaded artifact keys/hashes and which WASM hashes were newly authorized vs already authorized on the conductor. Re-running with unchanged artifacts is idempotent.

Requires canister IDs already present in the descriptor. Does **not** run deployer cycle checks, canister creation, backend install/configure, frontend deploy, DNS, smoke checks, commander grants, or controller topology.

### First-party file-registry publish and approval stamps

Realm install reads `get_namespace_approval_icc` / `approved: true`. Marketplace `verification_status` is UI-only. Approvals are hash-bound: a republish invalidates `content_matches` until the namespace is stamped again.

`gaas store_file` / `publish_namespace` (and therefore `gaas seed` catalog publish) now finalize every `ext/` and `codex/` publish by granting marketplace `_approvers` and calling marketplace `admin_approve_namespace`. The call is attributed to the marketplace principal, which is who realms trust. On `ic`, publish of an installable namespace without `marketplace_backend` fails closed.

After Realms `files publish` / `deploy-files.yml` (Test or staging only — never demo):

```bash
# from this repo, after files are on the registry
scripts/stamp_namespace_approvals.sh -e test --identity ci
# or
gaas stamp-namespace-approvals environments/test.json --identity ci --network ic --force
```

Add that as a required step after `realms files publish` in Realms `.github/workflows/deploy-files.yml` when `environment` is `test` or `staging`. Do not run it against demo.

### `gaas status`

Print canister status for every ID listed in the descriptor.

```
gaas status DESCRIPTOR [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--network TEXT` | `ic` | dfx network passed to `dfx canister status`. |

### `gaas dns-records`

Print DNS records required for the environment domain.

```
gaas dns-records DESCRIPTOR
```

Uses `realm_registry_frontend` from the descriptor; if missing, prints a placeholder warning and uses a sample ID for preview only.

## Related

- [Issue #1 — one-command GaaS deployment](https://github.com/smart-social-contracts/gos-as-a-service/issues/1)
- Live dogfood descriptors: [`environments/`](../environments/)
- Agent deploy loops and canister IDs: [AGENTS.md](../AGENTS.md)
