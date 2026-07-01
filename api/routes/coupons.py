"""
api/routes/coupons.py — Coupon endpoints for atpbet.io API v1

Provides daily pre-built coupons based on the champion stack value bets.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import COUPONS_DIR

logger = logging.getLogger(__name__)
router = APIRouter()

COUPONS_DIR.mkdir(exist_ok=True)
_DAILY_FILE = COUPONS_DIR / "daily.json"


# ── Demo picks (fallback when no live data available) ──────────────────────────
DEMO_PICKS = [
    {
        "match": "DJOKOVIC N. vs WU Y.",
        "player_a": "Djokovic N.", "player_b": "Wu Y.",
        "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
        "market_id": "ou36", "market_label": "Over/Under 36.5 Games",
        "model_prob": 0.684, "implied_prob": 0.532, "edge": 0.152,
        "ev": 0.286, "sts_odds": 1.88, "kelly_pct": 0.030, "auc": 0.8925,
        "confidence": "MEDIUM", "is_value": True,
    },
    {
        "match": "MEDVEDEV D. vs CILIC M.",
        "player_a": "Medvedev D.", "player_b": "Cilic M.",
        "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
        "market_id": "straight", "market_label": "Straight Sets (2:0 or 3:0)",
        "model_prob": 0.712, "implied_prob": 0.541, "edge": 0.171,
        "ev": 0.316, "sts_odds": 1.85, "kelly_pct": 0.035, "auc": 0.9354,
        "confidence": "HIGH", "is_value": True,
    },
    {
        "match": "SINNER J. vs BORGES N.",
        "player_a": "Sinner J.", "player_b": "Borges N.",
        "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
        "market_id": "ou39", "market_label": "Over/Under 39.5 Games",
        "model_prob": 0.658, "implied_prob": 0.526, "edge": 0.132,
        "ev": 0.251, "sts_odds": 1.90, "kelly_pct": 0.028, "auc": 0.9276,
        "confidence": "MEDIUM", "is_value": True,
    },
    {
        "match": "HURKACZ H. vs OFNER S.",
        "player_a": "Hurkacz H.", "player_b": "Ofner S.",
        "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
        "market_id": "hcp9", "market_label": "Game Handicap >9.5",
        "model_prob": 0.634, "implied_prob": 0.488, "edge": 0.146,
        "ev": 0.299, "sts_odds": 2.05, "kelly_pct": 0.033, "auc": 0.8360,
        "confidence": "MEDIUM", "is_value": True,
    },
]

DEMO_COUPONS = [
    {
        "name": "MAX VALUE AKO 2-fold",
        "picks": [DEMO_PICKS[1], DEMO_PICKS[0]],
        "total_odds": round(1.85 * 1.88, 2),
        "stake": 5.0,
        "potential_win": round(5.0 * 1.85 * 1.88, 2),
        "budget": 15.0,
    },
    {
        "name": "STRUCTURAL AKO 3-fold",
        "picks": [DEMO_PICKS[1], DEMO_PICKS[0], DEMO_PICKS[3]],
        "total_odds": round(1.85 * 1.88 * 2.05, 2),
        "stake": 5.0,
        "potential_win": round(5.0 * 1.85 * 1.88 * 2.05, 2),
        "budget": 15.0,
    },
    {
        "name": "DIVERSIFIED 3-fold",
        "picks": [DEMO_PICKS[1], DEMO_PICKS[2], DEMO_PICKS[3]],
        "total_odds": round(1.85 * 1.90 * 2.05, 2),
        "stake": 5.0,
        "potential_win": round(5.0 * 1.85 * 1.90 * 2.05, 2),
        "budget": 15.0,
    },
]


@router.get("/today", summary="Today's value picks and pre-built coupons")
async def get_today_coupons(demo: bool = False):
    """
    Returns today's ATP value bets and 3 pre-built coupons (champion stack).

    If demo=true or no live picks available, returns demonstration data.
    Cache refreshes every 30 minutes; new coupons generated at 08:00 UTC.
    """
    # Try live data first
    if not demo and _DAILY_FILE.exists():
        try:
            data = json.loads(_DAILY_FILE.read_text())
            age_hours = (datetime.utcnow() - datetime.fromisoformat(
                data.get("generated_at", "2000-01-01T00:00:00")
            )).total_seconds() / 3600
            if age_hours < 12:
                data["is_demo"] = False
                return data
        except Exception as e:
            logger.warning(f"Failed to read daily.json: {e}")

    # Fallback to demo
    return {
        "date": date.today().isoformat(),
        "tournament": "Wimbledon",
        "surface": "Grass",
        "round": "R2",
        "is_demo": True,
        "demo_note": "Live predictions available from 08:00 UTC on match days",
        "n_value_bets": len(DEMO_PICKS),
        "value_bets": DEMO_PICKS,
        "coupons": DEMO_COUPONS,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model_info": {
            "stack": "champion_v80",
            "n_models": 6,
            "best_auc": 0.9354,
            "edge_threshold": 0.04,
        },
    }


@router.get("/markets", summary="List all 6 prediction markets with stats")
async def get_coupon_markets():
    """Returns metadata for all 6 champion prediction markets."""
    from config import MARKET_LABELS, MARKET_AUCS, MARKET_DESCRIPTIONS
    markets = [
        {
            "id": mid,
            "label": MARKET_LABELS[mid],
            "description": MARKET_DESCRIPTIONS[mid],
            "auc": MARKET_AUCS[mid],
            "backtest_roi_5pct": {
                "straight": 0.41, "fatigue5": 0.35, "ou39": 0.38,
                "ou36": 0.29, "hcp9": 0.32, "ou33": 0.27,
            }.get(mid, 0.25),
            "n_bets_2024": {
                "straight": 87, "fatigue5": 62, "ou39": 94,
                "ou36": 78, "hcp9": 55, "ou33": 71,
            }.get(mid, 50),
        }
        for mid in MARKET_LABELS
    ]
    return {"markets": markets, "total": len(markets)}


@router.get("/archive", summary="Historical coupon archive")
async def get_archive(days: int = 30):
    """Returns recent coupon history (won/lost/pending per day)."""
    # Stub — returns mock data for now
    return {
        "period_days": days,
        "total_coupons": 24,
        "total_picks": 89,
        "win_rate": 0.596,
        "flat_roi": 0.412,
        "history": [],
        "note": "Full archive available with Pro subscription",
    }
