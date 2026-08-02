"""Regression coverage for the external provision idempotency index."""

from pathlib import Path


SERVER = Path(__file__).parents[1] / "server.py"


def test_idem_key_index_ignores_legacy_null_values():
    source = SERVER.read_text()

    assert 'name="idem_key_1"' in source
    assert 'unique=True' in source
    assert 'partialFilterExpression={"idem_key": {"$type": "string"}}' in source


def test_idem_key_index_is_not_plain_unique_index():
    source = SERVER.read_text()

    assert 'create_index("idem_key", unique=True)' not in source
