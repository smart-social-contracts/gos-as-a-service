# Operating GaaS

The whole platform — conductor, governance multisig, file registry, realm
registry backend + portal, realm installer, marketplace, and the template every
realm stand is built from — is declared in [`casals.json`](../casals.json).
The Casals runbook (`Casals/docs/OPERATIONS.md`) explains the commands; this
page is what is specific to GaaS.

## One command

[`scripts/up.sh`](../scripts/up.sh) takes a clean checkout to a converged,
populated, DNS-mapped GaaS orchestra and is safe to re-run:

```sh
# production, from gos-as-a-service/ with Casals, realms and file-registry as sibling checkouts
export DFX_HSM_PIN=…                 # the hardware key behind --identity
export CLOUDFLARE_API_TOKEN=…        # Zone:Read + DNS:Edit on gos.earth; never commit it
export CASALS_HOME=…                 # where the first `up` wrote gaas.production.json (default ~/.casals)
scripts/up.sh -e production --identity prod-identity --upload-identity <plaintext identity> --yes

scripts/up.sh -e local --yes --smoke-realm first-realm   # a laptop: same phases on a local replica,
                                                          # then a realm born through the portal path
scripts/up.sh -e production --identity prod-identity --publish-only   # only the packages changed
# roll a new realm build onto the realms that already exist (a release, not an up)
casals -e production --identity prod-identity upgrade casals.json --wasm realm-backend --section Deployments
casals -e production --identity prod-identity upgrade casals.json --content frontend/realm-assets/main
```

Phases, each printed with a header and each idempotent:

| phase | what it runs | skip with |
|---|---|---|
| preflight | tools, python deps, identity, `DFX_HSM_PIN` / `CLOUDFLARE_API_TOKEN` / bindings present (production) | — |
| build | every `local:` source of the sheet: platform registry wasm, installer + registry backends, portal, realm halves in `../realms`, token wasm | `--skip-build`; `--build-only` stops here |
| pin | `casals pin casals.json`; production stops to have you commit changed pins unless `--yes` | — |
| up | `casals up` (locally through the Casals e2e harness: replica, funding, fresh + idempotent + runtime_stand grading); builds what the sheet declares, a no-op once built | — |
| export | `casals export` → the live ids (never a table in the repo) | — |
| domains | `realms domains apply` (`gos.earth` → `realm-registry-frontend`) when `dns.provider` is not `none` | `--no-domains` |
| publish | `realms files publish` → the GaaS `file-registry` the installer fetches from | `--skip-publish`; `--publish-only` runs just this |
| verify | `casals plan` empty, registry lists the published namespaces, `--smoke-realm` mints a realm, URLs printed | — |

`--extensions a,b` / `--codices x` narrow what is published (CI publishes
`dominion` + `hello_world` and mints `ci-realm` with both). `realms/scripts/local_up.sh --gaas`
wraps this script for a laptop. The rest of this page is what those phases
do, one at a time, for when you need to run or debug a single step.

## Build, then `up`

The sheet references product wasms and frontend dists as `local:` paths, so
build them first (`scripts/up.sh -e <env> --build-only`; CI runs the same
phase): installer and registry backends with basilisk, the portal with
`npm run build`, the realm backend and frontend in `../realms`, the platform
file registry wasm in `../file-registry`, the token wasm from the ic-tokens
release. Then, from the Casals repo:

```sh
python -m casals_cli.main -e local --identity local-dev up ../gos-as-a-service/casals.json --yes
```

The same command with `-e production` and the environment's deployer identity
is the production procedure; the differences between environments (principals,
budgets, flags such as `test_flags.ii_bypass`) are the `environments` block of
the sheet, nothing else. Production additionally requires `sha256` pins on
every `registry.wasms` and `registry.publish` row (`casals pin casals.json`
after building; bundles hash as in `Casals/docs/BUNDLES.md`), reads the
conductor id from `$CASALS_HOME/<orchestra>.production.json` (set
`CASALS_HOME` to where the first `up` wrote it — a missing binding is a stop,
not a silent second conductor), and with a touch-policy hardware key wants
`--upload-identity <plaintext identity>` for the store uploads of step 4.

### Existing realms are not touched by `up`

