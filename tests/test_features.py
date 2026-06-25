"""
Tests for engine/features.py — 10 tests.
Spec: feature_engineering/
Iter: 41-42
"""
import pytest
import math
from datetime import date
from engine.features import FeatureBuilder, EWMA_ALPHA, H2H_PRIOR_ALPHA, H2H_PRIOR_BETA


# -----------------------------------------------------------------------
# Test 1: EWMA convergence
# -----------------------------------------------------------------------
def test_ewma_converges():
    """After 50 wins, ewma_win_pct converges significantly from 0.5 toward 1.0"""
    fb = FeatureBuilder()
    for _ in range(50):
        fb.update_ewma(1, {"win_pct": 1.0})
    ewma = fb.get_ewma(1)
    # After 50 updates with alpha=0.15, should be well above 0.5
    assert ewma["win_pct"] > 0.85, f"Expected convergence > 0.85, got {ewma['win_pct']}"


# -----------------------------------------------------------------------
# Test 2: EWMA N_eff = 2/alpha - 1
# -----------------------------------------------------------------------
def test_ewma_n_eff():
    """N_eff = 2/alpha - 1 = 2/0.15 - 1 ≈ 12.3"""
    n_eff = 2.0 / EWMA_ALPHA - 1.0
    assert abs(n_eff - 12.333) < 0.1, f"N_eff={n_eff}"
    # After N_eff updates, signal weight should be ~1 - 1/e
    fb = FeatureBuilder()
    n = int(round(n_eff))
    for _ in range(n):
        fb.update_ewma(99, {"win_pct": 1.0})
    ewma = fb.get_ewma(99)
    # should be meaningfully above initial 0.5
    assert ewma["win_pct"] > 0.7


# -----------------------------------------------------------------------
# Test 3: H2H posterior with n=0 -> p=0.5 (prior)
# -----------------------------------------------------------------------
def test_h2h_prior_zero():
    """No match history -> posterior mean = 0.5"""
    fb = FeatureBuilder()
    result = fb.compute_h2h_posterior(100, 200)
    # Beta(3, 3) mean = 3/6 = 0.5
    assert abs(result["posterior_mean"] - 0.5) < 1e-9
    assert result["total"] == 0


# -----------------------------------------------------------------------
# Test 4: H2H posterior n=10, 7W-3L -> p > 0.5
# -----------------------------------------------------------------------
def test_h2h_posterior_wins():
    """7 wins, 3 losses -> Beta(10, 6) mean = 10/16 = 0.625 > 0.5"""
    fb = FeatureBuilder()
    # Record 7 wins for player 100 against player 200
    for _ in range(7):
        fb.record_h2h(100, 200, winner_id=100)
    for _ in range(3):
        fb.record_h2h(100, 200, winner_id=200)
    result = fb.compute_h2h_posterior(100, 200)
    # Alpha post = 3 + 7 = 10, Beta post = 3 + 3 = 6 -> mean = 10/16
    expected = (H2H_PRIOR_ALPHA + 7) / (H2H_PRIOR_ALPHA + 7 + H2H_PRIOR_BETA + 3)
    assert abs(result["posterior_mean"] - expected) < 1e-9
    assert result["posterior_mean"] > 0.5


# -----------------------------------------------------------------------
# Test 5: H2H surface filter works
# -----------------------------------------------------------------------
def test_h2h_surface_filter():
    """Surface-filtered H2H returns correct surface stats"""
    fb = FeatureBuilder()
    # 3 clay wins for player 1 vs player 2
    for _ in range(3):
        fb.record_h2h(1, 2, winner_id=1, surface="clay")
    # 1 hard win for player 2
    fb.record_h2h(1, 2, winner_id=2, surface="hard")

    # Clay-filtered posterior for player 1
    clay_result = fb.compute_h2h_posterior(1, 2, surface="clay")
    hard_result = fb.compute_h2h_posterior(1, 2, surface="hard")

    # Clay: 3W-0L -> Alpha=6, Beta=3 -> mean = 6/9 ~ 0.667
    assert clay_result["posterior_mean"] > hard_result["posterior_mean"], (
        f"Clay p={clay_result['posterior_mean']:.3f} should be > hard p={hard_result['posterior_mean']:.3f}"
    )
    assert clay_result["wins_a"] == 3
    assert hard_result["wins_b"] == 1


# -----------------------------------------------------------------------
# Test 6: age_performance_factor(26) == 1.0
# -----------------------------------------------------------------------
def test_age_factor_prime():
    """Age 26 is in prime (25-27) -> factor should be 1.0"""
    fb = FeatureBuilder()
    factor = fb.age_performance_factor(26.0)
    assert abs(factor - 1.0) < 0.001, f"Expected ~1.0, got {factor}"


# -----------------------------------------------------------------------
# Test 7: age_performance_factor(34) < 0.95
# -----------------------------------------------------------------------
def test_age_factor_veteran():
    """Age 34 is in decline range -> factor < 0.95"""
    fb = FeatureBuilder()
    factor = fb.age_performance_factor(34.0)
    assert factor < 0.95, f"Expected < 0.95, got {factor}"


# -----------------------------------------------------------------------
# Test 8: fatigue_score with rest_hours < 14 -> scheduling_flag
# -----------------------------------------------------------------------
def test_fatigue_scheduling_flag():
    """Rest < 14 hours should produce high fatigue and trigger scheduling_flag"""
    fb = FeatureBuilder()
    # Set player metadata with low rest
    fb._player_meta[42] = {
        "rest_hours": 10.0,
        "sets_last_7d": 8.0,
        "tz_crossings": 0,
    }
    feats = fb.build_features(
        player_id=42, opponent_id=99,
        surface="hard", tourney_level="250",
        best_of=3, match_date=date(2025, 1, 15)
    )
    assert feats["scheduling_flag"] == 1, "scheduling_flag should be 1 for rest < 14h"
    # Also check directly
    score = fb.fatigue_score(sets_7d=8.0, rest_hours=10.0)
    assert score > 0.0


# -----------------------------------------------------------------------
# Test 9: build_match_features returns dict with 100+ keys
# -----------------------------------------------------------------------
def test_build_match_features_count():
    """build_match_features should return 100+ feature keys"""
    fb = FeatureBuilder()
    feats = fb.build_match_features(
        player_a=1, player_b=2,
        surface="hard", tourney_level="M",
        best_of=3, match_date=date(2025, 6, 1)
    )
    assert isinstance(feats, dict)
    assert len(feats) >= 100, f"Expected 100+ features, got {len(feats)}"


# -----------------------------------------------------------------------
# Test 10: No leakage - features don't know the future
# -----------------------------------------------------------------------
def test_no_future_leakage():
    """Features should not include match outcome or any future information"""
    fb = FeatureBuilder()
    feats = fb.build_match_features(
        player_a=10, player_b=20,
        surface="clay", tourney_level="G",
        best_of=5, match_date=date(2025, 5, 26)
    )
    # Check for actual outcome/result keys (not partial word matches like 'score')
    # We allow things like 'fatigue_score', 'tourney_level_score', '1stwon_pct'
    # which are legitimate feature names. We look for exact outcome keys.
    forbidden_exact = {"winner", "result", "outcome", "sets_won", "games_won"}
    leaked = {k for k in feats if k in forbidden_exact}
    assert not leaked, f"Potential leakage keys found: {leaked}"
    # Ensure no NaN values
    for k, v in feats.items():
        if isinstance(v, float):
            assert not math.isnan(v), f"NaN found for key: {k}"
