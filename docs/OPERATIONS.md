# Operating GaaS

The whole platform — conductor, governance multisig, file registry, realm
registry backend + portal, realm installer, marketplace, and the template every
realm stand is built from — is declared in [`casals.json`](../casals.json).
The Casals runbook (`Casals/docs/OPERATIONS.md`) explains the commands; this
page is what is specific to GaaS.

## Build, then `up`

The sheet references product wasms and frontend dists as `local:` paths, so
build them first (the exact recipes are the build steps of
[`.github/workflows/gaas-e2e.yml`](../.github/workflows/gaas-e2e.yml)):
installer and registry backends with basilisk, the portal with `npm run build`,
the realm backend and frontend in `../realms`, the token wasm from the
ic-tokens release. Then, from the Casals repo:

```sh
python -m casals_cli.main -e local --identity local-dev up ../gos-as-a-service/casals.json --yes
```

The same command with `-e ic` and the environment's deployer identity is the
production procedure; the differences between environments (principals,
budgets, flags such as `test_flags.ii_bypass`) are the `environments` block of
the sheet, nothing else.

## What happens when a realm is deployed

1. The portal wizard calls `realm-registry-backend.request_deployment(manifest)`.
2. The installer calls the conductor's `create_stand({section: "Deployments",
   name, members})` — its entire contract with Casals — and polls `get_tree`.
3. The conductor builds the stand from the `Deployments` template on its
   reconcile timer (`conductor.settings.reconcile_interval_secs`): baton,
   realm backend, realm frontend, optional token; controllers, baton hand-off,
   `/canister_ids.js` and `.ic-assets.json5` all come from the template.
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
gets them from here. CI (`gaas-e2e.yml`) publishes `dominion` + `hello_world`
and mints `ci-realm` with both; the run fails if the realm does not list them.

## Checks

```sh
# from Casals/: converge + idempotency + a runtime stand, oracle-graded
KEEP=1 SCENARIOS=fresh,idempotent,runtime_stand python tests/e2e/run_e2e.py ../gos-as-a-service/casals.json
# from here: a realm born the way the portal does it
CASALS_HOME=~/.casals python tests/e2e/deploy_realm.py my-realm
```

`deploy_realm.py` prints the realm's frontend and portal URLs; re-running it
with the same name completes in a second (idempotent).
