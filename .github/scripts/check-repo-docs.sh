#!/bin/bash
# Per-repo documentation consistency checker (v2).
# Scans markdown, txt, toml, and requirements.txt for banned patterns.
#
# Usage: bash check-repo-docs.sh [repo-root]

set -euo pipefail

BASE="${1:-.}"
ERRORS=0

# Build file list: .md, .txt, .toml, .ipynb (notebooks contain install guidance too).
# Excludes: .git, node_modules, executed notebook outputs, and negative test fixtures.
# doc-check-fixtures/ contains intentional bad patterns for checker self-testing.
# Note: test-fixtures/ is excluded only in the cross-repo checker (check-doc-consistency.sh),
# not here, because the per-repo checker is used directly by the self-test suite.
FILES=$(find "$BASE" -maxdepth 4 \
    \( -name '*.md' -o -name '*.txt' -o -name '*.toml' -o -name '*.ipynb' -o -name 'requirements*.txt' \) \
    -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*_executed*' \
    -not -path '*/doc-check-fixtures/*' \
    2>/dev/null | sort -u || true)

FILE_COUNT=$(echo "$FILES" | grep -c . || echo 0)

echo "QONTOS Per-Repo Doc Check (v2)"
echo "==============================="
echo "Scanning $FILE_COUNT files"

# Check 1: No non-canonical security emails
echo ""
echo "--- Security email ---"
BAD_SEC=$(echo "$FILES" | xargs grep -n 'security@' 2>/dev/null \
    | grep -v 'security@qontos.io' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_SEC" ]; then
    echo "  ✗ Non-canonical security email:"
    echo "$BAD_SEC" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

# Check 2: No aspirational pip install
echo ""
echo "--- Aspirational pip install ---"
BAD_PIP=$(echo "$FILES" | xargs grep -n 'pip install qontos\b\|pip install qontos-sim\b\|pip install qontos-bench\b' 2>/dev/null \
    | grep -v 'git+' | grep -v 'simplify' | grep -v 'Once published' | grep -v 'will simplify' \
    | grep -v 'Never write' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_PIP" ]; then
    echo "  ✗ Aspirational install:"
    echo "$BAD_PIP" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

# Check 3: No @main in install/dependency references
echo ""
echo "--- @main references ---"
BAD_MAIN=$(echo "$FILES" | xargs grep -n '@main' 2>/dev/null \
    | grep -v 'Never use' | grep -v 'CONTRIBUTING' || true)
if [ -n "$BAD_MAIN" ]; then
    echo "  ✗ @main reference:"
    echo "$BAD_MAIN" | sed 's/^/    /'
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ OK"
fi

echo ""
echo "==============================="
if [ "$ERRORS" -gt 0 ]; then
    echo "FAIL: $ERRORS issue(s)"
    exit 1
else
    echo "PASS"
fi
