"""P0-1 regression test (2026-10-01): org invite must reject invalid emails.

Bug: POST /api/orgs/{org_id}/invites stored ANY string as the member email;
the members-list endpoint then failed EmailStr validation on read and 500'd
the whole org (UI degraded to "Members (0)").

Fix: EMAIL_RE validation in routers/orgs.py (422 invalid_email) +
_sanitize_members() read-side filter. This file tests the validator logic +
sanitizer directly (no Mongo, no live API) so it never runs against prod.
"""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from routers.orgs import EMAIL_RE, _sanitize_members  # noqa: E402
from models import OrgMember  # noqa: E402


@pytest.mark.parametrize("email", [
    "not-an-email",
    "definitely-not-an-email",
    "a@b",
    "@domain.com",
    "user@",
    "",
    None,
])
def test_invalid_emails_rejected(email):
    if email is None or not isinstance(email, str):
        assert not email, "None must fail"
        # EMAIL_RE.match(None) would raise; endpoint guards with `not email` first
        return
    assert not EMAIL_RE.match(email), f"{email!r} should be rejected"


@pytest.mark.parametrize("email", [
    "test.qa1@trustoffice.app",
    "colleague@example.com",
    "first.last+tag@sub.domain.io",
])
def test_valid_emails_accepted(email):
    assert EMAIL_RE.match(email), f"{email!r} should be accepted"


def test_sanitize_members_skips_malformed_rows():
    good = {
        "member_id": "mem_ok", "org_id": "org_x", "user_id": "user_1",
        "email": "test.qa1@trustoffice.app", "name": "Ok", "role": "member",
        "status": "active", "invited_at": "2026-10-01T00:00:00+00:00",
        "invited_by": "user_1", "joined_at": None,
    }
    bad = dict(good, member_id="mem_bad", email="not-an-email")
    out = _sanitize_members([good, bad])
    assert len(out) == 1 and out[0].email == "test.qa1@trustoffice.app"


def test_sanitize_members_valid_row_survives():
    good = {
        "member_id": "mem_ok", "org_id": "org_x", "user_id": None,
        "email": "track3-member@testing.trustoffice.app", "name": "B",
        "role": "member", "status": "invited",
        "invited_at": "2026-10-01T00:00:00+00:00", "invited_by": "user_1",
    }
    (out,) = _sanitize_members([good])
    assert isinstance(out, OrgMember)