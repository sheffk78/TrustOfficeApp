"""
Regression tests: Google Drive cloud-backup OAuth multiplexing (2026-11-06,
chunk SYSTEM/kit-os/GOALS/trustoffice-cloud-storage-connect-test).

Guards the wiring fixed after the member-level test found the consent
round-trip dead-ending on the shared redirect var:

- sign-in flow reads GOOGLE_LOGIN_REDIRECT_URI (fallback: legacy var)
- backup google_drive multiplexes through the same registered redirect
- auth.google_callback routes cloud_backup-tagged states BEFORE login-state
  validation (tag only routes; JWT is re-verified by the backup completer)
- the completer re-verifies the JWT state and consumes the routing tag row
"""
import inspect
import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017/test")
os.environ.setdefault(
    "GOOGLE_LOGIN_REDIRECT_URI",
    "https://api.trustoffice.app/api/auth/google/callback",
)
os.environ.setdefault(
    "GOOGLE_REDIRECT_URI",
    "https://api.trustoffice.app/api/auth/google/callback",
)

from routers import auth as auth_router  # noqa: E402
from routers import cloud_backup as backup_router  # noqa: E402


def test_signin_reads_login_redirect_with_fallback():
    assert auth_router.GOOGLE_REDIRECT_URI == os.environ["GOOGLE_LOGIN_REDIRECT_URI"]


def test_google_drive_uses_multiplexed_redirect_key():
    assert backup_router.OAUTH_CONFIG["google_drive"]["redirect_key"] == "GOOGLE_REDIRECT_URI"


def test_initiate_oauth_tags_google_drive_state():
    src = inspect.getsource(backup_router.initiate_oauth)
    assert "flow" in src and "oauth_states" in src


def test_login_callback_routes_backup_tags_before_login_validation():
    src = inspect.getsource(auth_router.google_callback)
    tag = src.find("cloud_backup")
    inval = src.find("Invalid OAuth state")
    assert 0 < tag < inval, "backup routing must precede login-state handling"


def test_completer_reverifies_jwt_and_consumes_tag():
    src = inspect.getsource(backup_router.complete_google_backup_connect)
    assert "_verify_oauth_state" in src, "tag routes but JWT re-verification is the authorization"
    assert "delete_one" in src, "routing tag row must be single-use"
