# AGENTS.md — gos-as-a-service

Agent guidance for the GOS-as-a-Service platform (registry + installer + wizard UI).

> **WARNING:** `gos.earth` is **LIVE**. Never reinstall production canisters without explicit human instruction. Prefer read-only queries (`__browse__`, `--query`) when investigating production state.

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
casals.json                     # The environments (local, production): every id, host, controller and test flag
```

Canister ids, hosts and per-environment behaviour live in `casals.json` only
(read live ids with `casals export`). Canisters get theirs at runtime —
`configure` / `set_canister_config_json` for backends, the conductor-written
`/canister_ids.js` (`network`, `portal_url`, ids) for frontends. Never add a
table keyed by network name to code, scripts, workflows or docs; CI rejects id
literals outside `casals.json`.

Portal host: `environments.production.portal_host` (`gos.earth`) → **`realm_registry_frontend`**. Realms marketplace hosts (`*.realmsgos.org`) → **`marketplace_frontend`** when declared in the sheet (see below).

The environment is declared in `casals.json` and built with `casals up` (see `docs/OPERATIONS.md` and the Casals repo). **One command** does the whole thing — build → `casals pin` → `casals up` → `casals export` → `realms domains apply` → `realms files publish` → verify: `scripts/up.sh -e production --identity prod-identity --upload-identity <plain> --yes` (with `DFX_HSM_PIN`, `CLOUDFLARE_API_TOKEN`, `CASALS_HOME` set); `scripts/up.sh -e local --yes` on a laptop, or `realms/scripts/local_up.sh --gaas` for both orchestras.

## DNS-mapped frontends — why we keep `realm_registry_frontend` and `marketplace_frontend`

`*.gos.earth` does **not** point at “the GaaS stack.” Registrar records and IC custom-domain registration bind the portal hostname to **one canister ID**: `realm_registry_frontend` (the id is in `casals.json` / `casals export`).

`*.realmsgos.org` is DNS-mapped the same way to **`marketplace_frontend`** when that canister is in the sheet.

Deleting either canister would:

- Break the public URL immediately (the ID in DNS / IC domain tables would be `IC0301`)
- Force new registrar records **and** a new IC boundary-node domain registration
- Cost hours of downtime and risk losing the hostname

A deleted canister ID **cannot be reused**. The replacement frontend would be a new ID, so DNS must be redone.

**Other frontends are not DNS-mapped** (`casals_frontend`, file-registry UI, realm UIs). They can be destroyed and recreated with new IDs. Only the DNS-mapped frontends must survive a full rebuild.

Never `dfx canister delete` on these canisters (or any fat canister) — leftover cycles are burned, and you would still have to remap DNS. Wipe assets in place (`reinstall`) or let `casals destroy` sweep cycles to the deployer.

**Destroy:** portal/realm teardown uses `delegated_destroy` (installer → Casals) without a multisig vote; the installer **refuses** destroy when `casals_canister_id` is unset (no raw IC delete). Operators and agents must **never** run `dfx canister delete`. Use `casals destroy` or Casals `destroy_stand` / `destroy_canister`. Casals Cycles ops destroy for non-controllers goes through Motoko `DestroyStand` / `DestroyCanister`. Multisig `SetCanisterControllers` only works when the multisig is already an IC controller of the target.

## Registry / wizard UI

The **create-realm wizard** and **deployment status page** live in
`src/realm_registry_frontend/` (`gos.earth`).

**After changing wizard or deployment-progress UI, deploy the registry frontend**
or users will see stale behaviour (e.g. deployment stuck at "Queued" while the job is
actually installing extensions on-chain). The deploy is the sheet's: rebuild the
dist (`npm run build --workspace=realm_registry_frontend`), then `casals up -e
production` from the Casals repo converges the `realm-registry-frontend` canister
(see `docs/OPERATIONS.md`). Never `dfx deploy` a canister the conductor controls.

**Note:** `dfx build realm_registry_backend` may need an explicit basilisk step first if
it produces no WASM — run
`python -m basilisk realm_registry_backend src/realm_registry_backend/main.py`, then
`gzip -kf .basilisk/realm_registry_backend/realm_registry_backend.wasm` before
`dfx canister install …` on a **local** replica.

**Hard-refresh** the browser (Ctrl+Shift+R) after deploy — asset canisters cache aggressively.

### Mobile bottom chrome (corner ears overlay)

On mobile the map is full-viewport; stats and version sit in a transparent center
strip over the globe, with compass / assistant **corner ears** fixed to the bottom
left and right (`RegistryMobileChrome.svelte`).

- `position: fixed; bottom: 0` — ears anchor to the viewport, not document flow.
- `env(safe-area-inset-bottom)` on the chrome wrapper only.
- **No UA sniffing** — do not branch layout on `navigator.userAgent`.
- Test mode banner height still comes from `TestModeBanner` →
  `--test-mode-banner-height` (`readTestModeBannerHeightPx` for assistant offsets).

Minor clipping in some in-app browsers (Brave, DDG) is usually the browser chrome
overlapping fixed UI, not a missing page inset — avoid inventing per-browser padding
unless a real device test shows content is unreachable.

## Deploying registry / installer changes

There is one path per environment: `scripts/up.sh -e <env>`, i.e. rebuild, then
`casals up -e <env>` on `casals.json`, then publish (`docs/OPERATIONS.md`).
`local` is a fresh replica (the script builds everything from source);
`production` is `gos.earth`. The
conductor is the controller of every canister it manages, so an imperative
`dfx deploy --network …` is not a shortcut — it fails, and if it did not it
would leave the sheet lying.

For a local replica without the conductor (single-canister iteration):

```bash
export PATH="$PWD/.venv-basilisk/bin:$PATH"
dfx start --background --clean
dfx deploy realm_registry_backend
npm run build --workspace=realm_registry_frontend && dfx deploy realm_registry_frontend
```

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

Portal URL pattern: `{portal_base}/r/{slug}` (e.g. `https://gos.earth/r/my-realm`); `portal_base` is the registry's configured `portal_url` (casals.json), never derived from a network name.

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
| `retry_deployment(job_id)` | update | **Resume** a failed job from its failed step (owner or controller) |

