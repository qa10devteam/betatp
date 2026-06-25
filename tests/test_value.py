"""
Tests for value/devig.py + value/ev_calculator.py — 15 tests.
Spec: value_detector/
Iter: 41-42
"""
import pytest
import math
from value.devig import (
    overround as calc_overround,
    devig_proportional,
    devig_additive,
    devig_power_shin,
    devig_multiplicative,
    best_devig,
)
from value.ev_calculator import (
    expected_value,
    kelly_fraction,
    lay_kelly,
    ev_scan_match,
    minimum_bets_for_detection,
)


# -----------------------------------------------------------------------
# Test 1: EV = p * odds - 1 (basic formula)
# -----------------------------------------------------------------------
def test_ev_basic():
    """EV = p * odds - 1"""
    assert abs(expected_value(0.7, 1.5) - (0.7 * 1.5 - 1.0)) < 1e-9


# -----------------------------------------------------------------------
# Test 2: EV(0.5, 2.0) == 0.0
# -----------------------------------------------------------------------
def test_ev_fair_odds():
    """Fair odds: EV = 0"""
    assert abs(expected_value(0.5, 2.0)) < 1e-9


# -----------------------------------------------------------------------
# Test 3: EV(0.6, 2.0) == 0.2
# -----------------------------------------------------------------------
def test_ev_edge():
    """60% chance at evens: EV = 0.2"""
    assert abs(expected_value(0.6, 2.0) - 0.2) < 1e-9


# -----------------------------------------------------------------------
# Test 4: Kelly p=0.55, odds=2.0, full Kelly -> f* = 0.10
# -----------------------------------------------------------------------
def test_kelly_full():
    """Kelly: p=0.55, odds=2.0 (b=1.0) -> f* = (0.55 - 0.45) / 1.0 = 0.10"""
    # fraction=1.0 for full Kelly
    f = kelly_fraction(0.55, 2.0, fraction=1.0)
    assert abs(f - 0.10) < 1e-9, f"Expected 0.10, got {f}"


# -----------------------------------------------------------------------
# Test 5: Half Kelly -> fraction=0.5
# -----------------------------------------------------------------------
def test_kelly_half():
    """Half Kelly = full Kelly * 0.5"""
    full = kelly_fraction(0.55, 2.0, fraction=1.0)
    half = kelly_fraction(0.55, 2.0, fraction=0.5)
    assert abs(half - full * 0.5) < 1e-9


# -----------------------------------------------------------------------
# Test 6: devig_proportional - overround > 1.0 for typical book odds
# -----------------------------------------------------------------------
def test_devig_proportional_overround():
    """Bookmaker odds should have overround > 1.0"""
    ov = calc_overround(1.91, 1.91)
    assert ov > 1.0, f"Overround should be > 1.0, got {ov}"


# -----------------------------------------------------------------------
# Test 7: devig_proportional - sum of probs = 1.0
# -----------------------------------------------------------------------
def test_devig_proportional_sums_to_one():
    """Proportional de-vig should give probabilities summing to 1"""
    p_a, p_b = devig_proportional(1.91, 1.91)
    assert abs(p_a + p_b - 1.0) < 1e-9
    p_a, p_b = devig_proportional(1.50, 2.80)
    assert abs(p_a + p_b - 1.0) < 1e-9


# -----------------------------------------------------------------------
# Test 8: devig_power_shin - sum of probs = 1.0
# -----------------------------------------------------------------------
def test_devig_power_shin_sums_to_one():
    """Power/Shin de-vig should give probabilities summing to 1"""
    p_a, p_b = devig_power_shin(1.91, 1.91)
    assert abs(p_a + p_b - 1.0) < 1e-9
    p_a, p_b = devig_power_shin(1.50, 2.80)
    assert abs(p_a + p_b - 1.0) < 1e-9


