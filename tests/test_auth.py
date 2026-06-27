"""
tests/test_auth.py — Coverage tests for api/auth.py
"""
import asyncio
import pytest

from api.auth import (
    create_token,
    verify_token,
    get_current_user,
    require_tier,
    SubscriptionTier,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# 1. create_token returns a string
# ---------------------------------------------------------------------------

def test_create_token():
    token = create_token("u1", "PRO")
    assert isinstance(token, str)
    assert len(token) > 10


# ---------------------------------------------------------------------------
# 2. verify round-trip
# ---------------------------------------------------------------------------

def test_verify_token_valid():
    token = create_token("alice", "ELITE")
    result = verify_token(token)
    assert result is not None
    assert result["user_id"] == "alice"
    assert result["tier"] == "ELITE"


# ---------------------------------------------------------------------------
# 3. bad token -> None
# ---------------------------------------------------------------------------

def test_verify_token_invalid():
    result = verify_token("this.is.not.a.valid.token.at.all")
    assert result is None


def test_verify_token_empty():
    assert verify_token("") is None


# ---------------------------------------------------------------------------
# 4. no token -> FREE tier (anonymous user)
# ---------------------------------------------------------------------------

def test_get_current_user_anon():
    """No token provided → anonymous FREE user."""
    user = asyncio.run(get_current_user(authorization=None, x_auth_token=None))
    assert user["tier"] == "FREE"
    assert user["user_id"] == "anonymous"


# ---------------------------------------------------------------------------
# 5. PRO user can access PRO endpoint
# ---------------------------------------------------------------------------

def test_require_tier_ok():
    """PRO user passes a PRO-gated dependency without raising."""
    dep = require_tier(SubscriptionTier.PRO)
    # Call the inner async function directly with a PRO user dict
    pro_user = {"user_id": "u1", "tier": "PRO"}
    result = asyncio.run(dep(user=pro_user))
    assert result["tier"] == "PRO"


def test_require_tier_elite_allowed_for_elite():
    """ELITE user passes an ELITE-gated dependency."""
    dep = require_tier(SubscriptionTier.ELITE)
    elite_user = {"user_id": "u2", "tier": "ELITE"}
    result = asyncio.run(dep(user=elite_user))
    assert result["tier"] == "ELITE"


# ---------------------------------------------------------------------------
# 6. FREE user blocked from ELITE endpoint
# ---------------------------------------------------------------------------

def test_require_tier_forbidden():
    """FREE user is blocked from an ELITE-gated endpoint (HTTP 403)."""
    dep = require_tier(SubscriptionTier.ELITE)
    free_user = {"user_id": "anon", "tier": "FREE"}
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dep(user=free_user))
    assert exc_info.value.status_code == 403


def test_require_tier_free_blocked_pro():
    """FREE user is blocked from a PRO-gated endpoint."""
    dep = require_tier(SubscriptionTier.PRO)
    free_user = {"user_id": "anon", "tier": "FREE"}
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dep(user=free_user))
    assert exc_info.value.status_code == 403
