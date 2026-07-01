"""
engine/prediction_service.py — Core prediction service for atpbet.io

Wraps the ChampionStack and computes edge, EV, Kelly stake for each match.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from config import DEFAULT_EDGE_THRESHOLD, MAX_KELLY_FRACTION, MARKET_LABELS, MARKET_AUCS

logger = logging.getLogger(__name__)


@dataclass
class MarketPrediction:
    market_id: str
    label: str
    model_prob: float
    implied_prob: float          # from bookmaker odds
    edge: float                  # model_prob - implied_prob
    ev: float                    # edge / implied_prob
    sts_odds: float
    kelly_pct: float             # recommended bankroll fraction
    auc: float
    is_value: bool               # edge > threshold


@dataclass
class MatchPrediction:
    player_a: str
    player_b: str
    surface: str
    tournament: str
    round_num: str
    markets: dict[str, MarketPrediction] = field(default_factory=dict)
    confidence: str = "LOW"      # HIGH / MEDIUM / LOW
    n_value_markets: int = 0
    best_market: Optional[str] = None
    best_edge: float = 0.0


class PredictionService:
    """
    Generates structured predictions for a tennis match using the champion stack.

    Usage:
        svc = PredictionService()
        result = svc.predict(
            player_a="Djokovic N.",
            player_b="Alcaraz C.",
            surface="Grass",
            tournament="Wimbledon",
            round_num="QF",
            features=np.array([...]),   # 103-element feature vector
            market_odds={               # bookmaker odds per market
                "straight": 2.10,
                "ou36": 1.88,
                ...
            }
        )
    """

    def __init__(self):
        # Lazy import to avoid circular dependency
        from ml.champion_stack import champion_stack
        self._stack = champion_stack

    def predict(
        self,
        player_a: str,
        player_b: str,
        surface: str,
        tournament: str,
        round_num: str,
        features: np.ndarray,
        market_odds: Optional[dict[str, float]] = None,
    ) -> MatchPrediction:
        """
        Run full prediction for a match.

        Args:
            features: 103-element numpy array built by engine.feature_builder
            market_odds: {market_id: decimal_odds} — if None, uses model probability only

        Returns:
            MatchPrediction with per-market edge, EV, Kelly
        """
        if not self._stack._loaded:
            self._stack.load()

        result = MatchPrediction(
            player_a=player_a,
            player_b=player_b,
            surface=surface,
            tournament=tournament,
            round_num=round_num,
        )

        market_odds = market_odds or {}
        raw_probs = self._stack.predict_all(features)

        for market_id, model_prob in raw_probs.items():
            sts_odds = market_odds.get(market_id, None)

            if sts_odds is not None and sts_odds > 1.0:
                implied_prob = 1.0 / sts_odds
            else:
                # No bookmaker odds available: use model prob as reference
                implied_prob = 1.0 - model_prob + 0.05  # synthetic margin
                sts_odds = round(1.0 / max(implied_prob, 0.01), 2)

            edge = model_prob - implied_prob
            ev = edge / max(implied_prob, 0.01)

            # Half-Kelly criterion
            if edge > 0 and sts_odds > 1.0:
                b = sts_odds - 1.0
                kelly_raw = (b * model_prob - (1 - model_prob)) / b
                kelly_pct = max(0.0, min(kelly_raw * 0.5, MAX_KELLY_FRACTION))
            else:
                kelly_pct = 0.0

            mp = MarketPrediction(
                market_id=market_id,
                label=MARKET_LABELS.get(market_id, market_id),
                model_prob=round(model_prob, 4),
                implied_prob=round(implied_prob, 4),
                edge=round(edge, 4),
                ev=round(ev, 4),
                sts_odds=sts_odds,
                kelly_pct=round(kelly_pct, 4),
                auc=MARKET_AUCS.get(market_id, 0.0),
                is_value=edge > DEFAULT_EDGE_THRESHOLD,
            )
            result.markets[market_id] = mp

        # Compute confidence: how many models agree (edge > threshold)
        value_markets = [m for m in result.markets.values() if m.is_value]
        result.n_value_markets = len(value_markets)
        result.confidence = (
            "HIGH" if len(value_markets) >= 4
            else "MEDIUM" if len(value_markets) >= 2
            else "LOW"
        )

        # Best market by edge
        if value_markets:
            best = max(value_markets, key=lambda m: m.edge)
            result.best_market = best.market_id
            result.best_edge = best.edge

        return result


def prediction_to_dict(pred: MatchPrediction) -> dict:
    """Serialise MatchPrediction to JSON-safe dict for API responses."""
    return {
        "match": f"{pred.player_a} vs {pred.player_b}",
        "player_a": pred.player_a,
        "player_b": pred.player_b,
        "surface": pred.surface,
        "tournament": pred.tournament,
        "round": pred.round_num,
        "confidence": pred.confidence,
        "n_value_markets": pred.n_value_markets,
        "best_market": pred.best_market,
        "best_edge": pred.best_edge,
        "markets": {
            mid: {
                "label": m.label,
                "model_prob": m.model_prob,
                "implied_prob": m.implied_prob,
                "edge": m.edge,
                "ev": m.ev,
                "sts_odds": m.sts_odds,
                "kelly_pct": m.kelly_pct,
                "auc": m.auc,
                "is_value": m.is_value,
            }
            for mid, m in pred.markets.items()
        },
    }
