"""
Regression tests (2026-09-04):

BUG 1 — Demo trust leaked into real accounts' sidebar dropdown.
Justin Bartlett had 1 real trust but "Smith Family Trust" (demo) still showed
in the left-hand nav trust selector. Root causes:
  a) GET /trusts returned ALL trusts including is_demo: True ones.
  b) Trust-insert paths outside POST /trusts (external provisioning,
     admin API) never ran demo cleanup, so demo trusts coexisted with real
     ones indefinitely.

Fixes:
  a) GET /trusts excludes is_demo: True.
  b) Shared services/demo_cleanup.py is invoked on first real trust creation
     from every insert path (routers/trusts.py, routers/external.py x2,
     routers/admin_api.py) + admin purge endpoint
     POST /admin/users/{user_id}/purge-demo-data for existing accounts.

BUG 2 — Accept-Property minutes only documented the FIRST property.
Multi-property submissions (property_items) created one Schedule A item per
property (all linked to the same minutes record), but the generated minutes
document rendered only the first property via legacy single-item fields.

Fix: generate_property_acceptance_content renders one numbered resolution
block per property item.

Pure-unit tests (AST source assertions + direct execution of the extracted
generator function — no live server, no DB, no fastapi import), following
the pattern of test_checkout_first.py.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load(path):
    return ast.parse((BACKEND_DIR / path).read_text())


def _fn_src(tree, name, fallback_path="routers/trusts.py"):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment((BACKEND_DIR / fallback_path).read_text(), node) or ""
    return ""


# ---------------------------------------------------------------------------
# BUG 1a: GET /trusts must exclude demo trusts
# ---------------------------------------------------------------------------

class TestGetTrustsExcludesDemo:
    def test_list_query_filters_is_demo(self):
        src = (BACKEND_DIR / "routers/trusts.py").read_text()
        start = src.index('async def get_trusts(')
        end = src.index('@router.get("/trusts/{trust_id}"')
        body = src[start:end]
        # Demo trusts must be filtered out when the user has real trusts;
        # demo-only accounts (no real trust) keep seeing their demo trusts.
        assert 't.get("is_demo") is not True' in body, (
            "GET /trusts must filter out demo trusts once real trusts exist"
        )
        assert "real_trusts if real_trusts else all_trusts" in body, (
            "demo-only accounts must still see their demo trusts"
        )

    def test_docstring_documents_demo_exclusion(self):
        src = (BACKEND_DIR / "routers/trusts.py").read_text()
        start = src.index('async def get_trusts(')
        end = src.index('@router.get("/trusts/{trust_id}"')
        body = src[start:end]
        assert "demo" in body.lower()


# ---------------------------------------------------------------------------
# BUG 1b: shared demo cleanup service + wiring on every trust insert path
# ---------------------------------------------------------------------------

class TestSharedDemoCleanupService:
    def test_service_module_exists_with_purge_and_cleanup(self):
        svc = (BACKEND_DIR / "services/demo_cleanup.py").read_text()
        assert "async def purge_demo_data_for_user(" in svc
        assert "async def cleanup_demo_on_first_real_trust(" in svc
        assert "async def collect_demo_trust_ids(" in svc

    def test_service_preserves_user_onboarding(self):
        svc = (BACKEND_DIR / "services/demo_cleanup.py").read_text()
        assert "user_onboarding" in svc, (
            "purge must document that user_onboarding is deliberately not touched"
        )
        # The purge body must not delete from user_onboarding
        start = svc.index("async def purge_demo_data_for_user")
        body = svc[start:]
        assert 'db["user_onboarding"]' not in body and "db.user_onboarding" not in body

    def test_service_only_deletes_demo_flagged_or_orphaned(self):
        svc = (BACKEND_DIR / "services/demo_cleanup.py").read_text()
        start = svc.index("async def purge_demo_data_for_user")
        body = svc[start:svc.index("async def cleanup_demo_on_first_real_trust")]
        assert '{"user_id": user_id, "is_demo": True}' in body
        assert '{"trust_id": {"$in": demo_trust_ids}}' in body

    def test_trusts_router_delegates_to_service(self):
        src = (BACKEND_DIR / "routers/trusts.py").read_text()
        assert "cleanup_demo_on_first_real_trust" in src, (
            "trusts.py must delegate first-real-trust cleanup to the shared service"
        )
        # The old inline duplicate must be gone
        assert "_DEMO_CLEANUP_COLLECTIONS" not in src

    def test_external_provisioning_runs_cleanup(self):
        src = (BACKEND_DIR / "routers/external.py").read_text()
        assert src.count("cleanup_demo_on_first_real_trust") >= 2, (
            "Both WingPoint provisioning trust-insert paths must run demo cleanup"
        )

    def test_admin_api_trust_creation_runs_cleanup(self):
        src = (BACKEND_DIR / "routers/admin_api.py").read_text()
        assert "cleanup_demo_on_first_real_trust" in src

    def test_admin_purge_endpoint_exists(self):
        src = (BACKEND_DIR / "routers/admin_api.py").read_text()
        assert '@router.post("/users/{user_id}/purge-demo-data")' in src
        assert "purge_demo_data_for_user" in src

    def test_demo_delete_endpoint_delegates_to_service(self):
        src = (BACKEND_DIR / "routers/demo.py").read_text()
        assert "purge_demo_data_for_user" in src

    def test_seed_refuses_when_real_trusts_exist(self):
        src = (BACKEND_DIR / "routers/demo.py").read_text()
        start = src.index('async def seed_demo_data(')
        end = src.index("TRUST 1:")
        body = src[start:end]
        # Seeding must never mix demo data with real trusts
        assert '"is_demo": {"$ne": True}' in body, (
            "seed must count real (non-demo) trusts"
        )
        assert '"blocked_by_real_data": True' in body, (
            "seed must refuse with blocked_by_real_data when real trusts exist"
        )

    def test_trust_limit_count_excludes_demo_trusts(self):
        src = (BACKEND_DIR / "routers/trusts.py").read_text()
        start = src.index('async def create_trust(')
        end = src.index('async def get_trusts(')
        body = src[start:end]
        # Demo trusts must not consume plan trust limits
        assert body.count('"is_demo": {"$ne": True}') >= 1, (
            "existing_count for trust limits must exclude demo trusts"
        )


# ---------------------------------------------------------------------------
# BUG 2: acceptance-of-property minutes must render ALL properties
# ---------------------------------------------------------------------------

def _exec_generator():
    """Extract and execute generate_property_acceptance_content standalone."""
    from types import SimpleNamespace

    src = (BACKEND_DIR / "routers/minutes.py").read_text()
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "generate_property_acceptance_content":
            fn = node
            break
    assert fn is not None, "generate_property_acceptance_content must exist in routers/minutes.py"

    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {}
    exec(compile(module, "<extracted>", "exec"), namespace)
    return namespace["generate_property_acceptance_content"]


class TestPropertyAcceptanceMultiItem:
    def setup_method(self):
        self.gen = _exec_generator()

    def test_multi_item_renders_one_resolution_per_property(self):
        data = {
            "grantor_name": "Jane Grantor",
            "property_items": [
                {"grantor_name": "Jane Grantor", "property_description": "Parcel A — 10 acres, Utah",
                 "property_value": 50000, "conveyance_date": "September 1, 2026"},
                {"grantor_name": "Jane Grantor", "property_description": "Parcel B — cabin, Idaho",
                 "property_value": 120000, "conveyance_date": "September 1, 2026"},
                {"grantor_name": "Jane Grantor", "property_description": "John Deere tractor",
                 "property_value": 25000, "conveyance_date": "September 1, 2026"},
            ],
        }
        doc = self.gen(data)
        assert "Resolution 1:" in doc
        assert "Resolution 2:" in doc
        assert "Resolution 3:" in doc
        assert "Resolution 4:" not in doc
        assert "Parcel A" in doc and "Parcel B" in doc and "John Deere tractor" in doc
        assert doc.count("Acceptance of Additional Property into Trust") == 3

    def test_single_item_legacy_mode_unchanged(self):
        data = {
            "grantor_name": "Jane Grantor",
            "property_description": "Legacy single property",
            "property_value": 1000,
            "conveyance_date": "January 5, 2026",
        }
        doc = self.gen(data)
        assert "Resolution 1:" in doc
        assert "Resolution 2:" not in doc
        assert "Legacy single property" in doc
        assert "$1,000.00" in doc

    def test_each_block_has_required_resolution_language(self):
        data = {
            "property_items": [
                {"property_description": f"Property {i}", "property_value": i * 100}
                for i in range(1, 4)
            ],
        }
        doc = self.gen(data)
        # Core legal language must appear in every block
        assert doc.count("WHEREAS,") == 3
        assert doc.count("Schedule A to the Trust Indenture is hereby amended") == 3
        assert doc.count("Vote: Unanimous approval") == 3

    def test_empty_and_missing_values_render_blank_lines(self):
        data = {
            "property_items": [
                {"property_description": "No value given"},
            ],
        }
        doc = self.gen(data)
        assert "$______________" in doc

    def test_empty_property_items_falls_back_to_legacy(self):
        data = {
            "grantor_name": "Jane Grantor",
            "property_description": "Fallback property",
        }
        doc = self.gen(data)
        assert "Fallback property" in doc
        assert "Resolution 1:" in doc

    def test_non_dict_items_do_not_crash(self):
        data = {"property_items": ["not-a-dict", {"property_description": "Real one"}]}
        doc = self.gen(data)
        assert "Real one" in doc
        assert "Resolution 2:" in doc


# ---------------------------------------------------------------------------
# Multi-property → Schedule A linkage (static checks on the template flow)
# ---------------------------------------------------------------------------

class TestPropertyScheduleALinkage:
    def test_template_flow_creates_one_schedule_a_item_per_property(self):
        src = (BACKEND_DIR / "routers/minutes.py").read_text()
        start = src.index('async def create_minutes_from_template')
        body = src[start:]
        assert "for item in property_items:" in body, (
            "multi-item flow must create a Schedule A item per property"
        )
        assert '"minutes_ref": minutes_id' in body, (
            "every created Schedule A item must link back to the minutes record"
        )

    def test_frontend_builder_sends_full_items_array(self):
        src = (BACKEND_DIR.parent / "frontend/src/pages/minutesTemplateForm/templateDataBuilders.js").read_text()
        assert "property_items: items.map(" in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))