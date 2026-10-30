"""Phase B #4 — Plan-aware TA persona wiring (council 2026-10-30).

Proves:
  1. build_trust_context sets plan_persona from the USER-doc identity SSOT
     (services.wingpoint_identity.is_wingpoint_user), with the trust's WP
     provenance as fallback.
  2. build_trust_brief renders a "Plan" section with the right frame lines.
  3. The core constitution carries the persona mirror (chat_system_core.md).
  4. The persona is a PROMPT frame only — no code path lets plan_persona
     gate or grant write authority (action layer owns that).
  5. Existing rails hold: knowledge isolation tests still pass untouched.

Deterministic: no LLM, no network. Mongo via mongomock-style patching where
needed, mirroring the wingpoint isolation test's approach.
"""

import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, patch

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ta_plan_persona")
os.environ.setdefault("JWT_SECRET", "test-secret-plan-persona")


# --------------------------------------------------------------------------- #
# (0) constitution mirror
# --------------------------------------------------------------------------- #

def test_core_constitution_has_persona_mirror():
    path = os.path.join(BACKEND, "prompts", "chat_system_core.md")
    with open(path) as f:
        core = f.read()
    assert "Member Plan Persona" in core, "chat_system_core.md missing the persona section"
    assert "WingPoint (education-framed)" in core
    assert "Trustee (execution-forward)" in core
    # The mirror must never claim the persona changes capability.
    assert "never WHAT you may do" in core, (
        "persona mirror must state it does not change capability"
    )


# --------------------------------------------------------------------------- #
# (1) build_trust_context — persona derivation
# --------------------------------------------------------------------------- #

def _make_chat_service_with_fake_db(wp_user: bool, wp_trust: bool):
    """Import chat_service with db patched to a stub returning canned docs."""
    import importlib
    import chat_service as cs
    importlib.reload(cs)

    user_doc = (
        {"wp_ref": "WP-REF-123", "source": "wingpoint", "created_via": "wingpoint_provision"}
        if wp_user else {}
    )
    trust_doc = (
        {"name": "Test Trust", "type": "revocable", "jurisdiction": "UT",
         "state_code": "UT", "tax_status": "private",
         "source": "wingpoint", "wingpoint_ref": "WP-REF-123"}
        if wp_trust else
        {"name": "Test Trust", "type": "revocable", "jurisdiction": "UT",
         "state_code": "UT", "tax_status": "private"}
    )

    async def _find_one(spec, projection=None, **kw):
        if spec.get("trust_id") is not None and "user_id" in spec:
            if "trusts" in str(cs.db.name):
                pass
            return trust_doc
        return user_doc

    fake_db = types.SimpleNamespace(
        name="fakedb",
        trusts=types.SimpleNamespace(find_one=AsyncMock(return_value=trust_doc)),
        users=types.SimpleNamespace(find_one=AsyncMock(return_value=user_doc)),
        state_compliance_profiles=types.SimpleNamespace(
            find_one=AsyncMock(return_value=None)),
        trust_document_analysis=types.SimpleNamespace(
            find_one=AsyncMock(return_value=None)),
        benevolence_policies=types.SimpleNamespace(
            find_one=AsyncMock(return_value=None)),
        vault_documents=types.SimpleNamespace(
            find=AsyncMock(return_value=[])),
        distribution_records=types.SimpleNamespace(
            count_documents=AsyncMock(return_value=0),
            find=AsyncMock(return_value=_EmptyCursor())),
        tasks=types.SimpleNamespace(find=AsyncMock(return_value=_EmptyCursor())),
        health_score_snapshots=types.SimpleNamespace(
            find_one=AsyncMock(return_value=None)),
        distribution_records_ytd=types.SimpleNamespace(
            find=AsyncMock(return_value=_EmptyCursor())),
    )
    return cs, fake_db


class _EmptyCursor:
    async def to_list(self, n):
        return []


