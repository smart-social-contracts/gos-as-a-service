# Casals follow-up — realm frontend `Commit` (Grok)

Scope: [smart-social-contracts/casals](https://github.com/smart-social-contracts/casals).
Nothing here is implemented in gos-as-a-service. The installer already does its
part; this is the remaining work on the provisioner.

This is an independent spec of the same gap as
[`CASALS_FOLLOWUP_ASSET_PERMISSIONS_Opus.md`](CASALS_FOLLOWUP_ASSET_PERMISSIONS_Opus.md).
Where the two differ, this document is the Grok reading.

## Why

A Realms GOS realm is two canisters. The backend must hold certified-assets
`Commit` on the frontend so it can write `/custom/` branding and `/ext/`
extension bundles after install. Granting `Commit` requires
`ManagePermissions` (or IC control) on that asset canister.

On the Casals path those controllers are **Casals + the governance multisig**.
The installer is neither, by design. Casals is supposed to grant `Commit` to
the paired stand backend whenever it provisions or re-uploads the frontend
(`_grant_backend_commit` in Casals `src/lifecycle.py`).

When that grant is missing, the realm is unusable: branding 404s, every
extension 404s. The installer can *see* the hole (`list_permitted`) but cannot
fill it. Retrying the GaaS job cannot change that.

Live case: job `job_20260828152332_870e` (RealmsTest8, test.gos.earth),
backend `pxip5-cyaaa-aaaae-ag3dq-cai`, frontend
`o2glt-nqaaa-aaaae-ag3ea-cai`, installer `fltjm-tyaaa-aaaap-qunhq-cai`.
Rejection: caller is not a controller and has no `ManagePermissions`.

## Installer behaviour (this repo, done)

`grant_frontend_access` (`src/realm_installer/asset_permissions.py`,
`src/realm_installer/main.py`):

1. `list_permitted` for `Commit` on the frontend. Anyone can query this; the
   installer does not need `ManagePermissions` to read it.
2. If the backend principal is already on that list → step completes
   (`already granted by the platform provisioner`).
3. If not, try `grant_permission`. That only works on the legacy off-chain
   deployer path, where the installer *is* a controller.
4. On an authorization refusal, re-check `list_permitted`. If still missing,
   **fail the job** with a message that names both canisters and says retry
   cannot help. The provision heartbeat never re-drives a failed job.

A failed `grant_frontend_access` is a bootstrap failure, not a partial
success (`BOOTSTRAP_STEP_KINDS` in `deploy_resume.py`).

## What Casals must still do

### 1. A repair endpoint the installer can call

Today the only Casals path that re-grants `Commit` is `provision_assets`,
which also re-uploads the whole frontend bundle. That is the wrong tool: a
permission repair is one inter-canister call, not a multi-ingress asset sync.

Requested: one idempotent update, stand-scoped, authorized the same way as
other lifecycle calls on that stand (installer as commander of Deployments is
enough).

Prefer the **narrow** form:

```
"grant_stand_backend_commit" : (text) -> (text);
// {"canister": "<frontend name or id>"}
// grants Commit on that asset canister to the paired stand backend.
// If the permission already exists, return ok. Do not take a principal
// argument and do not accept ManagePermissions as a permission to grant.
```

A general `grant_asset_permission` that can hand `ManagePermissions` to an
arbitrary principal is a wider authz surface than this bug needs. If Casals
already wants a generic grant helper internally, keep it private; the
installer-facing method should only ever do “paired backend gets `Commit`”.

With that, a missing grant becomes: installer calls Casals → Casals grants →
installer re-checks `list_permitted` → step completes. No topology change.

### 2. Do not drop the grant when the backend is not registered yet

`_grant_backend_commit` looks up the stand backend from the frontend. If the
frontend is provisioned first (`deploy_scope: frontend_only`, reinstall of
assets before the backend row exists, any reordering), the lookup is empty
and the grant is skipped. The return value is discarded, so nothing in
`get_events` records it.

Requested:

- Emit a visible event when the paired backend cannot be resolved.
- Re-run the grant when a backend is later attached to that stand (create or
  register), not only at frontend provision time.

Gap 1’s endpoint is the implementation: `_provision_assets` /
`_upload_bundle` / “backend added” should all call the same function.

## Explicitly out of scope

- Do **not** add the installer as a lasting IC controller of a realm frontend.
- Do **not** grant the installer lasting `ManagePermissions` on a realm
  frontend. Create-time `ManagePermissions` for the installer would also
  unblock `grant_permission`, but it widens installer authority forever for a
  one-shot grant Casals already knows how to make.
- Do **not** have the installer call `provision_assets` as a permission
  repair. That re-uploads `/` and can wipe `/ext/` and `/custom/` unless those
  are restored in the same job.

## Which Casals

Only **GaaS Casals** (`gaas_casals_backend`) provisions realm stands and their
batons. Realms-org Casals (`realmsgos_casals_backend`) orchestrates
marketplace + the extension catalog and never touches a realm frontend.
This follow-up applies to the GaaS conductor only.

See [`PLATFORM_LAYER_SPLIT.md`](PLATFORM_LAYER_SPLIT.md) for the two-stack
split; it does not change this grant.

## Related: broken `AssetPermission` candid on Casals

Every `dfx canister call` against a Casals backend currently prints:

```
type AssetPermission = variant { Commit : ; Prepare : ; ManagePermissions :  };
error: parser error
WARNING: Cannot fetch Candid interface for <method>, sending arguments with inferred types.
```

Unit variants must be `Commit;` not `Commit : ;`. The malformed type is in
the interface dfx fetches from Casals (or from a DID Casals vendors). The
call still goes through with inferred types, so this is log noise, not the
`Commit`-grant hole — but it is the same type and it hides real errors in
`gaas new` logs. Fix the DID in Casals so dfx can fetch the interface.

## Acceptance

A GaaS-queued `realms new --deploy-mode=gaas` finishes `grant_frontend_access`
as `completed` / `already granted by the platform provisioner` without the
installer holding control or `ManagePermissions` on the frontend.

If the grant was skipped because the backend was registered later, calling
the repair endpoint (or re-provisioning the backend) makes `list_permitted`
show the backend principal under `Commit`, and a retry of only that installer
step succeeds.
