"""
api/middleware/subscription.py — Subscription tier limits and ASGI middleware for betatp.io
"""
from __future__ import annotations

import time
import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger(__name__)

# ── Tier limits ────────────────────────────────────────────────────────────────

TIER_LIMITS: dict[str, dict] = {
    "FREE": {
        "coupons_per_day": 3,
        "live":            False,
        "clv":             False,
    },
    "PRO": {
        "coupons_per_day": 20,
        "live":            False,
        "clv":             True,
    },
    "ELITE": {
        "coupons_per_day": 999,
        "live":            True,
        "clv":             True,
    },
}

# Feature -> key in TIER_LIMITS that gates it
_FEATURE_KEY_MAP: dict[str, str] = {
    "coupons": "coupons_per_day",  # truthy check (>0)
    "live":    "live",
    "clv":     "clv",
}


def check_tier_access(tier: str, feature: str) -> bool:
    """
    Return True if the given tier is allowed to access the feature.

    Features: 'coupons', 'live', 'clv'
    """
    limits = TIER_LIMITS.get(tier.upper(), TIER_LIMITS["FREE"])
    key = _FEATURE_KEY_MAP.get(feature.lower())
    if key is None:
        # Unknown feature — allow by default (don't gate unknown things)
        return True
    val = limits.get(key, False)
    if isinstance(val, bool):
        return val
    # Numeric limit: treat >0 as allowed
    return int(val) > 0


# ── In-memory rate-limit counters ──────────────────────────────────────────────
# Structure: {(user_id, endpoint): (count, window_start_ts)}
_rate_counters: dict[tuple[str, str], tuple[int, float]] = defaultdict(lambda: (0, time.time()))
_WINDOW_SECONDS = 86400  # 24-hour rolling window


def rate_limit_check(user_id: str, tier: str, endpoint: str) -> bool:
    """
    Check whether the user is within their per-day rate limit for the endpoint.
    Returns True if the request should be allowed, False if it exceeds the limit.

    Currently enforces 'coupons_per_day' for coupon-related endpoints.
    Other endpoints are always allowed (return True).
    """
    # Only apply coupon-specific rate limiting
    is_coupon_endpoint = "coupon" in endpoint.lower()
    if not is_coupon_endpoint:
        return True

    limits = TIER_LIMITS.get(tier.upper(), TIER_LIMITS["FREE"])
    daily_limit: int = limits.get("coupons_per_day", 3)

    key = (user_id, "coupons")
    count, window_start = _rate_counters[key]

    now = time.time()
    if now - window_start > _WINDOW_SECONDS:
        # Reset window
        _rate_counters[key] = (1, now)
        return True

    if count >= daily_limit:
        logger.debug(
            "Rate limit exceeded for user=%s tier=%s endpoint=%s count=%d limit=%d",
            user_id, tier, endpoint, count, daily_limit,
        )
        return False

    _rate_counters[key] = (count + 1, window_start)
    return True


# ── ASGI middleware ────────────────────────────────────────────────────────────

class TierLimitMiddleware:
    """
    ASGI middleware that:
      1. Reads the Authorization header to extract tier (best-effort).
      2. Adds X-Tier response header.
      3. Adds X-Rate-Limit-Coupons-Remaining response header for coupon endpoints.
    """

    def __init__(self, app, secret_key: str | None = None):
        self.app = app
        self._secret_key = secret_key

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract tier from request headers (best-effort, no hard block here)
        tier = "FREE"
        user_id = "anonymous"

        headers = dict(scope.get("headers", []))
        auth_bytes = headers.get(b"authorization", b"")
        x_token_bytes = headers.get(b"x-auth-token", b"")

        raw_token: str | None = None
        if auth_bytes:
            parts = auth_bytes.decode(errors="replace").split()
            raw_token = parts[1] if len(parts) == 2 else (parts[0] if parts else None)
        elif x_token_bytes:
            raw_token = x_token_bytes.decode(errors="replace")

        if raw_token:
            try:
                from api.auth import verify_token
                info = verify_token(raw_token)
                if info:
                    tier = info.get("tier", "FREE")
                    user_id = info.get("user_id", "anonymous")
            except Exception:
                pass

        path = scope.get("path", "")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra_headers: list[tuple[bytes, bytes]] = [
                    (b"x-tier", tier.encode()),
                ]
                # Coupon remaining header
                if "coupon" in path.lower():
                    limits = TIER_LIMITS.get(tier.upper(), TIER_LIMITS["FREE"])
                    daily_limit = limits.get("coupons_per_day", 3)
                    key = (user_id, "coupons")
                    used, window_start = _rate_counters.get(key, (0, time.time()))
                    if time.time() - window_start > _WINDOW_SECONDS:
                        used = 0
                    remaining = max(0, daily_limit - used)
                    extra_headers.append(
                        (b"x-rate-limit-coupons-remaining", str(remaining).encode())
                    )

                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + extra_headers

            await send(message)

        await self.app(scope, receive, send_with_headers)