# -----------------------------------------------------------------------
# Test 9: devig_power_shin - favourite has higher p than proportional (FLB correction)
# -----------------------------------------------------------------------
def test_devig_power_shin_flb_correction():
    """
    For asymmetric odds (1.30 vs 3.80), favourite (lower odds) gets
    LOWER p in Shin vs proportional (corrects favourite-longshot bias).
    Or equivalently, longshot gets higher p.
    """
    # Favourite: 1.30, Longshot: 3.80
    shin_a, shin_b = devig_power_shin(1.30, 3.80)
    prop_a, prop_b = devig_proportional(1.30, 3.80)
    # Shin reduces favourite probability (FLB correction)
    # So favourite (a) should have LOWER p in Shin than proportional
    assert shin_a < prop_a, (
        f"Shin favourite p={shin_a:.4f} should be < proportional p={prop_a:.4f}"
    )
    # And longshot (b) should have HIGHER p in Shin
    assert shin_b > prop_b


# -----------------------------------------------------------------------
# Test 10: devig_multiplicative - sum = 1.0
# -----------------------------------------------------------------------
def test_devig_multiplicative_sums_to_one():
    """Multiplicative de-vig sums to 1"""
    p_a, p_b = devig_multiplicative(1.91, 1.91)
    assert abs(p_a + p_b - 1.0) < 1e-9
    p_a, p_b = devig_multiplicative(1.50, 2.50)
    assert abs(p_a + p_b - 1.0) < 1e-9


# -----------------------------------------------------------------------
# Test 11: All 4 devig methods sum to 1.0
# -----------------------------------------------------------------------
def test_all_devig_methods_sum_to_one():
    """All 4 de-vig methods should produce probabilities summing to 1"""
    odds_pairs = [(1.91, 1.91), (1.50, 2.80), (1.20, 5.00)]
    methods = [devig_proportional, devig_additive, devig_power_shin, devig_multiplicative]
    for odds_a, odds_b in odds_pairs:
        for method in methods:
            p_a, p_b = method(odds_a, odds_b)
            total = p_a + p_b
            assert abs(total - 1.0) < 1e-6, (
                f"{method.__name__}({odds_a}, {odds_b}): sum={total:.6f}"
            )


# -----------------------------------------------------------------------
# Test 12: ev_scan_match with EV > 0.02 -> signal = True
# -----------------------------------------------------------------------
def test_ev_scan_signal_positive():
    """When model has clear edge, ev_scan_match returns signal=True"""
    # p_model = 0.70, but odds_a = 2.20 implies p_fair ~ 0.48
    # EV = 0.70 * 2.20 - 1 = 0.54 >> 0.02
    result = ev_scan_match(p_model=0.70, odds_a=2.20, odds_b=1.70, min_ev=0.02)
    assert result is not None
    assert result["signal"] is True
    assert result["ev"] > 0.02


# -----------------------------------------------------------------------
# Test 13: ev_scan_match with EV < 0.02 -> None or signal=False
# -----------------------------------------------------------------------
def test_ev_scan_no_signal():
    """When model matches market, no signal"""
    # p_model = 0.52, odds_a = 1.91, odds_b = 1.91
    # EV = 0.52 * 1.91 - 1 = -0.0068 < 0.02
    result = ev_scan_match(p_model=0.52, odds_a=1.91, odds_b=1.91, min_ev=0.02)
    assert result is None, f"Expected None, got {result}"


# -----------------------------------------------------------------------
# Test 14: overround for 1.91/1.91 ≈ 1.047
# -----------------------------------------------------------------------
def test_overround_symmetric():
    """1.91/1.91 overround = 2/1.91 ≈ 1.0471"""
    ov = calc_overround(1.91, 1.91)
    expected = 2 / 1.91
    assert abs(ov - expected) < 1e-6, f"Expected {expected:.4f}, got {ov:.4f}"
    assert abs(ov - 1.047) < 0.001


# -----------------------------------------------------------------------
# Test 15: minimum_bets_for_detection — 3% edge ≈ 500 bets
# -----------------------------------------------------------------------
def test_minimum_bets_3pct():
    """3% edge with std=0.05 and power=0.80 should require ~500 bets"""
    n = minimum_bets_for_detection(true_ev=0.03, std=0.05, power=0.80)
    # Should be in reasonable range around 500
    assert 200 <= n <= 1500, f"Expected ~500 bets, got {n}"
    # Higher edge requires fewer bets
    n_high = minimum_bets_for_detection(true_ev=0.10, std=0.05, power=0.80)
    assert n_high < n, "Higher edge should require fewer bets"
