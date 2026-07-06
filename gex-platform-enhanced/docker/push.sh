#!/usr/bin/env bash
# ── Build & Push GEX images to Docker Hub ────────────────────────────────
# Replaces the retired files/docker/push.sh (ADR 2026-07-06): images are
# built from THIS repo's source trees — never from rsync snapshots — so the
# published image is provably the code the tests inspect.
#
# Run from anywhere:
#   ./docker/push.sh <namespace> [tag]
# Examples:
#   ./docker/push.sh jmlamay
#   ./docker/push.sh co-work-gex v1.0.0
# ─────────────────────────────────────────────────────────────────────────

set -euo pipefail

NAMESPACE="${1:?Usage: ./push.sh <namespace> [tag]}"
TAG="${2:-latest}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"                # gex-platform-enhanced/
PF_ENGINE_DIR="$(cd "$REPO/../gex_pf_engine/backend" && pwd)"

FRONTEND_IMAGE="$NAMESPACE/gex-frontend:$TAG"
BACKEND_IMAGE="$NAMESPACE/gex-backend:$TAG"
PF_ENGINE_IMAGE="$NAMESPACE/gex-pf-engine:$TAG"
TEA_ENGINE_IMAGE="$NAMESPACE/gex-tea-engine:$TAG"

echo "══════════════════════════════════════════════════════════════"
echo "  GEX → Docker Hub"
echo "  Namespace : $NAMESPACE   Tag: $TAG"
echo "  Source    : $REPO"
echo "══════════════════════════════════════════════════════════════"

echo ""
echo "▶ Logging in..."
docker login

echo ""
echo "▶ Building gex-backend (context: backend/)..."
docker build -f "$REPO/docker/Dockerfile.backend.prod" -t "$BACKEND_IMAGE" "$REPO/backend"

echo ""
echo "▶ Building gex-frontend (context: repo root)..."
docker build -f "$REPO/docker/Dockerfile.frontend.prod" -t "$FRONTEND_IMAGE" "$REPO"

echo ""
echo "▶ Building gex-pf-engine (context: ../gex_pf_engine/backend)..."
docker build -t "$PF_ENGINE_IMAGE" "$PF_ENGINE_DIR"

echo ""
echo "▶ Building gex-tea-engine (context: tea_engine/)..."
docker build -t "$TEA_ENGINE_IMAGE" "$REPO/tea_engine"

echo ""
echo "▶ Pushing..."
docker push "$BACKEND_IMAGE"
docker push "$FRONTEND_IMAGE"
docker push "$PF_ENGINE_IMAGE"
docker push "$TEA_ENGINE_IMAGE"

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  ✓ Done!"
echo "  $BACKEND_IMAGE"
echo "  $FRONTEND_IMAGE"
echo "  $PF_ENGINE_IMAGE"
echo "  $TEA_ENGINE_IMAGE"
echo "══════════════════════════════════════════════════════════════"
