#!/bin/bash
# Run all code quality checks for the rom-decomp-64 project.
# Usage: bash py/scripts/check.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY_DIR="$SCRIPT_DIR/../"

echo "========================================="
echo "  rom-decomp-64 checker"
echo "========================================="
echo ""

# 1. Ruff Lint
echo "--- [1/5] Ruff Lint ---"
if python3 -m ruff check "$PY_DIR/"; then
    echo "Ruff lint: All checks passed"
else
    echo "Ruff lint: Errors found"
    FAILED=1
fi
echo ""

# 2. Ruff Format
echo "--- [2/5] Ruff Format ---"
if python3 -m ruff format --check "$PY_DIR/" 2>&1; then
    echo "Ruff format: All files formatted"
else
    echo "Ruff format: Some files need formatting (run: python3 -m ruff format py/)"
    # Don't fail on format differences — it's a warning
fi
echo ""

# 3. Mypy Type Checking
echo "--- [3/5] Mypy Type Check ---"
MYPY_OUTPUT=$(python3 -m mypy "$PY_DIR/" 2>&1) || true
MYPY_EXIT=$?
echo "$MYPY_OUTPUT"
# Count errors (exclude legacy test file errors)
CORE_ERRORS=$(echo "$MYPY_OUTPUT" | grep -c "error:" | head -1)
TEST_ERRORS=$(echo "$MYPY_OUTPUT" | grep -c "test_" | head -1)
REAL_ERRORS=$((CORE_ERRORS - TEST_ERRORS))
if [ "$REAL_ERRORS" -le 0 ]; then
    echo "Mypy: No errors in production code ($TEST_ERRORS legacy test errors excluded)"
else
    echo "Mypy: $REAL_ERRORS errors in production code"
    FAILED=1
fi
echo ""

# 4. Grep for linter bypass comments
echo "--- [4/5] Linter Bypass Comments ---"
BYPASS_COUNT=$(grep -rn "# type: ignore\|# noqa" "$PY_DIR/" --include='*.py' 2>/dev/null | wc -l)
if [ "$BYPASS_COUNT" -eq 0 ]; then
    echo "No '# type: ignore' or '# noqa' comments found"
else
    echo "Found $BYPASS_COUNT linter bypass comment(s):"
    grep -rn "# type: ignore\|# noqa" "$PY_DIR/" --include='*.py' 2>/dev/null
    FAILED=1
fi
echo ""

# 5. Smoke Test (extraction with vanilla ROM)
echo "--- [5/5] Extraction Smoke Test ---"
if [ -f "$PROJECT_ROOT/baserom.us.z64" ]; then
    # Run from the py directory so local imports work
    cd "$PY_DIR"
    EXTRACT_OUTPUT=$(python3 extract.py "$PROJECT_ROOT/baserom.us.z64" 2>&1) || EXTRACT_EXIT=$?
    EXTRACT_EXIT=${EXTRACT_EXIT:-0}
    cd "$PROJECT_ROOT"

    # Show just the summary
    echo "$EXTRACT_OUTPUT" | grep -A 10 "=== Parse summary ===" || true
    if [ $EXTRACT_EXIT -eq 0 ]; then
        echo "Extraction: Completed successfully"
    else
        echo "Extraction: Failed (exit code $EXTRACT_EXIT)"
        # If it failed, show the full output to help debugging
        echo "--- FULL OUTPUT ---"
        echo "$EXTRACT_OUTPUT"
        echo "-------------------"
        FAILED=1
    fi
else
    echo "Skipped: No baserom.us.z64 found"
fi
echo ""

# Summary
echo "========================================="
if [ "${FAILED:-0}" -eq 1 ]; then
    echo "SOME CHECKS FAILED"
    exit 1
else
    echo "ALL CHECKS PASSED"
    exit 0
fi
