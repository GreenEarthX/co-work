#!/usr/bin/env bash
# Generate RSA-2048 key pair for JWT RS256 signing.
# Writes private.pem and public.pem to the directory specified by $KEY_DIR
# (default: backend/secrets/).
#
# Usage:
#   ./scripts/generate_jwt_keys.sh
#   KEY_DIR=/run/secrets ./scripts/generate_jwt_keys.sh

set -euo pipefail

KEY_DIR="${KEY_DIR:-$(dirname "$0")/../backend/secrets}"
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

PRIVATE_KEY="$KEY_DIR/private.pem"
PUBLIC_KEY="$KEY_DIR/public.pem"

openssl genrsa -out "$PRIVATE_KEY" 2048
chmod 600 "$PRIVATE_KEY"

openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
chmod 644 "$PUBLIC_KEY"

echo "Keys written to:"
echo "  Private: $PRIVATE_KEY"
echo "  Public:  $PUBLIC_KEY"
echo ""
echo "Set in .env:"
echo "  JWT_PRIVATE_KEY_PATH=$PRIVATE_KEY"
echo "  JWT_PUBLIC_KEY_PATH=$PUBLIC_KEY"
