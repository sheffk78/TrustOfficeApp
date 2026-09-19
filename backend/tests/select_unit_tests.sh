#!/usr/bin/env bash
# select_unit_tests.sh — compute pytest --ignore args for CI unit runs.
#
# Background (2026-09-19): the backend test tree mixes two kinds of suites:
#   1. Live-API suites that call requests.post/get against BASE_URL derived
#      from REACT_APP_BACKEND_URL — designed for the nightly cron run against
#      a deployed server (conftest.py gates these away from prod hosts).
#   2. True unit suites that run in-process against a local Mongo.
# Running (1) without a server produces ~820 errors + ~190 failures that are
# all MissingSchema noise, drowning real regressions.
#
# This script scans tests/ for live-API markers and emits --ignore args for
# them, so CI runs the rest. Self-maintaining: new live-API suites are picked
# up automatically by their imports/calls, no list to hand-update.
#
# Live-API markers (any one qualifies):
#   - REACT_APP_BACKEND_URL / BACKEND_URL / TEST_BASE_URL env reads
#   - requests.(post|get|put|delete|patch) calls
#   - httpx.(post|get) calls with an http URL
# Exemptions (never ignored):
#   - conftest.py, health_monitor.py, __init__.py
set -uo pipefail
cd "$(dirname "$0")"   # now inside tests/

MARKERS='REACT_APP_BACKEND_URL|BACKEND_URL|TEST_BASE_URL|requests\.(post|get|put|delete|patch)\(|httpx\.(post|get)\(|^from test_[a-z_]+_router import \*|BASE_URL *='

# Isolation-hostile files: they inject sys.modules stubs (e.g. a fake
# "dependencies") at import time that poison every later collection in the
# same process. They must run alone, never in the combined CI unit run.
ISOLATION_HOSTILES='test_cc_normalize.py test_booking_email_endpoints.py test_booking_lead_push.py'

args=""
for f in test_*.py; do
  # Isolation-hostile check first (by name)
  skip=0
  for h in $ISOLATION_HOSTILES; do
    [ "$f" = "$h" ] && skip=1
  done
  [ "$skip" = "1" ] && { args="$args --ignore=tests/$f"; continue; }
  if grep -qE "$MARKERS" "$f" 2>/dev/null; then
    args="$args --ignore=tests/$f"
  fi
done

echo "$args"