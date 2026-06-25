"""tests/conftest.py — Pytest fixtures for betatp.io test suite."""
from __future__ import annotations

from datetime import date, datetime

import pytest


@pytest.fixture
def sample_player() -> dict:
    """Minimal player dict matching Player ORM fields."""
    return {
        "id": 104745,
        "name": "Novak Djokovic",
        "country": "SRB",
        "dob": date(1987, 5, 22),
        "hand": "R",
        "height": 188,
    }


@pytest.fixture
def sample_player_2() -> dict:
    """Second player fixture for H2H tests."""
    return {
        "id": 103819,
        "name": "Rafael Nadal",
        "country": "ESP",
        "dob": date(1986, 6, 3),
        "hand": "L",
        "height": 185,
    }


@pytest.fixture
def sample_match(sample_player, sample_player_2) -> dict:
    """Minimal match dict matching Match ORM fields."""
    return {
        "id": "2024_2024-540_F_104745_103819",
        "tourney_id": "2024-540",
        "tourney_name": "Roland Garros",
        "surface": "Clay",
        "tourney_level": "G",
        "tourney_date": date(2024, 6, 9),
        "best_of": 5,
        "round": "F",
        "winner_id": sample_player["id"],
        "loser_id": sample_player_2["id"],
        "score": "3-6 6-3 6-2 6-2",
        "minutes": 193,
        "w_ace": 3, "w_df": 4, "w_svpt": 130,
        "w_1stIn": 80, "w_1stWon": 55, "w_2ndWon": 30,
        "w_SvGms": 14, "w_bpSaved": 8, "w_bpFaced": 10,
        "l_ace": 2, "l_df": 5, "l_svpt": 110,
        "l_1stIn": 65, "l_1stWon": 40, "l_2ndWon": 22,
        "l_SvGms": 13, "l_bpSaved": 5, "l_bpFaced": 12,
        "winner_rank": 1, "loser_rank": 3,
        "is_indoor": False,
        "is_high_altitude": False,
    }


@pytest.fixture
def sample_elo_history(sample_player, sample_match) -> dict:
    """Elo snapshot after a match."""
    return {
        "player_id": sample_player["id"],
        "match_id": sample_match["id"],
        "match_date": sample_match["tourney_date"],
        "overall_elo": 2214.5,
        "hard_elo": 2198.0,
        "clay_elo": 2230.0,
        "grass_elo": 2180.0,
        "serve_elo": 2190.0,
        "return_elo": 2240.0,
        "n_matches": 1247,
        "n_hard": 510,
        "n_clay": 450,
        "n_grass": 287,
    }


@pytest.fixture
def tiny_matches_df():
    """
    Small in-memory DataFrame mimicking load_all_matches() output.
    5 rows — enough for pipeline unit tests.
    """
    import pandas as pd

    data = {
        "match_id": [
            "2024_2024-540_F_104745_103819",
            "2024_2024-540_SF_104745_200001",
            "2024_2024-540_SF_103819_200002",
            "2024_2024-540_QF_200001_200003",
            "2024_2024-540_QF_200002_200004",
        ],
        "tourney_id": ["2024-540"] * 5,
        "tourney_name": ["Roland Garros"] * 5,
        "surface": ["Clay"] * 5,
        "tourney_level": ["G"] * 5,
        "tourney_date": pd.to_datetime([
            "2024-06-09", "2024-06-07", "2024-06-07",
            "2024-06-05", "2024-06-05",
        ]),
        "best_of": [5] * 5,
        "round": ["F", "SF", "SF", "QF", "QF"],
        "winner_id": [104745, 104745, 103819, 200001, 200002],
        "winner_name": ["Novak Djokovic", "Novak Djokovic", "Rafael Nadal", "Player A", "Player B"],
        "winner_ioc": ["SRB", "SRB", "ESP", "ARG", "GER"],
        "winner_hand": ["R", "R", "L", "R", "R"],
        "winner_ht": [188, 188, 185, 182, 190],
        "loser_id": [103819, 200001, 200002, 200003, 200004],
        "loser_name": ["Rafael Nadal", "Player A", "Player B", "Player C", "Player D"],
        "loser_ioc": ["ESP", "ARG", "GER", "FRA", "ITA"],
        "loser_hand": ["L", "R", "R", "R", "L"],
        "loser_ht": [185, 182, 190, 178, 183],
        "score": ["3-6 6-3 6-2 6-2", "6-3 6-4 6-2", "6-1 6-2 6-3", "6-4 7-5 6-3", "6-2 6-3 6-4"],
        "minutes": [193, 130, 110, 125, 115],
        "winner_rank": [1, 1, 3, 12, 18],
        "loser_rank": [3, 12, 18, 22, 35],
        "w_svpt": [130, 110, 105, 100, 95],
        "w_1stIn": [80, 70, 68, 65, 60],
        "w_1stWon": [55, 50, 48, 45, 43],
        "w_2ndWon": [30, 25, 24, 22, 20],
        "w_ace": [3, 8, 5, 4, 6],
        "w_df": [4, 3, 2, 3, 2],
        "w_SvGms": [14, 12, 11, 11, 10],
        "w_bpSaved": [8, 5, 6, 4, 3],
        "w_bpFaced": [10, 7, 8, 6, 5],
        "l_svpt": [110, 100, 98, 95, 90],
        "l_1stIn": [65, 60, 58, 55, 52],
        "l_1stWon": [40, 38, 36, 34, 32],
        "l_2ndWon": [22, 20, 19, 17, 16],
        "l_ace": [2, 5, 4, 3, 4],
        "l_df": [5, 4, 3, 4, 3],
        "l_SvGms": [13, 11, 10, 10, 9],
        "l_bpSaved": [5, 4, 5, 3, 2],
        "l_bpFaced": [12, 8, 9, 7, 6],
        "is_indoor": [False] * 5,
        "is_high_altitude": [False] * 5,
    }
    return pd.DataFrame(data)