Realm stands are minted by the installer from the `Deployments` section's
`stand_template`, and each mint builds itself (Casals #52: `create_stand`
arms a one-shot build for that stand). `casals up` builds what the sheet
declares and is a no-op afterwards — a bumped realm wasm or realm frontend
bundle in the template reaches new mints only. Rolling it onto realms that
already exist is a release: `casals upgrade casals.json --wasm realm-backend
--section Deployments` (or `--stand realm-<x>` for one), `casals upgrade casals.json
--content frontend/realm-assets/main` for the frontend bundle. Baton-governed
members come back as `pending` until the baton's other commanders approve.
The e2e corpus' `dynamic-stands` orchestra runs exactly this shape.

## What happens when a realm is deployed

1. The portal wizard calls `realm-registry-backend.request_deployment(manifest)`.
2. The installer calls the conductor's `create_stand({section: "Deployments",
   name, members})` — its entire contract with Casals — and polls `get_tree`.
3. The conductor builds the stand from the `Deployments` template on a
   one-shot timer armed by `create_stand` (a failed round shows as the stand's
   `build_error` in `get_tree`): baton, realm backend, realm frontend, optional
   token; controllers, baton hand-off, `/canister_ids.js` and
   `.ic-assets.json5` all come from the template.
4. Once the members are `installed` the installer bootstraps the realm
   (`enter_setup`, `configure_canister_ids`, `grant_frontend_access`) and
   registers it.
5. A realm grows itself: its backend, a stand commander with `stand.create`,
   calls `create_stand({name, members: ["<stand>-quarter-<n>"]})`.

`casals show` / the conductor frontend list every realm stand like any other.

## Custom domain, after `up`

`casals up` does not touch DNS. `gos.earth` → `realm-registry-frontend` (the
sheet's `domains` block) is applied with the Realms product CLI, which reads
the canister id from the GaaS conductor:

```sh
# from realms/, CASALS_HOME pointing at the bindings `casals up` wrote
realms domains check ../gos-as-a-service/casals.json -e production
export CLOUDFLARE_API_TOKEN=…     # Zone:Read + DNS:Edit on gos.earth; never commit it
realms domains apply ../gos-as-a-service/casals.json -e production
```

Run `apply` before destroying a previous portal frontend; see
`realms/docs/OPERATIONS.md` for what it does.

## Content, after `up`

The installer fetches a new realm's codex and extensions from this orchestra's
`file-registry` (`installer.config.file_registry_id`), and the portal stores
user branding there. `casals up` leaves it empty; the sheet grants what its
writers need (config rows on `file-registry`):

- `grant_publish {namespace: "*"}` → the operator: `realms files publish` may
  write every `ext/…` / `codex/…` namespace.
- `set_config {auto_grant_publishers: true}`: a portal user's branding upload
  (signed by the user) creates its namespace and makes them its publisher.
- `grant_publish {namespace: "_approvers"}` → the Realms marketplace, whose
  `review_listing` stamps approvals on the registry a listing names.

Then publish the packages, from the `realms` checkout, as the operator:

```sh
casals -e production export ../gos-as-a-service/casals.json     # bindings: file-registry
export DFX_HSM_PIN=…                                              # hardware key; passed to every icp call
realms files publish -n ic --registry <file-registry> --identity prod-identity
```

A realm minted afterwards with a codex (`realm.codex.package`) or extensions
gets them from here. This is the publish phase of `scripts/up.sh`
(`--publish-only` runs just it). CI (`gaas-e2e.yml`) runs the script with
`--codices dominion --extensions hello_world --smoke-realm ci-realm`; the run
fails if the realm does not list them.

## Checks

```sh
scripts/up.sh -e local --skip-build --yes        # up + publish + verify again: must report no changes
# from Casals/: converge + idempotency + a runtime stand, oracle-graded
KEEP=1 SCENARIOS=fresh,idempotent,runtime_stand python tests/e2e/run_e2e.py ../gos-as-a-service/casals.json
# from here: a realm born the way the portal does it
CASALS_HOME=~/.casals python tests/e2e/deploy_realm.py my-realm
```

`deploy_realm.py` prints the realm's frontend and portal URLs; re-running it
with the same name completes in a second (idempotent).
