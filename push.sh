#!/usr/bin/env bash
# ── Build & Push GEX images to Docker Hub ───────────────────────────────
# Usage: ./push.sh <namespace> [tag]
# Examples:
#   ./push.sh jmlamay
#   ./push.sh co-work-gex v1.0.0
# ────────────────────────────────────────────────────────────────────────

set -euo pipefail

NAMESPACE="${1:?Usage: ./push.sh <namespace> [tag]}"
TAG="${2:-latest}"

DIR="$(cd "$(dirname "$0")" && pwd)"

FRONTEND_IMAGE="$NAMESPACE/gex-frontend:$TAG"
BACKEND_IMAGE="$NAMESPACE/gex-backend:$TAG"
PF_ENGINE_IMAGE="$NAMESPACE/gex-pf-engine:$TAG"

echo "══════════════════════════════════════════════════════════════"
echo "  GEX → Docker Hub"
echo "  Namespace : $NAMESPACE   Tag: $TAG"
echo "══════════════════════════════════════════════════════════════"

echo ""
echo "▶ Logging in..."
docker login

echo ""
echo "▶ Building gex-frontend..."
docker build -f "$DIR/Dockerfile.frontend.prod" -t "$FRONTEND_IMAGE" "$DIR"

echo ""
echo "▶ Building gex-backend..."
docker build -f "$DIR/Dockerfile.backend.prod" -t "$BACKEND_IMAGE" "$DIR"

echo ""
echo "▶ Building gex-pf-engine..."
docker build -f "$DIR/Dockerfile.pf-engine.prod" -t "$PF_ENGINE_IMAGE" "$DIR"

echo ""
echo "▶ Pushing..."
docker push "$FRONTEND_IMAGE"
docker push "$BACKEND_IMAGE"
docker push "$PF_ENGINE_IMAGE"

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  ✓ Done!"
echo "  $FRONTEND_IMAGE"
echo "  $BACKEND_IMAGE"
echo "  $PF_ENGINE_IMAGE"
echo "══════════════════════════════════════════════════════════════"
