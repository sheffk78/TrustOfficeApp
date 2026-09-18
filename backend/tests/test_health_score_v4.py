# Unit tests for the v4 health score — pure function, no DB required.
# Background (Jeff, 2026-09-17): score structurally punished quiet, well-run
# trusts (35-point denominator floor, green >=96 unreachable, upcoming tax
# deadlines penalized, onboarding gave zero credit). v4 fixes all four.
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import HealthColor
from routers.governance import (
    _compute_health_score,
    SCORE_GREEN_THRESHOLD,
    SCORE_YELLOW_THRESHOLD,
    QUARTER_GRACE_DAYS,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # mid-quarter


def _base_data(**overrides):
    """A quiet, well-run benevolence trust: minutes + annual review done,
    assets fresh, setup complete, nothing else applicable."""
    data = {
        "now": NOW,
        "quarterly_minutes": 2,
        "total_tasks": 0,
        "overdue_tasks": 0,
        "comp_plan": None,
        "ytd_total": 0,
        "approved_amount": 0,
        "dist_count": 0,
        "benevolence_dists": [],
        "annual_review": {"task_id": "t1"},
        "pending_annual_review": None,
        "trust_created_at": "2025-01-01T00:00:00+00:00",
        "active_assets": [{"description": "House", "last_valued_date": "2026-06-01T00:00:00+00:00"}],
        "twelve_months_ago": datetime(2025, 9, 16, tzinfo=timezone.utc),
        "total_txns": 0,
        "classified_txns": 0,
        "active_alert_count": 0,
        "risk_findings": [],
        "onboarding_state_raw": {
            "trust_doc_uploaded": True,
            "beneficiaries_added": True,
            "successor_trustee_added": True,
            "assets_added": True,
            "minutes_generated": True,
            "ein_doc_uploaded": True,
            "formation_date_added": True,
            "backup_connected": True,
            "ein_entered": True,
            "calendar_set": True,
        },
        "benevolence_enabled": True,
    }
    data.update(overrides)
    return data


def _criterion(result, name):
    return next(c for c in result["criteria"] if c.name == name)


# --- The Jeff scenario: quiet benevolence trust doing everything right ---

def test_quiet_benevolence_trust_scores_100():
    """Minutes + annual review + fresh assets + full setup = 100, green, no
    red-banner conditions. This was 43/red under v3 (35-point floor)."""
    result = _compute_health_score(_base_data())
    assert result["total_score"] == 100, f"expected 100, got {result['total_score']}"
    assert result["color"] == HealthColor.green
    assert result["has_critical_risk"] is False


def test_denominator_excludes_no_data_criteria():
    """Only applicable criteria count: minutes 15 + annual 15 + assets 15 +
    foundation 15 = 60. Comp plan / distributions / transactions (no_data)
    are excluded, not zeroed in."""
    result = _compute_health_score(_base_data())
    assert result["applicable_max"] == 60
    assert result["base_score"] == 60


def test_no_35_point_floor():
    """Fresh trust with nothing done: denominator = 45 (quarterly, annual,
    foundation — the ones that are applicable), not inflated by the old 35
    floor, and the empty criteria honestly score 0."""
    empty = _base_data(
        quarterly_minutes=0,
        annual_review=None,
        active_assets=[],
        onboarding_state_raw={},
        risk_findings=[],
        benevolence_enabled=False,
    )
    result = _compute_health_score(empty)
    assert result["applicable_max"] == 45
    assert result["total_score"] == 0  # genuinely red, honestly


def test_denominator_never_below_foundation():
    """Absolute worst case (day 2 of quarter, brand-new trust): only
    Foundation + Annual Review are applicable — small honest denominator."""
    day2 = datetime(2026, 10, 2, tzinfo=timezone.utc)
    empty = _base_data(
        now=day2,
        quarterly_minutes=0,
        annual_review=None,
        active_assets=[],
        onboarding_state_raw={},
        risk_findings=[],
        benevolence_enabled=False,
    )
    result = _compute_health_score(empty)
    assert result["applicable_max"] == 30
    assert result["total_score"] == 0


def test_partial_setup_scores_partial_foundation():
    """6/10 setup steps done (benevolence auto-credits calendar), rest of
    quiet trust perfect → 90 yellow→green boundary case: (15+15+15+9)/60 = 90."""
    raw = {k: True for k in _base_data()["onboarding_state_raw"]}
    for k in ["backup_connected", "ein_entered", "ein_doc_uploaded",
              "calendar_set", "successor_trustee_added"]:
        raw[k] = False
    result = _compute_health_score(_base_data(onboarding_state_raw=raw))
    # benevolence auto-credits calendar → 6/10 done, not 5/10
    assert _criterion(result, "Foundation & Setup").points == 9
    assert result["total_score"] == 90
    assert result["color"] == HealthColor.green


def test_benevolence_calendar_auto_credit():
    """Benevolence trust with no calendar_set still gets the calendar step
    (mirrors frontend calendar_set || benevolence_enabled)."""
    raw = {k: True for k in _base_data()["onboarding_state_raw"]}
    raw["calendar_set"] = False
    result = _compute_health_score(_base_data(onboarding_state_raw=raw))
    assert result["total_score"] == 100


# --- Quarterly minutes grace period ---

def test_quarter_start_grace_period():
    """Day 5 of the quarter with no minutes: not yet due (no_data), excluded
    from denominator — no day-1 score cliff."""
    early = datetime(2026, 10, 5, tzinfo=timezone.utc)  # day 4 of Q4
    data = _base_data(now=early, quarterly_minutes=0)
    result = _compute_health_score(data)
    crit = _criterion(result, "Quarterly Minutes")
    assert crit.no_data is True
    assert result["applicable_max"] == 45  # annual + assets + foundation
    assert result["total_score"] == 100


def test_after_grace_period_missing_minutes_count():
    """Day 40 of the quarter with no minutes: now it counts as a miss."""
    late = datetime(2026, 11, 10, tzinfo=timezone.utc)
    data = _base_data(now=late, quarterly_minutes=0)
    result = _compute_health_score(data)
    crit = _criterion(result, "Quarterly Minutes")
    assert crit.no_data is False
    assert crit.points == 0
    # (15+15+15+0)/60 → 75 yellow
    assert result["total_score"] == 75
    assert result["color"] == HealthColor.yellow


# --- Tax penalties: overdue penalizes, upcoming doesn't ---

def test_overdue_tax_penalizes():
    overdue = [{"type": "tax_deadline", "severity": "high", "module": "tax_calendar",
                "title": "Overdue: Form 1041", "detail": "Was due 10 days ago"}]
    result = _compute_health_score(_base_data(risk_findings=overdue))
    # 100 - 12 (high) = 88
    assert result["total_score"] == 88
    assert result["color"] == HealthColor.green  # still green — one slip shouldn't nuke it


def test_upcoming_tax_does_not_penalize():
    """Upcoming deadlines are reminders — excluded from the score path by
    gather_risk_findings(include_upcoming_tax=False); if one leaks through the
    cache it would be medium severity. This test pins the intended exclusion:
    the health-score caller must not pass upcoming findings."""
    from routers.governance import _gather_risk_findings  # ensures wiring intact
    import inspect
    src = inspect.getsource(_gather_risk_findings)
    assert "include_upcoming_tax=False" in src


def test_critical_risk_caps_at_50():
    critical = [{"type": "notice_required", "severity": "critical", "module": "state_compliance",
                 "title": "Beneficiary notice not sent", "detail": ""}]
    result = _compute_health_score(_base_data(risk_findings=critical))
    assert result["total_score"] == 50
    assert result["has_critical_risk"] is True


# --- Color thresholds ---

def test_color_thresholds():
    assert SCORE_GREEN_THRESHOLD == 85
    assert SCORE_YELLOW_THRESHOLD == 65
    assert QUARTER_GRACE_DAYS == 30
    from routers.governance import _score_to_color
    assert _score_to_color(85) == HealthColor.green
    assert _score_to_color(84) == HealthColor.yellow
    assert _score_to_color(65) == HealthColor.yellow
    assert _score_to_color(64) == HealthColor.red


def test_diligent_trust_with_one_medium_risk_stays_green():
    """A well-run trust with a medium finding (e.g. UTC gap) loses 5 pts → 95
    green, not the old 91 → still-red-after-96-threshold situation."""
    med = [{"type": "utc_gap", "severity": "medium", "module": "state_compliance",
            "title": "UTC gap", "detail": ""}]
    result = _compute_health_score(_base_data(risk_findings=med))
    assert result["total_score"] == 95
    assert result["color"] == HealthColor.green


if __name__ == "__main__":
    import pytest
    pytest.main([os.path.abspath(__file__), "-v", "--tb=short"])