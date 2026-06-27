"""
tests/test_schema.py — Coverage tests for api/schemas.py and engine/coupon.py schemas
"""
import pytest
from datetime import date, datetime, timezone
from pydantic import ValidationError

from api.schemas import (
    CouponRequest,
    CouponResponse,
    AlertResponse,
    SelectionDetail,
    MatchPredictionResponse,
    MonteCarloResult,
    EloRatings,
)


# ---------------------------------------------------------------------------
# 1. test_coupon_schema_valid
# ---------------------------------------------------------------------------

def test_coupon_schema_valid():
    """CouponResponse accepts valid data."""
    coupon = CouponResponse(
        coupon_id="abc123",
        coupon_date=date.today(),
        coupon_type="single",
        priority="TOP PICK",
        headline="Alcaraz dominuje — EV +8%",
        summary="Świetna selekcja na dziś.",
        total_ev=0.08,
        recommended_total_stake=0.03,
        selections=[],
    )
    assert coupon.coupon_id == "abc123"
    assert coupon.priority == "TOP PICK"


# ---------------------------------------------------------------------------
# 2. test_selection_schema_ev_validation
# ---------------------------------------------------------------------------

def test_selection_schema_ev_validation():
    """SelectionDetail correctly stores ev_pct."""
    sel = SelectionDetail(
        match_id="m1",
        player_backed="Carlos Alcaraz",
        opponent="Novak Djokovic",
        surface="Hard",
        tourney_name="Wimbledon",
        tourney_level="G",
        bk_odds=1.80,
        p_model=0.65,
        ev_pct=0.072,
        confidence="HIGH",
        kelly_stake_pct=0.025,
        recommended_stake_units=0.5,
        reasoning="Alcaraz in great form.",
        form_last5="WWWLW",
        h2h_summary="8-6",
        elo_diff=120.0,
        fatigue_flag=False,
    )
    assert sel.ev_pct == pytest.approx(0.072)
    assert sel.confidence == "HIGH"


# ---------------------------------------------------------------------------
# 3. test_prediction_response_sum — p_win_a + p_win_b ~= 1.0
# ---------------------------------------------------------------------------

def test_prediction_response_sum():
    """p_win_a + p_win_b should sum to approximately 1.0."""
    mc = MonteCarloResult(
        p_win_sets=[0.55, 0.30, 0.10, 0.05],
        simulations=10000,
        confidence_interval_95=[0.52, 0.58],
    )
    elo = EloRatings(overall=1800.0, hard=1780.0, clay=1750.0, grass=1820.0,
                     serve=1810.0, return_elo=1790.0)
    resp = MatchPredictionResponse(
        player_a_name="Alcaraz",
        player_b_name="Djokovic",
        p_win_a=0.65,
        p_win_b=0.35,
        ev_a=0.08,
        ev_b=-0.02,
        monte_carlo_result=mc,
        elo_ratings_a=elo,
        elo_ratings_b=elo,
        signal="BET_A",
        latency_ms=12.3,
    )
    assert abs(resp.p_win_a + resp.p_win_b - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# 4. test_coupon_request_defaults
# ---------------------------------------------------------------------------

def test_coupon_request_defaults():
    """CouponRequest has sensible defaults."""
    req = CouponRequest()
    assert req.coupon_date is None
    assert req.coupon_type == "MIXED"
    assert req.max_selections == 5


def test_coupon_request_custom():
    """CouponRequest accepts custom values."""
    req = CouponRequest(coupon_date=date(2025, 7, 1), coupon_type="single", max_selections=3)
    assert req.coupon_type == "single"
    assert req.max_selections == 3


# ---------------------------------------------------------------------------
# 5. test_alert_schema
# ---------------------------------------------------------------------------

def test_alert_schema():
    """AlertResponse stores all required fields correctly."""
    ts = datetime.now(timezone.utc)
    alert = AlertResponse(
        alert_id="alrt-001",
        timestamp=ts,
        alert_type="HIGH_VALUE",
        title="High EV Alert",
        message="Alcaraz has +9.2% EV at odds 1.95",
        data={"match_id": "m99", "ev": 9.2},
    )
    assert alert.alert_id == "alrt-001"
    assert alert.alert_type == "HIGH_VALUE"
    assert alert.data is not None and alert.data["ev"] == 9.2


def test_alert_schema_no_data():
    """AlertResponse data field is optional (defaults to None)."""
    ts = datetime.now(timezone.utc)
    alert = AlertResponse(
        alert_id="alrt-002",
        timestamp=ts,
        alert_type="COUPON_READY",
        title="Coupon Ready",
        message="Your daily coupon is ready.",
    )
    assert alert.data is None


# ---------------------------------------------------------------------------
# 6. test_bet_schema_optional_fields
# ---------------------------------------------------------------------------

def test_bet_schema_optional_fields():
    """CouponHistoryItem optional fields default to None."""
    from api.schemas import CouponHistoryItem
    item = CouponHistoryItem(
        coupon_id="c1",
        coupon_date=date.today(),
        coupon_type="trixie",
        priority="RECOMMENDED",
        headline="Test coupon",
        total_ev=0.04,
        recommended_total_stake=0.06,
    )
    assert item.actual_return is None
    assert item.result is None


def test_bet_schema_with_result():
    """CouponHistoryItem with result set."""
    from api.schemas import CouponHistoryItem
    item = CouponHistoryItem(
        coupon_id="c2",
        coupon_date=date.today(),
        coupon_type="single",
        priority="TOP PICK",
        headline="Winner",
        total_ev=0.09,
        recommended_total_stake=0.05,
        actual_return=1.8,
        result="WIN",
    )
    assert item.result == "WIN"
    assert item.actual_return == pytest.approx(1.8)
