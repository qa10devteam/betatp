"""
derivative_scanner.py — Scan derivative tennis markets for value on betatp.io

Uses MonteCarloEngine (engine.monte_carlo) to derive model probabilities for:
  • Total games over/under
  • Tiebreak occurrence
  • Set-score betting

MonteCarloEngine.simulate_match(config: MatchConfig) -> SimulationResult
  MatchConfig:     p_serve_a, p_serve_b, best_of (3|5), final_set_format
  SimulationResult: p_set_scores, p_tiebreak_any, expected_games, ...
"""

from __future__ import annotations

import logging
import math
import sys
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import of engine types — tolerates being run before package install.
# ---------------------------------------------------------------------------

def _import_engine():
    """Return (MonteCarloEngine, MatchConfig) classes."""
    try:
        from engine.monte_carlo import MonteCarloEngine, MatchConfig  # type: ignore
        return MonteCarloEngine, MatchConfig
    except ImportError:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from engine.monte_carlo import MonteCarloEngine, MatchConfig  # type: ignore
        return MonteCarloEngine, MatchConfig


# ---------------------------------------------------------------------------
# EV / odds helpers
# ---------------------------------------------------------------------------

def _ev_from_prob_odds(model_p: float, bk_odds: float) -> float:
    """EV = model_p * bk_odds - 1  (for decimal odds)."""
    return model_p * bk_odds - 1.0


def _bk_p_from_odds(bk_odds: float) -> float:
    """Bookmaker's raw (vig-inclusive) implied probability."""
    if bk_odds <= 0:
        raise ValueError(f"Decimal odds must be positive, got {bk_odds}")
    return 1.0 / bk_odds


def _recommendation(ev: float) -> str:
    if ev >= 0.10:
        return "STRONG BET"
    if ev >= 0.06:
        return "BET"
    if ev >= 0.04:
        return "CONSIDER"
    return "PASS"


# ---------------------------------------------------------------------------
# DerivativeScanner
# ---------------------------------------------------------------------------

