#!/usr/bin/env bash
# Rebuild the self-hosted @dfinity client bundle (dist/dfinity.js).
#
# We pre-bundle @dfinity/agent + @dfinity/auth-client + their transitive
# deps into a single ES module so the page doesn't pull anything from a
# CDN. This avoids two real-world problems:
#
#   1. esm.sh resolves @dfinity/agent and @dfinity/auth-client
#      independently, sometimes pulling mismatched @dfinity/candid
#      versions, which crashes with "does not provide an export named
#      'bufFromBufLike'".
#   2. CDN downtime / latency would silently break the admin UI.
#
# Run from this script's directory:
#   ./build-dfinity-bundle.sh
#
# Output: ../dist/dfinity.js (~190 KB, exports HttpAgent, Actor, AuthClient)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DIST="$HERE/../dist"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> staging in $WORK"
cd "$WORK"
npm init -y >/dev/null 2>&1
npm install --silent --no-audit --no-fund \
    @dfinity/agent@3 \
    @dfinity/auth-client@3 \
    @dfinity/identity@3 \
    @dfinity/principal@3 \
    @dfinity/candid@3

cat > entry.js <<'EOF'
export { HttpAgent, Actor } from "@dfinity/agent";
export { AuthClient } from "@dfinity/auth-client";
EOF

echo "==> bundling with esbuild"
npx --yes esbuild@0.21.5 entry.js \
    --bundle --format=esm --target=es2022 \
    --minify --legal-comments=none \
    --outfile="$DIST/dfinity.js"

echo "==> done — $(wc -c < "$DIST/dfinity.js") bytes -> $DIST/dfinity.js"
