"""Run the CI unit test selection (same filter as .github workflow + select_unit_tests.sh)."""
import os
import subprocess
import sys
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent

ignores = subprocess.run(
    ["bash", "tests/select_unit_tests.sh"], cwd=str(BACKEND),
    capture_output=True, text=True,
).stdout.split()

print(f"ignoring {len([a for a in ignores if a.startswith('--ignore=')])} live-API suites")
env = os.environ.copy()
env.setdefault("MONGO_URL", "mongodb://127.0.0.1:27999")
env.setdefault("DB_NAME", "test_ci_unit")
env.setdefault("JWT_SECRET", "test-secret")
env.setdefault("CORS_ORIGINS", "http://localhost:3000")

r = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *ignores],
    cwd=str(BACKEND), env=env,
)
sys.exit(r.returncode)
