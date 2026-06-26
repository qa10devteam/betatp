"""
api/schemas.py — Pydantic models dla wszystkich endpoints betatp.io API
"""
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str


# ── Coupon ─────────────────────────────────────────────────────────────────────

class SelectionDetail(BaseModel):
    match_id: str
    player_backed: str
    opponent: str
    surface: str
    tourney_name: str
    tourney_level: str
    bk_odds: float
    p_model: float
    ev_pct: float
    confidence: str
    kelly_stake_pct: float
    recommended_stake_units: float
    reasoning: str
    form_last5: str
    h2h_summary: str
    elo_diff: float
    fatigue_flag: bool


class CouponResponse(BaseModel):
    coupon_id: str
    coupon_date: date
    coupon_type: str
    priority: str  # TOP PICK / RECOMMENDED / SPECULATIVE
    headline: str
    summary: str
    total_ev: float
    recommended_total_stake: float
    selections: list[dict]


class CouponRequest(BaseModel):
    coupon_date: Optional[date] = None
    coupon_type: Optional[str] = "MIXED"
    max_selections: Optional[int] = 5


class CouponHistoryItem(BaseModel):
    coupon_id: str
    coupon_date: date
    coupon_type: str
    priority: str
    headline: str
    total_ev: float
    recommended_total_stake: float
    actual_return: Optional[float] = None
    result: Optional[str] = None  # WIN / LOSS / PENDING


# ── Predictions ────────────────────────────────────────────────────────────────

class MatchPredictionRequest(BaseModel):
    player_a_name: str
    player_b_name: str
    surface: str = Field(default="hard", description="hard / clay / grass")
    tourney_level: str = Field(default="250", description="G / M / 500 / 250 / D / F")
    best_of: int = Field(default=3, ge=3, le=5)
    odds_a: float = Field(description="Decimal odds for player A")
    odds_b: float = Field(description="Decimal odds for player B")


class EloRatings(BaseModel):
    overall: float
    hard: float
    clay: float
    grass: float
    serve: float
    return_elo: float


class MonteCarloResult(BaseModel):
    p_win_sets: list[float]
    simulations: int
    confidence_interval_95: list[float]


class MatchPredictionResponse(BaseModel):
    player_a_name: str
    player_b_name: str
    p_win_a: float
    p_win_b: float
    ev_a: float
    ev_b: float
    monte_carlo_result: MonteCarloResult
    elo_ratings_a: EloRatings
    elo_ratings_b: EloRatings
    signal: str  # BET_A / BET_B / NO_BET
    latency_ms: float


# ── Player Elo ─────────────────────────────────────────────────────────────────

class PlayerEloResponse(BaseModel):
    player_id: int
    player_name: Optional[str] = None
    elo: EloRatings
    n_matches: int
    is_provisional: bool
    last_match_date: Optional[date] = None


# ── Live ───────────────────────────────────────────────────────────────────────

class LiveStateUpdate(BaseModel):
    sets_a: int = Field(ge=0, le=3)
    sets_b: int = Field(ge=0, le=3)
    games_a: int = Field(ge=0, le=7)
    games_b: int = Field(ge=0, le=7)
    pts_a: int = Field(ge=0, le=7)
    pts_b: int = Field(ge=0, le=7)
    server: str = Field(description="A or B")


class LiveProbResponse(BaseModel):
    p_win_a: float
    p_win_b: float
    latency_ms: float


# ── Alert ──────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    alert_id: str
    timestamp: datetime
    alert_type: str  # COUPON_READY / HIGH_VALUE / LIVE_UPDATE
    title: str
    message: str
    data: Optional[dict] = None
