"""
PreMatchPredictor — betatp.io
Blends Elo, Monte Carlo, and optional ML ensemble predictions into a single
probability estimate for a tennis match outcome.

Spec: AX-05, AX-06, PRED-01..PRED-04
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default blend weights
_ELO_WEIGHT_COLD = 0.90   # n_matches < 10  (cold start)
_ELO_WEIGHT_WARM = 0.30   # n_matches >= 10 (enough data → trust ML more)
_ML_WEIGHT_WARM  = 0.70

# Minimum number of MC simulations to report MC outputs
_MIN_MC_SIMS = 1_000


class PreMatchPredictor:
    """
    Orchestrates pre-match win-probability estimation.

    Priority:
      1. If ml_ensemble is available and player has >= 10 matches:
         blend(Elo 30%, ML 70%)
      2. Cold start (< 10 matches) or no ML:
         blend(Elo 90%, [ML 10% if available else 0%])
      3. Monte Carlo refines serve-side probability for the Elo component
         (when mc_engine is provided).
    """

    def __init__(
        self,
        elo_engine,
        mc_engine,
        feature_builder=None,
        ml_ensemble=None,
    ) -> None:
        """
        Parameters
        ----------
        elo_engine : EloEngine
            Initialised EloEngine (engine.elo).
        mc_engine : MonteCarloEngine
            Initialised MonteCarloEngine (engine.monte_carlo).
        feature_builder : FeatureBuilder | None
            Optional FeatureBuilder used to generate ML feature vectors.
        ml_ensemble : object | None
            Optional trained ML ensemble with a `predict_proba(X)` interface.
            If None, only Elo (+ MC) is used.
        """
        self.elo_engine = elo_engine
        self.mc_engine = mc_engine
        self.feature_builder = feature_builder
        self.ml_ensemble = ml_ensemble

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        player_a: str,
        player_b: str,
        surface: str,
        tourney_level: str = "ATP",
    ) -> dict:
        """
        Predict win probabilities for a pre-match encounter.

        Parameters
        ----------
        player_a, player_b : str
            Player identifiers (same as used in EloEngine).
        surface : str
            Court surface: 'hard' | 'clay' | 'grass'.
        tourney_level : str
            Tournament level code, e.g. 'G', 'M', '500', '250'.

        Returns
        -------
        dict with keys:
            player_a, player_b, surface,
            p_win_a, p_win_b,
            elo_rating_a, elo_rating_b, elo_diff,
            confidence, method, mc_outputs
        """
        # ── 1. Elo ratings ────────────────────────────────────────────
        elo_a_obj = self.elo_engine.get_or_create(player_a)
        elo_b_obj = self.elo_engine.get_or_create(player_b)

        elo_rating_a = self.elo_engine.get_blended_surface_elo(player_a, surface)
        elo_rating_b = self.elo_engine.get_blended_surface_elo(player_b, surface)
        elo_diff = elo_rating_a - elo_rating_b

        n_matches_a = elo_a_obj.n_matches
        n_matches_b = elo_b_obj.n_matches
        n_matches = min(n_matches_a, n_matches_b)  # conservative: use the smaller

        # ── 2. Pure Elo probability ────────────────────────────────────
        p_elo = self._elo_predict(player_a, player_b, surface)

        # ── 3. Optional MC refinement ─────────────────────────────────
        mc_outputs: dict = {}
        try:
            mc_outputs = self._run_mc(player_a, player_b, surface, tourney_level)
            # MC provides an independent win-probability estimate
            p_mc = mc_outputs.get("p_win_a", p_elo)
            # Blend MC into Elo component (50/50 between pure elo and MC)
            p_elo_refined = 0.5 * p_elo + 0.5 * p_mc
        except Exception as exc:  # noqa: BLE001
            logger.warning("MC simulation failed: %s — falling back to pure Elo.", exc)
            p_elo_refined = p_elo

        # ── 4. Optional ML probability ────────────────────────────────
        p_ml: Optional[float] = None
        if self.ml_ensemble is not None and self.feature_builder is not None:
            try:
                p_ml = self._ml_predict(player_a, player_b, surface, tourney_level)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ML ensemble prediction failed: %s", exc)
                p_ml = None

        # ── 5. Blend ──────────────────────────────────────────────────
        p_win_a = self._blend_prediction(p_elo_refined, p_ml=p_ml, n_matches=n_matches)
        p_win_b = 1.0 - p_win_a

        # ── 6. Confidence & method tag ────────────────────────────────
        confidence, method = self._assess_confidence(
            n_matches=n_matches,
            p_ml=p_ml,
            mc_available=bool(mc_outputs),
        )

        return {
            "player_a": player_a,
            "player_b": player_b,
            "surface": surface,
            "p_win_a": round(p_win_a, 6),
            "p_win_b": round(p_win_b, 6),
            "elo_rating_a": round(elo_rating_a, 2),
            "elo_rating_b": round(elo_rating_b, 2),
            "elo_diff": round(elo_diff, 2),
            "confidence": confidence,
            "method": method,
            "mc_outputs": mc_outputs,
        }

    def predict_batch(self, matches: list[dict]) -> list[dict]:
        """
        Predict a list of matches.

        Each dict in *matches* must contain:
            player_a, player_b, surface
        and optionally:
            tourney_level  (default 'ATP')

        Returns list of prediction dicts in the same order.
        """
        results = []
        for match in matches:
            try:
                result = self.predict(
                    player_a=match["player_a"],
                    player_b=match["player_b"],
                    surface=match["surface"],
                    tourney_level=match.get("tourney_level", "ATP"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "predict_batch: error on %s vs %s — %s",
                    match.get("player_a"),
                    match.get("player_b"),
                    exc,
                )
                result = {
                    "player_a": match.get("player_a"),
                    "player_b": match.get("player_b"),
                    "surface": match.get("surface"),
                    "error": str(exc),
                }
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _elo_predict(self, player_a: str, player_b: str, surface: str) -> float:
        """
        Pure Elo win probability for player_a over player_b on *surface*.

        Uses the blended surface Elo (alpha*surface + (1-alpha)*overall)
        from EloEngine.get_blended_surface_elo().

        Returns
        -------
        float
            P(player_a wins) in [0, 1].
        """
        ra = self.elo_engine.get_blended_surface_elo(player_a, surface)
        rb = self.elo_engine.get_blended_surface_elo(player_b, surface)
        return self.elo_engine.win_probability(ra, rb)

    def _blend_prediction(
        self,
        p_elo: float,
        p_ml: Optional[float] = None,
        n_matches: Optional[int] = None,
    ) -> float:
        """
        Blend Elo (+ MC-refined) and ML predictions.

        Cold-start logic (based on the *lesser* player's match count):
          - n_matches < 10  → elo_weight = 0.90, ml_weight = 0.10
          - n_matches >= 10 → elo_weight = 0.30, ml_weight = 0.70

        If p_ml is None, Elo weight becomes 1.0 regardless.

        Parameters
        ----------
        p_elo : float
            Elo (possibly MC-blended) probability for player_a.
        p_ml : float | None
            ML ensemble probability for player_a (or None if unavailable).
        n_matches : int | None
            Minimum number of matches across both players (cold-start guard).

        Returns
        -------
        float
            Final blended probability, clamped to [0.01, 0.99].
        """
        if p_ml is None:
            return float(max(0.01, min(0.99, p_elo)))

        cold_start = (n_matches is not None) and (n_matches < 10)

        if cold_start:
            elo_weight = _ELO_WEIGHT_COLD
            ml_weight = 1.0 - elo_weight   # 0.10
        else:
            elo_weight = _ELO_WEIGHT_WARM   # 0.30
            ml_weight = _ML_WEIGHT_WARM     # 0.70

        p_blended = elo_weight * p_elo + ml_weight * p_ml
        return float(max(0.01, min(0.99, p_blended)))

    def _run_mc(
        self,
        player_a: str,
        player_b: str,
        surface: str,
        tourney_level: str,
    ) -> dict:
        """
        Run a Monte Carlo simulation for this match and return a summary dict.

        Uses serve/return Elo ratings to derive approximate serve-win percentages
        for each player, then passes them to MonteCarloEngine.simulate_match().

        Returns
        -------
        dict with keys:
            p_win_a, p_win_b, expected_sets, expected_games,
            expected_duration_minutes, p_tiebreak_any,
            confidence_interval_95, set_scores
        """
        from engine.monte_carlo import MatchConfig

        a_obj = self.elo_engine.get_or_create(player_a)
        b_obj = self.elo_engine.get_or_create(player_b)

        # Derive approximate serve-win probability from serve/return Elo ratings
        # P(server A wins a serve point) ≈ win_prob(serve_A, return_B)
        p_serve_a = self.elo_engine.win_probability(a_obj.serve, b_obj.return_elo)
        p_serve_b = self.elo_engine.win_probability(b_obj.serve, a_obj.return_elo)

        # Clamp to realistic tennis range [0.50, 0.80]
        p_serve_a = max(0.50, min(0.80, p_serve_a))
        p_serve_b = max(0.50, min(0.80, p_serve_b))

        # Grand Slams are best-of-5; everything else best-of-3
        best_of = 5 if tourney_level == "G" else 3

        config = MatchConfig(
            p_serve_a=p_serve_a,
            p_serve_b=p_serve_b,
            best_of=best_of,  # type: ignore[arg-type]
        )
        sim = self.mc_engine.simulate_match(config)

        return {
            "p_win_a": sim.p_win_a,
            "p_win_b": sim.p_win_b,
            "expected_sets": sim.expected_sets,
            "expected_games": sim.expected_games,
            "expected_duration_minutes": sim.expected_duration_minutes,
            "p_tiebreak_any": sim.p_tiebreak_any,
            "confidence_interval_95": sim.confidence_interval_95,
            "set_scores": sim.p_set_scores,
            "p_serve_a_used": p_serve_a,
            "p_serve_b_used": p_serve_b,
            "n_simulations": sim.n_simulations,
        }

    def _ml_predict(
        self,
        player_a: str,
        player_b: str,
        surface: str,
        tourney_level: str,
    ) -> float:
        """
        Generate an ML ensemble win-probability for player_a.

        Builds feature vector via FeatureBuilder, then calls
        ml_ensemble.predict_proba(X).

        Returns
        -------
        float  P(player_a wins) according to ML ensemble.
        """
        from datetime import date as _date

        if self.feature_builder is None or self.ml_ensemble is None:
            raise RuntimeError("feature_builder and ml_ensemble are required for ML prediction")

        feats = self.feature_builder.build_match_features(
            player_a=player_a,
            player_b=player_b,
            surface=surface,
            tourney_level=tourney_level,
            best_of=3,
            match_date=_date.today(),
            elo_engine=self.elo_engine,
        )

        # Convert to a 2-D array for sklearn-compatible interface
        import numpy as np
        feature_values = [
            v for v in feats.values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        X = np.array(feature_values, dtype=float).reshape(1, -1)

        proba = self.ml_ensemble.predict_proba(X)
        # Assume binary classifier: class 1 = player_a wins
        if hasattr(proba, "__len__") and len(proba[0]) >= 2:
            return float(proba[0][1])
        return float(proba[0][0])

    def _assess_confidence(
        self,
        n_matches: int,
        p_ml: Optional[float],
        mc_available: bool,
    ) -> tuple[str, str]:
        """
        Return a (confidence_label, method_tag) pair.

        confidence labels: 'low' | 'medium' | 'high'
        method tags:       'elo_only' | 'elo_mc' | 'elo_ml' | 'elo_mc_ml'
        """
        if n_matches < 10:
            confidence = "low"
        elif n_matches < 30:
            confidence = "medium"
        else:
            confidence = "high"

        if p_ml is not None and mc_available:
            method = "elo_mc_ml"
        elif p_ml is not None:
            method = "elo_ml"
        elif mc_available:
            method = "elo_mc"
        else:
            method = "elo_only"

        return confidence, method