class DerivativeScanner:
    """
    Scans derivative markets for positive expected value.

    Parameters
    ----------
    n_simulations : int
        Number of Monte Carlo iterations per scan call (default 20 000).
    ev_threshold  : float
        Minimum EV (fraction, e.g. 0.04 = 4 %) to surface a result.
    """

    EV_THRESHOLD: float = 0.04

    def __init__(
        self,
        n_simulations: int   = 20_000,
        ev_threshold:  float = EV_THRESHOLD,
    ):
        self.n_simulations = n_simulations
        self.ev_threshold  = ev_threshold
        self._MCEngine, self._MatchConfig = _import_engine()

    # ------------------------------------------------------------------
    # Internal: run simulation
    # ------------------------------------------------------------------

    def _run_simulation(self, match: dict):
        """Build a MatchConfig from match dict, run MC, return SimulationResult."""
        config = self._MatchConfig(
            p_serve_a=match["p_serve_a"],
            p_serve_b=match["p_serve_b"],
            best_of=match.get("best_of", 3),
            final_set_format=match.get("final_set_format", "tiebreak"),
        )
        engine = self._MCEngine(n_simulations=self.n_simulations)
        return engine.simulate_match(config)

    # ------------------------------------------------------------------
    # scan_total_games
    # ------------------------------------------------------------------

    def scan_total_games(
        self,
        match:          dict,
        bk_line:        float,
        bk_odds_over:   float,
        bk_odds_under:  float,
    ) -> List[Dict]:
        """
        Scan over/under total games market.

        Parameters
        ----------
        match         : dict  — p_serve_a, p_serve_b, best_of (default 3)
        bk_line       : float — bookmaker's total-games line (e.g. 21.5)
        bk_odds_over  : float — decimal odds for OVER
        bk_odds_under : float — decimal odds for UNDER

        Returns
        -------
        List of value-positive dicts with keys:
            market, ev, model_p, bk_p, bk_odds, recommendation
        """
        sim = self._run_simulation(match)
        e_games: float    = sim.expected_games
        set_scores: dict  = sim.p_set_scores      # {'2-0': 0.35, '2-1': 0.40, ...}

        model_p_over, model_p_under = self._estimate_over_under(
            set_scores=set_scores,
            e_games=e_games,
            bk_line=bk_line,
            match=match,
        )

        output: List[Dict] = []
        for side, model_p, bk_odds in (
            ("OVER",  model_p_over,  bk_odds_over),
            ("UNDER", model_p_under, bk_odds_under),
        ):
            bk_p = _bk_p_from_odds(bk_odds)
            ev   = _ev_from_prob_odds(model_p, bk_odds)

            logger.debug(
                "TotalGames %s | line=%.1f | model_p=%.4f | bk_p=%.4f | EV=%.4f",
                side, bk_line, model_p, bk_p, ev,
            )

            if ev > self.ev_threshold:
                output.append({
                    "market":         f"Total Games {side} {bk_line}",
                    "ev":             round(ev, 6),
                    "model_p":        round(model_p, 6),
                    "bk_p":           round(bk_p, 6),
                    "bk_odds":        bk_odds,
                    "recommendation": _recommendation(ev),
                })

        return output

    def _estimate_over_under(
        self,
        set_scores: dict,
        e_games:    float,
        bk_line:    float,
        match:      dict,
    ) -> Tuple[float, float]:
        """
        Estimate P(total_games > bk_line) and P(total_games <= bk_line).

        Strategy:
        - Use the set-score distribution + typical median game totals per outcome.
        - Fall back to a Gaussian approximation around e_games if set_scores empty.
        """
        if not set_scores:
            sigma = 2.5
            z = (bk_line - e_games) / sigma
            p_under = 1.0 / (1.0 + math.exp(-1.7 * z))   # Φ(z) logistic approx
            return 1.0 - p_under, p_under

        best_of = match.get("best_of", 3)
        # Approximate median game totals per set-score
        if best_of == 5:
            median_games: Dict[str, float] = {
                "3-0": 33.0, "3-1": 42.0, "3-2": 51.0,
                "0-3": 33.0, "1-3": 42.0, "2-3": 51.0,
            }
        else:
            median_games = {
                "2-0": 22.0, "2-1": 31.0,
                "0-2": 22.0, "1-2": 31.0,
            }

        p_over  = 0.0
        p_under = 0.0
        covered = 0.0

        for score, prob in set_scores.items():
            g = median_games.get(score, e_games)
            if g > bk_line:
                p_over  += prob
            elif g < bk_line:
                p_under += prob
            else:
                # Exactly on the line — split
                p_over  += prob * 0.5
                p_under += prob * 0.5
            covered += prob

        if covered > 0:
            p_over  /= covered
            p_under /= covered

        return p_over, p_under

    # ------------------------------------------------------------------
    # scan_tiebreak
    # ------------------------------------------------------------------

    def scan_tiebreak(
        self,
        match:   dict,
        bk_p_tb: float,
        bk_odds: float,
    ) -> dict:
        """
        Scan the 'tiebreak in match' market.

        Parameters
        ----------
        match    : dict  — p_serve_a, p_serve_b, best_of
        bk_p_tb  : float — bookmaker's quoted P(tiebreak occurs) (0–1).
                           Pass 0 to derive it solely from bk_odds.
        bk_odds  : float — decimal odds for "Yes — tiebreak occurs"

        Returns
        -------
        dict with: market, ev, model_p, bk_p, bk_odds, recommendation
        Returns empty dict {} if EV is below threshold.
        """
        sim      = self._run_simulation(match)
        model_p: float = sim.p_tiebreak_any
        bk_p    = _bk_p_from_odds(bk_odds) if bk_p_tb <= 0 else float(bk_p_tb)
        ev      = _ev_from_prob_odds(model_p, bk_odds)

        logger.debug(
            "Tiebreak | model_p=%.4f | bk_p=%.4f | bk_odds=%.2f | EV=%.4f",
            model_p, bk_p, bk_odds, ev,
        )

        if ev <= self.ev_threshold:
            return {}

        return {
            "market":         "Tiebreak in Match",
            "ev":             round(ev, 6),
            "model_p":        round(model_p, 6),
            "bk_p":           round(bk_p, 6),
            "bk_odds":        bk_odds,
            "recommendation": _recommendation(ev),
        }

    # ------------------------------------------------------------------
    # scan_set_betting
    # ------------------------------------------------------------------

    def scan_set_betting(
        self,
        match:    dict,
        set_odds: dict,
    ) -> List[Dict]:
        """
        Scan set-score betting markets.

        Parameters
        ----------
        match    : dict — p_serve_a, p_serve_b, best_of
        set_odds : dict — e.g. {'2-0': 2.10, '2-1': 3.20, '0-2': 4.50, '1-2': 5.80}

        Returns
        -------
        List of value-positive dicts (EV > ev_threshold), sorted by EV desc.
            market, ev, model_p, bk_p, bk_odds, recommendation
        """
        sim        = self._run_simulation(match)
        set_scores = sim.p_set_scores   # {'2-0': 0.35, '2-1': 0.40, ...}

        output: List[Dict] = []

        for score, bk_odds in set_odds.items():
            model_p = set_scores.get(score, 0.0)
            if model_p <= 0:
                logger.debug("Set score %s not in MC results — skipping", score)
                continue

            bk_p = _bk_p_from_odds(bk_odds)
            ev   = _ev_from_prob_odds(model_p, bk_odds)

            logger.debug(
                "SetBetting %s | model_p=%.4f | bk_p=%.4f | bk_odds=%.2f | EV=%.4f",
                score, model_p, bk_p, bk_odds, ev,
            )

            if ev > self.ev_threshold:
                output.append({
                    "market":         f"Set Score {score}",
                    "ev":             round(ev, 6),
                    "model_p":        round(model_p, 6),
                    "bk_p":           round(bk_p, 6),
                    "bk_odds":        bk_odds,
                    "recommendation": _recommendation(ev),
                })

        output.sort(key=lambda d: d["ev"], reverse=True)
        return output

    # ------------------------------------------------------------------
    # Convenience: scan all markets at once
    # ------------------------------------------------------------------

    def scan_all(
        self,
        match:              dict,
        total_games_config: Optional[dict] = None,
        tiebreak_config:    Optional[dict] = None,
        set_odds:           Optional[dict] = None,
    ) -> Dict[str, list]:
        """
        Run all configured scanners and return a combined result dict.

        Parameters
        ----------
        match               : dict — match parameters
        total_games_config  : dict — keys: bk_line, bk_odds_over, bk_odds_under
        tiebreak_config     : dict — keys: bk_p_tb (optional), bk_odds
        set_odds            : dict — score → decimal odds

        Returns
        -------
        dict with keys: 'total_games', 'tiebreak', 'set_betting'
        """
        output: Dict[str, list] = {
            "total_games": [],
            "tiebreak":    [],
            "set_betting": [],
        }

        if total_games_config:
            output["total_games"] = self.scan_total_games(
                match=match,
                bk_line=total_games_config["bk_line"],
                bk_odds_over=total_games_config["bk_odds_over"],
                bk_odds_under=total_games_config["bk_odds_under"],
            )

        if tiebreak_config:
            tb = self.scan_tiebreak(
                match=match,
                bk_p_tb=tiebreak_config.get("bk_p_tb", 0.0),
                bk_odds=tiebreak_config["bk_odds"],
            )
            if tb:
                output["tiebreak"] = [tb]

        if set_odds:
            output["set_betting"] = self.scan_set_betting(
                match=match,
                set_odds=set_odds,
            )

        return output
