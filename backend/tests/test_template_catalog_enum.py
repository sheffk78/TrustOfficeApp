"""Regression: every catalog template must be a valid MinutesTemplateType.

Jeff hit an error page on Trust Minutes (2026-09-18): 'spending_authorization'
was in the template registry + generator since 2026-08-12 but missing from the
MinutesTemplateType enum → POST /minutes-templates returned 422 for it.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

import pytest

pytest.importorskip("fastapi")


def test_every_registry_template_is_valid_enum():
    from routers.template_registry import TEMPLATE_REGISTRY
    from models import MinutesTemplateType

    valid = {t.value for t in MinutesTemplateType}
    missing = [k for k in TEMPLATE_REGISTRY if k not in valid]
    assert not missing, f"registry types missing from MinutesTemplateType: {missing}"


def test_spending_authorization_accepted():
    from models import MinutesTemplateType
    assert MinutesTemplateType("spending_authorization") == "spending_authorization"