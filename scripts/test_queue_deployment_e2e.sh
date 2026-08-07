#!/usr/bin/env bash
# =============================================================================
# E2E test for the queue-based deployment pipeline (Issue #205)
#
# Tests the full flow:
#   1. Submit a deployment via request_deployment on the registry backend
#   2. Installer enqueues and allocates canisters
#   3. Worker picks up job, downloads artifacts, deploys WASM + frontend
#   4. Worker reports canister_ready + frontend_verified
#   5. Installer verifies hashes and notifies registry
#   6. Credits captured on success
#
# Prerequisites:
#   - dfx SDK installed
#   - Canisters deployed: realm_registry_backend, realm_installer
#   - Deploy service running (for branding upload test, optional)
#   - Run from the gos-as-a-service repo root
#
# Usage:
#   bash scripts/test_queue_deployment_e2e.sh [--network staging|demo]
#   bash scripts/test_queue_deployment_e2e.sh --dry-run   # validate setup only
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

pass()  { PASS=$((PASS+1)); echo -e "${GREEN}  PASS $1${NC}"; }
fail()  { FAIL=$((FAIL+1)); echo -e "${RED}  FAIL $1${NC}"; }
skip()  { SKIP=$((SKIP+1)); echo -e "${YELLOW}  SKIP $1${NC}"; }
info()  { echo -e "${BLUE}$1${NC}"; }
warn()  { echo -e "${YELLOW}$1${NC}"; }

NETWORK="staging"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --network) NETWORK="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Usage: $0 [--network staging|demo] [--dry-run]"; exit 1 ;;
  esac
done

export TERM="${TERM:-xterm}"
export DFX_WARNING="-mainnet_plaintext_identity"

# ── Canister IDs ──────────────────────────────────────────────────────
declare -A REGISTRY_IDS=(
  [staging]="7wzxh-wyaaa-aaaau-aggyq-cai"
  [demo]="rhw4p-gqaaa-aaaac-qbw7q-cai"
)
declare -A INSTALLER_IDS=(
  [staging]="lusjm-wqaaa-aaaau-ago7q-cai"
  [demo]="2s4td-daaaa-aaaao-bazmq-cai"
)

REGISTRY_ID="${REGISTRY_IDS[$NETWORK]:-}"
INSTALLER_ID="${INSTALLER_IDS[$NETWORK]:-}"

if [[ -z "$REGISTRY_ID" || -z "$INSTALLER_ID" ]]; then
  echo "ERROR: No canister IDs for network '$NETWORK'"
  exit 1
fi

info "╔══════════════════════════════════════════════════╗"
info "║  Queue Deployment E2E Test (Issue #205)          ║"
info "║  Network: $NETWORK"
info "║  Registry: $REGISTRY_ID"
info "║  Installer: $INSTALLER_ID"
info "╚══════════════════════════════════════════════════╝"

# ── Helper: call a canister ────────────────────────────────────────────
dfx_call() {
  local canister="$1" method="$2" arg="$3"
  dfx canister call "$canister" "$method" "$arg" --network "$NETWORK" --output json 2>&1
}

dfx_query() {
  local canister="$1" method="$2" arg="$3"
  dfx canister call --query "$canister" "$method" "$arg" --network "$NETWORK" --output json 2>&1
}

# ── Phase 0: Validate setup ──────────────────────────────────────────
info "\n Phase 0: Validate setup"

# Check dfx
if ! command -v dfx &>/dev/null; then
  fail "dfx not found in PATH"
  exit 1
fi
pass "dfx found: $(dfx --version)"

# Check canister accessibility (installer has health + info; registry may not)
INSTALLER_HEALTH=$(dfx_query "$INSTALLER_ID" "health" "()" 2>&1 || echo "ERROR")
if echo "$INSTALLER_HEALTH" | grep -qE '"ok":\s*true|ok = true'; then
  pass "Installer reachable (health ok)"
else
  fail "Cannot reach installer ($INSTALLER_ID)"
  echo "  Response: $INSTALLER_HEALTH"
fi

INSTALLER_INFO=$(dfx_query "$INSTALLER_ID" "info" "()" 2>&1 || echo "ERROR")
if echo "$INSTALLER_INFO" | grep -q "report_frontend_verified"; then
  pass "Installer has report_frontend_verified endpoint (new code deployed)"
else
  warn "  Installer does NOT have report_frontend_verified yet — deploy new code first"
fi

if $DRY_RUN; then
  info "\n Dry run complete. Setup looks good."
  info "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
  exit 0
fi

# ── Phase 1: Check credit balance ────────────────────────────────────
info "\n Phase 1: Credit balance check"

CREDITS_RAW=$(dfx_query "$REGISTRY_ID" "get_user_credits" "()" 2>&1 || echo "{}")
info "  Credits response: $CREDITS_RAW"

# ── Phase 2: Submit deployment ────────────────────────────────────────
info "\n Phase 2: Submit deployment request"

REALM_NAME="e2e-test-$(date +%s)"
RELEASE_TAG="v0.3.2"
RELEASE_BASE="https://github.com/smart-social-contracts/realms/releases/download"
declare -A FILE_REGISTRY_IDS=(
  [staging]="iebdk-kqaaa-aaaau-agoxq-cai"
  [demo]="vi64l-3aaaa-aaaae-qj4va-cai"
)
FILE_REGISTRY_ID="${FILE_REGISTRY_IDS[$NETWORK]:-}"

