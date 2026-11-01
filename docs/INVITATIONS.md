# Alpha invitations

Alpha access is by invitation. An invitation code unlocks the portal for one
person and adds 50 free credits to their account (a realm costs 5). There is no
billing in Alpha: the buy button is disabled and reads "Buy credits", with
"Not available" under it.

## The flow

1. The applicant fills in the Tally form linked from gos.earth. Tally emails the
   operator.
2. The operator reviews the request and runs `scripts/invite.py <email>`.
3. The script stores the code's sha256 hash in the registry and emails the code
   from `contact@realmsgos.org`.
4. The applicant signs in at gos.earth/deploy-gos (or the Billing tab of My
   Dashboard) and enters the code. The registry activates their account and adds
   the credits in one step. Until then both pages show a "Request an invitation"
   button that opens the Tally form, and the Billing tab asks for the code where
   the voucher box will appear once they are activated.

A code works once, expires after `--days` (default 30) and never leaves the
operator's machine except in that email: the registry holds the hash only.

A principal that was activated before invitations existed cannot get credits
from a code; give existing testers a voucher instead.

## One-time setup per environment

- **The registry wasm with invitations must be live first.** The script calls
  the registry's `create_invitation_codes` with `{hash, credits, expires_at}`
  entries and reads its JSON reply; an older registry build expects a plain
  list of hashes and answers differently. Upgrade the registry before the first
  invitation.
- **Card billing off.** A fresh build applies `test_flags.disable_card_billing`
  from the sheet (`casals.json` and the other sheets) in its `configure` step.
  `casals up` does not reach an environment that is already built, so there
  the flag goes in through a proposal like the one below, and the registry
  must then report it:

  ```sh
  icp canister call "$GAAS_MULTISIG" propose \
    "(variant { CallCanister = record { canister = principal \"$REGISTRY_BACKEND\"; method = \"set_canister_config_json\"; arg_json = \"{\\\"test_flags\\\":{\\\"disable_card_billing\\\":true}}\" } }, null)" \
    -n ic --identity <operator identity>
  icp canister call "$REGISTRY_BACKEND" get_runtime_flags '()' -n ic --query
  ```

  `get_runtime_flags` must show `test_mode_disable_card_billing` as `true`.
- **Invitation mode on.** Without it there is no gate (anyone can create a
  realm) and `redeem_invitation_code` does nothing, so no credits are granted. The
  registry's controller is the GaaS multisig; turn the mode on with a proposal
  signed by the operator identity:

  ```sh
  icp canister call "$GAAS_MULTISIG" propose \
    "(variant { CallCanister = record { canister = principal \"$REGISTRY_BACKEND\"; method = \"set_invitation_mode\"; arg_json = \"true\" } }, null)" \
    -n ic --identity <operator identity>
  icp canister call "$REGISTRY_BACKEND" get_invitation_mode '()' -n ic --query
  ```

  The query must answer `enabled`.

## Inviting someone on staging / production

The script makes the code through the GaaS multisig (the registry's controller;
threshold 1 with the operator as its only signer, so the proposal executes at
once), checks the registry's own reply, then emails the code. It needs:

- `REGISTRY_BACKEND` and `GAAS_MULTISIG`: the environment's canister ids. They
  are not written in this repo outside `casals.json`; read them with
  `casals export` (below).
- `--identity`: the operator identity that ran `casals up` for that
  environment. Staging uses the session identity that built it
  (`dev-session-31oct` at the time of writing); production uses the identity
  from `Casals/docs/OPERATIONS.md` "Hardware keys" (the short-lived delegation
  from `prod-identity`, one HSM touch).
- `--portal`: where the applicant signs in. **Pass it on every environment but
  production**: the default is `https://gos.earth`, and a code made on staging
  does not work there.
- SMTP settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`) from
  the secrets file. Run the script through `.cto/secrets.sh run`, which injects
  them without printing them. `--dry-run` needs none. `SMTP_USER` is the
  mailbox `contact@smartsocialcontracts.org`: `realmsgos.org` is only a domain
  alias on Infomaniak and cannot log in. `SMTP_PASSWORD` is an Infomaniak
  device password, made with the mail configuration wizard for that mailbox,
  not the account password. The email is still sent From
  `contact@realmsgos.org`.

The script logs in to the mail server first and creates the code only after
that succeeds, so a wrong SMTP login stops it with nothing stored.

Always run the dry run first: it shows the email and the proposal and creates
and sends nothing. The code it prints is a placeholder, not a stored code. The
email subject names the portal host (`Your staging.gos.earth invitation code`),
which is why `--portal` matters.

Read the two ids from the Casals checkout (`PYTHONPATH` set to it), for the
environment you invite on. In the export they are the `realm-registry-backend`
canister and the multisig:

```sh
python3 -m casals_cli.main -e staging export casals.staging.json      # staging
python3 -m casals_cli.main -e production export casals.json          # production
```

### Staging (staging.gos.earth)

```sh
export REGISTRY_BACKEND=<staging realm-registry-backend id> GAAS_MULTISIG=<staging multisig id>

python3 scripts/invite.py applicant@example.org --dry-run \
  --portal https://staging.gos.earth

.cto/secrets.sh run python3 scripts/invite.py applicant@example.org \
  --identity dev-session-31oct --portal https://staging.gos.earth
```

### Production (gos.earth)

Check first that invitation mode is on (`get_invitation_mode` answers
`enabled`), then:

```sh
export REGISTRY_BACKEND=<production realm-registry-backend id> GAAS_MULTISIG=<production multisig id>

python3 scripts/invite.py applicant@example.org --dry-run

.cto/secrets.sh run python3 scripts/invite.py applicant@example.org \
  --identity <production operator identity>
```

No `--portal` here: the default is the production portal.

### Options and failures

`--days N` (validity, default 30), `--credits N` (default 50), `--network`
(default `ic`), `--portal` (default `https://gos.earth`).

If the email fails after the code was stored, the script prints the code on
stderr so it can be sent by hand; do not run it again for the same person.

## Revoking

Through a multisig proposal like the one above: `revoke_invitation_code(<hash>)`
disables an unused code, `deactivate_principal(<principal>)` closes an
account's access.
