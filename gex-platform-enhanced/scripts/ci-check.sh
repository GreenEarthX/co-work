#!/usr/bin/env bash
#
# CI gate (Ticket 1a + menu doctrine). Run from anywhere:
#     bash scripts/ci-check.sh
#
# Fails (exit 1) if ANY of these regress:
#   menu:   a role sees a route under two names / a route→label collision /
#           a role loses a signature task (persona-minimum)
#   authz:  an unauthorized user can call a sensitive backend endpoint
#           a Project-A entitlement can access Project B
#           revoked / expired access still works
#           a qualified role with NO relationship to the project is allowed
#           (route tests prove the "hidden from menu but URL-open" gap is closed)
#   guard:  a sensitive route fails OPEN (renders content) on auth error
#
# STATUS: this is a CI-READY local script. It is NOT yet wired into a hosted CI
# provider — the project is not under version control here (no .git). To wire it:
# add `bash scripts/ci-check.sh` as the required check in your CI pipeline
# (e.g. a GitHub Actions step) once the repo is initialised.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

echo "═══ 1/4 · MENU AUDIT (duplicate routes · persona-minimum) ═══"
if ( cd "$ROOT/frontend" && node scripts/audit-menu.mjs >/tmp/gex_menu_audit.log 2>&1 ); then
  echo "✅ menu audit PASS"
else
  echo "❌ menu audit FAIL"; tail -20 /tmp/gex_menu_audit.log; FAIL=1
fi

echo ""
echo "═══ 2/4 · BACKEND AUTHORIZATION TESTS (pytest) ═══"
PYTEST_BIN="python -m pytest"
if [ -x "$ROOT/backend/venv/bin/python" ]; then PYTEST_BIN="$ROOT/backend/venv/bin/python -m pytest"; fi
if ( cd "$ROOT/backend" && $PYTEST_BIN tests/test_finance_entitlements.py tests/test_route_authorization.py -q ); then
  echo "✅ backend authorization PASS"
else
  echo "❌ backend authorization FAIL"; FAIL=1
fi

echo ""
echo "═══ 3/4 · FRONTEND ROUTE-GUARD TESTS (vitest) ═══"
if ( cd "$ROOT/frontend" && npm test --silent >/tmp/gex_vitest.log 2>&1 ); then
  echo "✅ frontend guard tests PASS"
else
  echo "❌ frontend guard tests FAIL"; tail -25 /tmp/gex_vitest.log; FAIL=1
fi

echo ""
echo "═══ 4/4 · BUNDLE HYGIENE (no sensitive data / no direct engine access) ═══"
# Sensitive finance/model figures must NOT ship in the frontend bundle (R1),
# and the frontend must never call the PF engine on :8001 directly (R2).
HYG=$(grep -rnE "BPI\+EIB Term Sheet|KfW Term Sheet|Gabillon alpha parameter|drawdownAmount:[[:space:]]*[0-9]" "$ROOT/frontend/src" 2>/dev/null || true)
ENG=$(grep -rnE "fetch\([^)]*:8001" "$ROOT/frontend/src" 2>/dev/null || true)
if [ -z "$HYG" ] && [ -z "$ENG" ]; then
  echo "✅ bundle hygiene PASS (no sensitive constants, no direct :8001 engine calls)"
else
  echo "❌ bundle hygiene FAIL"; [ -n "$HYG" ] && echo "$HYG"; [ -n "$ENG" ] && echo "$ENG"; FAIL=1
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "═══ CI GATE: ✅ PASS ═══"; exit 0
else
  echo "═══ CI GATE: ❌ FAIL ═══"; exit 1
fi
