from mcp.server.fastmcp import Context
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
import json
import os
import re
from upstash_redis import Redis
from dotenv import load_dotenv

MAX_PRICING_CALLS = 10
RESET_WINDOW_HOURS = 24

load_dotenv()

def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Reutilizable en serverless mientras la función esté caliente
redis = Redis(
    url=_require_env("KV_REST_API_URL"),
    token=_require_env("KV_REST_API_TOKEN"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_subject(value: Any) -> Optional[str]:
    if value is None:
        return None

    value_str = str(value).strip()
    if not value_str:
        return None

    lowered = value_str.lower()
    if lowered in {"anonymous", "user:anonymous", "none", "null"}:
        return None

    return value_str


def _extract_subject_from_meta(meta: Any) -> Optional[str]:
    if meta is None:
        return None

    # 1) Dict / mapping
    if isinstance(meta, dict):
        for key in ("openai/subject", "openai_subject", "subject"):
            subject = _normalize_subject(meta.get(key))
            if subject:
                return subject

    get_method = getattr(meta, "get", None)
    if callable(get_method):
        for key in ("openai/subject", "openai_subject", "subject"):
            try:
                subject = _normalize_subject(get_method(key))
                if subject:
                    return subject
            except Exception:
                pass

    # 2) Pydantic o similar
    dump_method = getattr(meta, "model_dump", None)
    if callable(dump_method):
        try:
            dumped = dump_method()
            if isinstance(dumped, dict):
                for key in ("openai/subject", "openai_subject", "subject"):
                    subject = _normalize_subject(dumped.get(key))
                    if subject:
                        return subject
        except Exception:
            pass

    # 3) Atributos normales
    for attr_name in ("openai_subject", "subject"):
        if hasattr(meta, attr_name):
            try:
                subject = _normalize_subject(getattr(meta, attr_name))
                if subject:
                    return subject
            except Exception:
                pass

    # 4) Último recurso: repr(meta)
    meta_repr = repr(meta)
    patterns = (
        r"openai/subject='([^']+)'",
        r'openai/subject="([^"]+)"',
        r"openai_subject='([^']+)'",
        r'openai_subject="([^"]+)"',
        r"subject='([^']+)'",
        r'subject="([^"]+)"',
    )

    for pattern in patterns:
        match = re.search(pattern, meta_repr)
        if match:
            subject = _normalize_subject(match.group(1))
            if subject:
                return subject

    return None


def _extract_subject_from_ctx(ctx: Context) -> Optional[str]:
    request_context = getattr(ctx, "request_context", None)
    meta = getattr(request_context, "meta", None) if request_context else None

    if meta is None:
        print("[pricing_limit] no meta present in request_context")
        return None

    subject = _extract_subject_from_meta(meta)

    if subject:
        print(f"[pricing_limit] resolved openai subject={subject!r}")
        return subject

    print("[pricing_limit] could not resolve openai/subject from meta")
    return None


def resolve_user_key(ctx: Context) -> Optional[str]:
    subject = _extract_subject_from_ctx(ctx)
    if not subject:
        return None
    return f"user:{subject}"


def _redis_key_for_user(ctx: Context) -> Optional[str]:
    user_key = resolve_user_key(ctx)
    if user_key is None:
        return None
    return f"pricing_limit:{user_key}"


def _serialize_state(count: int, reset_at: datetime) -> str:
    return json.dumps(
        {
            "count": count,
            "reset_at": reset_at.isoformat(),
        }
    )


def _deserialize_state(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    if isinstance(raw, str):
        data = json.loads(raw)
    elif isinstance(raw, dict):
        data = raw
    else:
        return None

    return {
        "count": int(data["count"]),
        "reset_at": datetime.fromisoformat(data["reset_at"]),
    }


def _write_state(ctx: Context, count: int, reset_at: datetime) -> None:
    key = _redis_key_for_user(ctx)
    if key is None:
        print("[pricing_limit] no reliable subject, skipping redis write")
        return

    ttl_seconds = max(1, int((reset_at - utc_now()).total_seconds()))
    redis.set(key, _serialize_state(count, reset_at), ex=ttl_seconds)


def _get_or_create_user_limit_state(ctx: Context) -> Optional[Dict[str, Any]]:
    key = _redis_key_for_user(ctx)
    now = utc_now()

    if key is None:
        print("[pricing_limit] no reliable subject, skipping limit state creation")
        return None

    state = _deserialize_state(redis.get(key))

    if state is None:
        reset_at = now + timedelta(hours=RESET_WINDOW_HOURS)
        count = 0
        _write_state(ctx, count, reset_at)
        return {
            "count": count,
            "reset_at": reset_at,
        }

    if now >= state["reset_at"]:
        reset_at = now + timedelta(hours=RESET_WINDOW_HOURS)
        count = 0
        _write_state(ctx, count, reset_at)
        return {
            "count": count,
            "reset_at": reset_at,
        }

    return state


def get_user_limit_info(ctx: Context) -> Dict[str, Any]:
    state = _get_or_create_user_limit_state(ctx)

    if state is None:
        return {
            "count": 0,
            "remaining": MAX_PRICING_CALLS,
            "reset_at": None,
            "reset_at_iso": None,
            "max_calls": MAX_PRICING_CALLS,
            "limit_reached": False,
            "anonymous": True,
            "user_key": None,
        }

    user_key = resolve_user_key(ctx)

    return {
        "count": state["count"],
        "remaining": max(0, MAX_PRICING_CALLS - state["count"]),
        "reset_at": state["reset_at"],
        "reset_at_iso": state["reset_at"].isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": state["count"] >= MAX_PRICING_CALLS,
        "anonymous": False,
        "user_key": user_key,
    }


def can_user_call_pricing(ctx: Context) -> bool:
    state = _get_or_create_user_limit_state(ctx)

    if state is None:
        print("[pricing_limit] no reliable subject, allowing pricing call without consuming quota")
        return True

    return state["count"] < MAX_PRICING_CALLS


def consume_pricing_call(ctx: Context) -> Dict[str, Any]:
    state = _get_or_create_user_limit_state(ctx)

    if state is None:
        print("[pricing_limit] no reliable subject, not consuming quota")
        return {
            "count": 0,
            "remaining": MAX_PRICING_CALLS,
            "reset_at": None,
            "reset_at_iso": None,
            "max_calls": MAX_PRICING_CALLS,
            "limit_reached": False,
            "anonymous": True,
            "user_key": None,
        }

    count = state["count"] + 1
    reset_at = state["reset_at"]

    _write_state(ctx, count, reset_at)

    user_key = resolve_user_key(ctx)

    return {
        "count": count,
        "remaining": max(0, MAX_PRICING_CALLS - count),
        "reset_at": reset_at,
        "reset_at_iso": reset_at.isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": count >= MAX_PRICING_CALLS,
        "anonymous": False,
        "user_key": user_key,
    }