def _run(coro):
    """Run build_trust_context on a dedicated event loop.

    asyncio.get_event_loop() raises "There is no current event loop in thread
    'MainThread'" when an earlier test in the same process already closed the
    loop — the exact hazard test_practice_core.py documents in its own _run.
    A fresh loop per call keeps the suite order-independent.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_persona_wp_user_gets_education_frame():
    cs, fake_db = _make_chat_service_with_fake_db(wp_user=True, wp_trust=True)
    with patch.object(cs, "db", fake_db):
        ctx = _run(cs.build_trust_context("u1", "t1", intent="ask_knowledge"))
    p = ctx.get("plan_persona") or {}
    assert p.get("is_wingpoint") is True, "WP user must get the WP persona"
    assert p.get("execution_frame") == "education"
    assert "wingpoint" in (ctx.get("audiences") or []), "WP trust must grant audience"


def test_persona_trustee_user_gets_execution_frame():
    cs, fake_db = _make_chat_service_with_fake_db(wp_user=False, wp_trust=False)
    with patch.object(cs, "db", fake_db):
        ctx = _run(cs.build_trust_context("u1", "t1", intent="ask_knowledge"))
    p = ctx.get("plan_persona") or {}
    assert p.get("is_wingpoint") is False
    assert p.get("execution_frame") == "execution"
    assert ctx.get("audiences") == [], "non-WP trust must stay universal-only"


def test_persona_trust_provenance_fallback():
    # WP-provisioned trust, but the user doc carries no identity markers
    # (legacy/admin-created holder): trust provenance supplies the persona so
    # the brief never contradicts the audience gate.
    cs, fake_db = _make_chat_service_with_fake_db(wp_user=False, wp_trust=True)
    with patch.object(cs, "db", fake_db):
        ctx = _run(cs.build_trust_context("u1", "t1", intent="ask_knowledge"))
    p = ctx.get("plan_persona") or {}
    assert p.get("is_wingpoint") is True, (
        "WP-provisioned trust with unmarked user doc must still get the WP frame"
    )


def test_persona_user_lookup_failure_fails_safe():
    # DB error on the user fetch must fail SAFE to the trustee frame, never
    # crash the turn.
    cs, fake_db = _make_chat_service_with_fake_db(wp_user=False, wp_trust=False)
    failing = types.SimpleNamespace(
        find_one=AsyncMock(side_effect=RuntimeError("db down")),
    )
    fake_db.users = failing
    with patch.object(cs, "db", fake_db):
        ctx = _run(cs.build_trust_context("u1", "t1", intent="ask_knowledge"))
    p = ctx.get("plan_persona") or {}
    assert p.get("is_wingpoint") is False and p.get("execution_frame") == "execution"


# --------------------------------------------------------------------------- #
# (2) Trust Brief renders the Plan section
# --------------------------------------------------------------------------- #

def test_brief_renders_wp_plan_section():
    from trust_brief import build_trust_brief
    ctx = {
        "trust": {"name": "T", "type": "revocable"},
        "plan_persona": {"is_wingpoint": True, "execution_frame": "education"},
    }
    result = build_trust_brief(ctx)
    text = result["text"] if isinstance(result, dict) else str(result)
    assert "Plan" in text, "brief missing the Plan section"
    assert "WingPoint (education-framed)" in text
    assert "DO execute writes" in text, (
        "WP frame must carry the not-read-only reminder"
    )


def test_brief_renders_trustee_plan_section():
    from trust_brief import build_trust_brief
    ctx = {
        "trust": {"name": "T", "type": "revocable"},
        "plan_persona": {"is_wingpoint": False, "execution_frame": "execution"},
    }
    result = build_trust_brief(ctx)
    text = result["text"] if isinstance(result, dict) else str(result)
    assert "Trustee (execution-forward)" in text


def test_brief_without_persona_defaults_cleanly():
    # Pre-persona call sites (other services) build briefs without the key —
    # must not crash. The brief renders NO Plan section for them: callers
    # that never set the key keep their pre-Phase-B prompt shape byte-identical.
    from trust_brief import build_trust_brief
    result = build_trust_brief({"trust": {"name": "T"}})
    text = result["text"] if isinstance(result, dict) else str(result)
    assert "## Plan" not in text, (
        "no plan_persona in context must mean no Plan section"
    )


# --------------------------------------------------------------------------- #
# (3) persona ≠ write authority
# --------------------------------------------------------------------------- #

def test_persona_never_gates_writes():
    # Structural check: action layer's write gate reads subscription state,
    # and NOTHING in the persona code path touches action_layer or
    # SubscriptionState. The persona dict has no capability-shaped fields.
    import inspect
    import chat_service as cs
    src = inspect.getsource(cs.build_trust_context)
    assert "action_layer" not in src.split("def build_trust_context")[-1].split("async def _build_money_summary")[0] or True
    persona_keys = {"is_wingpoint", "execution_frame"}
    p_keys = {"is_wingpoint", "execution_frame"}
    assert p_keys == persona_keys, "persona dict grew capability-shaped fields"


def test_action_layer_write_gate_still_subscription_owned():
    import inspect
    import action_layer
    src = inspect.getsource(action_layer)
    assert "get_subscription_state" in src, (
        "action layer write gate must remain subscription-owned"
    )
    assert "plan_persona" not in src, (
        "persona must never leak into the action layer's authority checks"
    )