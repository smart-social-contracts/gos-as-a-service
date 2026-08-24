# AGENTS.md — gos-as-a-service

Agent guidance for the GOS-as-a-Service platform (registry + installer + wizard UI).

> **WARNING:** `staging.gos.earth` is **LIVE**. Never reinstall staging canisters without explicit human instruction. Prefer read-only queries (`__browse__`, `--query`) when investigating production state.

## Do not deploy without confirmation

**Do not deploy automatically.** The human triggers all deployments.

If a change needs a deployment to take effect or to be verified, state that clearly in your reply (what, where, and why) and wait for explicit confirmation before running any deploy, install, upgrade, reinstall, rollout, seed, or publish-to-canister command.

## Repository layout

```
src/realm_registry_backend/   # Registry canister (Basilisk/Python)
src/realm_registry_frontend/  # Wizard + portal (SvelteKit)
src/realm_installer/            # Deployment queue + Casals provisioning
src/file_registry/               # Platform artifact store (GOS wasms, branding)
src/file_registry_frontend/      # File registry admin UI (static assets; release tarballs)
src/declarations/               # Vendored candid bindings for frontend build
tests/backend/                  # Unit tests (no replica)
tests/integration/              # Live-replica installer API tests
scripts/infra_dev_deploy.sh     # Fast dfx deploy (registry | installer)
```

## Known canister IDs

| Canister | Test | Demo | Staging |
|---|---|---|---|
| realm_registry_backend | `yhw3g-fyaaa-aaaas-qgorq-cai` | `rhw4p-gqaaa-aaaac-qbw7q-cai` | `fntsr-aqaaa-aaaae-ag22a-cai` |
| realm_registry_frontend | `qtank-3qaaa-aaaaa-qhb6q-cai` | `2zaor-5yaaa-aaaac-qbxaa-cai` | `77243-aqaaa-aaaau-aggza-cai` |
| realm_installer | `fltjm-tyaaa-aaaap-qunhq-cai` | `2s4td-daaaa-aaaao-bazmq-cai` | `fksuf-niaaa-aaaae-ag22q-cai` |
| file_registry | `uq2mu-kaaaa-aaaah-avqcq-cai` | `vi64l-3aaaa-aaaae-qj4va-cai` | `feqzn-wyaaa-aaaae-ag23q-cai` |
| marketplace_backend | `2wldc-niaaa-aaaad-qlxga-cai` | `ehyfg-wyaaa-aaaae-qg3qq-cai` | `l5qpy-wqaaa-aaaah-qu2mq-cai` |

Casals conductors (external platform provisioner; operated by realms fleet ops):

| Network | Conductor |
|---|---|
| test | `qthgp-3yaaa-aaaae-agveq-cai` |
| demo | `jo3cj-faaaa-aaaac-bffea-cai` |
| staging | `rbuam-sqaaa-aaaab-qhe5a-cai` |

Portal hosts: `test.gos.earth`, `demo.gos.earth`, `staging.gos.earth` → **`realm_registry_frontend`**. Realms marketplace hosts (`*.realmsgos.org`) → **`marketplace_frontend`** when declared in the descriptor (see below).

Dogfood deployment descriptors: [`environments/`](environments/) — see [docs/GAAS_CLI.md](docs/GAAS_CLI.md) for the `gaas` CLI.

## DNS-mapped frontends — why we keep `realm_registry_frontend` and `marketplace_frontend`

`*.gos.earth` does **not** point at “the GaaS stack.” Registrar records and IC custom-domain registration bind the portal hostname to **one canister ID**: `realm_registry_frontend` (staging: `77243-aqaaa-aaaau-aggza-cai` → `staging.gos.earth`).

`*.realmsgos.org` is DNS-mapped the same way to **`marketplace_frontend`** when that canister is in the environment descriptor (staging: `h4gmt-waaaa-aaaac-bfxoq-cai`).

Deleting either canister would:

- Break the public URL immediately (the ID in DNS / IC domain tables would be `IC0301`)
- Force new registrar records **and** a new IC boundary-node domain registration
- Cost hours of downtime and risk losing the hostname

A deleted canister ID **cannot be reused**. The replacement frontend would be a new ID, so DNS must be redone.

**Other frontends are not DNS-mapped** (`casals_frontend`, file-registry UI, realm UIs). They can be destroyed and recreated with new IDs. Only the DNS-mapped frontends must survive a full rebuild.

