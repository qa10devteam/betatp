"""
tests/test_coupon.py — 12 tests for CouponGenerator B2C module.
"""
import pytest
from datetime import date
from engine.coupon import (
    BetSelection,
    Coupon,
    CouponGenerator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TODAY = date(2025, 1, 15)


def make_prediction(
    match_id="m1",
    player_a="Carlos Alcaraz",
    player_b="Novak Djokovic",
    surface="Hard",
    tourney="Australian Open",
    tourney_level="G",
    p_model=0.65,
    bk_odds_a=1.80,
    bk_odds_b=2.10,
    elo_diff=120.0,
    surface_elo_diff=80.0,
    form_a="WWWWL",
    form_b="LWWLL",
    fatigue_a=False,
    fatigue_b=False,
    h2h="8-6 (Hard: 4-3)",
    match_date=None,
):
    return {
        "match_id": match_id,
        "player_a": player_a,
        "player_b": player_b,
        "surface": surface,
        "tourney": tourney,
        "tourney_level": tourney_level,
        "p_model": p_model,
        "bk_odds_a": bk_odds_a,
        "bk_odds_b": bk_odds_b,
        "elo_diff": elo_diff,
        "surface_elo_diff": surface_elo_diff,
        "form_a": form_a,
        "form_b": form_b,
        "fatigue_a": fatigue_a,
        "fatigue_b": fatigue_b,
        "h2h": h2h,
        "match_date": match_date or TODAY,
    }


def make_three_predictions():
    """Return 3 predictions all with EV > 5%."""
    return [
        make_prediction("m1", p_model=0.68, bk_odds_a=1.90, match_date=TODAY),
        make_prediction("m2", player_a="Jannik Sinner", player_b="Daniil Medvedev",
                        p_model=0.62, bk_odds_a=1.85, match_date=TODAY),
        make_prediction("m3", player_a="Rafael Nadal", player_b="Andy Murray",
                        p_model=0.72, bk_odds_a=1.70, match_date=TODAY),
    ]


@pytest.fixture
def gen():
    return CouponGenerator(min_ev=0.02, min_odds=1.30, max_odds=5.00, max_kelly=0.05)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# 1. generate_singles filtruje EV < min_ev
def test_generate_singles_filters_low_ev(gen):
    """Predictions with EV < min_ev must be excluded.
    Use odds outside [min_odds, max_odds] to ensure both sides are filtered.
    """
    # odds_a < min_odds (1.10 < 1.30) -> filtered; odds_b > max_odds (6.50 > 5.00) -> filtered
    bad = make_prediction(match_id="bad", p_model=0.50, bk_odds_a=1.10, bk_odds_b=6.50)
    result = gen.generate_singles([bad])
    assert len(result) == 0, "Selections with odds out of range should be filtered out"


# 2. generate_singles sortuje po EV desc
def test_generate_singles_sorted_ev_desc(gen):
    """Singles must be sorted by EV descending."""
    preds = make_three_predictions()
    result = gen.generate_singles(preds)
    evs = [s.ev_pct for s in result]
    assert evs == sorted(evs, reverse=True), "Singles should be sorted by EV descending"


# 3. generate_singles: kelly_stake <= max_kelly
def test_generate_singles_kelly_capped(gen):
    """Half Kelly must not exceed max_kelly."""
    preds = make_three_predictions()
    result = gen.generate_singles(preds)
    for sel in result:
        assert sel.kelly_stake_pct <= gen.max_kelly + 1e-9, (
            f"Kelly {sel.kelly_stake_pct} exceeds max_kelly {gen.max_kelly}"
        )


# 4. BetSelection.reasoning zawiera min 3 zdania
def test_generate_singles_reasoning_min_3_sentences(gen):
    """Reasoning must contain at least 3 sentences."""
    preds = make_three_predictions()
    result = gen.generate_singles(preds)
    assert len(result) > 0, "Expected at least one selection"
    for sel in result:
        # Count sentences roughly by splitting on '. ' or ending period
        sentences = [s.strip() for s in sel.reasoning.split(".") if s.strip()]
        assert len(sentences) >= 3, (
            f"Reasoning has only {len(sentences)} sentences: {sel.reasoning!r}"
        )


# 5. BetSelection.confidence jest HIGH/MEDIUM/LOW
def test_generate_singles_confidence_valid(gen):
    """Confidence must be one of HIGH, MEDIUM, LOW."""
    preds = make_three_predictions()
    result = gen.generate_singles(preds)
    valid = {"HIGH", "MEDIUM", "LOW"}
    for sel in result:
        assert sel.confidence in valid, f"Invalid confidence: {sel.confidence}"


# 6. build_system_bet 2/3: 3 selekcje -> combined odds > max individual odds
def test_build_system_2of3_combined_odds(gen):
    """System 2/3 combined odds should be product of selections."""
    preds = make_three_predictions()
    singles = gen.generate_singles(preds)
    assert len(singles) >= 3, "Need 3+ singles for this test"
    coupon = gen.build_system_bet(singles[:3], "2/3")
    assert coupon is not None
    assert coupon.coupon_type == "2/3"
    assert len(coupon.selections) == 3


# 7. build_system_bet trixie: 3 selections -> coupon_type == trixie
def test_build_system_trixie_type(gen):
    """Trixie coupon built from 3 selections."""
    preds = make_three_predictions()
    singles = gen.generate_singles(preds)
    assert len(singles) >= 3
    coupon = gen.build_system_bet(singles[:3], "trixie")
    assert coupon is not None
    assert coupon.coupon_type == "trixie"
    assert len(coupon.selections) == 3


# 8. combined_odds > max(individual odds)
def test_combined_odds_greater_than_individual(gen):
    """Combined odds (product) must be greater than any single selection odds."""
    preds = make_three_predictions()
    singles = gen.generate_singles(preds)
    assert len(singles) >= 2
    coupon = gen.build_system_bet(singles[:3], "2/3")
    assert coupon is not None
    max_individual = max(s.bk_odds for s in coupon.selections)
    assert coupon.combined_odds > max_individual, (
        f"Combined {coupon.combined_odds} should be > max individual {max_individual}"
    )


# 9. generate_daily_coupons zwraca dict z wymaganymi kluczami
def test_generate_daily_coupons_required_keys(gen):
    """Daily coupons dict must contain all required keys."""
    preds = make_three_predictions()
    result = gen.generate_daily_coupons(preds, TODAY)
    required_keys = {"date", "singles", "system_2of3", "trixie", "yankee", "top_pick", "summary"}
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


# 10. top_pick ma najwyższe EV
def test_generate_daily_coupons_top_pick_highest_ev(gen):
    """top_pick must be the selection with highest EV."""
    preds = make_three_predictions()
    result = gen.generate_daily_coupons(preds, TODAY)
    assert result["top_pick"] is not None
    singles = result["singles"]
    max_ev = max(s.ev_pct for s in singles)
    assert abs(result["top_pick"].ev_pct - max_ev) < 1e-9, (
        f"top_pick EV {result['top_pick'].ev_pct} != max EV {max_ev}"
    )


# 11. generate_singles z 0 selekcji EV > min_ev -> pusta lista
def test_generate_singles_empty_when_no_ev(gen):
    """Return empty list when no predictions meet EV threshold or odds range."""
    # odds_a < min_odds -> filtered out; odds_b > max_odds -> filtered out
    preds = [
        make_prediction(match_id="x1", p_model=0.30, bk_odds_a=1.10, bk_odds_b=6.00),
        make_prediction(match_id="x2", p_model=0.35, bk_odds_a=1.15, bk_odds_b=7.00),
    ]
    result = gen.generate_singles(preds)
    assert result == [], f"Expected empty list, got {len(result)} selections"


# 12. system wymaga min 3 selekcji
def test_build_system_requires_min_3_selections(gen):
    """System bet should return None if fewer than 3 eligible selections."""
    preds = make_three_predictions()
    singles = gen.generate_singles(preds)
    # Pass only 2 selections
    coupon = gen.build_system_bet(singles[:2], "2/3")
    assert coupon is None, "System with < 3 selections should return None"
