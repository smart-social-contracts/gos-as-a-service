# GaaS CLI — descriptor-driven environment deployment

The **gaas** CLI deploys a complete GOS-as-a-Service (GaaS) environment from a single JSON **descriptor**: platform canisters, file registry seeding, frontend builds, DNS wiring, and smoke checks. It is the user-facing entry point for [one-command, descriptor-driven GaaS environment deployment](https://github.com/smart-social-contracts/gos-as-a-service/issues/1).

Dogfood descriptors for our live fleets live in [`environments/`](../environments/) (`test.json`, `staging.json`, `demo.json`).

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
    "casals_conductor": "qthgp-3yaaa-aaaae-agveq-cai",
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
| `implementation` | **yes** | — | GOS id. Known: `realms-gos` (available), `chora-gos` (not yet available). |
| `version` | **yes** | — | Release tag matching `vX.Y.Z` (e.g. `v0.4.0`). |
| `release_repo` | **yes** | — | GitHub repo slug (`owner/repo`) for release artifacts. |
| `artifacts.backend_wasm_key` | **yes** | — | File-registry namespace key for backend WASM. Default for `realms-gos`: `realm-backend`. |
| `artifacts.frontend_wasm_key` | **yes** | — | File-registry namespace key for frontend assets. Default for `realms-gos`: `realm-assets`. |
| `loader_profile` | **yes** | — | Portal embed profile. Default for `realms-gos`: `realms-iframe-v1`. |

### `canisters` keys

Only these names are accepted:

| Key | Role |
|---|---|
| `realm_registry_backend` | Credits, slug claims, deployment requests |
| `realm_registry_frontend` | Create-realm wizard + federation portal |
| `realm_installer` | Deployment queue + Casals provisioning |
| `file_registry` | Platform artifact store |
| `file_registry_frontend` | File registry admin UI |
| `casals_conductor` | External Casals orchestrator canister ID |
| `casals_frontend` | Casals orchestration UI (standalone assets canister) |

Leave a key out (or omit the entire `canisters` object) to create that canister during deploy. The file registry backend ID is generated at build time when created fresh.

### `casals`

| Field | Required | Default | Description |
|---|---|---|---|
| `version` | **yes** | — | Casals release tag (`vX.Y.Z`). Default pin: `v0.3.0`. |
| `release_repo` | no | `smart-social-contracts/Casals` | GitHub repo for Casals release artifacts. |

### `services`

| Field | Required | Default | Description |
|---|---|---|---|
| `billing_url` | no | `null` | HTTPS URL for the credits / Stripe billing service. When present, credits are enforced unless `open_mode` is explicitly `true`. |
| `deploy_url` | no | `null` | HTTPS URL for the off-chain deploy worker API. |
| `open_mode` | no | derived | When `true`, the registry skips credit holds for realm deploy/upgrade. When `false`, credits are enforced. When omitted, defaults to `true` if `billing_url` is absent, otherwise `false`. Set explicitly on environments that use a billing URL but should not gate deployments (e.g. test/staging). |

Both URLs must use `https://`. Empty strings are treated as absent.

Our live environments use `https://billing.realmsgos.dev` and `https://deploy.realmsgos.dev` (confirmed in `src/realm_registry_frontend/src/lib/config-resolvers.js` defaults).

### `dns`

| Field | Required | Default | Description |
|---|---|---|---|
| `provider` | no | `"manual"` | DNS provider. Only `"manual"` is implemented; gaas prints records for you to add at your registrar. |

### Known GOS implementations (`known.py`)

| ID | Label | Default version | Release repo | Loader profile |
|---|---|---|---|---|
| `realms-gos` | Realms GOS | `v0.3.1` | `smart-social-contracts/realms` | `realms-iframe-v1` |
| `chora-gos` | Chora GOS | `v0.1.0` | `smart-social-contracts/chora` | `chora-iframe-v1` (unavailable) |

### Cycles estimate (`known.py`)

Default required cycles: **9 trillion** (`7 canisters × 1T + 2T install buffer`).

## Prerequisites

| Requirement | Notes |
|---|---|
| **dfx** | DFINITY SDK installed and on `PATH`. gaas sets `TERM=xterm` and `DFX_WARNING=-mainnet_plaintext_identity`. |
| **dfx identity** | Named identity with controller access to target canisters. Create with `dfx identity new <name>`. |
| **Cycles (IC mainnet)** | ~9T cycles recommended. Check balance: `dfx cycles balance --network ic`. Top up via the [cycles ledger](https://internetcomputer.org/docs/current/developer-docs/setup/cycles/cycles-wallet) or IC faucet for test principals. |
| **Local replica** | For `--network local`: `dfx start --background` before deploy. Preflight runs `dfx ping local`. |
| **Node.js / npm** | Required for registry and file-registry frontend builds during the install-frontends phase. |
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

## Open mode vs billing

| `services.open_mode` | `services.billing_url` | Behaviour |
|---|---|---|
| `true` | any | **Open mode** — deployments proceed without credit checks. |
| `false` | present | Credits enforced (5 credits per realm deploy, holds/capture via billing service). |
| omitted | present | Credits enforced (same as `open_mode: false`). |
| omitted | absent | **Open mode** — no billing URL and no explicit flag. |

`deploy_url` is independent: it points the registry frontend at an off-chain worker for legacy deploy paths. Omit both billing URLs for fully self-contained environments.

## Third-party self-hosting

gaas descriptors are designed for **any domain** — nothing hardcodes `gos.earth` or `realmsgos.*` in the deploy pipeline. Set `domain`, `services`, and canister IDs to your own infrastructure.

**CSP `frame-ancestors` caveat:** Realms realm frontends ship with a restrictive Content-Security-Policy. The realm installer patches certified assets at provision time to add your portal origin (derived from the descriptor domain) to `frame-ancestors`, so realms embed correctly in your federation portal without manual CSP edits.

## Troubleshooting

| Symptom | Cause | gaas mitigation |
|---|---|---|
| `dfx deploy` hits wrong canister / no-op | Stale `remote.id` in `dfx.json` silently redirects installs | gaas always passes **explicit canister IDs** from the descriptor to `dfx canister install`, bypassing remote.id |
| Frontend deploy fails after WASM module change | Certified-assets canisters need full reinstall, not upgrade | gaas uses `--mode reinstall` for frontend canisters |
| Realm deploy pulls wrong GOS version | Pin drift across repos | Single `gos[].version` pin in the descriptor; file registry seeded from that release |
| Empty `file_registry` canister ID | ID is assigned at first `dfx canister create` | Omit `file_registry` from `canisters` on fresh deploy; gaas writes the generated ID back to state |
| DNS verify loop times out | Registrar propagation delay or wrong host labels | Run `gaas dns-records <file>` and compare; re-run deploy after fixing records |
| Preflight: insufficient cycles | Wallet below 9T estimate | `dfx cycles balance --network ic`; top up via cycles ledger |
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

**Deploy phases** (when pipeline runs):

1. Validating descriptor, identity, cycles
2. Creating canisters
3. Installing backends
4. Configuring backends
5. Seeding file registry
6. Building + installing frontends
7. Domain wiring (DNS verify + IC registration)
8. Smoke checks

If a phase is not yet implemented, the pipeline pauses and prints a resume command.

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