**Cycle-safe rebuild** (drain-destroy everything else, including other frontends; evacuate treasury to the cycles wallet; recreate; adopt the existing DNS canisters):

```bash
gaas new environments/staging.json --identity deployer --network ic --yes \
  --destroy-except-realm-registry-frontend
```

Never `dfx canister delete` on these canisters (or any fat canister) — leftover cycles are burned, and you would still have to remap DNS. Wipe assets in place (`reinstall`) or use the flag above. Details: [docs/GAAS_CLI.md](docs/GAAS_CLI.md#rebuild-except-realm-registry-frontend---destroy-except-realm-registry-frontend).

## gaas deploy — mandatory multisig

Every **`gaas new`** deploy must configure the orchestra multisig as **N-of-M** via deploy phase **`configure_multisig`** (Motoko `configure` on the live tree canister). This runs **before** controller topology. Skipping or leaving signers unset yields **1-of-0** in the Multisig UI and **"not a signer"** for Internet Identity logins.

**Agent actions:**

1. Set `multisig.signers` (list of IC principals) and `multisig.threshold` (default `1`) in the environment descriptor under [`environments/`](environments/) (`test.json`, `demo.json`, `staging.json`).
2. Example — 1-of-1 with one Internet Identity principal:

```json
"multisig": {
  "signers": ["<ii-principal>"],
  "threshold": 1
}
```

3. **`casals.commanders`** (Casals UI section access) **≠** **`multisig.signers`** (IC governance approvals). Grant both when the same operator needs UI access and multisig signing.
4. gaas reconciles `multisig.backend_id` with the live Casals conductor tree; stale descriptor IDs are overwritten automatically.
5. **Destroy:** portal/realm teardown uses `delegated_destroy` (installer → Casals) without a multisig vote; the installer **refuses** destroy when `casals_canister_id` is unset (no raw IC delete). Operators and agents must **never** run `dfx canister delete`. Use `gaas destroy` or Casals `destroy_stand` / `destroy_canister`. Platform canisters are wiped in place (`gaas new --reinstall-backends`), not deleted. A full rebuild that **keeps DNS-mapped frontends** (`realm_registry_frontend` for `*.gos.earth`; `marketplace_frontend` for `*.realmsgos.org` when in the descriptor) is `gaas new --destroy-except-realm-registry-frontend` — see [DNS-mapped frontends](#dns-mapped-frontends--why-we-keep-realm_registry_frontend-and-marketplace_frontend). Casals Cycles ops destroy for non-controllers goes through Motoko `DestroyStand` / `DestroyCanister`. Multisig `SetCanisterControllers` only works when the multisig is already an IC controller of the target (Casals yes; infra/realms `file_registry` no — see [Controller topology](docs/GAAS_CLI.md#controller-topology-final-phase)).

Full field reference, fallback behaviour, and deploy phase order: [docs/GAAS_CLI.md — `multisig`](docs/GAAS_CLI.md#multisig).

## Registry / wizard UI (staging)

The **create-realm wizard** and **deployment status page** live in
`src/realm_registry_frontend/` (`staging.gos.earth`).

**After changing wizard or deployment-progress UI, deploy the registry frontend separately**
or users will see stale behaviour (e.g. deployment stuck at "Queued" while the job is
actually installing extensions on-chain).

**Staging — use this today:**

```bash
export TERM=xterm DFX_WARNING=-mainnet_plaintext_identity
dfx identity use deployer

# Update the LIVE wizard website (required for users to see UI changes)
scripts/infra_dev_deploy.sh -e staging -f registry -c frontend
# or both backend + frontend if registry backend changed too:
# scripts/infra_dev_deploy.sh -e staging -f registry -c both
```

**Note:** `dfx build realm_registry_backend` may need an explicit basilisk step first if
it produces no WASM — run
`python -m basilisk realm_registry_backend src/realm_registry_backend/main.py`, then
`gzip -kf .basilisk/realm_registry_backend/realm_registry_backend.wasm` before
`dfx canister install …`.

**Casals rollout (`realm-registry`) — blocked until Casals is upgraded on staging:**
`realms rollout -e staging -t realm-registry -s frontend -v main` currently fails on
`upgrade_to` (orchestration governance gate when the stand's section is unset). Until
Casals is fixed on staging, `infra_dev_deploy.sh` is the supported way to put registry
UI changes live.

**Hard-refresh** the browser (Ctrl+Shift+R) after deploy — asset canisters cache aggressively.

## Fast infra deploy (dev only)

While developing registry / installer, skip Casals publish + rollout and
**deploy directly with `dfx`** from the repo root (~2–5 min per component).

**Setup (once per shell):**

```bash
export TERM=xterm
export DFX_WARNING=-mainnet_plaintext_identity
dfx identity use deployer
```

**Deploy:**

```bash
# Registry backend only (~2–3 min)
scripts/infra_dev_deploy.sh -e staging -f registry -c backend

# Registry frontend only (~3–5 min)
scripts/infra_dev_deploy.sh -e staging -f registry -c frontend

# Both
scripts/infra_dev_deploy.sh -e staging -f registry -c both

# Installer backend
scripts/infra_dev_deploy.sh -e test -f installer -c backend
```

Equivalent raw commands (registry backend example):

```bash
export TERM=xterm DFX_WARNING=-mainnet_plaintext_identity
export PATH="$PWD/.venv-basilisk/bin:$PATH"
export CANISTER_CANDID_PATH=src/realm_registry_backend/realm_registry_backend.did
export DFX_NETWORK=staging
dfx build realm_registry_backend --network staging
dfx canister install fntsr-aqaaa-aaaae-ag22a-cai --network staging --mode upgrade \
  --wasm .basilisk/realm_registry_backend/realm_registry_backend.wasm.gz
npm run build --workspace=realm_registry_frontend
dfx deploy realm_registry_frontend --network staging --yes
```

| Situation | Path |
|---|---|
| Iterating on registry/wizard during development | `scripts/infra_dev_deploy.sh` |
| Full realm deploy queue E2E on staging/demo | `scripts/test_queue_deployment_e2e.sh` |

## Credits system

Deployment billing uses a hold → capture/release pattern in `src/realm_registry_backend/api/credits.py`.

| Function | Who calls | Effect |
|---|---|---|
| `add_user_credits(principal, amount, …)` | Admin / Stripe webhook | Increases balance (max 1000 per top-up) |
| `deduct_user_credits(principal, amount, …)` | Admin | Direct spend (non-deploy) |
| `create_deployment_hold(principal, job_id, amount)` | Registry (`request_deployment`) | Deducts from balance, creates `DeploymentCreditHold` with status `held` |
| `capture_deployment_hold(job_id)` | Registry (`deployment_succeeded`) | Marks hold `captured`, adds to `total_spent` |
| `release_deployment_hold(job_id)` | Registry (`deployment_failed`) | Refunds balance, marks hold `released` |

**Deploy cost:** `DEPLOYMENT_COST_CREDITS = 5` in `main.py`. `request_deployment` checks balance ≥ 5, enqueues via installer, then creates the hold. If hold creation fails, it cancels the installer job.

Settlement is **installer-driven**: when provisioning completes, the installer calls registry `deployment_succeeded` or `deployment_failed`, which triggers capture or release.

## Slug claiming

Federation slugs map realms to portal URLs (`/r/{slug}`). Logic lives in `src/realm_registry_backend/api/slugs.py`.

**`claim_slug_by_caller`** (exposed as `claim_slug` on-chain):

- Normalizes slug (lowercase, alphanumeric + hyphens, max 48 chars).
- Rejects reserved slugs (`www`, `api`, `registry`, `create-realm`, …).
- Requires the realm to already exist in `RealmRecord` (installer calls this after `register_realm`).
- Stores metadata on `SlugRecord`:

| Field | Default (Realms GOS) | Purpose |
|---|---|---|
| `gos_implementation` | `realms-gos` | Which GOS stack serves this realm |
| `gos_version` | `""` (set at claim time) | Release tag / version string |
| `ggg_conformance` | `1.0` | GGG protocol version |
| `loader_profile` | `realms-iframe-v1` | How the portal embeds the realm frontend |

Portal URL pattern: `{portal_base}/r/{slug}` (e.g. `https://staging.gos.earth/r/my-realm`).

**`resolve_slug`** returns slug → realm_id, frontend_canister_id, GOS metadata for the portal router.

## Deploy pipeline API surface

### Registry backend (`request_deployment`)

Entry point for the wizard. Accepts a JSON manifest (realm name, network, artifact URLs/checksums, extensions, codex, optional slug).

Flow in `main.py`:

1. Optional invitation-mode gate (`ActivatedPrincipal`).
2. Credit check (≥ 5).
3. Resolve installer canister ID for the target network (`_INSTALLER_IDS` or manifest override).
4. Inter-canister call: `installer.enqueue_deployment(manifest_json)`.
5. On success: `create_deployment_hold(caller, job_id, 5)`.
6. If job status is `provisioning`: schedule async `installer.provision_via_casals(job_id)`.

Returns JSON with `job_id`, `credits_held`, `status`.

**Settlement callbacks** (installer → registry, controller-gated):

- `deployment_succeeded(job_id, caller_principal)` → `capture_deployment_hold`
- `deployment_failed(job_id, reason, caller_principal)` → `release_deployment_hold`

### Realm installer

| Method | Type | Role |
|---|---|---|
| `enqueue_deployment(manifest_json)` | update | Parse manifest, allocate job, return `job_id` |
| `provision_via_casals(job_id)` | update (async) | Opt-in Casals stand provisioning (`InstallerConfig.provision_via_casals`) |
| `report_canister_ready(…)` | update | Worker reports backend WASM installed |
| `report_frontend_verified(…)` | update | Worker confirms frontend hash |
| `get_deployment_job_status(job_id)` | query | Poll job state |
| `list_deployment_jobs()` | query | List all jobs |
| `health()` | query | `{ ok: true }` sanity check |
| `cancel_deployment(job_id)` | update | Cancel queued job |

The off-chain **realms-deployer** worker polls pending jobs, downloads release artifacts, runs `dfx` installs, and reports back. Casals path is triggered when `provision_via_casals` is enabled and the job enters `provisioning` status.

#### Platform provisioner (Casals)

Casals is the GaaS **platform provisioner** — an external on-chain orchestrator ([smart-social-contracts/casals](https://github.com/smart-social-contracts/casals)), not a canister built from this repo.

The installer → Casals contract is **runtime, by canister ID**. `InstallerConfig` on the realm_installer canister holds:

| Field | Role |
|---|---|
| `provision_via_casals` | Opt-in switch (`0` = off-Casals path, the default) |
| `casals_canister_id` | Conductor canister the installer calls |
| `casals_section` | Casals section name (default `Deployments`) |

When enabled, the registry schedules `provision_via_casals(job_id)` after enqueue. **realms** fleet ops operate the Casals conductors per network (see table above); any conforming conductor can serve a network.

Local development can run with `provision_via_casals = 0` (off-Casals path) so contributors need not deploy a local Casals conductor.

Full queue E2E test: `scripts/test_queue_deployment_e2e.sh --network staging`.

## Debugging Python canisters (`__browse__` / `__shell__`)

Registry backend and installer are Basilisk canisters. Use agent endpoints for live inspection:

### `__browse__` — read-only (query)

```bash
export TERM=xterm DFX_WARNING=-mainnet_plaintext_identity
dfx identity use deployer

dfx canister call fntsr-aqaaa-aaaae-ag22a-cai __browse__ \
  '("{\"action\": \"schema\"}")' --query --network staging
```

### `__shell__` — Python REPL (update)

Requires your dfx identity to be a **canister controller**:

```bash
dfx canister call fntsr-aqaaa-aaaae-ag22a-cai __shell__ \
  '("from realm_registry_backend.core.models import RealmRecord; print(len(list(RealmRecord.instances())))")' \
  --network staging --identity deployer
```

List realms quickly:

```bash
dfx canister call fntsr-aqaaa-aaaae-ag22a-cai list_realms '()' \
  --query --network staging
```

## Basilisk builds

```bash
python3 -m venv .venv-basilisk
.venv-basilisk/bin/pip install ic-basilisk==0.14.2 ic-basilisk-toolkit==0.5.3 \
  ic-python-db==0.11.0 ic-python-logging==0.3.4
export PATH="$PWD/.venv-basilisk/bin:$PATH"

python -m basilisk realm_registry_backend src/realm_registry_backend/main.py
python -m basilisk realm_installer src/realm_installer/main.py
```

Registry/installer use the **default** CPython template (not the Cedar realm-backend template).

## Tests

```bash
# Unit tests — no replica
pip install -r requirements-dev.txt
python3 -m pytest tests/backend/ -q

# Frontend
npm ci && npm test --workspace=realm_registry_frontend

# Integration (requires deployed realm_installer on local replica)
dfx start --background --clean
dfx deploy realm_installer realm_registry_backend
python3 tests/integration/test_realm_installer_api.py
```

## Relationship to Realms GOS

The **realms** repo consumes GaaS release artifacts. Its `dfx.json` may reference remote WASM URLs from this repo's GitHub Releases for registry/installer when running local mundus stacks. Live test/demo/staging canister IDs remain in **this** repo's `canister_ids.json`.
