"""
api/routes/predictions.py — Prediction endpoints for atpbet.io API v1
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response schemas ─────────────────────────────────────────────────

class MatchPredictionRequest(BaseModel):
    player_a: str = "Djokovic N."
    player_b: str = "Alcaraz C."
    surface: str = "Grass"
    tournament: str = "Wimbledon"
    round_num: str = "R1"
    odds_a: float = 1.50
    odds_b: float = 2.50


class MarketInfo(BaseModel):
    id: str
    label: str
    description: str
    auc: float
    loaded: bool


class MarketsResponse(BaseModel):
    markets: list[MarketInfo]
    n_loaded: int
    timestamp: str


class PlayerStatsResponse(BaseModel):
    player: str
    n_matches: int
    ace_rate: float
    hold_pct: float
    first_won_pct: float
    bp_saved_pct: float


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/match", summary="Predict a match across all 6 markets")
async def predict_match(req: MatchPredictionRequest):
    """
    Run champion stack prediction for a single match.

    Returns probabilities, edge, EV, and Kelly stake for all 6 markets.
    Value bets (edge > 4%) are flagged with is_value=true.
    """
    import asyncio
    import numpy as np
    from engine.feature_builder import build_features_for_match
    from engine.prediction_service import PredictionService, prediction_to_dict

    try:
        features, stats_a, stats_b = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: build_features_for_match(
                player_a=req.player_a,
                player_b=req.player_b,
                surface=req.surface,
                round_num=req.round_num,
                odds_a=req.odds_a,
                odds_b=req.odds_b,
            )
        )
    except Exception as e:
        logger.warning(f"Feature build failed for {req.player_a} vs {req.player_b}: {e}")
        # Use default features on DB failure
        from engine.feature_builder import build_features, _default_player_stats
        stats_a = _default_player_stats()
        stats_b = _default_player_stats()
        features = build_features(
            player_a_stats=stats_a,
            player_b_stats=stats_b,
            elo_a=1550.0,
            elo_b=1500.0,
            surface_elo_a=1550.0,
            surface_elo_b=1500.0,
            odds_a=req.odds_a,
            odds_b=req.odds_b,
            surface=req.surface,
            round_num=req.round_num,
        )

    svc = PredictionService()
    pred = svc.predict(
        player_a=req.player_a,
        player_b=req.player_b,
        surface=req.surface,
        tournament=req.tournament,
        round_num=req.round_num,
        features=features,
        market_odds={
            "straight": req.odds_a * 1.3,
            "fatigue5": req.odds_b * 0.8,
            "ou39": 1.88,
            "ou36": 1.90,
            "hcp9": 2.05,
            "ou33": 1.95,
        },
    )

    return {
        **prediction_to_dict(pred),
        "stats_a": stats_a,
        "stats_b": stats_b,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/markets", response_model=MarketsResponse, summary="List all prediction markets")
async def get_markets():
    """
    Returns metadata for all 6 champion prediction markets:
    model name, AUC, description, and load status.
    """
    from ml.champion_stack import champion_stack
    if not champion_stack._loaded:
        champion_stack.load()

    return MarketsResponse(
        markets=[MarketInfo(**m) for m in champion_stack.market_info],
        n_loaded=champion_stack.n_models,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.get("/player", response_model=PlayerStatsResponse, summary="Get rolling player stats")
async def get_player_stats(name: str):
    """
    Returns rolling serve/return stats for a player (last 40 matches from 2023+).
    Use player's last name or full name (fuzzy search).
    """
    import asyncio
    from engine.feature_builder import get_conn, get_player_stats

    try:
        conn = await asyncio.get_event_loop().run_in_executor(None, get_conn)
        cur = conn.cursor()
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: get_player_stats(cur, name)
        )
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Player stats fetch failed for {name}: {e}")
        from engine.feature_builder import _default_player_stats
        stats = _default_player_stats()

    return PlayerStatsResponse(
        player=name,
        n_matches=stats.get("n_matches", 0),
        ace_rate=round(stats.get("ace_rate", 0), 4),
        hold_pct=round(stats.get("hold_pct", 0), 4),
        first_won_pct=round(stats.get("first_won_pct", 0), 4),
        bp_saved_pct=round(stats.get("bp_saved_pct", 0), 4),
    )


@router.get("/model/info", summary="Champion stack summary")
async def model_info():
    """Returns champion stack version, AUCs, and training data summary."""
    from ml.champion_stack import champion_stack
    if not champion_stack._loaded:
        champion_stack.load()

    return {
        "stack_version": "champion_v80",
        "n_models": champion_stack.n_models,
        "training_matches": 197495,
        "holdout_matches": 1904,
        "holdout_year": 2024,
        "best_model": {"id": "straight", "auc": 0.9354, "file": "lgbm_v70_is_straight"},
        "markets": champion_stack.market_info,
        "backtest": {
            "total_bets": 57,
            "win_rate": 0.596,
            "flat_roi": 0.587,
            "kelly_roi": 0.587,
            "max_drawdown": 0.179,
            "edge_threshold": 0.15,
        },
    }
