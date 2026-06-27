"""
api/auth.py — JWT authentication & subscription tier enforcement for betatp.io
"""
from __future__ import annotations

import os
import hmac
import hashlib
import base64
import json
import time
from enum import Enum
from typing import Optional

from fastapi import Header, HTTPException, Depends, status

# ── Try PyJWT first ────────────────────────────────────────────────────────────
_JWT_AVAILABLE = False
try:
    import jwt as _pyjwt  # noqa: F401 — checked at import time
    _JWT_AVAILABLE = True
except ImportError:
    pass

SECRET_KEY: str = os.getenv("SECRET_KEY", "betatp-dev-secret-2024")
_ALGORITHM = "HS256"
_TOKEN_TTL = 86400  # 24 hours


# ── Subscription tiers ─────────────────────────────────────────────────────────

class SubscriptionTier(str, Enum):
    FREE  = "FREE"
    PRO   = "PRO"
    ELITE = "ELITE"


_TIER_ORDER = {
    SubscriptionTier.FREE:  0,
    SubscriptionTier.PRO:   1,
    SubscriptionTier.ELITE: 2,
}


# ── Token creation ─────────────────────────────────────────────────────────────

def create_token(user_id: str, tier: str) -> str:
    """Create a signed token encoding user_id and tier."""
    payload = {
        "sub": user_id,
        "tier": tier,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_TTL,
    }

    if _JWT_AVAILABLE:
        import jwt  # type: ignore[import]
        return jwt.encode(payload, SECRET_KEY, algorithm=_ALGORITHM)

    # Fallback: base64(json).HMAC-SHA256-hex
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    sig = hmac.new(
        SECRET_KEY.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return f"{body}.{sig}"


# ── Token verification ─────────────────────────────────────────────────────────

def verify_token(token: str) -> Optional[dict]:
    """Verify a token. Returns {user_id, tier} or None on failure."""
    if not token:
        return None

    if _JWT_AVAILABLE:
        try:
            import jwt  # type: ignore[import]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[_ALGORITHM])
            return {"user_id": payload["sub"], "tier": payload.get("tier", "FREE")}
        except Exception:
            return None

    # Fallback HMAC path
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        body, sig = parts
        expected = hmac.new(
            SECRET_KEY.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padding = 4 - len(body) % 4
        decoded_payload = json.loads(
            base64.urlsafe_b64decode(body + "=" * padding)
        )
        if decoded_payload.get("exp", 0) < time.time():
            return None
        return {
            "user_id": decoded_payload["sub"],
            "tier": decoded_payload.get("tier", "FREE"),
        }
    except Exception:
        return None


# ── FastAPI dependency: current user ──────────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
) -> dict:
    """
    FastAPI dependency. Extracts bearer token from Authorization header
    (or X-Auth-Token fallback). Returns {user_id, tier}.
    Anonymous users transparently get FREE tier.
    """
    token: Optional[str] = None

    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
    elif x_auth_token:
        token = x_auth_token

    if not token:
        return {"user_id": "anonymous", "tier": "FREE"}

    user = verify_token(token)
    if user is None:
        return {"user_id": "anonymous", "tier": "FREE"}

    return user


# ── Tier-based access guard ────────────────────────────────────────────────────

def require_tier(min_tier: SubscriptionTier):
    """
    FastAPI dependency factory that enforces a minimum subscription tier.

    Access rules:
      FREE  -> basic endpoints only
      PRO   -> coupons + CLV
      ELITE -> live data + CLV + coupons (everything)

    Usage:
        @router.get("/coupons")
        async def coupons(user=Depends(require_tier(SubscriptionTier.PRO))):
            ...
    """

    async def dependency(
        user: dict = Depends(get_current_user),
    ) -> dict:
        user_tier_str = user.get("tier", "FREE")
        try:
            user_tier = SubscriptionTier(user_tier_str)
        except ValueError:
            user_tier = SubscriptionTier.FREE

        if _TIER_ORDER.get(user_tier, 0) < _TIER_ORDER.get(min_tier, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This endpoint requires {min_tier.value} tier or higher. "
                    f"Your current tier: {user_tier.value}. "
                    "Upgrade at betatp.io/upgrade"
                ),
            )
        return user

    dependency.__name__ = f"require_{min_tier.value.lower()}_tier"
    return dependency
