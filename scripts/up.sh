#!/usr/bin/env bash
# up.sh — the GaaS orchestra (casals.json), end-to-end, in one command:
#
#   preflight → build → pin → casals up → export → domains → publish → verify
#
#   This builds the sheet (day one); re-runs are no-ops. Rolling a new realm wasm or
#   bundle onto existing realms is a release, not an up:
#     casals -e production upgrade casals.json --wasm realm-backend --section Deployments
#     casals -e production upgrade casals.json --content frontend/realm-assets/main
#
#   scripts/up.sh -e local --yes                       # laptop / CI: everything, test variant
#   scripts/up.sh -e production --identity prod-identity --upload-identity <plain> --yes
#   scripts/up.sh -e production --publish-only          # only the content phases (packages changed)
#   scripts/up.sh -e local --build-only                 # just the artifacts the sheet references
#
# Options
#   -e, --env ENV               local | production (environments.<env> of the sheet)  [required]
#   --identity NAME             deploy identity; default local-dev for local, required otherwise
#   --upload-identity NAME      plaintext identity for the store uploads (forwarded to casals up);
#                               with a touch-policy YubiKey this avoids a touch per upload
#   --skip-build                reuse the artifacts already on disk
#   --build-only                stop after the build phase
#   --skip-publish              stop after up + domains (provision only)
#   --publish-only              skip build/pin/up/domains: export bindings and publish + verify
#   --no-domains                skip `realms domains apply`
#   --branding                  also `realms files publish-branding`
#   --extensions LIST           forward to `realms files publish` (comma-separated ids)
#   --codices LIST              forward to `realms files publish`
#   --extensions-only | --codices-only
#   --smoke-realm NAME          after publish, mint NAME through the portal path (tests/e2e/deploy_realm.py)
#   --bootstrap                 forward to casals up (production: allow a brand-new conductor)
#   -y, --yes                   non-interactive (casals up --yes, domains --yes, no pin prompt)
#   -h, --help
#
# Environment
#   CASALS_HOME          bindings root. local: <CASALS_HOME>/<orchestra>/ (the e2e harness layout,
#                        default ~/casals-home); other envs: <CASALS_HOME> itself (default ~/.casals),
#                        which is where a previous `casals up` wrote <orchestra>.<env>.json.
#   CASALS_DIR, REALMS_DIR, FILE_REGISTRY_DIR   sibling checkouts (default ../Casals, ../realms,
#                        ../file-registry); the sheet installs the realm wasm and frontend from ../realms
#   IC_TOKENS_VERSION    ic-tokens release for the token wasm (default 0.1.0)
#   SCENARIOS            local only: harness scenarios (default fresh,idempotent,runtime_stand)
#   DFX_HSM_PIN          production: PIN of the hardware key behind --identity
#   CLOUDFLARE_API_TOKEN production: Zone:Read + DNS:Edit on the zone, for the domains phase
#   REALM_CODEX, REALM_EXTENSIONS   what --smoke-realm asks for (default dominion / hello_world)
#
# Every phase is idempotent: a second run rebuilds (or --skip-build), finds the pins clean,
# `casals plan` empty, domains in place, 0 changed files, and exits 0.
set -euo pipefail

GAAS_DIR="${GAAS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="$(dirname "$GAAS_DIR")"
CASALS_DIR="${CASALS_DIR:-$ROOT/Casals}"
REALMS_DIR="${REALMS_DIR:-$ROOT/realms}"
FILE_REGISTRY_DIR="${FILE_REGISTRY_DIR:-$ROOT/file-registry}"
SHEET="$GAAS_DIR/casals.json"
IC_TOKENS_VERSION="${IC_TOKENS_VERSION:-0.1.0}"
SCENARIOS="${SCENARIOS:-fresh,idempotent,runtime_stand}"

export TERM="${TERM:-xterm}"
export DFX_WARNING=-mainnet_plaintext_identity
export PYTHONUNBUFFERED=1