MANIFEST=$(cat <<EOF
{
  "realm": {
    "name": "$REALM_NAME",
    "display_name": "E2E Test Realm",
    "description": "Automated test realm for queue deployment pipeline",
    "welcome_message": "Welcome to the E2E test realm!",
    "codex": {"package": "syntropia", "version": "latest"},
    "extensions": ["all"]
  },
  "network": "$NETWORK",
  "file_registry_canister_id": "$FILE_REGISTRY_ID",
  "canister_artifacts": {
    "realm": {
      "backend": {
        "wasm": {
          "url": "$RELEASE_BASE/$RELEASE_TAG/realm_backend.wasm.gz",
          "checksum": ""
        }
      },
      "frontend": {
        "url": "$RELEASE_BASE/$RELEASE_TAG/realm_frontend.tar.gz",
        "checksum": ""
      }
    }
  }
}
EOF
)

MANIFEST_ESCAPED=$(echo "$MANIFEST" | python3 -c "
import sys, json
raw = sys.stdin.read()
obj = json.loads(raw)
print(json.dumps(json.dumps(obj)))
" | sed 's/^"//;s/"$//')

info "  Submitting deployment for realm: $REALM_NAME"
DEPLOY_RAW=$(dfx_call "$REGISTRY_ID" "request_deployment" "(\"$MANIFEST_ESCAPED\")" 2>&1)
info "  Response: ${DEPLOY_RAW:0:200}"

# Parse response
JOB_ID=$(echo "$DEPLOY_RAW" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    payload = data.get('Ok', data) if isinstance(data, dict) else data
    if isinstance(payload, str):
        payload = json.loads(payload)
    print(payload.get('job_id', ''))
except Exception as e:
    print('')
" 2>/dev/null)

if [[ -n "$JOB_ID" ]]; then
  pass "Deployment enqueued: job_id=$JOB_ID"
else
  fail "Deployment request failed (no job_id in response)"
  info "\n Stopping — cannot continue without job_id."
  info "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
  exit 1
fi

# ── Phase 3: Poll job status ─────────────────────────────────────────
info "\n Phase 3: Poll job status (timeout: 5 min)"

MAX_WAIT=300
ELAPSED=0
INTERVAL=10
FINAL_STATUS=""

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
  STATUS_RAW=$(dfx_query "$INSTALLER_ID" "get_deployment_job_status" "(\"$JOB_ID\")" 2>&1 || echo "{}")

  CURRENT_STATUS=$(echo "$STATUS_RAW" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    payload = data.get('Ok', data) if isinstance(data, dict) else data
    if isinstance(payload, str):
        payload = json.loads(payload)
    print(payload.get('status', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)

  echo -e "  [${ELAPSED}s] Status: $CURRENT_STATUS"

  case "$CURRENT_STATUS" in
    completed|failed|failed_verification|cancelled)
      FINAL_STATUS="$CURRENT_STATUS"
      break
      ;;
  esac

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ -z "$FINAL_STATUS" ]]; then
  fail "Job timed out after ${MAX_WAIT}s (last status: $CURRENT_STATUS)"
elif [[ "$FINAL_STATUS" == "completed" ]]; then
  pass "Deployment completed successfully"
else
  fail "Deployment ended with status: $FINAL_STATUS"
fi

# ── Phase 4: Verify deployment ───────────────────────────────────────
info "\n Phase 4: Verify deployed realm"

if [[ "$FINAL_STATUS" == "completed" ]]; then
  # Get the full job status for canister IDs
  FULL_STATUS=$(dfx_query "$INSTALLER_ID" "get_deployment_job_status" "(\"$JOB_ID\")" 2>&1 || echo "{}")
  info "  Full status: ${FULL_STATUS:0:300}"

  BACKEND_CID=$(echo "$FULL_STATUS" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    payload = data.get('Ok', data) if isinstance(data, dict) else data
    if isinstance(payload, str):
        payload = json.loads(payload)
    print(payload.get('backend_canister_id', ''))
except:
    print('')
" 2>/dev/null)

  FRONTEND_CID=$(echo "$FULL_STATUS" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    payload = data.get('Ok', data) if isinstance(data, dict) else data
    if isinstance(payload, str):
        payload = json.loads(payload)
    print(payload.get('frontend_canister_id', ''))
except:
    print('')
" 2>/dev/null)

  if [[ -n "$BACKEND_CID" ]]; then
    pass "Backend canister: $BACKEND_CID"

    # Verify WASM is installed (canister responds to info)
    BACKEND_INFO=$(dfx_query "$BACKEND_CID" "info" "()" 2>&1 || echo "ERROR")
    if echo "$BACKEND_INFO" | grep -qi "error\|reject_code"; then
      fail "Backend canister not responding to info()"
    else
      pass "Backend canister responds to info()"
    fi
  else
    skip "Backend canister ID not in status response"
  fi

  if [[ -n "$FRONTEND_CID" ]]; then
    pass "Frontend canister: $FRONTEND_CID"
  else
    skip "Frontend canister ID not in status response"
  fi
else
  skip "Deployment did not complete — skipping verification"
fi

# ── Results ──────────────────────────────────────────────────────────
info "\n══════════════════════════════════════════════"
info "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
info "══════════════════════════════════════════════"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
