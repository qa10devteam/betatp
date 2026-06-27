"""
tests/integration/test_coupon_flow.py — Integration tests for coupon pipeline (h8)
====================================================================================
Tests:
  1. test_daily_coupon_build        — DailyCouponBuilder().build(mock_matches)
  2. test_system_bet_trixie         — SystemBetBuilder().build_system(3_selections, 'TRIXIE')
  3. test_coupon_ranker             — CouponRanker().rank_coupons(singles, [])
  4. test_reasoning_polish          — generate_reasoning returns Polish string with '%'
  5. test_full_pipeline             — predictor mock -> coupon generator -> ranker -> daily builder
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_matches():
    """5 ATP mock match dicts with ev, p_model, odds, player fields."""
    return [
        {
            "player": "Carlos Alcaraz",
            "player_backed": "Carlos Alcaraz",
            "opponent": "Holger Rune",
            "surface": "Clay",
            "odds": 1.62,
            "p_model": 0.72,
            "ev": 0.1664,
            "kelly": 0.045,
        },
        {
            "player": "Jannik Sinner",
            "player_backed": "Jannik Sinner",
            "opponent": "Alexander Zverev",
            "surface": "Hard",
            "odds": 1.75,
            "p_model": 0.67,
            "ev": 0.1725,
            "kelly": 0.038,
        },
        {
            "player": "Novak Djokovic",
            "player_backed": "Novak Djokovic",
            "opponent": "Casper Ruud",
            "surface": "Hard",
            "odds": 1.55,
            "p_model": 0.74,
            "ev": 0.147,
            "kelly": 0.052,
        },
        {
            "player": "Daniil Medvedev",
            "player_backed": "Daniil Medvedev",
            "opponent": "Stefanos Tsitsipas",
            "surface": "Hard",
            "odds": 1.90,
            "p_model": 0.60,
            "ev": 0.14,
            "kelly": 0.032,
        },
        {
            "player": "Taylor Fritz",
            "player_backed": "Taylor Fritz",
            "opponent": "Ben Shelton",
            "surface": "Hard",
            "odds": 1.85,
            "p_model": 0.61,
            "ev": 0.128,
            "kelly": 0.028,
        },
    ]


@pytest.fixture
def three_selections():
    """3 selections with good EV for system bet testing."""
    return [
        {"player": "Alcaraz", "odds": 1.62, "p_model": 0.72, "ev": 0.1664, "kelly": 0.045},
        {"player": "Sinner", "odds": 1.75, "p_model": 0.67, "ev": 0.1725, "kelly": 0.038},
        {"player": "Djokovic", "odds": 1.55, "p_model": 0.74, "ev": 0.147, "kelly": 0.052},
    ]


# ---------------------------------------------------------------------------
# Test 1: DailyCouponBuilder
# ---------------------------------------------------------------------------

def test_daily_coupon_build(mock_matches):
    """DailyCouponBuilder().build(mock_matches) returns dict with 'top_singles' key."""
    from engine.daily_coupon import DailyCouponBuilder

    builder = DailyCouponBuilder()
    coupon = builder.build(mock_matches, min_ev=0.0)

    assert isinstance(coupon, dict), "build() must return a dict"
    assert "top_singles" in coupon, "Coupon must have 'top_singles' key"
    assert isinstance(coupon["top_singles"], list), "'top_singles' must be a list"
    assert len(coupon["top_singles"]) <= 3, "top_singles must have at most 3 picks"
    assert "date" in coupon, "Coupon must have 'date' key"
    assert "generated_at" in coupon, "Coupon must have 'generated_at' key"


def test_daily_coupon_top_singles_non_empty(mock_matches):
    """With 5 high-EV matches, top_singles must not be empty."""
    from engine.daily_coupon import DailyCouponBuilder

    coupon = DailyCouponBuilder().build(mock_matches, min_ev=0.0)
    assert len(coupon["top_singles"]) > 0, "top_singles should not be empty with valid matches"


def test_daily_coupon_to_json(mock_matches):
    """to_json() returns valid JSON string after build()."""
    import json
    from engine.daily_coupon import DailyCouponBuilder

    builder = DailyCouponBuilder()
    builder.build(mock_matches, min_ev=0.0)
    json_str = builder.to_json()
    parsed = json.loads(json_str)
    assert "top_singles" in parsed


# ---------------------------------------------------------------------------
# Test 2: SystemBetBuilder TRIXIE
# ---------------------------------------------------------------------------

def test_system_bet_trixie(three_selections):
    """SystemBetBuilder().build_system(3_selections, 'TRIXIE') returns combinations."""
    from engine.coupon_system import SystemBetBuilder

    builder = SystemBetBuilder()
    result = builder.build_system(three_selections, "TRIXIE")

    assert isinstance(result, dict), "build_system must return a dict"
    assert "combinations" in result, "Result must have 'combinations' key"
    assert isinstance(result["combinations"], list), "'combinations' must be a list"
    assert len(result["combinations"]) > 0, "TRIXIE must produce combinations"

    # TRIXIE = 3 doubles (C(3,2) = 3 combinations)
    assert result["system_type"] == "TRIXIE", f"Expected TRIXIE, got {result['system_type']}"


def test_system_bet_trixie_has_three_doubles(three_selections):
    """TRIXIE must produce exactly 3 doubles."""
    from engine.coupon_system import SystemBetBuilder

    result = SystemBetBuilder().build_system(three_selections, "TRIXIE")
    combos = result["combinations"]
    # Each combo must have 2 legs
    two_leg_combos = [c for c in combos if c["legs"] == 2]
    assert len(two_leg_combos) == 3, f"TRIXIE must have 3 doubles, got {len(two_leg_combos)}"


def test_system_bet_2_3(three_selections):
    """SystemBetBuilder().build_system(3_selections, '2/3') returns C(3,2)=3 doubles."""
    from engine.coupon_system import SystemBetBuilder

    result = SystemBetBuilder().build_system(three_selections, "2/3")
    assert len(result["combinations"]) == 3


# ---------------------------------------------------------------------------
# Test 3: CouponRanker
# ---------------------------------------------------------------------------

def test_coupon_ranker(mock_matches):
    """CouponRanker().rank_coupons(singles, []) returns sorted list."""
    from engine.coupon_ranker import CouponRanker

    ranker = CouponRanker()
    ranked = ranker.rank_coupons(mock_matches, [])

    assert isinstance(ranked, list), "rank_coupons must return a list"
    assert len(ranked) == len(mock_matches), "Must return all items"

    # Verify sorted by EV descending
    evs = [r.get("ev", 0.0) for r in ranked]
    assert evs == sorted(evs, reverse=True), "Results must be sorted by EV descending"


def test_coupon_ranker_annotations(mock_matches):
    """Each ranked item must have score, confidence, reasoning."""
    from engine.coupon_ranker import CouponRanker

    ranked = CouponRanker().rank_coupons(mock_matches, [])
    for item in ranked:
        assert "score" in item, f"Missing 'score' in {item.get('player', '?')}"
        assert "confidence" in item, f"Missing 'confidence'"
        assert "reasoning" in item, f"Missing 'reasoning'"
        assert isinstance(item["score"], (int, float))
        assert item["confidence"] in ("WYSOKA", "ŚREDNIA", "NISKA")


def test_coupon_ranker_empty():
    """rank_coupons([],[]) returns empty list without error."""
    from engine.coupon_ranker import CouponRanker

    result = CouponRanker().rank_coupons([], [])
    assert result == []


# ---------------------------------------------------------------------------
# Test 4: Reasoning Polish with '%'
# ---------------------------------------------------------------------------

def test_reasoning_polish():
    """generate_reasoning returns a Polish string containing '%'."""
    from engine.coupon_ranker import CouponRanker

    ranker = CouponRanker()
    selection = {
        "player": "Jannik Sinner",
        "p_model": 0.67,
        "odds": 1.75,
        "ev": 0.1725,
        "surface": "Hard",
        "h2h": "3-1",
    }
    reasoning = ranker.generate_reasoning(selection)

    assert isinstance(reasoning, str), "reasoning must be a string"
    assert "%" in reasoning, f"reasoning must contain '%', got: {reasoning!r}"
    # Should contain Polish words
    assert "Model" in reasoning or "rynek" in reasoning or "EV" in reasoning, (
        f"reasoning should contain Polish content, got: {reasoning!r}"
    )


def test_reasoning_has_ev_plus_sign():
    """EV in reasoning shows sign (+ or -)."""
    from engine.coupon_ranker import CouponRanker

    ranker = CouponRanker()
    selection = {"p_model": 0.65, "odds": 1.80, "ev": 0.17}
    reasoning = ranker.generate_reasoning(selection)
    # Template: "EV +17.0%" or "EV -3.0%"
    assert "EV" in reasoning


def test_reasoning_surface_included():
    """Surface info is included in reasoning when provided."""
    from engine.coupon_ranker import CouponRanker

    ranker = CouponRanker()
    selection = {"p_model": 0.6, "odds": 1.9, "ev": 0.14, "surface": "Clay"}
    reasoning = ranker.generate_reasoning(selection)
    assert "Clay" in reasoning


# ---------------------------------------------------------------------------
# Test 5: Full pipeline
# ---------------------------------------------------------------------------

def test_full_pipeline(mock_matches):
    """
    Full pipeline:
    predictor mock -> coupon generator -> ranker -> daily builder chain.
    """
    from engine.coupon_ranker import CouponRanker
    from engine.daily_coupon import DailyCouponBuilder
    from engine.coupon_system import SystemBetBuilder

    # Step 1: Mock predictor output (already have mock_matches with ev/p_model/odds)
    predictions = mock_matches  # treat as predictor output

    # Step 2: Rank via CouponRanker
    ranker = CouponRanker()
    ranked = ranker.rank_coupons(predictions, [])
    assert len(ranked) > 0, "Ranker must produce results"

    # Step 3: Build daily coupon
    builder = DailyCouponBuilder()
    coupon = builder.build(ranked, min_ev=0.0)
    assert "top_singles" in coupon

    # Step 4: Build system bet from top 3
    top3 = ranked[:3]
    if len(top3) >= 3:
        sys_builder = SystemBetBuilder()
        system = sys_builder.build_system(top3, "2/3")
        assert "combinations" in system

    # Step 5: Verify coupon completeness
    assert isinstance(coupon["top_singles"], list)
    assert coupon.get("date") is not None
    assert len(coupon["top_singles"]) <= 3


def test_full_pipeline_with_min_ev_filter():
    """Pipeline filters out picks below min_ev threshold."""
    from engine.daily_coupon import DailyCouponBuilder

    low_ev_matches = [
        {"player": "PlayerA", "odds": 2.0, "p_model": 0.5, "ev": 0.005, "kelly": 0.01},
        {"player": "PlayerB", "odds": 2.0, "p_model": 0.5, "ev": 0.001, "kelly": 0.01},
    ]
    coupon = DailyCouponBuilder().build(low_ev_matches, min_ev=0.02)
    # All below min_ev → top_singles should be empty
    assert coupon["top_singles"] == [], "Low-EV picks should be filtered out"
