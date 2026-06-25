"""
tests/test_clv.py — 8 tests for CLVTracker module.
"""
import pytest
from datetime import datetime, timezone, timedelta
from value.clv_tracker import CLVTracker, BetRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tracker_with_bets(n: int, clv_value: float = 0.04, won: bool = True):
    """Create a CLVTracker with n bets all having same CLV."""
    t = CLVTracker()
    for i in range(n):
        # opening=2.10, closing such that CLV = clv_value
        opening = 2.10
        closing = opening / (1.0 + clv_value)
        bid = t.record_bet(f"match_{i}", "Player A", 10.0, opening)
        t.record_closing(bid, closing)
        t.record_result(bid, won)
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# 1. compute_clv: opening=2.10, closing=2.00 -> CLV=0.05
def test_compute_clv_positive():
    t = CLVTracker()
    bid = t.record_bet("m1", "Alcaraz", 10.0, 2.10)
    t.record_closing(bid, 2.00)
    clv = t.compute_clv(bid)
    expected = 2.10 / 2.00 - 1.0   # = 0.05
    assert abs(clv - expected) < 1e-9, f"Expected {expected}, got {clv}"


# 2. compute_clv: opening < closing -> CLV < 0
def test_compute_clv_negative():
    t = CLVTracker()
    bid = t.record_bet("m2", "Djokovic", 10.0, 1.80)
    t.record_closing(bid, 2.00)  # opening < closing
    clv = t.compute_clv(bid)
    assert clv < 0, f"CLV should be negative when opening < closing, got {clv}"


# 3. rolling_clv: średnia ostatnich 30 dni
def test_rolling_clv_30_days():
    t = CLVTracker()
    # Add recent bets
    for i in range(5):
        bid = t.record_bet(f"m{i}", "Player", 10.0, 2.10)
        ts_recent = datetime.now(tz=timezone.utc) - timedelta(days=5)
        t.record_closing(bid, 2.00, closing_timestamp=ts_recent)

    # Add old bet (outside 30 day window)
    bid_old = t.record_bet("old", "Player", 10.0, 2.10)
    ts_old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    t.record_closing(bid_old, 2.00, closing_timestamp=ts_old)

    rolling = t.rolling_clv(30)
    expected_clv = 2.10 / 2.00 - 1.0  # 0.05
    assert rolling is not None
    assert abs(rolling - expected_clv) < 1e-6, f"Expected ~{expected_clv:.4f}, got {rolling:.4f}"


# 4. significance_test: n<30 -> reject_h0=False (za mało danych)
def test_significance_test_not_reject_small_sample():
    """With fewer than 30 bets, reject_h0 must be False."""
    t = tracker_with_bets(10, clv_value=0.08)
    result = t.significance_test()
    assert result["reject_h0"] is False, (
        f"With n=10 should not reject H0, got reject_h0={result['reject_h0']}"
    )
    assert result["n_bets"] == 10


# 5. performance_tier: CLV=4% -> 'Elite'
def test_performance_tier_elite():
    t = tracker_with_bets(5, clv_value=0.04)
    tier = t.performance_tier()
    assert tier == "Elite", f"Expected Elite for 4% CLV, got {tier}"


# 6. performance_tier: CLV=0% -> 'Break-even'
def test_performance_tier_breakeven():
    t = tracker_with_bets(5, clv_value=0.00)
    tier = t.performance_tier()
    assert tier == "Break-even", f"Expected Break-even for 0% CLV, got {tier}"


# 7. record_result updates PnL
def test_record_result_updates_pnl():
    t = CLVTracker()
    bid = t.record_bet("m1", "Sinner", 10.0, 2.00)
    t.record_closing(bid, 1.90)

    # Win
    t.record_result(bid, True)
    rec = t._get(bid)
    expected_pnl = 10.0 * (2.00 - 1.0)  # stake * (odds - 1) = 10
    assert rec.actual_result == 1
    assert abs(rec.pnl - expected_pnl) < 1e-9, f"Expected PnL={expected_pnl}, got {rec.pnl}"

    # Test loss too
    bid2 = t.record_bet("m2", "Medvedev", 10.0, 1.80)
    t.record_closing(bid2, 1.75)
    t.record_result(bid2, False)
    rec2 = t._get(bid2)
    assert rec2.actual_result == 0
    assert abs(rec2.pnl - (-10.0)) < 1e-9, f"Expected PnL=-10, got {rec2.pnl}"


# 8. summary zwraca wszystkie wymagane klucze
def test_summary_required_keys():
    """summary() must return dict with all required keys."""
    t = tracker_with_bets(5, clv_value=0.03)
    s = t.summary()
    required = {
        "n_bets", "roi", "clv_7d", "clv_30d", "clv_90d", "clv_alltime",
        "significance", "tier", "profit_factor", "max_drawdown",
        "win_rate", "equity_curve",
    }
    for key in required:
        assert key in s, f"Missing key in summary: {key}"