ENV="" IDENTITY="" UPLOAD_IDENTITY="" SMOKE_REALM=""
SKIP_BUILD=0 BUILD_ONLY=0 SKIP_PUBLISH=0 PUBLISH_ONLY=0 NO_DOMAINS=0 BRANDING=0 YES=0 BOOTSTRAP=0
EXTENSIONS="" CODICES="" PUBLISH_FILTER=()
usage() { sed -n '2,45p' "$0"; }
while [ $# -gt 0 ]; do
  case "$1" in
    -e|--env) ENV="$2"; shift 2 ;;
    --env=*) ENV="${1#*=}"; shift ;;
    --identity) IDENTITY="$2"; shift 2 ;;
    --identity=*) IDENTITY="${1#*=}"; shift ;;
    --upload-identity) UPLOAD_IDENTITY="$2"; shift 2 ;;
    --upload-identity=*) UPLOAD_IDENTITY="${1#*=}"; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --build-only) BUILD_ONLY=1; shift ;;
    --skip-publish) SKIP_PUBLISH=1; shift ;;
    --publish-only) PUBLISH_ONLY=1; shift ;;
    --no-domains) NO_DOMAINS=1; shift ;;
    --branding) BRANDING=1; shift ;;
    --extensions) EXTENSIONS="$2"; shift 2 ;;
    --extensions=*) EXTENSIONS="${1#*=}"; shift ;;
    --codices) CODICES="$2"; shift 2 ;;
    --codices=*) CODICES="${1#*=}"; shift ;;
    --extensions-only|--codices-only) PUBLISH_FILTER+=("$1"); shift ;;
    --smoke-realm) SMOKE_REALM="$2"; shift 2 ;;
    --smoke-realm=*) SMOKE_REALM="${1#*=}"; shift ;;
    --bootstrap) BOOTSTRAP=1; shift ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "up.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1 ($2)"; }
confirm() { # confirm <prompt>  — true with --yes, else ask
  [ "$YES" = 1 ] && return 0
  [ -t 0 ] || die "$1 — no TTY to ask; re-run with --yes"
  read -r -p "$1 [y/N] " ans; [ "$ans" = y ] || [ "$ans" = Y ]
}

[ -n "$ENV" ] || { usage >&2; die "-e/--env is required (local | production)"; }
[ -f "$SHEET" ] || die "sheet not found: $SHEET"
[ -f "$CASALS_DIR/casals_cli/main.py" ] || die "Casals checkout not found at $CASALS_DIR (set CASALS_DIR)"
[ -f "$REALMS_DIR/casals.json" ] || die "realms checkout not found at $REALMS_DIR (set REALMS_DIR)"
[ -f "$FILE_REGISTRY_DIR/Makefile" ] || die "file-registry checkout not found at $FILE_REGISTRY_DIR (set FILE_REGISTRY_DIR)"

# sheet_get <python expression over `s` (the sheet) and `env`> — prints the value or ""
sheet_get() {
  python3 - "$SHEET" "$ENV" "$1" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1])); env = s.get("environments", {}).get(sys.argv[2])
if env is None:
    sys.exit(f"environment {sys.argv[2]!r} is not in the sheet (have: {', '.join(s.get('environments', {}))})")
try:
    v = eval(sys.argv[3], {}, {"s": s, "env": env})
except (KeyError, TypeError, AttributeError):
    v = ""
print("" if v is None else (json.dumps(v) if isinstance(v, (dict, list, bool)) else v))
EOF
}
ORCHESTRA="$(sheet_get 's["name"]')"
NETWORK="$(sheet_get 'env["network"]')"
DNS_PROVIDER="$(sheet_get 'env["dns"]["provider"]')"
# The realm halves the stand template installs: the gaas `local` environment
# hands new realms test flags, which only a test-variant realm wasm accepts.
BUILD_VARIANT="$(sheet_get 'env.get("build_variant")')"
if [ -z "$BUILD_VARIANT" ]; then
  if [ "$ENV" = local ]; then BUILD_VARIANT="test"; else BUILD_VARIANT="production"; fi
fi

if [ "$ENV" = local ]; then
  IDENTITY="${IDENTITY:-local-dev}"
  export CASALS_HOME="${CASALS_HOME:-$HOME/casals-home}"
  ORCH_HOME="$CASALS_HOME/$ORCHESTRA"          # the e2e harness / local_up.sh layout
else
  [ -n "$IDENTITY" ] || die "--identity is required for -e $ENV (the environment's deployer key)"
  export CASALS_HOME="${CASALS_HOME:-$HOME/.casals}"
  ORCH_HOME="$CASALS_HOME"
fi
BINDINGS_FILE="$ORCH_HOME/$ORCHESTRA.$ENV.json"
mkdir -p "$ORCH_HOME"

