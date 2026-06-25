"""
data/loader.py — TML-Database CSV ingestion pipeline for betatp.io

Loads all ATP match CSV files (YYYY.csv, 1968-2026) from TML-Database directory.
Provides:
  - load_all_matches(tml_path)      -> pd.DataFrame  (all ~198k matches)
  - load_players_from_matches(df)   -> pd.DataFrame  (unique player roster)
"""
from __future__ import annotations

import glob
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Column dtypes for numeric stat columns ───────────────────────────────────
_STAT_COLS = [
    "w_ace", "w_df", "w_svpt", "w_1stIn", "w_1stWon", "w_2ndWon",
    "w_SvGms", "w_bpSaved", "w_bpFaced",
    "l_ace", "l_df", "l_svpt", "l_1stIn", "l_1stWon", "l_2ndWon",
    "l_SvGms", "l_bpSaved", "l_bpFaced",
    "minutes", "best_of",
    "winner_rank", "winner_rank_points", "loser_rank", "loser_rank_points",
    "winner_seed", "loser_seed",
    "winner_ht", "loser_ht",
    "winner_age", "loser_age",
]

_STR_COLS = [
    "tourney_id", "tourney_name", "surface", "tourney_level",
    "round", "score",
    "winner_name", "winner_ioc", "winner_hand", "winner_entry",
    "loser_name", "loser_ioc", "loser_hand", "loser_entry",
]

_REQUIRED_COLS = {
    "tourney_id", "tourney_name", "surface", "tourney_level",
    "tourney_date", "best_of", "round",
    "winner_id", "winner_name",
    "loser_id", "loser_name",
}


def _parse_date(series: pd.Series) -> pd.Series:
    """Parse tourney_date from YYYYMMDD int or string format."""
    series = series.astype(str).str.strip()
    # Handle both 8-digit YYYYMMDD and already-formatted dates
    parsed = pd.to_datetime(series, format="%Y%m%d", errors="coerce")
    # Fallback: try flexible parse for any remaining NaTs
    mask_nat = parsed.isna()
    if mask_nat.any():
        parsed[mask_nat] = pd.to_datetime(series[mask_nat], errors="coerce")
    return parsed


def _load_single_csv(path: str | Path) -> Optional[pd.DataFrame]:
    """Load one CSV file; return None on failure."""
    path = Path(path)
    try:
        df = pd.read_csv(
            path,
            low_memory=False,
            dtype=str,              # read all as str first; cast later
            encoding="utf-8",
            on_bad_lines="skip",
        )
        if df.empty:
            return None
        # Check required columns
        missing = _REQUIRED_COLS - set(df.columns)
        if missing:
            logger.warning("Skipping %s — missing columns: %s", path.name, missing)
            return None
        return df
    except Exception as exc:
        logger.error("Failed to read %s: %s", path.name, exc)
        return None


