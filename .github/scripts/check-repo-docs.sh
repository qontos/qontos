#!/bin/bash
# Per-repo documentation consistency checker.
# Lightweight version that checks a single repo's docs for banned patterns.
# Copy or reference from each public repo's CI.
#
# Usage: bash check-repo-docs.sh [repo-root]

set -euo pipefail

BASE="${1:-.}"
ERRORS=0

echo "QONTOS Per-Repo Doc Check"
echo "========================="

# Check 1: No non-canonical security emails
echo ""
echo "--- Security email ---"
BAD_SEC=$(grep -rn 'security@' "$BASE"/*.md "$BASE"/**/*.md 2>/dev/null \
    | grep -v 'security@qontos.io' | grep -v 'node_modules' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_SEC" ]; then
    echo "  ✗ Non-canonical security email found:"
    echo "$BAD_SEC" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

# Check 2: No aspirational pip install
echo ""
echo "--- Aspirational pip install ---"
BAD_PIP=$(grep -rn 'pip install qontos\b\|pip install qontos-sim\b\|pip install qontos-bench\b' \
    "$BASE"/*.md "$BASE"/**/*.md 2>/dev/null \
    | grep -v 'git+' | grep -v 'simplify' | grep -v 'Once published' | grep -v 'will simplify' \
    | grep -v 'Never write' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_PIP" ]; then
    echo "  ✗ Aspirational install found:"
    echo "$BAD_PIP" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

# Check 3: No @main in install references
echo ""
echo "--- @main references ---"
BAD_MAIN=$(grep -rn '@main' "$BASE"/*.md "$BASE"/*.txt "$BASE"/*.toml 2>/dev/null \
    | grep -v 'Never use' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_MAIN" ]; then
    echo "  ✗ @main install reference found:"
    echo "$BAD_MAIN" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

echo ""
echo "========================="
if [ "$ERRORS" -gt 0 ]; then
    echo "FAIL: $ERRORS issue(s)"
    exit 1
else
    echo "PASS"
fi
