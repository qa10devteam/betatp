"""
data/quality.py — Data validation and normalisation for betatp.io

Functions:
  - validate_serve_stats(df)         → pd.DataFrame of invalid rows
  - detect_outliers(df)              → pd.DataFrame of low-match players
  - normalize_surface(surface_str)   → "Hard" | "Clay" | "Grass"
  - normalize_tourney_level(level)   → "G" | "M" | "500" | "250" | "D" | "F"
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Surface normalisation ────────────────────────────────────────────────────

_SURFACE_MAP: dict[str, str] = {
    "hard": "Hard",
    "clay": "Clay",
    "grass": "Grass",
    "carpet": "Hard",       # Carpet retired; treat as Hard
    "indoor hard": "Hard",
    "indoor": "Hard",
    "acrylic": "Hard",
}


def normalize_surface(surface_str: Optional[str]) -> str:
    """
    Normalise raw surface string to canonical value.

    Returns
    -------
    "Hard" | "Clay" | "Grass" — defaults to "Hard" for unknown/null values.
    """
    if not surface_str or pd.isna(surface_str):
        return "Hard"
    key = str(surface_str).strip().lower()
    return _SURFACE_MAP.get(key, "Hard")


# ─── Tournament level normalisation ──────────────────────────────────────────

_LEVEL_MAP: dict[str, str] = {
    "g": "G",     # Grand Slam
    "m": "M",     # Masters 1000
    "a": "250",   # ATP legacy 'A' = non-Masters main draw → 250 bucket
    "d": "D",     # Davis Cup
    "f": "F",     # ATP Finals / Year-end
    "c": "250",   # Challenger → 250 bucket
    "s": "500",   # ATP 500 legacy code
    "500": "500",
    "250": "250",
    "masters": "M",
    "grand slam": "G",
    "grandslam": "G",
}


def normalize_tourney_level(level: Optional[str]) -> str:
    """
    Normalise raw tournament level to canonical code.

    Returns
    -------
    "G" | "M" | "500" | "250" | "D" | "F" — defaults to "250" for unknowns.
    """
    if not level or pd.isna(level):
        return "250"
    key = str(level).strip().lower()
    return _LEVEL_MAP.get(key, "250")


# ─── Serve stat validation ────────────────────────────────────────────────────

# Valid ranges per spec
_SERVE_WIN_MIN = 0.30
_SERVE_WIN_MAX = 0.95
_ACE_MIN = 0.00
_ACE_MAX = 0.30


def _serve_win_pct(row: pd.Series, prefix: str) -> Optional[float]:
    """
    Compute serve win percentage for winner ('w') or loser ('l').
    = (1stWon + 2ndWon) / svpt
    """
    svpt = row.get(f"{prefix}_svpt")
    won_1st = row.get(f"{prefix}_1stWon")
    won_2nd = row.get(f"{prefix}_2ndWon")
    if pd.isna(svpt) or svpt == 0 or pd.isna(won_1st) or pd.isna(won_2nd):
        return None
    return (won_1st + won_2nd) / svpt


def _ace_pct(row: pd.Series, prefix: str) -> Optional[float]:
    """Ace percentage = aces / svpt."""
    svpt = row.get(f"{prefix}_svpt")
    ace = row.get(f"{prefix}_ace")
    if pd.isna(svpt) or svpt == 0 or pd.isna(ace):
        return None
    return ace / svpt


def validate_serve_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Check serve statistics are within valid physiological ranges.

    Validates:
      - serve_win_pct ∈ [0.30, 0.95] for both winner and loser
      - ace_pct       ∈ [0.00, 0.30] for both winner and loser

    Parameters
    ----------
    df : pd.DataFrame
        Match DataFrame (output of load_all_matches or similar).

    Returns
    -------
    pd.DataFrame
        Subset of df rows that fail at least one validation check,
        with extra columns: issue_column, computed_value.
        Empty DataFrame if all stats are valid.
    """
    stat_cols = [
        "w_svpt", "w_1stWon", "w_2ndWon", "w_ace",
        "l_svpt", "l_1stWon", "l_2ndWon", "l_ace",
    ]
    # Only rows that have at least some stats
    mask_has_stats = df["w_svpt"].notna() | df["l_svpt"].notna()
    sub = df[mask_has_stats].copy()

    if sub.empty:
        return pd.DataFrame()

    violations: list[dict] = []

    for idx, row in sub.iterrows():
        for prefix in ("w", "l"):
            svp = _serve_win_pct(row, prefix)
            if svp is not None and not (_SERVE_WIN_MIN <= svp <= _SERVE_WIN_MAX):
                violations.append({
                    "match_id": row.get("match_id", idx),
                    "tourney_date": row.get("tourney_date"),
                    "issue_column": f"{prefix}_serve_win_pct",
                    "computed_value": round(svp, 4),
                    "valid_range": f"[{_SERVE_WIN_MIN}, {_SERVE_WIN_MAX}]",
                })

            ap = _ace_pct(row, prefix)
            if ap is not None and not (_ACE_MIN <= ap <= _ACE_MAX):
                violations.append({
                    "match_id": row.get("match_id", idx),
                    "tourney_date": row.get("tourney_date"),
                    "issue_column": f"{prefix}_ace_pct",
                    "computed_value": round(ap, 4),
                    "valid_range": f"[{_ACE_MIN}, {_ACE_MAX}]",
                })

    if violations:
        vdf = pd.DataFrame(violations)
        logger.warning(
            "validate_serve_stats: %d violations found in %d rows",
            len(vdf),
            len(sub),
        )
        return vdf

    logger.info("validate_serve_stats: all %d stat rows passed", len(sub))
    return pd.DataFrame()


