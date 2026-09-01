# Casals follow-up — asset-canister permissions for realm frontends

Scope: [smart-social-contracts/casals](https://github.com/smart-social-contracts/casals).
**Nothing in this document is implemented in gos-as-a-service** — the installer
side is done (see below) and this is the remaining platform-side work.

## Why

A realm's backend needs `Commit` on its own frontend asset canister: it writes
`/custom/` branding and `/ext/` extension frontends after install. Granting that
needs `ManagePermissions` on the asset canister.

On the Casals provisioning path the installer holds neither control nor
`ManagePermissions` on that canister, and it should not: the asset canister is
controlled by Casals and the governance multisig. Casals already makes the grant
itself — `_grant_backend_commit` in `src/lifecycle.py` grants `Commit` to the
backend canister of the same stand from both `_provision_assets` and
`_upload_bundle`, on every create and reinstall.

The installer now verifies that grant with `list_permitted` on the asset
canister instead of blindly re-granting it, so the common case needs no Casals
change at all. What is missing is a way to *repair* the grant when the
verification says it is absent.

## Gap 1 — no way to (re)grant a single asset permission

Today the only Casals endpoint that re-grants `Commit` is
`provision_assets`, which also re-uploads the whole bundle from the file
registry: too heavy for a permission repair (a large bundle does not fit one
ingress window and has to be sliced with `offset`/`limit`).

Requested: a narrow, idempotent endpoint, e.g.

```
"grant_asset_permission" : (text) -> (text);   // {"canister": "<name>"|"canister_id",
                                               //  "to_principal": "<principal>",
                                               //  "permission": "Commit"|"Prepare"|"ManagePermissions"}
```

- Authorized like the other stand-scoped lifecycle calls (`_require_can_add`
  or commander of the stand), so the installer can call it for its own stands.
- Idempotent: granting an existing permission is a no-op success.
- Defaults good enough for the common case: `{"canister": "<stand>-frontend"}`
  with no `to_principal` should grant `Commit` to the paired stand backend
  (exactly what `_grant_backend_commit` computes).

With that, the installer's `grant_frontend_access` step can repair the missing
grant instead of failing the deployment.

## Gap 2 — the grant depends on canister creation order

`_grant_backend_commit` resolves the backend through
`_backend_cid_for_stand(frontend_cid, stand)`. If the frontend is provisioned
before a backend exists in that stand (`deploy_scope: frontend_only`, a
frontend re-provision before the backend is registered, or any future
reordering), the lookup returns `""` and no grant is made — silently, since the
function's return value is discarded.

Requested: emit an event when the paired backend cannot be resolved
(`assets_backend_unresolved` or similar) so the condition is visible in
`get_events`, and re-assert the grant when a backend is later added to the
stand. Alternatively make Gap 1's endpoint the single place that owns this, and
call it from `_provision_assets` / `_upload_bundle`.

## Explicitly not requested

- **Do not** add the installer (or Casals) as a lasting IC controller of the
  realm's asset canister. The topology is deliberate: controllers are Casals
  and the governance multisig.
- **Do not** grant the installer `ManagePermissions` as a lasting permission
  either. If Gap 1 lands, the installer never needs a permission of its own on
  a realm's asset canister. Granting `ManagePermissions` at create time would
  also work, but it widens the installer's authority for no gain over an
  audited Casals endpoint.

## What the installer already does (this repo, no Casals dependency)

- Verifies `Commit` on the frontend with `list_permitted` before attempting a
  grant, so the grant Casals made is recognised rather than re-attempted.
- Only attempts `grant_permission` when the permission is genuinely absent
  (that path still works on the legacy off-chain deployer path, where the
  installer is a controller).
- On an authorization refusal, re-checks and then fails the step with the real
  reason, naming both canisters and stating that retrying cannot change the
  outcome — see `src/realm_installer/asset_permissions.py`.
- Never re-runs a completed `enter_setup` / `configure_canister_ids`, and never
  auto-retries a failed job, so a missing grant surfaces as a blocked
  deployment instead of an endless "Retrying automatically".

Live case this came from: job `job_20260828152332_870e` (RealmsTest8,
test.gos.earth), backend `pxip5-cyaaa-aaaae-ag3dq-cai`, frontend
`o2glt-nqaaa-aaaae-ag3ea-cai`, installer `fltjm-tyaaa-aaaap-qunhq-cai`.
