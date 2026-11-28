"""Regression: legacy entity docs missing later-added fields must not 500
GET /api/entities (production ValidationError: manager_names Field required,
fingerprint b2b50917, 2026-11-27)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



def test_entity_response_accepts_legacy_doc():
    from models import EntityResponse

    legacy = {
        "entity_id": "entity_legacy1",
        "trust_id": "trust_1",
        "name": "Family Trust",
        "entity_type": "Trust",
        "created_at": "2026-01-01T00:00:00+00:00",
        "ein_provision_note": "CP 575 letter proves EIN exists.",
    }
    out = EntityResponse.model_validate(legacy)
    assert out.manager_names == ""
    assert out.oversight_required is False


def test_entity_response_helper_backfills_none_fields():
    from routers.entities import _entity_response

    doc = {
        "entity_id": "entity_legacy2",
        "trust_id": "trust_1",
        "name": "Legacy LLC",
        "entity_type": "LLC",
        "created_at": "2026-01-01T00:00:00+00:00",
        "manager_names": None,
    }
    out = _entity_response(doc)
    assert out.manager_names == ""
    assert out.legal_name == ""

