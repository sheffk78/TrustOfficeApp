"""WingPoint doctrine (Jeff 2026-10-16): provisioned/linked WingPoint trusts get
benevolence_enabled=True + tax_status='508' set at creation time.

RUNTIME NOTE: tests 1-2 need the backend venv (fastapi/pyotp/postmarker present
in prod/venv, not on the workstation). Test 3 runs everywhere — the tax math
module has no heavy deps. Verification evidence (workstation, 2026-10-16):
- AST: both _build_trust_doc + _build_link_trust_doc carry the two doctrine fields; py_compile OK.
- Direct run: is_tax_exempt({benevolence_enabled:True, tax_status:'508'}) is True;
  _generate_entries(trust, 2027) == [] — provisioned WingPoint trusts generate
  a ZERO-entry tax calendar.
"""
import sys
import importlib
import pytest
from types import SimpleNamespace

sys.path.insert(0, ".")

try:
    external = importlib.import_module("routers.external")
    _BACKEND_DEPS = True
except Exception:  # workstation lacks fastapi/pyotp/postmarker — calendar test still runs
    _BACKEND_DEPS = False

pytestmark_venv = pytest.mark.skipif(not _BACKEND_DEPS, reason="backend venv deps not installed locally")


def _req(cls, **over):
    base = dict(
        trustoffice_user_id="u1",
        wingpoint_ref="wp_ref_1",
        email=None,
        trust_name="Kohler Family Trust",
        jurisdiction="TX",
    )
    base.update(over)
    return cls(**base)


@pytestmark_venv
def test_provision_trust_doc_carries_doctrine():
    req = _req(
        external.WingPointProvisionRequest,
        email="cust@example.com",
        grantor_first_name="Ann",
        grantor_last_name="Lee",
    )
    doc = external._build_trust_doc(req, "u1", "family", "Ann Lee", "trust_abc", SimpleNamespace(isoformat=lambda: "now"))
    assert doc["benevolence_enabled"] is True
    assert doc["tax_status"] == "508"


@pytestmark_venv
def test_link_trust_doc_carries_doctrine():
    req = _req(external.LinkTrustRequest)
    doc = external._build_link_trust_doc(req, "u1", "family", "Ann Lee", "trust_abc", SimpleNamespace(isoformat=lambda: "now"))
    assert doc["benevolence_enabled"] is True
    assert doc["tax_status"] == "508"


def test_generated_tax_calendar_is_exempt():
    # Runs even without the backend venv (tax_calendar_math has no heavy deps).
    from utils.tax_calendar_math import _generate_entries, is_tax_exempt
    trust = {"trust_id": "t", "benevolence_enabled": True, "tax_status": "508"}
    assert is_tax_exempt(trust) is True
    assert _generate_entries(trust, 2027) == []