casals() { (cd "$CASALS_DIR" && CASALS_HOME="$ORCH_HOME" python3 -m casals_cli.main -e "$ENV" --identity "$IDENTITY" "$@"); }

# ── preflight ─────────────────────────────────────────────────────────────────
say "Preflight: $ORCHESTRA -e $ENV (network $NETWORK, realm build variant $BUILD_VARIANT)"
need icp     "npm install -g @icp-sdk/icp-cli"
need dfx     "dfx generate (portal candid declarations): https://internetcomputer.org/docs/building-apps/getting-started/install"
need node    "node 20+"
need npm     "node 20+"
need python3 "python 3.11"
need curl    "curl"
need make    "make (file-registry build)"
python3 -c 'import basilisk' 2>/dev/null || die "python deps missing: pip install -r $CASALS_DIR/requirements-dev.txt -r $GAAS_DIR/requirements-dev.txt"
python3 -c 'import ic' 2>/dev/null       || die "python deps missing: pip install -r $CASALS_DIR/requirements-dev.txt"
note "gaas:          $GAAS_DIR"
note "Casals:        $CASALS_DIR"
note "realms:        $REALMS_DIR"
note "file-registry: $FILE_REGISTRY_DIR"
note "bindings:      $BINDINGS_FILE"
note "identity:      $IDENTITY${UPLOAD_IDENTITY:+ (uploads: $UPLOAD_IDENTITY)}"

