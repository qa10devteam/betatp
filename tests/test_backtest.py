"""
test_backtest.py — 5 tests for BacktestEngine
"""
import pytest
import numpy as np
from backtest.engine import BacktestConfig, BacktestResult, BacktestEngine


# ─────────────────────── Fixtures ───────────────────────────────

@pytest.fixture
def default_config():
    return BacktestConfig()


@pytest.fixture
def engine(default_config):
    return BacktestEngine(default_config)


# ─────────────────────── Test 1: BacktestConfig defaults ─────────────────────

def test_backtest_config_defaults(default_config):
    """BacktestConfig should have sensible default values"""
    cfg = default_config
    assert cfg.train_end_year == 2018
    assert cfg.test_start_year == 2019
    assert cfg.test_end_year == 2025
    assert 0.0 < cfg.kelly_fraction <= 1.0, "Kelly fraction should be in (0, 1]"
    assert cfg.min_ev >= 0.0, "min_ev should be non-negative"
    assert cfg.min_odds >= 1.0, "min_odds should be >= 1"
    assert cfg.max_odds > cfg.min_odds, "max_odds must exceed min_odds"
    assert 0.0 < cfg.max_stake_pct <= 1.0, "max_stake_pct should be in (0, 1]"
    assert cfg.initial_bankroll > 0.0, "initial_bankroll must be positive"
    assert cfg.n_books > 0, "n_books must be positive"


# ─────────────────────── Test 2: _simulate_bet win -> positive PnL ───────────

def test_simulate_bet_win(engine):
    """Winning bet should produce positive PnL"""
    stake = 100.0
    odds = 2.5
    outcome = 1  # win
    pnl = engine._simulate_bet(stake, odds, outcome)
    assert pnl > 0, f"Expected positive PnL on win, got {pnl}"
    # PnL = stake * (odds - 1) = 100 * 1.5 = 150
    assert pnl == pytest.approx(stake * (odds - 1), rel=1e-9)


# ─────────────────────── Test 3: _simulate_bet loss -> negative PnL ──────────

def test_simulate_bet_loss(engine):
    """Losing bet should produce negative PnL"""
    stake = 100.0
    odds = 2.5
    outcome = 0  # loss
    pnl = engine._simulate_bet(stake, odds, outcome)
    assert pnl < 0, f"Expected negative PnL on loss, got {pnl}"
    # PnL = -stake
    assert pnl == pytest.approx(-stake, rel=1e-9)


# ─────────────────────── Test 4: compute_metrics roi calculation ──────────────

def test_compute_metrics_roi(engine):
    """ROI = sum(pnl) / sum(stakes) * 100"""
    bet_history = [
        {"stake": 100.0, "odds": 2.0, "outcome": 1, "pnl": 100.0,
         "bankroll": 1100.0, "ev": 0.05, "clv": 0.02, "surface": "Hard", "level": "G", "date": "2020-01"},
        {"stake": 100.0, "odds": 2.0, "outcome": 0, "pnl": -100.0,
         "bankroll": 1000.0, "ev": 0.05, "clv": 0.02, "surface": "Hard", "level": "G", "date": "2020-01"},
        {"stake": 50.0, "odds": 3.0, "outcome": 1, "pnl": 100.0,
         "bankroll": 1100.0, "ev": 0.08, "clv": 0.03, "surface": "Clay", "level": "M", "date": "2020-02"},
    ]
    result = engine.compute_metrics(bet_history)
    total_stake = 100.0 + 100.0 + 50.0  # = 250.0
    total_pnl = 100.0 - 100.0 + 100.0  # = 100.0
    expected_roi = total_pnl / total_stake * 100  # = 40.0
    assert isinstance(result, BacktestResult)
    assert result.roi_pct == pytest.approx(expected_roi, rel=1e-6)
    assert result.n_bets == 3


# ─────────────────────── Test 5: max_drawdown >= 0 ───────────────────────────

def test_max_drawdown_non_negative(engine):
    """max_drawdown_pct must always be >= 0"""
    # Scenario with a drawdown
    bet_history = [
        {"stake": 100.0, "odds": 2.0, "outcome": 0, "pnl": -100.0,
         "bankroll": 900.0, "ev": 0.05, "clv": 0.0, "surface": "Hard", "level": "G", "date": "2020-01"},
        {"stake": 50.0, "odds": 2.0, "outcome": 1, "pnl": 50.0,
         "bankroll": 950.0, "ev": 0.05, "clv": 0.0, "surface": "Clay", "level": "G", "date": "2020-02"},
        {"stake": 50.0, "odds": 2.0, "outcome": 1, "pnl": 50.0,
         "bankroll": 1000.0, "ev": 0.05, "clv": 0.0, "surface": "Hard", "level": "G", "date": "2020-03"},
    ]
    result = engine.compute_metrics(bet_history)
    assert result.max_drawdown_pct >= 0.0, "max_drawdown_pct must be non-negative"

    # Scenario with no drawdown (all wins)
    bet_history_win = [
        {"stake": 100.0, "odds": 2.0, "outcome": 1, "pnl": 100.0,
         "bankroll": 1100.0, "ev": 0.05, "clv": 0.0, "surface": "Hard", "level": "G", "date": "2020-01"},
        {"stake": 100.0, "odds": 2.0, "outcome": 1, "pnl": 100.0,
         "bankroll": 1200.0, "ev": 0.05, "clv": 0.0, "surface": "Clay", "level": "G", "date": "2020-02"},
    ]
    result_win = engine.compute_metrics(bet_history_win)
    assert result_win.max_drawdown_pct >= 0.0