The off-chain **realms-deployer** worker polls pending jobs, downloads release artifacts, runs `dfx` installs, and reports back. Casals path is triggered when `provision_via_casals` is enabled and the job enters `provisioning` status.

#### Failed deploys resume; they never replay

A deploy that failed after its canisters existed must not be re-driven from
step zero — `enter_setup` and `configure_canister_ids` are one-shot on a live
stand, so a replay fails every bootstrap step and leaves the realm half-built.

- Deploy task ids come from `deploy_resume.deploy_task_id(job_id)`. Never mint
  one from `ic.time()`: IC time is identical for every message in a round, so
  two jobs provisioned together wrote **two task rows under one name**. The
  name alias resolves to whichever wrote last, so one realm's card served the
  other realm's failed steps, that realm's own row stayed `queued` and
  unreachable, and its job sat in `extensions` forever.
- A second pass resumes the recorded task (completed steps keep their status;
  only failed and provably abandoned `running` steps run again) and skips the
  Casals provisioning calls entirely when the canisters and the task exist.
- **Ownership decides, never the recorded id alone.** A task is applied to the
  job whose `backend_canister_id` equals `task.target_canister_id`
  (`task_owner_job`); `get_deploy_task_status` reports a foreign task as
  `foreign` with no steps rather than showing it; a rebuild carries over the
  completed steps of the realm's own prior task row (`best_owned_task`).
- The **provision heartbeat never re-drives a failed job** (`pending` /
  `provisioning` only). Recovery is an explicit `retry_deployment`. What the
  heartbeat *does* do is reconcile: a job stranded in `extensions` (task gone,
  foreign, or finished without settling it) is failed with the reason, which
  releases the credit hold and stops the card animating.
- A failed bootstrap step (`enter_setup`, `configure_canister_ids`,
  `grant_frontend_access`) fails the job. It is not a partial success: the
  realm never entered setup or cannot write its own frontend.
- `realm_stage` is **not** proof that `enter_setup` ran — a freshly installed
  realm reports `setup` with `realm_name: "Default Realm"`. Use the task
  records (or the realm's own name/network fields) to tell them apart.

#### Frontend asset permissions are Casals's to grant

The realm backend needs `Commit` on its frontend asset canister (`/custom/`
branding, `/ext/` extension frontends). Casals grants it to the paired stand
backend when it provisions the frontend bundle. The installer holds no
`ManagePermissions` there and **must not** be made a lasting controller of a
realm asset canister — it verifies the grant with `list_permitted` and reports
a precise failure when it is missing. Remaining platform-side work:
[docs/CASALS_FOLLOWUP_ASSET_PERMISSIONS.md](docs/CASALS_FOLLOWUP_ASSET_PERMISSIONS.md).

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

Full queue E2E: `.github/workflows/gaas-e2e.yml` (`casals up -e local`, then a wizard deploy against the local installer).

## Debugging Python canisters (`__browse__` / `__shell__`)

Registry backend and installer are Basilisk canisters. Use agent endpoints for live inspection:

### `__browse__` — read-only (query)

```bash
export TERM=xterm DFX_WARNING=-mainnet_plaintext_identity
dfx identity use deployer

dfx canister call <realm-registry-backend> __browse__ \
  '("{\"action\": \"schema\"}")' --query --network ic
```

### `__shell__` — Python REPL (update)

Requires your dfx identity to be a **canister controller**:

```bash
dfx canister call <realm-registry-backend> __shell__ \
  '("from realm_registry_backend.core.models import RealmRecord; print(len(list(RealmRecord.instances())))")' \
  --network ic --identity deployer
```

List realms quickly:

```bash
dfx canister call <realm-registry-backend> list_realms '()' \
  --query --network ic
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

`realm_registry_backend` and `realm_installer` declare `service : (text) -> {…}`
(their `@init` takes a config JSON string), so a plain `dfx deploy <name>` needs
an argument or it fails with **"Expected arguments but found none"**. `dfx.json`
carries `"init_arg": "(\"\")"` for both — an empty config, which both `@init`
bodies skip. A new Basilisk canister with init parameters needs the same entry;
`tests/backend/test_dfx_init_args.py` fails if one is missing.

## Relationship to Realms GOS

The **realms** repo consumes GaaS release artifacts. Its `dfx.json` may reference remote WASM URLs from this repo's GitHub Releases for registry/installer when running local mundus stacks. Live test/demo/staging canister IDs remain in **this** repo's `canister_ids.json`.