if [ "$ENV" = local ]; then
  # Plaintext key, local replica only. local_up.sh mirrors it into dfx.
  if ! icp identity list 2>/dev/null | awk '{print $1=="*"?$2:$1}' | grep -qx "$IDENTITY"; then
    icp identity new "$IDENTITY" --storage plaintext
  fi
  # A sidecar replica (CASALS_REPLICA_PORT) leaves its coordinates under CASALS_HOME.
  if [ -f "$CASALS_HOME/.replica/env" ] && [ -z "${CASALS_REPLICA_HOME:-}" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$CASALS_HOME/.replica/env"
    set +a
  fi
else
  icp identity list 2>/dev/null | awk '{print $1=="*"?$2:$1}' | grep -qx "$IDENTITY" \
    || die "icp identity '$IDENTITY' not found (icp identity list)"
  [ -n "${DFX_HSM_PIN:-}" ] || die "DFX_HSM_PIN is not set; every signature of a hardware identity needs it"
  if [ "$PUBLISH_ONLY" = 0 ] && [ ! -f "$BINDINGS_FILE" ] && [ "$BOOTSTRAP" = 0 ]; then
    die "no bindings at $BINDINGS_FILE — point CASALS_HOME at the directory of the first \`up\`, or pass --bootstrap to create a brand-new $ENV conductor on purpose"
  fi
  if [ "$NO_DOMAINS" = 0 ] && [ "$DNS_PROVIDER" != none ] && [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
    die "CLOUDFLARE_API_TOKEN is not set (dns.provider=$DNS_PROVIDER); export it or pass --no-domains"
  fi
fi
# The `realms` product CLI (files publish, domains) comes from the sibling
# checkout (editable, so a re-run is a no-op check).
if ! command -v realms >/dev/null 2>&1 || \
   [ "$(cd /tmp && python3 -c 'import realms.cli.main as m; print(m.__file__)' 2>/dev/null)" != "$REALMS_DIR/cli/realms/cli/main.py" ]; then
  say "Preflight: pip install -e $REALMS_DIR/cli (the realms CLI)"
  python3 -m pip install -q -e "$REALMS_DIR/cli" >/dev/null
fi
need realms "pip install -e $REALMS_DIR/cli"

# ── build ─────────────────────────────────────────────────────────────────────
# The exact recipes CI runs (.github/workflows/gaas-e2e.yml). Every artifact is
# a `local:` source of the sheet; a missing one makes `casals up` refuse.
if [ "$PUBLISH_ONLY" = 0 ] && [ "$SKIP_BUILD" = 0 ]; then
  say "Build: pinned python deps (gaas + realms; a stale ic-python-db yields a wasm that traps at init)"
  (cd "$GAAS_DIR" && python3 -m pip install -q -r requirements-dev.txt)
  (cd "$REALMS_DIR" && python3 -m pip install -q -r requirements.txt)

  say "Build: platform file registry wasm in $FILE_REGISTRY_DIR"
  (cd "$FILE_REGISTRY_DIR" && make build-backend && ls -l .basilisk/ic_file_registry/ic_file_registry.wasm)

  say "Build: platform backends (realm_installer, realm_registry_backend)"
  (cd "$GAAS_DIR"
   CANISTER_CANDID_PATH="$PWD/src/realm_installer/realm_installer.did" \
     python3 -m basilisk realm_installer src/realm_installer/main.py
   CANISTER_CANDID_PATH="$PWD/src/realm_registry_backend/realm_registry_backend.did" \
     python3 -m basilisk realm_registry_backend src/realm_registry_backend/main.py
   ls -l .basilisk/realm_installer/realm_installer.wasm .basilisk/realm_registry_backend/realm_registry_backend.wasm)

  say "Build: portal (realm_registry_frontend/dist)"
  (cd "$GAAS_DIR"
   npm ci --legacy-peer-deps
   dfx generate realm_registry_backend
   dfx generate realm_installer
   npm run build --workspace=realm_registry_frontend
   test -f src/realm_registry_frontend/dist/index.html)

  say "Build: realm backend (--variant $BUILD_VARIANT) and realm frontend in $REALMS_DIR"
  (cd "$REALMS_DIR"
   CANISTER_CANDID_PATH="$PWD/src/realm_backend/realm_backend.did" \
     python3 scripts/pack_realm_backend.py --variant "$BUILD_VARIANT"
   ls -l .basilisk/realm_backend/realm_backend.wasm
   # Root workspace install (a workspace-local install strands vite away from the
   # hoisted @sveltejs/kit), then the workspace package the frontend imports.
   npm install --legacy-peer-deps
   npm run build --workspace packages/extension-bridge
   (cd src/realm_frontend && REALMS_BUILD_VARIANT="$BUILD_VARIANT" npm run build && test -f dist/index.html)
   python3 scripts/check_frontend_variant.py src/realm_frontend/dist "$BUILD_VARIANT")

  say "Build: ic-tokens token wasm (v$IC_TOKENS_VERSION)"
  mkdir -p "$REALMS_DIR/.external-wasms"
  if [ -s "$REALMS_DIR/.external-wasms/token_backend.wasm" ]; then
    note "have token_backend.wasm"
  else
    curl -fsSL "https://github.com/smart-social-contracts/ic-tokens/releases/download/v${IC_TOKENS_VERSION}/token_backend.wasm" \
      -o "$REALMS_DIR/.external-wasms/token_backend.wasm"
    note "fetched token_backend.wasm"
  fi
fi
[ "$BUILD_ONLY" = 1 ] && { say "Build only: done"; exit 0; }

# ── pin ───────────────────────────────────────────────────────────────────────
# Production refuses a registry.wasms / registry.publish row without a sha256
# that matches what was built; other environments re-pin to the build and say so.
if [ "$PUBLISH_ONLY" = 0 ]; then
  if [ "$ENV" = local ]; then
    say "Pin: informational for -e local (up re-pins to what was built)"
    casals pin "$SHEET" --check || note "rows drift from their pins; fine locally, run \`casals pin casals.json\` before a production deploy"
  else
    say "Pin: casals pin casals.json (production requires pins on every row)"
    casals pin "$SHEET"
    if ! (cd "$GAAS_DIR" && git diff --quiet -- casals.json); then
      (cd "$GAAS_DIR" && git --no-pager diff --stat -- casals.json)
      note "casals pin rewrote pins in casals.json: review and commit them (the sheet in git must match what runs)."
      confirm "Continue the deploy with these pins?" || die "stopped at pin; commit casals.json and re-run"
    else
      note "pins unchanged"
    fi
  fi
fi

# ── up ────────────────────────────────────────────────────────────────────────
if [ "$PUBLISH_ONLY" = 0 ]; then
  if [ "$ENV" = local ]; then
    # The Casals e2e harness: starts the replica if needed, funds the identity,
    # then grades the sheet (fresh, idempotent, runtime_stand: a stand minted
    # through create_stand converges — the installer's path). KEEP=1 leaves it up.
    say "casals up (harness, scenarios: $SCENARIOS)"
    (cd "$CASALS_DIR" && CASALS_HOME="$CASALS_HOME" CASALS_E2E_ENV=local CASALS_E2E_IDENTITY="$IDENTITY" \
       KEEP=1 SCENARIOS="$SCENARIOS" python3 tests/e2e/run_e2e.py "$SHEET")
  else
    up_args=(up "$SHEET")
    [ "$YES" = 1 ] && up_args+=(--yes)
    [ "$BOOTSTRAP" = 1 ] && up_args+=(--bootstrap)
    global_args=()
    [ -n "$UPLOAD_IDENTITY" ] && global_args+=(--upload-identity "$UPLOAD_IDENTITY")
    if [ "$ENV" = local ]; then
      eval "$(cd "$CASALS_DIR" && python3 -m casals_cli.replica start)"   # idempotent
    elif [ "$YES" = 0 ] && [ -f "$BINDINGS_FILE" ]; then
      say "casals plan (what up would change)"
      casals plan "$SHEET" || true
      confirm "Apply this plan to $ENV as $IDENTITY?" || die "stopped before up"
    fi
    say "casals ${global_args[*]:-} ${up_args[*]}"
    [ "$ENV" = local ] || note "a hardware identity signs bootstrap, set_sheet and every apply: expect touches / PIN prompts"
    casals ${global_args[@]+"${global_args[@]}"} "${up_args[@]}"
  fi
fi
[ -f "$BINDINGS_FILE" ] || die "no bindings at $BINDINGS_FILE after up"

# ── export ────────────────────────────────────────────────────────────────────
# Ids come from the live conductor, never from a table in the repo.
say "Export: live bindings"
EXPORT_JSON="$ORCH_HOME/$ORCHESTRA.$ENV.export.json"
casals export "$SHEET" > "$EXPORT_JSON"
binding() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("bindings",{}).get(sys.argv[2],""))' "$EXPORT_JSON" "$1"; }
FILE_REGISTRY="$(binding file-registry)"       # the GaaS platform registry (installer.file_registry_id), not the Realms fleet one
INSTALLER="$(binding realm-installer)"
PORTAL_FE="$(binding realm-registry-frontend)"
CASALS_FE="$(python3 -c 'import json,sys; print((json.load(open(sys.argv[1])).get("conductor") or {}).get("casals-frontend",""))' "$BINDINGS_FILE")"
NETWORK_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("network_url",""))' "$BINDINGS_FILE")"
[ -n "$FILE_REGISTRY" ] || die "export has no file-registry binding (is the Infra section built?)"
[ -n "$INSTALLER" ]     || die "export has no realm-installer binding"
if [ "$ENV" = local ]; then PUBLISH_NET="$NETWORK_URL"; else PUBLISH_NET="$NETWORK"; fi
note "file-registry    $FILE_REGISTRY"
note "realm-installer  $INSTALLER"
note "network          $PUBLISH_NET"

