"""Regression test for the hidden-certificate units-settings collection mismatch.

The old demo seeder wrote settings to ``trust_unit_settings`` (singular), while
trust-units code reads ``trust_units_settings`` (plural).  With four seeded
certificates consuming all 100 units, a missing settings document caused the
summary endpoint to silently create a fresh default and beneficiary entry to
fail as if the certificates were hidden.

This test uses a deterministic Motor-like fake so it does not touch production
MongoDB or require a running API server.  It reproduces the legacy singular
record, runs the data migration, and calls the real summary endpoint function.
"""

import asyncio
import copy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import trust_units  # noqa: E402
from scripts import migrate_trust_unit_settings  # noqa: E402


class _InsertResult:
    inserted_id = "fake-id"


class _FakeCursor:
    def __init__(self, documents):
        self._documents = documents

    def sort(self, key, direction):
        self._documents.sort(key=lambda document: document.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, length):
        return copy.deepcopy(self._documents[:length])

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._documents):
            raise StopAsyncIteration
        document = self._documents[self._index]
        self._index += 1
        return copy.deepcopy(document)


class _FakeCollection:
    def __init__(self):
        self.documents = []

    @staticmethod
    def _matches(document, query):
        return all(document.get(key) == value for key, value in query.items())

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if self._matches(document, query):
                result = copy.deepcopy(document)
                if projection:
                    for key, include in projection.items():
                        if include == 0:
                            result.pop(key, None)
                return result
        return None

    def find(self, query, projection=None):
        documents = [document for document in self.documents if self._matches(document, query)]
        if projection:
            projected = []
            for document in documents:
                result = copy.deepcopy(document)
                for key, include in projection.items():
                    if include == 0:
                        result.pop(key, None)
                projected.append(result)
            documents = projected
        return _FakeCursor(documents)

    async def insert_one(self, document):
        self.documents.append(copy.deepcopy(document))
        return _InsertResult()

    async def count_documents(self, query):
        return sum(self._matches(document, query) for document in self.documents)


class _FakeDB:
    def __init__(self):
        self.trusts = _FakeCollection()
        self.trust_unit_settings = _FakeCollection()  # legacy singular collection
        self.trust_units_settings = _FakeCollection()  # canonical plural collection
        self.trust_unit_certificates = _FakeCollection()


def test_hidden_certificates_use_migrated_units_settings(monkeypatch):
    """Four seeded certificates remain visible after singular→plural migration."""

    async def scenario():
        fake_db = _FakeDB()
        trust_id = "trust_hidden_certificate_regression"
        user_id = "user_hidden_certificate_regression"

        await fake_db.trusts.insert_one({"trust_id": trust_id, "user_id": user_id})

        # Exact legacy shape: demo settings exist only in the singular collection.
        await fake_db.trust_unit_settings.insert_one({
            "trust_id": trust_id,
            "user_id": user_id,
            "total_authorized_units": 100,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": "2020-01-15T00:00:00+00:00",
            "is_demo": True,
        })

        # Four demo certificates consume the entire authorized pool.
        for number, units in enumerate((25, 30, 15, 30), start=1):
            await fake_db.trust_unit_certificates.insert_one({
                "certificate_id": f"cert_hidden_{number}",
                "trust_id": trust_id,
                "user_id": user_id,
                "certificate_number": f"CU-{number:03d}",
                "holder_name": f"Beneficiary {number}",
                "holder_identifier": f"Demo beneficiary {number}",
                "holder_type": "individual",
                "units": units,
                "issue_date": "2020-01-15",
                "status": "active",
                "replaced_by_certificate_id": None,
                "notes": "Demo certificate",
                "created_at": "2020-01-15T00:00:00+00:00",
                "updated_at": None,
            })

        monkeypatch.setattr(trust_units, "db", fake_db)
        monkeypatch.setattr(migrate_trust_unit_settings, "db", fake_db)

        # Before migration, the app cannot see the legacy settings and creates a
        # fresh default in the plural collection.  This is the pre-fix path that
        # made the seeded certificates appear hidden to beneficiary entry.
        default_settings = await trust_units.get_or_create_units_settings(trust_id, user_id)
        assert default_settings["total_authorized_units"] == 100
        assert await fake_db.trust_units_settings.count_documents({"trust_id": trust_id}) == 1

        # Remove that accidental default to model a clean deployment before the
        # migration runs, then migrate the singular record to the canonical one.
        fake_db.trust_units_settings.documents.clear()
        result = await migrate_trust_unit_settings.migrate_trust_unit_settings()
        assert result["moved"] == 1
        assert result["after_plural"] == 1

        summary = await trust_units.get_trust_units_summary(
            trust_id=trust_id,
            user={"user_id": user_id},
        )

        assert summary.settings.total_authorized_units == 100
        assert summary.total_issued_units == 100
        assert summary.remaining_units == 0
        assert summary.active_certificate_count == 4
        assert len(summary.certificates) == 4
        assert sum(c.units for c in summary.certificates) == 100
        assert all(c.percentage > 0 for c in summary.certificates)

    asyncio.run(scenario())

