"""
Feature Engineering — 54 features per player, 120+ per match.
Spec: feature_engineering/
Iter: 26-30
"""
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

EWMA_ALPHA = 0.15
H2H_PRIOR_ALPHA = 3.0
H2H_PRIOR_BETA = 3.0

TOURNEY_LEVEL_SCORES = {
    "G": 5.0, "M": 4.0, "500": 3.0, "250": 2.0,
    "D": 1.5, "F": 4.5, "A": 2.0, "C": 1.5,
}

ROUND_PRESSURE = {
    "R128": 0.1, "R64": 0.2, "R32": 0.3, "R16": 0.4,
    "QF": 0.6, "SF": 0.8, "F": 1.0, "BR": 0.7,
}


@dataclass
class PlayerFeatures:
    """54 features dla pojedynczego gracza przed meczem"""
    player_id: int

    # BLOK 1: Elo features (10)
    surface_elo: float = 1500.0
    overall_elo: float = 1500.0
    serve_elo: float = 1500.0
    return_elo: float = 1500.0
    surface_elo_uncertainty: float = 1.0  # 1/n_surface
    elo_momentum_30d: float = 0.0  # Elo change last 30 days
    elo_peak: float = 1500.0  # historical max
    elo_decline: float = 0.0  # current vs peak
    elo_trend_90d: float = 0.0  # linear trend last 90 days
    elo_stability: float = 0.0  # std of Elo last 20 matches

    # BLOK 2: EWMA form stats (9)
    ewma_win_pct: float = 0.5
    ewma_svw_pct: float = 0.62  # serve points won
    ewma_rpw_pct: float = 0.38  # return points won
    ewma_hold_pct: float = 0.75
    ewma_break_pct: float = 0.25
    ewma_ace_pct: float = 0.08
    ewma_df_pct: float = 0.03
    ewma_1stin_pct: float = 0.63
    ewma_1stwon_pct: float = 0.74

    # BLOK 3: Surface-specific stats (5)
    surface_win_pct: float = 0.5
    surface_svw_pct: float = 0.62
    surface_rpw_pct: float = 0.38
    surface_n_matches: int = 0
    surface_recent_form: float = 0.0  # W/L last 5 surface matches

    # BLOK 4: Serve stats (5)
    svpt_per_game: float = 4.5
    ace_per_set: float = 2.0
    df_per_set: float = 1.0
    bp_saved_pct: float = 0.60
    serve_dominance: float = 0.0  # svw - avg

    # BLOK 5: H2H Bayesian (4)
    h2h_wins: int = 0
    h2h_total: int = 0
    h2h_posterior_mean: float = 0.5  # Beta(3+wins, 3+losses) posterior
    h2h_surface_wins: int = 0

    # BLOK 6: Fatigue (4)
    fatigue_score: float = 0.0
    rest_hours: float = 72.0
    sets_last_7d: float = 0.0
    scheduling_flag: bool = False  # True if rest_hours < 14

    # BLOK 7: Tournament context (4)
    tourney_level_score: float = 2.0  # G=5,M=4,500=3,250=2
    is_indoor: bool = False
    is_high_altitude: bool = False
    round_pressure: float = 0.5  # R128=0.1 ... F=1.0

    # BLOK 8: Career arc (6)
    age: float = 26.0
    age_performance_factor: float = 1.0  # A(age) LOESS
    career_stage: str = "prime"  # young/prime/veteran/decline
    matches_ytd: int = 0
    experience_factor: float = 1.0
    is_returning_injury: bool = False


