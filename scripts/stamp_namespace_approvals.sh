#!/usr/bin/env bash
# Stamp marketplace approvals on file-registry ext/ and codex/ namespaces.
#
# First-party publish (gaas seed, this script, or realms deploy-files.yml)
# must leave get_namespace_approval_icc → approved:true and content_matches
# for the current hash. Realms refuse operator-attributed stamps; this routes
# through marketplace admin_approve_namespace.
#
# Test/staging only. Refuses demo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVIRONMENT=""
IDENTITY="${IDENTITY:-deployer}"
NETWORK="${NETWORK:-ic}"
FORCE=1

usage() {
  cat <<'EOF'
Usage: scripts/stamp_namespace_approvals.sh -e test|staging [options]

  -e, --environment   test or staging (demo is refused)
  -i, --identity      dfx identity (default: deployer)
  -n, --network       dfx network (default: ic)
      --no-force      only stamp namespaces that are not currently approved
  -h, --help          show this help

Requires a gaas-cli install (pip install -e cli/) and environments/<env>.json.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--environment) ENVIRONMENT="$2"; shift 2 ;;
    -i|--identity) IDENTITY="$2"; shift 2 ;;
    -n|--network) NETWORK="$2"; shift 2 ;;
    --no-force) FORCE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$ENVIRONMENT" ]]; then
  echo "error: -e/--environment is required" >&2
  usage >&2
  exit 2
fi

if [[ "$ENVIRONMENT" == "demo" ]]; then
  echo "error: refusing to stamp namespace approvals on demo" >&2
  exit 1
fi

if [[ "$ENVIRONMENT" != "test" && "$ENVIRONMENT" != "staging" ]]; then
  echo "error: environment must be test or staging (got ${ENVIRONMENT})" >&2
  exit 1
fi

DESCRIPTOR="$ROOT/environments/${ENVIRONMENT}.json"
if [[ ! -f "$DESCRIPTOR" ]]; then
  echo "error: missing descriptor ${DESCRIPTOR}" >&2
  exit 1
fi

export TERM="${TERM:-xterm}"
export DFX_WARNING="${DFX_WARNING:--mainnet_plaintext_identity}"

ARGS=(stamp-namespace-approvals "$DESCRIPTOR" --identity "$IDENTITY" --network "$NETWORK")
if [[ "$FORCE" -eq 1 ]]; then
  ARGS+=(--force)
else
  ARGS+=(--no-force)
fi

exec python3 -m gaas "${ARGS[@]}"
