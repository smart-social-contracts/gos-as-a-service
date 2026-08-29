#!/usr/bin/env bash
# Estado de los entornos — wrapper fino sobre scripts/estado_entornos.py.
#
# Uso:
#   ./scripts/estado_entornos.sh --identity deployer
#   ./scripts/estado_entornos.sh --identity my-dev-identity1 --env staging
#   ./scripts/estado_entornos.sh --fixtures tests/backend/fixtures/estado_entornos
#
# Solo lectura: queries (--query) y `canister status`; nunca upgrade/reinstall.
# Requiere dfx o icp en PATH y una identidad controller de los canisters.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export TERM="${TERM:-xterm}"
export DFX_WARNING=-mainnet_plaintext_identity

exec python3 "$SCRIPT_DIR/estado_entornos.py" "$@"
