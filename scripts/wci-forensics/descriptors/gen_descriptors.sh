#!/usr/bin/env bash
# Regenerate deployment_descriptors.binpb from the server proto registry.
#
# The generator (gen_descriptors.go) must build inside the
# temporal-auto-scaled-workers Go module so that go.temporal.io/server resolves
# to the version pinned in that repo's go.mod. This script copies the generator
# into a throwaway package under the repo, runs it, writes the descriptor set
# next to this script, then cleans up. Re-run whenever the pinned
# go.temporal.io/server or go.temporal.io/api versions change.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Path to a checkout of the temporal-auto-scaled-workers Go module. Override with
# WCI_REPO=/path/to/temporal-auto-scaled-workers
REPO="${WCI_REPO:-/path/to/temporal-auto-scaled-workers}"
# Optional: prepend a dir containing `go` to PATH (e.g. a mise/asdf shims dir).
[ -n "${GO_BIN_DIR:-}" ] && export PATH="$GO_BIN_DIR:$PATH"

if [ ! -d "$REPO" ]; then
  echo "repo not found at '$REPO'; set WCI_REPO to your temporal-auto-scaled-workers checkout" >&2
  exit 1
fi
if ! command -v go >/dev/null 2>&1; then
  echo "go not found on PATH (set GO_BIN_DIR to a dir containing 'go')" >&2
  exit 1
fi

TMP="$REPO/cmd/_wci_forensics_gendesc"
mkdir -p "$TMP"
cp "$HERE/gen_descriptors.go" "$TMP/main.go"
trap 'rm -rf "$TMP"' EXIT

( cd "$REPO" && go run ./cmd/_wci_forensics_gendesc ) > "$HERE/deployment_descriptors.binpb"

echo "wrote $HERE/deployment_descriptors.binpb ($(wc -c < "$HERE/deployment_descriptors.binpb") bytes)" >&2