# ── domains ───────────────────────────────────────────────────────────────────
if [ "$PUBLISH_ONLY" = 0 ]; then
  if [ "$NO_DOMAINS" = 1 ]; then
    say "Domains: skipped (--no-domains)"
  elif [ "$DNS_PROVIDER" = none ] || [ -z "$DNS_PROVIDER" ]; then
    say "Domains: none for -e $ENV (dns.provider=${DNS_PROVIDER:-unset})"
  else
    say "Domains: realms domains apply (Cloudflare records → IC gateway registration → HTTP 200)"
    dom_args=(domains apply "$SHEET" -e "$ENV" --export "$EXPORT_JSON")
    [ "$YES" = 1 ] && dom_args+=(--yes)
    (cd "$REALMS_DIR" && CASALS_HOME="$ORCH_HOME" realms "${dom_args[@]}")
  fi
fi
[ "$SKIP_PUBLISH" = 1 ] && { say "Provisioned; publish skipped (--skip-publish)"; exit 0; }

# ── publish ───────────────────────────────────────────────────────────────────
# `casals up` provisions canisters, not content. The installer fetches a new
# realm's codex and extensions from this registry (installer.config.file_registry_id)
# and the portal stores user branding in it; the sheet granted the operator
# publish rights on every namespace. `files publish` is idempotent (unchanged
# files are skipped). The packages live in the realms checkout.
pub_filter=(${PUBLISH_FILTER[@]+"${PUBLISH_FILTER[@]}"})
[ -n "$EXTENSIONS" ] && pub_filter+=(--extensions "$EXTENSIONS")
[ -n "$CODICES" ]    && pub_filter+=(--codices "$CODICES")
say "Publish: packages → GaaS file registry $FILE_REGISTRY"
[ "$ENV" = local ] || note "signed by $IDENTITY (a hardware key: one touch per upload batch)"
(cd "$REALMS_DIR" && realms files publish --network "$PUBLISH_NET" --registry "$FILE_REGISTRY" --identity "$IDENTITY" ${pub_filter[@]+"${pub_filter[@]}"})
if [ "$BRANDING" = 1 ]; then
  say "Publish: branding"
  (cd "$REALMS_DIR" && realms files publish-branding --network "$PUBLISH_NET" --registry "$FILE_REGISTRY" --identity "$IDENTITY") \
    || note "branding publish skipped (no branding sources)"
