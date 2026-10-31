# Alpha invitations

Alpha access is by invitation. An invitation code unlocks the portal for one
person and adds 50 free credits to their account (a realm costs 5). There is no
billing in Alpha: card checkout reads "Coming soon".

## The flow

1. The applicant fills in the Tally form linked from gos.earth. Tally emails the
   operator.
2. The operator reviews the request and runs `scripts/invite.py <email>`.
3. The script stores the code's sha256 hash in the registry and emails the code
   from `contact@realmsgos.org`.
4. The applicant signs in at gos.earth/deploy-gos and enters the code. The
   registry activates their account and adds the credits in one step.

A code works once, expires after `--days` (default 30) and never leaves the
operator's machine except in that email: the registry holds the hash only.

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

## Sending an invitation

Canister ids come from `casals export`; the operator identity is the one that
ran `casals up` (the multisig's only signer, threshold 1, so a proposal executes
at once). SMTP settings come from the secrets file and are never printed.

```sh
export REGISTRY_BACKEND=<realm-registry-backend id> GAAS_MULTISIG=<multisig id>

# Show the email and the proposal, create and send nothing:
python3 scripts/invite.py applicant@example.org --dry-run

.cto/secrets.sh run python3 scripts/invite.py applicant@example.org \
  --identity <operator identity>
```

Options: `--days N` (validity, default 30), `--credits N` (default 50),
`--network` (default `ic`), `--portal` (default `https://gos.earth`).

If the email fails after the code was stored, the script prints the code on
stderr so it can be sent by hand; do not run it again for the same person.

## Revoking

Through a multisig proposal like the one above: `revoke_invitation_code(<hash>)`
disables an unused code, `deactivate_principal(<principal>)` closes an
account's access.