def _cast_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Cast numeric and date columns to proper types."""
    # Parse tourney_date
    df["tourney_date"] = _parse_date(df["tourney_date"])

    # Cast numeric columns (coerce errors to NaN)
    for col in _STAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Ensure winner_id / loser_id are integers (coerce bad values to NaN then drop)
    for id_col in ("winner_id", "loser_id"):
        df[id_col] = pd.to_numeric(df[id_col], errors="coerce")

    return df


def _build_match_id(df: pd.DataFrame) -> pd.Series:
    """
    Construct unique match identifier:
      {year}_{tourney_id}_{round}_{winner_id}_{loser_id}
    """
    year = df["tourney_date"].dt.year.astype(str)
    tourney = df["tourney_id"].str.replace(r"\s+", "_", regex=True)
    rnd = df["round"].str.replace(r"\s+", "_", regex=True)
    w = df["winner_id"].astype(int).astype(str)
    l = df["loser_id"].astype(int).astype(str)
    return year + "_" + tourney + "_" + rnd + "_" + w + "_" + l


def load_all_matches(tml_path: str | Path) -> pd.DataFrame:
    """
    Load all ATP match CSV files from TML-Database directory.

    Supports both year-only files (YYYY.csv) and legacy naming.
    Returns a cleaned, normalised DataFrame with ~198k rows.

    Parameters
    ----------
    tml_path : str | Path
        Path to TML-Database directory containing *.csv files.

    Returns
    -------
    pd.DataFrame
        Combined match DataFrame, sorted by tourney_date ascending.
    """
    tml_path = Path(tml_path)
    if not tml_path.exists():
        raise FileNotFoundError(f"TML-Database path not found: {tml_path}")

    # Find all CSV files (year files + any atp_matches_*.csv)
    csv_files = sorted(
        list(tml_path.glob("[0-9][0-9][0-9][0-9].csv")) +
        list(tml_path.glob("atp_matches_*.csv"))
    )

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {tml_path}")

    logger.info("Found %d CSV files in %s", len(csv_files), tml_path)

    frames: list[pd.DataFrame] = []
    for path in csv_files:
        df_raw = _load_single_csv(path)
        if df_raw is not None:
            frames.append(df_raw)

    if not frames:
        raise RuntimeError("No valid CSV files could be loaded")

    logger.info("Concatenating %d dataframes...", len(frames))
    df = pd.concat(frames, ignore_index=True, sort=False)

    # Cast types
    df = _cast_columns(df)

    # Drop rows with missing essential IDs or date
    initial_len = len(df)
    df = df.dropna(subset=["winner_id", "loser_id", "tourney_date"])
    df["winner_id"] = df["winner_id"].astype(int)
    df["loser_id"] = df["loser_id"].astype(int)
    dropped = initial_len - len(df)
    if dropped:
        logger.warning("Dropped %d rows with null winner_id/loser_id/tourney_date", dropped)

    # Build match ID
    df["match_id"] = _build_match_id(df)

    # Normalise surface
    from data.quality import normalize_surface, normalize_tourney_level
    df["surface"] = df["surface"].apply(normalize_surface)
    df["tourney_level"] = df["tourney_level"].apply(normalize_tourney_level)

    # Add is_indoor flag from 'indoor' column if available
    if "indoor" in df.columns:
        df["is_indoor"] = df["indoor"].str.upper().isin(["I", "1", "TRUE", "YES"])
    else:
        df["is_indoor"] = False

    df["is_high_altitude"] = False  # populated later by engine

    # Fill numeric stat columns with NaN (already done by coerce, just ensure type)
    for col in _STAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort chronologically
    df = df.sort_values("tourney_date", ascending=True).reset_index(drop=True)

    # Deduplicate on match_id (keep first occurrence)
    before_dedup = len(df)
    df = df.drop_duplicates(subset="match_id", keep="first")
    dupes = before_dedup - len(df)
    if dupes:
        logger.info("Removed %d duplicate match_ids", dupes)

    logger.info(
        "Loaded %d matches spanning %s to %s",
        len(df),
        df["tourney_date"].min().date(),
        df["tourney_date"].max().date(),
    )

    return df


def load_players_from_matches(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract unique player roster from a matches DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Output of load_all_matches().

    Returns
    -------
    pd.DataFrame
        Columns: player_id, name, country, hand, height
        One row per unique player, deduplicated.
    """
    # Build winner records
    winner_cols = {
        "player_id": "winner_id",
        "name": "winner_name",
        "country": "winner_ioc",
        "hand": "winner_hand",
        "height": "winner_ht",
    }
    loser_cols = {
        "player_id": "loser_id",
        "name": "loser_name",
        "country": "loser_ioc",
        "hand": "loser_hand",
        "height": "loser_ht",
    }

    def _extract(cols_map: dict) -> pd.DataFrame:
        available = {k: v for k, v in cols_map.items() if v in df.columns}
        sub = df[[v for v in available.values()]].copy()
        sub.columns = [k for k in available]
        return sub

    winners = _extract(winner_cols)
    losers = _extract(loser_cols)

    players = pd.concat([winners, losers], ignore_index=True)

    # Deduplicate: keep most recent (last occurrence, which has potentially more info)
    players = players.drop_duplicates(subset=["player_id"], keep="last")

    # Cast height to numeric
    if "height" in players.columns:
        players["height"] = pd.to_numeric(players["height"], errors="coerce")

    # Filter out invalid IDs
    players = players[players["player_id"].notna()]
    players["player_id"] = players["player_id"].astype(int)

    players = players.reset_index(drop=True)

    logger.info("Extracted %d unique players from match data", len(players))
    return players
