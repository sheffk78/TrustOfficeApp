"""
Shared Action Layer for TrustOffice.

Pattern grafted from BuilderIO/agent-native (research report:
Kit/life/brands/TrustOffice/reports/agent-native-deepdive-2026-09-21.md),
adapted to the existing FastAPI + MongoDB stack. One capability, many
surfaces: the same run() function serves the Trust Assistant (chat), the
React dashboard (HTTP), and any future surface (CLI / MCP) without the
chat path and the UI path duplicating business logic.

An action is a plain dict registered in ACTIONS via the @action decorator:

    @action(
        name="generate-minutes",
        description="Create a draft minutes record for a trust meeting.",
        write=True,
        fields=[F("minutes_type", "string", required=True), ...],
    )
    async def generate_minutes(params: dict, ctx: ActionContext) -> dict:
        ...

Design rules (mirroring agent-native's contract):
- The run() function is the single source of truth. The chat agent calls
  call_action() in-process; the UI calls POST /api/actions/{name}; both
  land on the same run() with the same validation.
- Trust scoping is enforced in ONE place: call_action injects ctx and
  verifies the caller owns trust_id (or trust_id is None → active trust).
- Write actions respect the subscription write gate; read actions never
  require it.
- Schemas are declarative field specs (mirrors ACTION_REGISTRY fields) and
  are convertible to JSON Schema for LLM tool definitions later.
- Every call is audit-logged to audit_logs (action "action_call").
"""

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ==================== FIELD SPEC ====================

_FIELD_TYPES = ("string", "number", "boolean", "list", "dict", "any")


class F:
    """Declarative field spec (mirror of ACTION_REGISTRY's field dicts)."""

    __slots__ = ("name", "type", "required", "default", "description", "enum", "max_length")

    def __init__(
        self,
        name: str,
        type_: str = "string",
        required: bool = False,
        default: Any = None,
        description: str = "",
        enum: Optional[List[str]] = None,
        max_length: Optional[int] = None,
    ):
        if type_ not in _FIELD_TYPES:
            raise ValueError(f"Invalid field type '{type_}' for field '{name}' (allowed: {_FIELD_TYPES})")
        self.name = name
        self.type = type_
        self.required = required
        self.default = default
        self.description = description
        self.enum = enum
        self.max_length = max_length

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }
        if self.enum is not None:
            d["enum"] = self.enum
        if self.max_length is not None:
            d["max_length"] = self.max_length
        return d


# ==================== VALIDATION ====================

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def _validate_type(value: Any, type_: str, field_name: str) -> Any:
    """Coerce + type-check one field. Returns the coerced value."""
    if value is None:
        return None
    if type_ == "string":
        if not isinstance(value, str):
            raise TypeError(f"Field '{field_name}' must be a string")
        return value
    if type_ == "number":
        if isinstance(value, bool):
            raise TypeError(f"Field '{field_name}' must be a number")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value) if "." in value or "e" in value.lower() else int(value)
            except ValueError:
                raise TypeError(f"Field '{field_name}' must be a number")
        raise TypeError(f"Field '{field_name}' must be a number")
    if type_ == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
        raise TypeError(f"Field '{field_name}' must be a boolean")
    if type_ == "list":
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        raise TypeError(f"Field '{field_name}' must be a list")
    if type_ == "dict":
        if isinstance(value, dict):
            return value
        raise TypeError(f"Field '{field_name}' must be an object")
    return value  # "any"


def validate_params(action: "Action", params: dict) -> dict:
    """
    Validate + coerce incoming params against the action's field specs.

    - Unknown keys are REJECTED (prevents parameter-injection through the
      HTTP surface and makes agent tool schemas trustworthy).
    - Required fields must be present and non-empty.
    - enum fields must match; max_length enforced for strings.
    Returns the coerced params dict (defaults filled in).
    """
    if not isinstance(params, dict):
        raise ActionError("action_params_invalid", "Params must be an object")

    out: dict = {}
    known = {f.name: f for f in action.fields}

    for key, value in params.items():
        if key not in known:
            raise ActionError(
                "action_params_invalid",
                f"Unknown field '{key}' for action '{action.name}'",
            )
        f = known[key]
        if value is None:
            if f.required:
                raise ActionError("action_params_invalid", f"Field '{f.name}' is required")
            continue
        coerced = _validate_type(value, f.type, f.name)
        if f.type == "string":
            if f.max_length is not None and len(coerced) > f.max_length:
                raise ActionError(
                    "action_params_invalid",
                    f"Field '{f.name}' exceeds max length {f.max_length}",
                )
            if f.enum and coerced not in f.enum:
                raise ActionError(
                    "action_params_invalid",
                    f"Field '{f.name}' must be one of: {', '.join(f.enum)}",
                )
        elif f.type == "list" and f.enum:
            for item in coerced:
                if not isinstance(item, str) or item not in f.enum:
                    raise ActionError(
                        "action_params_invalid",
                        f"Field '{f.name}' items must be from: {', '.join(f.enum)}",
                    )
        out[key] = coerced

    for f in action.fields:
        if f.name in out:
            continue
        if f.required:
            raise ActionError("action_params_invalid", f"Field '{f.name}' is required")
        if f.default is not None:
            out[f.name] = f.default
    return out


