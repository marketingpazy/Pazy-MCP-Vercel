from mcp.server.fastmcp import Context
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

MAX_PRICING_CALLS = 10
RESET_WINDOW_HOURS = 24


@dataclass
class UserRateLimitState:
    count: int
    reset_at: datetime

PRICING_CALLS_BY_USER: dict[str, UserRateLimitState] = {}

def _extract_subject_from_ctx(ctx: Context) -> Optional[str]:
    request_context = getattr(ctx, "request_context", None)
    meta = getattr(request_context, "meta", None) if request_context else None

    if meta is not None:
        for key in ("openai_subject", "openai/subject", "subject", "user_id", "user"):
            if isinstance(meta, dict) and meta.get(key):
                return str(meta[key])
            attr_name = key.replace("/", "_")
            if hasattr(meta, attr_name):
                value = getattr(meta, attr_name)
                if value:
                    return str(value)

    client_id = getattr(ctx, "client_id", None)
    if client_id:
        return f"client:{client_id}"

    return None


def resolve_user_key(ctx: Context) -> str:
    subject = _extract_subject_from_ctx(ctx)
    if subject:
        return f"user:{subject}"

    session_id = getattr(ctx, "session_id", None)
    if session_id:
        return f"session:{session_id}"

    request_id = getattr(ctx, "request_id", None)
    if request_id:
        return f"request:{request_id}"

    return "user:anonymous"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_user_limit_state(ctx: Context) -> UserRateLimitState:
    user_key = resolve_user_key(ctx)
    now = utc_now()
    state = PRICING_CALLS_BY_USER.get(user_key)

    if state is None:
        state = UserRateLimitState(
            count=0,
            reset_at=now + timedelta(hours=RESET_WINDOW_HOURS),
        )
        PRICING_CALLS_BY_USER[user_key] = state
        return state

    if now >= state.reset_at:
        state.count = 0
        state.reset_at = now + timedelta(hours=RESET_WINDOW_HOURS)

    return state


def get_user_limit_info(ctx: Context) -> Dict[str, Any]:
    state = _get_or_create_user_limit_state(ctx)
    return {
        "count": state.count,
        "remaining": max(0, MAX_PRICING_CALLS - state.count),
        "reset_at": state.reset_at,
        "reset_at_iso": state.reset_at.isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": state.count >= MAX_PRICING_CALLS,
    }


def can_user_call_pricing(ctx: Context) -> bool:
    state = _get_or_create_user_limit_state(ctx)
    return state.count < MAX_PRICING_CALLS


def consume_pricing_call(ctx: Context) -> Dict[str, Any]:
    state = _get_or_create_user_limit_state(ctx)
    state.count += 1
    return {
        "count": state.count,
        "remaining": max(0, MAX_PRICING_CALLS - state.count),
        "reset_at": state.reset_at,
        "reset_at_iso": state.reset_at.isoformat(),
        "max_calls": MAX_PRICING_CALLS,
        "limit_reached": state.count >= MAX_PRICING_CALLS,
    }