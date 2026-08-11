#!/usr/bin/env bash
# ── Sync GEX projects to local docker folder ────────────────────────────

set -euo pipefail

# Resolve the workspace root from this script's own location, so the script
# works both in the dev workspace and in a fresh clone of the repository.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXCLUDES=(
  --exclude='node_modules'
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='.git'
  --exclude='dist'
  --exclude='*.db'
  --exclude='.env'
  --exclude='micro_service'
)

echo "▶ Syncing gex-platform-enhanced..."
rsync -a --delete "${EXCLUDES[@]}" \
  "$ROOT/gex-platform-enhanced/" \
  "$ROOT/docker/gex-platform-enhanced/"

echo "▶ Syncing gex_pf_engine..."
rsync -a --delete "${EXCLUDES[@]}" \
  "$ROOT/gex_pf_engine/" \
  "$ROOT/docker/gex_pf_engine/"

# Shared data files that live outside either project but are needed at runtime
echo "▶ Syncing shared data files..."
rsync -a "$ROOT/gex_fuel_catalog.json" "$ROOT/docker/gex_fuel_catalog.json"

echo "✓ Done"