def to_json_schema(action: "Action") -> dict:
    """Convert an action's fields to a JSON-Schema tool definition (LLM-ready)."""
    props: dict = {}
    required: List[str] = []
    for f in action.fields:
        t = {"string": "string", "number": "number", "boolean": "boolean", "any": "object"}[f.type]
        if f.type == "list":
            t = "array"
        elif f.type == "dict":
            t = "object"
        spec: dict = {"type": t, "description": f.description or f.name.replace("_", " ")}
        if f.type == "array":
            spec["items"] = {"type": "string"}
        if f.enum:
            spec["enum"] = f.enum
        if f.max_length:
            spec["maxLength"] = f.max_length
        props[f.name] = spec
        if f.required:
            required.append(f.name)
    return {"type": "function", "function": {"name": action.name, "description": action.description, "parameters": {"type": "object", "properties": props, "required": required}}}


class ActionError(Exception):
    """Typed error carrying a machine code + human detail (HTTP 400)."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class ActionContext:
    """Injected into every run(): who is calling, on which trust."""

    __slots__ = ("user_id", "trust_id", "user", "surface")

    def __init__(self, user_id: str, trust_id: Optional[str], user: dict, surface: str):
        self.user_id = user_id
        self.trust_id = trust_id
        self.user = user or {}
        self.surface = surface  # "chat" | "ui" | "system"

    def __repr__(self):
        return f"ActionContext(user_id={self.user_id!r}, trust_id={self.trust_id!r}, surface={self.surface!r})"


@dataclass
class Action:
    name: str
    description: str
    handler: Callable[[dict, ActionContext], Awaitable[dict]]
    fields: List[F] = field(default_factory=list)
    write: bool = False
    trust_scoped: bool = True
    surfaces: tuple = ("ui", "chat")

    def to_manifest(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "write": self.write,
            "trust_scoped": self.trust_scoped,
            "fields": [f.to_dict() for f in self.fields],
            "surfaces": list(self.surfaces),
        }


# ==================== REGISTRY ====================

ACTIONS: Dict[str, Action] = {}


def action(
    name: str,
    description: str,
    write: bool = False,
    trust_scoped: bool = True,
    fields: Optional[List[F]] = None,
    surfaces: tuple = ("ui", "chat"),
) -> Callable:
    """Register an action. Handler signature: async (params, ctx) -> dict."""

    def deco(fn):
        if not _NAME_RE.match(name):
            raise ValueError(f"Invalid action name '{name}' (must match {_NAME_RE.pattern})")
        if name in ACTIONS:
            raise ValueError(f"Duplicate action name '{name}'")
        ACTIONS[name] = Action(
            name=name,
            description=description,
            handler=fn,
            fields=list(fields or []),
            write=write,
            trust_scoped=trust_scoped,
            surfaces=tuple(surfaces) or ("ui", "chat"),
        )
        return fn

    return deco


def get_action(name: str) -> Optional[Action]:
    return ACTIONS.get(name)


def list_actions() -> List[dict]:
    return [a.to_manifest() for a in ACTIONS.values()]


def to_llm_tools() -> List[dict]:
    """All actions as OpenAI-style tool definitions (for the Trust Assistant)."""
    return [to_json_schema(a) for a in ACTIONS.values()]


# ==================== EXECUTION ====================

async def call_action(
    name: str,
    params: dict,
    user_id: str,
    trust_id: Optional[str],
    user: Optional[dict] = None,
    surface: str = "ui",
    allow_unsafe: bool = False,
) -> dict:
    """
    The ONE entry point every surface uses.

    Order of operations:
      1. registry lookup          → 404 shape if unknown
      2. schema validation        → 400 shape on bad params
      3. trust ownership check    → 403 shape if the caller doesn't own it
      4. write gate (subscription read-only) → 403 shape for read-only plans
      5. handler execution        → 500 shape on unexpected exceptions
      6. audit log + timing
    Returns a uniform envelope: {ok, action, duration_ms, result|error}.
    Handler dicts may include {"ok": False, "error": ...} to soft-fail.
    """
    from database import db
    from utils.audit import log_audit_event

    started = time.monotonic()
    act = get_action(name)
    if act is None:
        return {"ok": False, "action": name, "error": {"code": "action_not_found", "detail": f"No action named '{name}'"}, "duration_ms": 0}

    if surface not in act.surfaces:
        return {
            "ok": False,
            "action": name,
            "error": {"code": "action_forbidden", "detail": f"Action '{name}' is not available on surface '{surface}'"},
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }

    try:
        params = validate_params(act, params or {})
    except ActionError as e:
        return {
            "ok": False,
            "action": name,
            "error": {"code": e.code, "detail": e.detail},
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }

    # Trust ownership: trust_id required for trust-scoped actions, and must
    # belong to the caller. Trust-agnostic actions skip this check.
    if act.trust_scoped:
        if not trust_id:
            return {"ok": False, "action": name, "error": {"code": "action_forbidden", "detail": "trust_id is required for this action"}, "duration_ms": round((time.monotonic() - started) * 1000, 1)}
        owner = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 1}
        )
        if not owner:
            return {
                "ok": False,
                "action": name,
                "error": {"code": "action_forbidden", "detail": "Trust not found for this user"},
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }

    # Write gate: read-only subscription plans cannot execute write actions.
    # The layer owns this check (not the HTTP router) so every surface —
    # chat, UI, future MCP/CLI — gets the same protection.
    if act.write:
        from dependencies import get_subscription_state

        sub_state = await get_subscription_state(user_id)
        if sub_state.is_read_only:
            return {
                "ok": False,
                "action": name,
                "error": {"code": "action_forbidden", "detail": "Read-only mode: your subscription does not allow write actions."},
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }

    ctx = ActionContext(
        user_id=user_id,
        trust_id=trust_id,
        user=(user if user is not None else {}),
        surface=surface,
    )
    try:
        result = await act.handler(params, ctx)
        result = result if isinstance(result, dict) else {"data": result}
    except ActionError as e:
        result = {"ok": False, "error": e.detail}
    except Exception as e:  # noqa: BLE001 — the layer owns error normalization
        logger.exception(f"Action '{name}' handler error")
        result = {"ok": False, "error": f"Internal error: {type(e).__name__}"}

    if not isinstance(result, dict):
        result = {"data": result}

    # Handler may return {"ok": False, "error": ...} → soft failure, still 200
    ok = bool(result.get("ok", True))
    if ok is False and "error" not in result:
        result["error"] = "Unknown error"

    duration_ms = round((time.monotonic() - started) * 1000, 1)

    # Audit log every call (best-effort — never blocks the response).
    try:
        details: dict = {
            "action": name,
            "surface": surface,
            "trust_id": trust_id,
            "ok": ok,
            "params": _redact_params(act, params),
        }
        if act.write:
            details["write"] = True
        await log_audit_event(user_id, "action_call", "action", name, details)
    except Exception:
        logger.warning(f"Audit log failed for action '{name}'", exc_info=True)

    return {
        "ok": ok,
        "action": name,
        "duration_ms": duration_ms,
        "result": {k: v for k, v in result.items() if k != "ok"},
    }


def _redact_params(act: Action, params: dict) -> dict:
    """Best-effort scrub of sensitive-looking params before audit logging."""
    scrubbed = {}
    for k, v in (params or {}).items():
        low = k.lower()
        if any(s in low for s in ("password", "secret", "token", "ssn", "account_number")):
            scrubbed[k] = "[redacted]"
        else:
            scrubbed[k] = v
    return scrubbed


# Seed actions are imported for their registration side effect. Modules may
# also register actions themselves via actions_seed.register_actions().
def register_all() -> int:
    """Import the seed modules so their @action decorators run. Returns count."""
    import actions_seed  # noqa: F401  (registers the 5 seed actions)

    return len(ACTIONS)