fi

# ── verify ────────────────────────────────────────────────────────────────────
say "Verify"
if [ "$PUBLISH_ONLY" = 0 ]; then
  # `up` converged when the sheet has nothing left to add: the plan is empty.
  # (--json is a global option of the CLI: it goes before the subcommand.)
  if casals --json plan "$SHEET" | python3 -c 'import json,sys; r=json.load(sys.stdin); sys.exit(0 if r.get("ok") and not (r.get("plan") or {}).get("items") else 1)'; then
    note "casals plan: empty"
  else
    casals plan "$SHEET" || true
    die "casals plan is not empty after up"
  fi
fi
# Read-only queries as `anonymous`: no touch on a hardware key, and the same
# call shape on a local replica (by URL) and on mainnet (by name).
if [ "$ENV" = local ]; then
  port="${NETWORK_URL##*:}"
  icp_net=(--network "$NETWORK_URL" --root-key fetch)
  url_of() { echo "http://$1.localhost:$port/"; }
  reg_url="$(url_of "$FILE_REGISTRY")"
else
  icp_net=(--network "$NETWORK")
  url_of() { echo "https://$1.icp0.io/"; }
  reg_url="https://$FILE_REGISTRY.raw.icp0.io/"
fi
namespaces="$(icp canister call "$FILE_REGISTRY" list_namespaces "()" --query "${icp_net[@]}" --identity anonymous 2>&1 || true)"
if printf '%s' "$namespaces" | grep -q '\\"namespace\\"\|"namespace"'; then
  note "file registry: $(printf '%s' "$namespaces" | grep -o 'namespace\\\?"' | wc -l) namespace(s)"
else
  printf '%s\n' "$namespaces" | tail -3
  die "GaaS file registry $FILE_REGISTRY lists no namespaces after publish"
fi
for want in ${EXTENSIONS//,/ }; do
  printf '%s' "$namespaces" | grep -q "ext/$want" || die "file registry has no ext/$want namespace"
done
# A unified codex (manifest kind: codex + backend/) is uploaded through the
# extension pipeline to ext/<id>/…; only the legacy layout lands under codex/.
for want in ${CODICES//,/ }; do
  printf '%s' "$namespaces" | grep -Eq "(ext|codex)/$want/" || die "file registry has no ext/$want or codex/$want namespace"
done

# A realm born the way the portal does it: request_deployment → installer
# create_stand → the conductor builds the stand → the installer fetches the
# codex and extensions the manifest names from this registry. Idempotent by name.
if [ -n "$SMOKE_REALM" ]; then
  say "Smoke: realm '$SMOKE_REALM' through the portal path"
  (cd "$GAAS_DIR" && CASALS_HOME="$CASALS_HOME" IDENTITY="$IDENTITY" TIMEOUT_S="${TIMEOUT_S:-1500}" \
     REALM_CODEX="${REALM_CODEX:-dominion}" REALM_EXTENSIONS="${REALM_EXTENSIONS:-hello_world}" \
     python3 tests/e2e/deploy_realm.py "$SMOKE_REALM")
fi

say "Done: $ORCHESTRA -e $ENV"
[ -n "$PORTAL_FE" ] && note "portal (wizard)    $(url_of "$PORTAL_FE")"
note "file registry      $reg_url"
[ -n "$CASALS_FE" ] && note "Casals frontend    $(url_of "$CASALS_FE")"
note "bindings           $BINDINGS_FILE"
note "export             $EXPORT_JSON"
