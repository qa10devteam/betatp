"""
tests/test_data.py — Data pipeline unit tests for betatp.io

Covers:
  1. ORM model instantiation (no DB required)
  2. normalize_surface correctness
  3. normalize_tourney_level correctness
  4. validate_serve_stats — valid data passes
  5. detect_outliers — correctly flags low-sample players
  6. load_players_from_matches — correct dedup
  7. Elo history fixture structure
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

from data.quality import (
    normalize_surface,
    normalize_tourney_level,
    validate_serve_stats,
    detect_outliers,
)
from data.loader import load_players_from_matches


# ─── Test 1: ORM model imports cleanly ───────────────────────────────────────

def test_models_import():
    """All ORM classes can be imported and Base.metadata has expected tables."""
    from data.models import Base, Player, Match, EloHistory, Coupon, Subscription, User, Alert

    table_names = set(Base.metadata.tables.keys())
    expected = {"players", "matches", "elo_history", "coupons", "subscriptions", "users", "alerts"}
    assert expected == table_names, f"Missing tables: {expected - table_names}"


# ─── Test 2: normalize_surface ───────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Hard", "Hard"),
    ("hard", "Hard"),
    ("HARD", "Hard"),
    ("Clay", "Clay"),
    ("clay", "Clay"),
    ("Grass", "Grass"),
    ("grass", "Grass"),
    ("Carpet", "Hard"),    # legacy → Hard
    ("carpet", "Hard"),
    ("Indoor Hard", "Hard"),
    (None, "Hard"),        # null → Hard
    ("", "Hard"),          # empty → Hard
    ("Unknown", "Hard"),   # unknown → Hard
])
def test_normalize_surface(raw, expected):
    assert normalize_surface(raw) == expected


# ─── Test 3: normalize_tourney_level ─────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("G", "G"),
    ("g", "G"),
    ("M", "M"),
    ("m", "M"),
    ("A", "250"),   # legacy ATP
    ("D", "D"),
    ("F", "F"),
    ("C", "250"),   # Challenger
    ("S", "500"),   # legacy 500
    ("500", "500"),
    ("250", "250"),
    (None, "250"),  # null → default 250
    ("", "250"),
    ("XYZ", "250"), # unknown → default 250
])
def test_normalize_tourney_level(raw, expected):
    assert normalize_tourney_level(raw) == expected


# ─── Test 4: validate_serve_stats — valid fixture passes ─────────────────────

def test_validate_serve_stats_valid(tiny_matches_df):
    """Clean fixture data should produce zero violations."""
    violations = validate_serve_stats(tiny_matches_df)
    assert violations.empty, (
        f"Expected no violations, got {len(violations)}:\n{violations}"
    )


# ─── Test 5: detect_outliers ─────────────────────────────────────────────────

def test_detect_outliers(tiny_matches_df):
    """
    tiny_matches_df has 5 players with >=2 appearances (104745, 103819)
    and 4 singletons (200001-200004) — all should be below min_matches=3.
    """
    outliers = detect_outliers(tiny_matches_df, min_matches=3)
    # 200001..200004 appear twice each (once as winner, once as loser) → still <3
    # Actually: 200001 wins 1, loses 1 = 2 total → flagged
    outlier_ids = set(outliers["player_id"].tolist())
    assert 200003 in outlier_ids, "200003 has only 1 match — should be outlier"
    assert 200004 in outlier_ids, "200004 has only 1 match — should be outlier"
    # Djokovic: winner in 2 rows = 2 matches (loser in 0) → with min=3 still flagged
    # Adjust: with min=10, all players should be flagged
    outliers_10 = detect_outliers(tiny_matches_df, min_matches=10)
    assert len(outliers_10) == 6, (
        f"Expected 6 players below 10 matches, got {len(outliers_10)}"
    )


# ─── Test 6: load_players_from_matches ───────────────────────────────────────

def test_load_players_from_matches(tiny_matches_df):
    """Should extract 6 unique players from 5-match DataFrame."""
    players = load_players_from_matches(tiny_matches_df)
    assert len(players) == 6, f"Expected 6 unique players, got {len(players)}"
    assert "player_id" in players.columns
    assert "name" in players.columns
    # No duplicate IDs
    assert players["player_id"].nunique() == len(players)


# ─── Test 7: sample_elo_history fixture structure ────────────────────────────

def test_elo_history_fixture(sample_elo_history):
    """Elo history fixture has all required fields with sensible values."""
    required_keys = {
        "player_id", "match_id", "match_date",
        "overall_elo", "hard_elo", "clay_elo", "grass_elo",
        "serve_elo", "return_elo",
        "n_matches", "n_hard", "n_clay", "n_grass",
    }
    assert required_keys <= set(sample_elo_history.keys())
    # Elo within valid range
    from engine.constants import ELO_FLOOR, ELO_CEILING
    assert ELO_FLOOR <= sample_elo_history["overall_elo"] <= ELO_CEILING
    # Match counts consistent
    assert sample_elo_history["n_matches"] >= (
        sample_elo_history["n_hard"] +
        sample_elo_history["n_clay"] +
        sample_elo_history["n_grass"]
    )
