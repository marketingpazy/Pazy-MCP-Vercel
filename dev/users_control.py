from mcp.server.fastmcp import Context
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
import json
import os
from upstash_redis import Redis

MAX_PRICING_CALLS = 10
RESET_WINDOW_HOURS = 24

# Reutilizable en serverless mientras la función esté caliente
redis = Redis(
    url=os.environ["KV_REST_API_URL"],
    token=os.environ["KV_REST_API_TOKEN"],
)


def _extract_subject_from_ctx(ctx: Context) -> Optional[str]:
    request_context = getattr(ctx, "request_context", None)
    meta = getattr(request_context, "meta", None) if request_context else None

    if meta is None:
        return None

    if isinstance(meta, dict):
        for key in (
            "openai/subject",
            "openai_subject",
            "subject",
            "user_id",
            "user",
        ):
            value = meta.get(key)
            if value:
                return str(value)

    for attr_name in (
        "openai_subject",
        "subject",
        "user_id",
        "user",
    ):
        if hasattr(meta, attr_name):
            value = getattr(meta, attr_name)
            if value:
                return str(value)

    return None


def resolve_user_key(ctx: Context) -> str:
    subject = _extract_subject_from_ctx(ctx)
    if subject:
        return f"user:{subject}"
    return "user:anonymous"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _redis_key_for_user(ctx: Context) -> str:
    return f"pricing_limit:{resolve_user_key(ctx)}"


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
    ttl_seconds = max(1, int((reset_at - utc_now()).total_seconds()))
    redis.set(key, _serialize_state(count, reset_at), ex=ttl_seconds)


def _get_or_create_user_limit_state(ctx: Context) -> Dict[str, Any]:
    key = _redis_key_for_user(ctx)
    now = utc_now()

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
    return {
        "count": state["count"],
        "remaining": max(0, MAX_PRICING_CALLS - state["count"]),
        "reset_at": state["reset_at"],
        "reset_at_iso": state["reset_at"].isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": state["count"] >= MAX_PRICING_CALLS,
    }


def can_user_call_pricing(ctx: Context) -> bool:
    state = _get_or_create_user_limit_state(ctx)
    return state["count"] < MAX_PRICING_CALLS


def consume_pricing_call(ctx: Context) -> Dict[str, Any]:
    state = _get_or_create_user_limit_state(ctx)

    count = state["count"] + 1
    reset_at = state["reset_at"]

    _write_state(ctx, count, reset_at)

    return {
        "count": count,
        "remaining": max(0, MAX_PRICING_CALLS - count),
        "reset_at": reset_at,
        "reset_at_iso": reset_at.isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": count >= MAX_PRICING_CALLS,
    }
