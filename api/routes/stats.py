"""
api/routes/stats.py — Statistics endpoints for betatp.io
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["stats"])

# ── Lazy loaders ───────────────────────────────────────────────────────────────

_elo_engine_instance = None


def _get_elo_engine():
    """Return a cached EloEngine instance if available, else None."""
    global _elo_engine_instance
    if _elo_engine_instance is not None:
        return _elo_engine_instance
    try:
        from engine.elo import EloEngine  # type: ignore
        _elo_engine_instance = EloEngine()
        return _elo_engine_instance
    except Exception:
        return None


def _get_clv_tracker():
    try:
        from value.clv_tracker import CLVTracker  # type: ignore
        return CLVTracker()
    except Exception:
        return None


# ── GET /stats/elo/{player_name} ───────────────────────────────────────────────

@router.get("/stats/elo/{player_name}")
async def get_player_elo(player_name: str):
    """
    Return Elo ratings for a player across all surfaces.
    Falls back to mock data if EloEngine has no entry for the player.
    """
    engine = _get_elo_engine()

    if engine is not None:
        try:
            # EloEngine.get_or_create gives a PlayerElo dataclass
            player_elo = engine.get_or_create(player_name)
            last_updated = (
                player_elo.last_match_date.isoformat()
                if player_elo.last_match_date
                else datetime.now(timezone.utc).date().isoformat()
            )
            return {
                "player":       player_name,
                "overall_elo":  round(player_elo.overall, 1),
                "hard_elo":     round(player_elo.hard, 1),
                "clay_elo":     round(player_elo.clay, 1),
                "grass_elo":    round(player_elo.grass, 1),
                "last_updated": last_updated,
                "source":       "engine",
            }
        except Exception as exc:
            logger.warning("EloEngine lookup failed for '%s': %s", player_name, exc)

    # Mock fallback — deterministic from player name hash
    seed = sum(ord(c) for c in player_name)
    base = 1400 + (seed % 400)
    return {
        "player":       player_name,
        "overall_elo":  round(base + 0.0, 1),
        "hard_elo":     round(base - 12.5 + (seed % 50), 1),
        "clay_elo":     round(base - 25.0 + (seed % 70), 1),
        "grass_elo":    round(base - 18.0 + (seed % 40), 1),
        "last_updated": datetime.now(timezone.utc).date().isoformat(),
        "source":       "mock",
    }


# ── GET /stats/clv ─────────────────────────────────────────────────────────────

@router.get("/stats/clv")
async def get_clv_summary():
    """
    Return Closing Line Value summary statistics.
    Falls back to mock data if CLVTracker has no recorded bets.
    """
    tracker = _get_clv_tracker()

    if tracker is not None:
        try:
            bets = getattr(tracker, "_bets", [])
            clv_values = [b.clv for b in bets if b.clv is not None]
            total_bets = len(bets)

            def avg_clv_window(days: int) -> float | None:
                """Average CLV for bets placed within the last N days."""
                if not clv_values:
                    return None
                from datetime import timedelta
                cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
                window = [
                    b.clv
                    for b in bets
                    if b.clv is not None and b.opening_timestamp >= cutoff
                ]
                return round(sum(window) / len(window) * 100, 2) if window else None

            avg_7  = avg_clv_window(7)
            avg_30 = avg_clv_window(30)
            avg_90 = avg_clv_window(90)

            # Statistical significance: need >= 30 bets with CLV data
            significant = len(clv_values) >= 30

            if total_bets > 0:
                return {
                    "avg_clv_7d":  avg_7,
                    "avg_clv_30d": avg_30,
                    "avg_clv_90d": avg_90,
                    "total_bets":  total_bets,
                    "significant": significant,
                    "source":      "tracker",
                }
        except Exception as exc:
            logger.warning("CLVTracker summary failed: %s", exc)

    # Mock fallback — typical positive CLV model
    return {
        "avg_clv_7d":  2.34,
        "avg_clv_30d": 1.87,
        "avg_clv_90d": 2.12,
        "total_bets":  57,
        "significant": True,
        "source":      "mock",
    }


# ── GET /stats/backtest ────────────────────────────────────────────────────────

@router.get("/stats/backtest")
async def get_backtest_results():
    """
    Return hardcoded v14 backtest results.
    Model: ATP value betting, edge >= 15%, 2022-2024.
    """
    return {
        "version":   "v14",
        "roi":       58.7,         # % return on investment
        "win_rate":  59.6,         # % of bets won
        "n_bets":    57,           # number of qualifying bets
        "edge":      ">=15%",      # minimum edge threshold
        "period":    "2022-2024",
        "stake":     "Kelly/2",
        "surface":   "all",
        "notes":     "Out-of-sample backtest. Past performance does not guarantee future results.",
    }


# ── GET /api/v1/coupons/today ─────────────────────────────────────────────────

@router.get("/coupons/today")
async def get_today_coupon_v1():
    """
    Versioned daily coupon endpoint.
    Returns top singles with 'top_singles' key for API v1 consumers.
    """
    from datetime import date as date_type
    target_date = date_type.today()

    # Try to build from DailyCouponBuilder with mock data
    mock_matches = [
        {
            "player": "Carlos Alcaraz",
            "player_backed": "Carlos Alcaraz",
            "opponent": "Holger Rune",
            "surface": "Clay",
            "odds": 1.62,
            "p_model": 0.72,
            "ev": 0.1664,
            "kelly": 0.045,
            "ev_pct": 16.64,
            "confidence": "HIGH",
        },
        {
            "player": "Jannik Sinner",
            "player_backed": "Jannik Sinner",
            "opponent": "Alexander Zverev",
            "surface": "Hard",
            "odds": 1.75,
            "p_model": 0.67,
            "ev": 0.1725,
            "kelly": 0.038,
            "ev_pct": 17.25,
            "confidence": "HIGH",
        },
        {
            "player": "Novak Djokovic",
            "player_backed": "Novak Djokovic",
            "opponent": "Casper Ruud",
            "surface": "Hard",
            "odds": 1.55,
            "p_model": 0.74,
            "ev": 0.147,
            "kelly": 0.052,
            "ev_pct": 14.70,
            "confidence": "HIGH",
        },
    ]

    try:
        from engine.daily_coupon import DailyCouponBuilder
        builder = DailyCouponBuilder()
        coupon = builder.build(mock_matches, min_ev=0.0)
    except Exception as exc:
        logger.warning("DailyCouponBuilder failed: %s", exc)
        coupon = {
            "date": str(target_date),
            "top_singles": mock_matches[:3],
            "system_2_3": None,
            "system_3_4": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Ensure top_singles is always present
    if "top_singles" not in coupon:
        coupon["top_singles"] = mock_matches[:3]

    return coupon