# ─── Outlier detection ───────────────────────────────────────────────────────

def detect_outliers(df: pd.DataFrame, min_matches: int = 10) -> pd.DataFrame:
    """
    Identify players with fewer than `min_matches` appearances.

    Low-sample players produce unreliable Elo estimates; flag them for
    Bayesian shrinkage or exclusion in ML features.

    Parameters
    ----------
    df : pd.DataFrame
        Match DataFrame with 'winner_id' and 'loser_id' columns.
    min_matches : int
        Threshold below which a player is flagged (default: 10).

    Returns
    -------
    pd.DataFrame
        Columns: player_id, n_matches
        Sorted ascending by n_matches.
    """
    if "winner_id" not in df.columns or "loser_id" not in df.columns:
        raise ValueError("DataFrame must contain 'winner_id' and 'loser_id' columns")

    # Count appearances (wins + losses)
    wins = df["winner_id"].value_counts().rename("wins")
    losses = df["loser_id"].value_counts().rename("losses")

    counts = (
        pd.concat([wins, losses], axis=1)
        .fillna(0)
        .astype(int)
    )
    counts["n_matches"] = counts["wins"] + counts["losses"]
    counts.index.name = "player_id"
    counts = counts.reset_index()

    outliers = counts[counts["n_matches"] < min_matches].sort_values("n_matches")

    logger.info(
        "detect_outliers: %d / %d players below threshold of %d matches",
        len(outliers),
        len(counts),
        min_matches,
    )
    return outliers[["player_id", "n_matches"]].reset_index(drop=True)


# ─── Combined quality report ─────────────────────────────────────────────────

def quality_report(df: pd.DataFrame) -> dict:
    """
    Run all quality checks and return a summary dict.

    Useful for logging / monitoring pipelines.
    """
    serve_issues = validate_serve_stats(df)
    low_sample = detect_outliers(df)

    report = {
        "total_matches": len(df),
        "date_range": (
            str(df["tourney_date"].min().date()) if "tourney_date" in df.columns else "N/A",
            str(df["tourney_date"].max().date()) if "tourney_date" in df.columns else "N/A",
        ),
        "serve_stat_violations": len(serve_issues),
        "low_sample_players": len(low_sample),
        "null_surface_pct": float(df["surface"].isna().mean()) if "surface" in df.columns else None,
        "surfaces": df["surface"].value_counts().to_dict() if "surface" in df.columns else {},
        "tourney_levels": (
            df["tourney_level"].value_counts().to_dict()
            if "tourney_level" in df.columns else {}
        ),
    }
    return report
