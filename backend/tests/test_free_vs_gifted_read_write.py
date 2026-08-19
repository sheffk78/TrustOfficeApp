"""
Regression tests for the FREE vs GIFTED read/write model (backend/dependencies.py).

Locks in Jeff's model:
  - FREE (non-gifted) users: READ access to their own data, but READ-ONLY
    (is_read_only=True) — they cannot do write work.
  - GIFTED users: full write access (is_read_only=False) while the gift is
    active, dropping to read-only when the gift expires.
  - forever_free: grandfathered/admin accounts with full write access.

Pure-unit tests on the state builders — no live server or DB required.
"""
import datetime
from datetime import timezone
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from dependencies import _build_free_state, _build_forever_free_state, _build_paid_state


def _mk_sub(**overrides):
    base = {
        "subscription_id": "sub_test",
        "user_id": "user_test",
        "plan_type": "free",
        "status": "active",
        "gifted": False,
        "gift_type": None,
        "gift_end_date": None,
        "trial_start_date": None,
        "trial_end_date": None,
    }
    base.update(overrides)
    return base


NOW = datetime.datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)
FUTURE = (NOW + datetime.timedelta(days=10)).isoformat()
PAST = (NOW - datetime.timedelta(days=1)).isoformat()


# ---- FREE (non-gifted) must be READ-ONLY ----

def test_active_free_user_is_read_only():
    """A plain free user (no gift) must be read-only — cannot write without paying."""
    state = _build_free_state("user_test", _mk_sub(), NOW)
    assert state.plan_type == "free"
    assert state.is_gifted is False
    assert state.is_active is True
    assert state.is_read_only is True  # CRITICAL: was False before the fix


def test_free_user_no_sub_status_is_read_only():
    """Free user even without explicit status must stay read-only."""
    state = _build_free_state("user_test", _mk_sub(status="trialing"), NOW)
    assert state.is_read_only is True


# ---- GIFTED must be WRITABLE while active ----

def test_active_gifted_user_is_writable():
    """Gifted free user with active gift gets full write access."""
    sub = _mk_sub(gifted=True, gift_type="14day", gift_end_date=FUTURE)
    state = _build_free_state("user_test", sub, NOW)
    assert state.is_gifted is True
    assert state.is_active is True
    assert state.is_read_only is False  # full write access during active gift


def test_active_gifted_trial_based_is_writable():
    """Gifted free user whose gift is trial-based (no gift_end_date) is writable."""
    sub = _mk_sub(gifted=True, gift_type="14day", gift_end_date=None, trial_end_date=FUTURE)
    state = _build_free_state("user_test", sub, NOW)
    assert state.is_gifted is True
    assert state.is_active is True
    assert state.is_read_only is False


def test_expired_gifted_user_is_read_only():
    """Gifted user whose gift has expired drops to read-only."""
    sub = _mk_sub(gifted=True, gift_type="14day", gift_end_date=PAST)
    state = _build_free_state("user_test", sub, NOW)
    assert state.is_gifted is True
    assert state.status == "expired"
    assert state.is_active is False
    assert state.is_read_only is True


def test_expired_gifted_paid_plan_is_read_only_without_stripe_subscription():
    """A paid-looking admin gift is still time-limited until Stripe payment exists."""
    sub = _mk_sub(plan_type="trustee", gifted=True, gift_type="trustee", gift_end_date=PAST)
    state = _build_paid_state("user_test", sub, NOW)
    assert state.is_gifted is True
    assert state.is_active is False
    assert state.is_read_only is True


# ---- forever_free is grandfathered/writable ----

def test_forever_free_is_writable():
    """forever_free (grandfathered/admin) users have full write access."""
    state = _build_forever_free_state("user_test", _mk_sub(plan_type="forever_free"))
    assert state.plan_type == "forever_free"
    assert state.is_active is True
    assert state.is_read_only is False
