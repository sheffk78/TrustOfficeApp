#!/usr/bin/env bash
# TrustOffice Test Runner
# Runs all test suites against the live API with rate-limit-aware pacing.
# Usage: ./run_tests.sh [--no-wait] [--suite isolation|smoke|all]
#
# Exits non-zero on any test failure.

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${REACT_APP_BACKEND_URL:-https://api.trustoffice.app}"
SUITE="${2:-all}"
WAIT="${1:---wait}"

# Map of test files
ISOLATION_TESTS="tests/test_data_isolation.py"
SMOKE_TESTS="tests/test_api_smoke.py"

echo "=== TrustOffice Test Runner ==="
echo "API: $API_URL"
echo "Suite: $SUITE"
echo ""

# Wait for rate limits to clear if --wait is specified (default)
if [[ "$WAIT" != "--no-wait" ]]; then
  echo "Waiting 65s for rate limits to clear..."
  sleep 65
fi

FAILURES=0

run_suite() {
  local name="$1"
  local files="$2"
  echo "--- Running $name ---"
  cd "$BACKEND_DIR"
  if REACT_APP_BACKEND_URL="$API_URL" python3 -m pytest $files -v --tb=short 2>&1; then
    echo "✅ $name passed"
  else
    echo "❌ $name failed"
    FAILURES=$((FAILURES + 1))
  fi
  echo ""
}

case "$SUITE" in
  isolation)
    run_suite "Data Isolation Tests" "$ISOLATION_TESTS"
    ;;
  smoke)
    run_suite "API Smoke Tests" "$SMOKE_TESTS"
    ;;
  all)
    run_suite "Data Isolation Tests" "$ISOLATION_TESTS"
    run_suite "API Smoke Tests" "$SMOKE_TESTS"
    ;;
  *)
    echo "Unknown suite: $SUITE"
    echo "Usage: $0 [--no-wait] [isolation|smoke|all]"
    exit 1
    ;;
esac

echo ""
echo "=== Results ==="
if [[ $FAILURES -eq 0 ]]; then
  echo "✅ All tests passed"
  exit 0
else
  echo "❌ $FAILURES suite(s) failed"
  exit 1
fi