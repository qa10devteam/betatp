"""
Tests for EloEngine — 15 test cases covering all 6 Elo variants.
"""
import math
import pytest
from datetime import date, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.elo import EloEngine, PlayerElo, ELO_MEAN, HALFLIFE_DAYS


@pytest.fixture
def engine():
    return EloEngine()


# --- Test 1: win_probability equal ratings ---
def test_win_probability_equal(engine):
    assert engine.win_probability(1500, 1500) == pytest.approx(0.5)


# --- Test 2: win_probability higher rated player ---
def test_win_probability_higher_wins(engine):
    assert engine.win_probability(1700, 1500) > 0.75


# --- Test 3: complementary probabilities ---
def test_win_probability_complementary(engine):
    ra, rb = 1600.0, 1400.0
    assert engine.win_probability(ra, rb) + engine.win_probability(rb, ra) == pytest.approx(1.0)


# --- Test 4: apply_decay 365 days halves the diff ---
def test_apply_decay_half_life(engine):
    player = engine.get_or_create(1)
    player.overall = 1700.0  # diff = 200
    player.last_match_date = date(2023, 1, 1)
    engine.apply_decay(player, date(2024, 1, 1))  # 365 days
    diff_after = player.overall - ELO_MEAN
    assert diff_after == pytest.approx(100.0, abs=1.0)  # 200 * 0.5 = 100


# --- Test 5: apply_decay long time converges to 1500 ---
def test_apply_decay_converges(engine):
    player = engine.get_or_create(2)
    player.overall = 2000.0
    player.last_match_date = date(2000, 1, 1)
    engine.apply_decay(player, date(2030, 1, 1))  # 30 years
    assert abs(player.overall - ELO_MEAN) < 1.0


# --- Test 6: surface_blend ---
def test_surface_blend_n0(engine):
    # n=0: 0% surface, 100% overall
    blended = engine.surface_blend(1600, 1500, 0)
    assert blended == pytest.approx(1500.0)


def test_surface_blend_large_n(engine):
    # n=100: ~96% surface
    blended = engine.surface_blend(1600, 1500, 100)
    alpha = 1 - math.exp(-100 / 30)
    expected = alpha * 1600 + (1 - alpha) * 1500
    assert blended == pytest.approx(expected)
    assert alpha > 0.96


# --- Test 7: k_factor ---
def test_k_factor_grand_slam(engine):
    assert engine.k_factor("G", 50) == pytest.approx(48.0)


def test_k_factor_provisional(engine):
    assert engine.k_factor("G", 10) == pytest.approx(96.0)  # provisional


# --- Test 8: update_match winner gains, loser loses ---
def test_update_match_winner_gains(engine):
    d = date(2023, 6, 1)
    w, l = engine.update_match(10, 20, "Hard", "G", d)
    assert w.overall > 1500.0
    assert l.overall < 1500.0


# --- Test 9: zero-sum overall ---
def test_update_match_zero_sum(engine):
    eng = EloEngine()
    d = date(2023, 6, 1)
    # Both provisional, same K
    w, l = eng.update_match(30, 40, "Hard", "G", d)
    total_change = (w.overall - 1500.0) + (l.overall - 1500.0)
    assert abs(total_change) < 1e-9


# --- Test 10: is_provisional after matches ---
def test_update_match_provisional(engine):
    d = date(2023, 1, 1)
    # Play 29 matches for player 50
    for i in range(29):
        engine.update_match(50, 100 + i, "Hard", "250", d + timedelta(days=i))
    w = engine.get_or_create(50)
    assert w.is_provisional is True  # still provisional at 29 matches

    engine.update_match(50, 200, "Hard", "250", d + timedelta(days=30))
    w = engine.get_or_create(50)
    assert w.is_provisional is False  # 30 matches = not provisional


# --- Test 11: predict_match probabilities sum to 1 ---
def test_predict_match_sum(engine):
    result_a = engine.predict_match(60, 70, "Hard")
    result_b = engine.predict_match(70, 60, "Hard")
    assert result_a["p_win_a"] + result_b["p_win_a"] == pytest.approx(1.0)


# --- Test 12: higher Elo → higher p_win ---
def test_predict_match_higher_elo_wins(engine):
    eng = EloEngine()
    a = eng.get_or_create(80)
    b = eng.get_or_create(90)
    a.overall = 1800.0
    b.overall = 1500.0
    result = eng.predict_match(80, 90, "Hard")
    assert result["p_win_a_overall"] > 0.5


# --- Test 13: Clay specialist advantage on clay ---
def test_predict_surface_clay_specialist(engine):
    eng = EloEngine()
    # Player A: Clay specialist (high clay, low overall)
    a = eng.get_or_create(100)
    b = eng.get_or_create(101)
    a.overall = 1500.0
    a.clay = 1800.0
    a.n_clay = 100  # many clay matches = high blend
    b.overall = 1600.0
    b.clay = 1500.0
    b.n_clay = 50

    result = eng.predict_match(100, 101, "Clay")
    # A's blended clay Elo should give advantage despite lower overall
    assert result["surface_elo_a"] > result["surface_elo_b"]
    assert result["p_win_a"] > 0.5


# --- Test 14: serve/return Elo updates with stats ---
def test_serve_return_elo_update(engine):
    eng = EloEngine()
    d = date(2023, 6, 1)
    w, l = eng.update_match(
        110, 120, "Hard", "G", d,
        w_svpt=80, w_1stWon=48, w_2ndWon=16,  # 64/80 = 0.80 SVW
        l_svpt=70, l_1stWon=35, l_2ndWon=7,   # 42/70 = 0.60 SVW
    )
    # Winner served well (0.80), should have serve Elo different from 1500
    assert w.serve != 1500.0 or l.serve != 1500.0
    # Return Elo should also be updated
    assert w.return_elo != 1500.0 or l.return_elo != 1500.0


# --- Test 15: 100 matches chronologically → stable ratings ---
def test_100_matches_stability(engine):
    import random
    random.seed(42)
    eng = EloEngine()
    base_date = date(2020, 1, 1)

    # Create 10 players
    players = list(range(200, 210))

    for i in range(100):
        p1, p2 = random.sample(players, 2)
        match_date = base_date + timedelta(days=i * 3)
        eng.update_match(p1, p2, "Hard", "250", match_date)

    # After 100 matches, all players should have ratings between floor and ceiling
    for pid in players:
        elo = eng.get_or_create(pid)
        assert 1000.0 <= elo.overall <= 2800.0
        assert elo.n_matches >= 0

    # Ratings should be spread out (not all at 1500)
    ratings = [eng.get_or_create(pid).overall for pid in players]
    assert max(ratings) - min(ratings) > 50  # meaningful spread


# --- Extra: surface counts incremented ---
def test_surface_counts(engine):
    eng = EloEngine()
    d = date(2023, 1, 1)
    eng.update_match(300, 301, "Clay", "500", d)
    w = eng.get_or_create(300)
    assert w.n_clay == 1
    assert w.n_hard == 0
    assert w.n_grass == 0