class FeatureBuilder:
    def __init__(self):
        # player_id -> dict of EWMA stats
        self._ewma_stats: dict[int, dict] = {}
        # (p1_id, p2_id) where p1 < p2 -> h2h dict
        self._h2h: dict[tuple, dict] = {}
        # player_id -> list of (date_str, elo) tuples for trend
        self._elo_history: dict[int, list] = {}
        # player_id -> metadata
        self._player_meta: dict[int, dict] = {}

    # ------------------------------------------------------------------
    # EWMA
    # ------------------------------------------------------------------

    def update_ewma(self, player_id: int, match_stats: dict) -> None:
        """Update EWMA stats after each match. alpha=0.15"""
        alpha = EWMA_ALPHA
        cur = self._ewma_stats.get(player_id, {})

        defaults = {
            "win_pct": 0.5,
            "svw_pct": 0.62,
            "rpw_pct": 0.38,
            "hold_pct": 0.75,
            "break_pct": 0.25,
            "ace_pct": 0.08,
            "df_pct": 0.03,
            "1stin_pct": 0.63,
            "1stwon_pct": 0.74,
            "svpt_per_game": 4.5,
            "ace_per_set": 2.0,
            "df_per_set": 1.0,
            "bp_saved_pct": 0.60,
        }

        # Init if first time
        if not cur:
            cur = dict(defaults)
            cur["n_matches"] = 0

        for key in defaults:
            if key in match_stats:
                cur[key] = alpha * match_stats[key] + (1 - alpha) * cur[key]

        cur["n_matches"] = cur.get("n_matches", 0) + 1
        self._ewma_stats[player_id] = cur

    def get_ewma(self, player_id: int) -> dict:
        """Return current EWMA stats for player (defaults if none)."""
        defaults = {
            "win_pct": 0.5,
            "svw_pct": 0.62,
            "rpw_pct": 0.38,
            "hold_pct": 0.75,
            "break_pct": 0.25,
            "ace_pct": 0.08,
            "df_pct": 0.03,
            "1stin_pct": 0.63,
            "1stwon_pct": 0.74,
            "svpt_per_game": 4.5,
            "ace_per_set": 2.0,
            "df_per_set": 1.0,
            "bp_saved_pct": 0.60,
            "n_matches": 0,
        }
        cur = self._ewma_stats.get(player_id, {})
        result = dict(defaults)
        result.update(cur)
        return result

    # ------------------------------------------------------------------
    # H2H Bayesian
    # ------------------------------------------------------------------

    def record_h2h(self, player_a: int, player_b: int, winner_id: int,
                   surface: Optional[str] = None, match_date: Optional[date] = None) -> None:
        """Record a H2H result between two players."""
        key = (min(player_a, player_b), max(player_a, player_b))
        if key not in self._h2h:
            self._h2h[key] = {
                "wins_a": 0, "wins_b": 0,
                "surface_wins_a": {}, "surface_wins_b": {},
                "dates": [],
            }
        record = self._h2h[key]
        a_wins = (winner_id == player_a)
        if a_wins:
            record["wins_a"] += 1
        else:
            record["wins_b"] += 1

        if surface:
            surf = surface.lower()
            if a_wins:
                record["surface_wins_a"][surf] = record["surface_wins_a"].get(surf, 0) + 1
            else:
                record["surface_wins_b"][surf] = record["surface_wins_b"].get(surf, 0) + 1

    def compute_h2h_posterior(self, player_a: int, player_b: int,
                               surface: Optional[str] = None) -> dict:
        """
        Beta(3+wins_A, 3+losses_A) posterior. Surface-filtered if surface given.
        Returns dict with posterior_mean, wins_a, wins_b, total.
        """
        key = (min(player_a, player_b), max(player_a, player_b))
        record = self._h2h.get(key, {})

        # Determine orientation: are we asking from player_a's perspective?
        a_is_min = (player_a == min(player_a, player_b))

        if not record:
            wins_a = 0
            wins_b = 0
        else:
            if a_is_min:
                wins_a_raw = record.get("wins_a", 0)
                wins_b_raw = record.get("wins_b", 0)
            else:
                wins_a_raw = record.get("wins_b", 0)
                wins_b_raw = record.get("wins_a", 0)

            if surface:
                surf = surface.lower()
                if a_is_min:
                    wins_a = record.get("surface_wins_a", {}).get(surf, 0)
                    wins_b = record.get("surface_wins_b", {}).get(surf, 0)
                else:
                    wins_a = record.get("surface_wins_b", {}).get(surf, 0)
                    wins_b = record.get("surface_wins_a", {}).get(surf, 0)
            else:
                wins_a = wins_a_raw
                wins_b = wins_b_raw

        alpha_post = H2H_PRIOR_ALPHA + wins_a
        beta_post = H2H_PRIOR_BETA + wins_b
        posterior_mean = alpha_post / (alpha_post + beta_post)

        return {
            "posterior_mean": posterior_mean,
            "wins_a": wins_a,
            "wins_b": wins_b,
            "total": wins_a + wins_b,
            "surface_wins_a": wins_a if surface else record.get("surface_wins_a", {}).get("", 0) if record else 0,
        }

    # ------------------------------------------------------------------
    # Age performance factor
    # ------------------------------------------------------------------

    def age_performance_factor(self, age: float) -> float:
        """
        LOESS approximation from ATP data 1990-2025:
        < 22: 0.92, 22-24: 0.97, 25-27: 1.00, 28-30: 0.98,
        31-33: 0.95, 34-36: 0.91, > 36: 0.85
        """
        # Piecewise linear LOESS approximation
        # Defined as flat ranges then interpolated at boundaries
        if age < 22.0:
            return 0.92
        elif age < 25.0:
            # 22-25: interpolate 0.92 -> 1.00 (we set start of prime at 25)
            t = (age - 22.0) / (25.0 - 22.0)
            return 0.92 + t * (1.00 - 0.92)
        elif age <= 27.0:
            return 1.00
        elif age <= 30.0:
            t = (age - 27.0) / (30.0 - 27.0)
            return 1.00 + t * (0.98 - 1.00)
        elif age <= 33.0:
            t = (age - 30.0) / (33.0 - 30.0)
            return 0.98 + t * (0.95 - 0.98)
        elif age <= 36.0:
            t = (age - 33.0) / (36.0 - 33.0)
            return 0.95 + t * (0.91 - 0.95)
        else:
            t = min((age - 36.0) / 4.0, 1.0)
            return 0.91 + t * (0.85 - 0.91)

    def _career_stage(self, age: float) -> str:
        if age < 22:
            return "young"
        elif age < 28:
            return "prime"
        elif age < 33:
            return "veteran"
        else:
            return "decline"

    # ------------------------------------------------------------------
    # Fatigue
    # ------------------------------------------------------------------

    def fatigue_score(self, sets_7d: float, rest_hours: float,
                      tz_crossings: int = 0) -> float:
        """
        FatigueScore = 0.3*SetsLoad + 0.4*RestPenalty + 0.2*TravelStress + 0.1*TimezoneStress
        """
        # SetsLoad: normalized over typical week (max ~15 sets)
        sets_load = min(sets_7d / 15.0, 1.0)

        # RestPenalty: exponential decay — very low rest -> high penalty
        # rest_hours=72 -> penalty=0, rest_hours=0 -> penalty=1
        rest_penalty = max(0.0, 1.0 - rest_hours / 72.0)

        # TravelStress: assume 0 unless we have data (tz_crossings proxy)
        travel_stress = min(tz_crossings / 12.0, 1.0) if tz_crossings > 0 else 0.0

        # TimezoneStress
        tz_stress = min(tz_crossings / 6.0, 1.0) if tz_crossings > 0 else 0.0

        score = (0.3 * sets_load + 0.4 * rest_penalty +
                 0.2 * travel_stress + 0.1 * tz_stress)
        return float(np.clip(score, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Build features
    # ------------------------------------------------------------------

    def build_features(
        self, player_id: int, opponent_id: int,
        surface: str, tourney_level: str, best_of: int,
        match_date: date, elo_engine=None
    ) -> dict:
        """
        Build full feature vector for one player vs opponent.
        Returns dict {feature_name: value} for LightGBM input.
        """
        feats: dict = {}

        # --- Elo features ---
        if elo_engine is not None:
            pdata = elo_engine.players.get(player_id)
            if pdata:
                surf_norm = surface.lower() if surface else "hard"
                feats["surface_elo"] = getattr(pdata, surf_norm, pdata.overall)
                feats["overall_elo"] = pdata.overall
                feats["serve_elo"] = pdata.serve
                feats["return_elo"] = pdata.return_elo
                n_surf = getattr(pdata, f"n_{surf_norm}", 0)
                feats["surface_elo_uncertainty"] = 1.0 / max(n_surf, 1)
            else:
                feats.update({
                    "surface_elo": 1500.0, "overall_elo": 1500.0,
                    "serve_elo": 1500.0, "return_elo": 1500.0,
                    "surface_elo_uncertainty": 1.0,
                })
        else:
            feats.update({
                "surface_elo": 1500.0, "overall_elo": 1500.0,
                "serve_elo": 1500.0, "return_elo": 1500.0,
                "surface_elo_uncertainty": 1.0,
            })

        feats["elo_momentum_30d"] = 0.0
        feats["elo_peak"] = feats["overall_elo"]
        feats["elo_decline"] = 0.0
        feats["elo_trend_90d"] = 0.0
        feats["elo_stability"] = 0.0

        # --- EWMA form ---
        ewma = self.get_ewma(player_id)
        feats["ewma_win_pct"] = ewma["win_pct"]
        feats["ewma_svw_pct"] = ewma["svw_pct"]
        feats["ewma_rpw_pct"] = ewma["rpw_pct"]
        feats["ewma_hold_pct"] = ewma["hold_pct"]
        feats["ewma_break_pct"] = ewma["break_pct"]
        feats["ewma_ace_pct"] = ewma["ace_pct"]
        feats["ewma_df_pct"] = ewma["df_pct"]
        feats["ewma_1stin_pct"] = ewma["1stin_pct"]
        feats["ewma_1stwon_pct"] = ewma["1stwon_pct"]

        # --- Surface stats ---
        feats["surface_win_pct"] = 0.5
        feats["surface_svw_pct"] = ewma["svw_pct"]
        feats["surface_rpw_pct"] = ewma["rpw_pct"]
        feats["surface_n_matches"] = 0
        feats["surface_recent_form"] = 0.0

        # --- Serve stats ---
        feats["svpt_per_game"] = ewma["svpt_per_game"]
        feats["ace_per_set"] = ewma["ace_per_set"]
        feats["df_per_set"] = ewma["df_per_set"]
        feats["bp_saved_pct"] = ewma["bp_saved_pct"]
        feats["serve_dominance"] = ewma["svw_pct"] - 0.62

        # --- H2H ---
        h2h = self.compute_h2h_posterior(player_id, opponent_id, surface=surface)
        feats["h2h_wins"] = h2h["wins_a"]
        feats["h2h_total"] = h2h["total"]
        feats["h2h_posterior_mean"] = h2h["posterior_mean"]
        feats["h2h_surface_wins"] = h2h["wins_a"]  # surface-filtered

        # --- Fatigue ---
        meta = self._player_meta.get(player_id, {})
        sets_7d = meta.get("sets_last_7d", 0.0)
        rest_h = meta.get("rest_hours", 72.0)
        tz = meta.get("tz_crossings", 0)
        fat = self.fatigue_score(sets_7d, rest_h, tz)
        feats["fatigue_score"] = fat
        feats["rest_hours"] = rest_h
        feats["sets_last_7d"] = sets_7d
        feats["scheduling_flag"] = int(rest_h < 14)

        # --- Tournament context ---
        feats["tourney_level_score"] = TOURNEY_LEVEL_SCORES.get(tourney_level, 2.0)
        feats["is_indoor"] = int(meta.get("is_indoor", False))
        feats["is_high_altitude"] = int(meta.get("is_high_altitude", False))
        feats["round_pressure"] = meta.get("round_pressure", 0.5)

        # --- Career arc ---
        dob = meta.get("dob")
        if dob and isinstance(dob, date):
            age = (match_date - dob).days / 365.25
        else:
            age = meta.get("age", 26.0)
        feats["age"] = age
        feats["age_performance_factor"] = self.age_performance_factor(age)
        feats["career_stage_encoded"] = {
            "young": 0, "prime": 1, "veteran": 2, "decline": 3
        }.get(self._career_stage(age), 1)
        feats["matches_ytd"] = meta.get("matches_ytd", 0)
        feats["experience_factor"] = min(ewma["n_matches"] / 100.0, 1.0)
        feats["is_returning_injury"] = int(meta.get("is_returning_injury", False))

        return feats

    def build_match_features(
        self, player_a: int, player_b: int, surface: str,
        tourney_level: str, best_of: int, match_date: date,
        elo_engine=None
    ) -> dict:
        """
        Build features for a full match as one flat vector.
        Prefix 'a_' for player_a, 'b_' for player_b + diff features.
        ~120+ total features.
        """
        feats_a = self.build_features(
            player_a, player_b, surface, tourney_level, best_of, match_date, elo_engine
        )
        feats_b = self.build_features(
            player_b, player_a, surface, tourney_level, best_of, match_date, elo_engine
        )

        combined: dict = {}

        for k, v in feats_a.items():
            combined[f"a_{k}"] = v
        for k, v in feats_b.items():
            combined[f"b_{k}"] = v

        # Diff features for key numeric stats
        numeric_diff_keys = [
            "surface_elo", "overall_elo", "serve_elo", "return_elo",
            "ewma_win_pct", "ewma_svw_pct", "ewma_rpw_pct",
            "h2h_posterior_mean", "fatigue_score", "age_performance_factor",
        ]
        for k in numeric_diff_keys:
            va = feats_a.get(k, 0.0)
            vb = feats_b.get(k, 0.0)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                combined[f"diff_{k}"] = va - vb

        # Match-level context
        combined["surface"] = surface.lower() if surface else "hard"
        combined["tourney_level"] = tourney_level
        combined["best_of"] = best_of
        combined["match_date"] = match_date.isoformat()

        return combined
