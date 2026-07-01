"""
engine/value_detector.py — Value bet detection and Kelly stake sizing for atpbet.io

Scans a list of match predictions, filters for value bets (edge > threshold),
and builds ranked picks for coupon generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import DEFAULT_EDGE_THRESHOLD, MAX_KELLY_FRACTION, COUPON_BUDGET_DEFAULT

logger = logging.getLogger(__name__)


@dataclass
class ValueBet:
    player_a: str
    player_b: str
    surface: str
    tournament: str
    round_num: str
    market_id: str
    market_label: str
    model_prob: float
    implied_prob: float
    sts_odds: float
    edge: float                  # model_prob - implied_prob
    ev: float                    # edge / implied_prob
    kelly_pct: float             # recommended bankroll fraction (half-Kelly, capped)
    stake_usd: float             # stake in USD at default budget
    auc: float
    confidence: str              # from parent MatchPrediction


@dataclass
class Coupon:
    name: str                    # "MAX VALUE AKO 2-fold" etc.
    picks: list[ValueBet]
    total_odds: float
    stake: float
    potential_win: float
    budget: float


class ValueDetector:
    """
    Scans match predictions for value bets above a given edge threshold.
    """

    def __init__(
        self,
        edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
        kelly_cap: float = MAX_KELLY_FRACTION,
        budget: float = COUPON_BUDGET_DEFAULT,
    ):
        self.edge_threshold = edge_threshold
        self.kelly_cap = kelly_cap
        self.budget = budget

    def scan(self, match_predictions: list) -> list[ValueBet]:
        """
        Extract all value bets from a list of MatchPrediction objects.

        Returns sorted list: highest edge first.
        """
        from engine.prediction_service import MatchPrediction

        value_bets: list[ValueBet] = []

        for pred in match_predictions:
            for market_id, mp in pred.markets.items():
                if not mp.is_value:
                    continue
                if mp.edge < self.edge_threshold:
                    continue

                stake_usd = round(mp.kelly_pct * self.budget, 2)

                vb = ValueBet(
                    player_a=pred.player_a,
                    player_b=pred.player_b,
                    surface=pred.surface,
                    tournament=pred.tournament,
                    round_num=pred.round_num,
                    market_id=market_id,
                    market_label=mp.label,
                    model_prob=mp.model_prob,
                    implied_prob=mp.implied_prob,
                    sts_odds=mp.sts_odds,
                    edge=mp.edge,
                    ev=mp.ev,
                    kelly_pct=mp.kelly_pct,
                    stake_usd=stake_usd,
                    auc=mp.auc,
                    confidence=pred.confidence,
                )
                value_bets.append(vb)

        value_bets.sort(key=lambda v: v.edge, reverse=True)
        logger.info(f"[ValueDetector] Found {len(value_bets)} value bets above {self.edge_threshold:.0%} edge")
        return value_bets


class CouponBuilder:
    """
    Builds pre-packaged coupons (accumulators) from value bets.

    Generates 3 coupons:
      1. MAX VALUE AKO: top 2 picks by edge
      2. STRUCTURAL 3-FOLD: top 3 picks by edge
      3. DIVERSIFIED 3-FOLD: top 3 picks from different markets
    """

    def __init__(self, budget: float = COUPON_BUDGET_DEFAULT, n_coupons: int = 3):
        self.budget = budget
        self.n_coupons = n_coupons
        self.stake_per_coupon = round(budget / n_coupons, 2)

    def build(self, value_bets: list[ValueBet]) -> list[Coupon]:
        if not value_bets:
            return []

        coupons = []

        # Coupon 1: MAX VALUE — top 2 picks by edge
        top2 = value_bets[:2]
        if top2:
            coupons.append(self._make_coupon("MAX VALUE AKO 2-fold", top2))

        # Coupon 2: STRUCTURAL — top 3 picks by edge
        top3 = value_bets[:3]
        if top3:
            coupons.append(self._make_coupon("STRUCTURAL AKO 3-fold", top3))

        # Coupon 3: DIVERSIFIED — 3 picks from different markets
        seen_markets: set[str] = set()
        diversified: list[ValueBet] = []
        for vb in value_bets:
            if vb.market_id not in seen_markets:
                diversified.append(vb)
                seen_markets.add(vb.market_id)
            if len(diversified) == 3:
                break
        if diversified:
            coupons.append(self._make_coupon("DIVERSIFIED 3-fold", diversified))

        return coupons

    def _make_coupon(self, name: str, picks: list[ValueBet]) -> Coupon:
        total_odds = 1.0
        for vb in picks:
            total_odds *= vb.sts_odds
        total_odds = round(total_odds, 2)
        potential_win = round(self.stake_per_coupon * total_odds, 2)
        return Coupon(
            name=name,
            picks=picks,
            total_odds=total_odds,
            stake=self.stake_per_coupon,
            potential_win=potential_win,
            budget=self.budget,
        )


def value_bet_to_dict(vb: ValueBet) -> dict:
    return {
        "match": f"{vb.player_a} vs {vb.player_b}",
        "player_a": vb.player_a,
        "player_b": vb.player_b,
        "surface": vb.surface,
        "tournament": vb.tournament,
        "round": vb.round_num,
        "market_id": vb.market_id,
        "market_label": vb.market_label,
        "model_prob": vb.model_prob,
        "implied_prob": vb.implied_prob,
        "sts_odds": vb.sts_odds,
        "edge": vb.edge,
        "ev": vb.ev,
        "kelly_pct": vb.kelly_pct,
        "stake_usd": vb.stake_usd,
        "auc": vb.auc,
        "confidence": vb.confidence,
    }


def coupon_to_dict(c: Coupon) -> dict:
    return {
        "name": c.name,
        "picks": [value_bet_to_dict(p) for p in c.picks],
        "total_odds": c.total_odds,
        "stake": c.stake,
        "potential_win": c.potential_win,
        "budget": c.budget,
    }
