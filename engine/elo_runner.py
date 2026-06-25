"""
Elo Runner — processes a DataFrame of matches chronologically
and updates the EloEngine state.
"""
from __future__ import annotations

import pandas as pd
from datetime import date

from engine.elo import EloEngine


def compute_all_elos(matches_df: pd.DataFrame, elo_engine: EloEngine) -> EloEngine:
    """
    Process all matches chronologically and update Elo ratings.

    Args:
        matches_df: DataFrame with columns:
            winner_id, loser_id, surface, tourney_level, tourney_date,
            w_svpt, w_1stWon, w_2ndWon, l_svpt, l_1stWon, l_2ndWon
        elo_engine: EloEngine instance to update

    Returns:
        Updated EloEngine
    """
    df = matches_df.copy()

    # Sort chronologically
    df = df.sort_values("tourney_date", ascending=True, na_position="last")

    for _, row in df.iterrows():
        winner_id = row.get("winner_id")
        loser_id = row.get("loser_id")

        # Skip rows with missing player IDs
        if pd.isna(winner_id) or pd.isna(loser_id):
            continue

        winner_id = str(winner_id).strip()
        loser_id = str(loser_id).strip()

        surface = row.get("surface", "Hard")
        tourney_level = row.get("tourney_level", "250")

        tourney_date = row.get("tourney_date")
        if pd.isna(tourney_date):
            continue
        if isinstance(tourney_date, str):
            match_date = date.fromisoformat(tourney_date[:10])
        elif hasattr(tourney_date, "date"):
            match_date = tourney_date.date()
        elif isinstance(tourney_date, date):
            match_date = tourney_date
        else:
            continue

        def _safe_int(val) -> int | None:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            return int(val)

        w_svpt = _safe_int(row.get("w_svpt"))
        w_1stWon = _safe_int(row.get("w_1stWon"))
        w_2ndWon = _safe_int(row.get("w_2ndWon"))
        l_svpt = _safe_int(row.get("l_svpt"))
        l_1stWon = _safe_int(row.get("l_1stWon"))
        l_2ndWon = _safe_int(row.get("l_2ndWon"))

        elo_engine.update_match(
            winner_id=winner_id,
            loser_id=loser_id,
            surface=surface,
            tourney_level=tourney_level,
            match_date=match_date,
            w_svpt=w_svpt,
            w_1stWon=w_1stWon,
            w_2ndWon=w_2ndWon,
            l_svpt=l_svpt,
            l_1stWon=l_1stWon,
            l_2ndWon=l_2ndWon,
        )

    return elo_engine
