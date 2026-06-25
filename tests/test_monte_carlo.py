"""
Tests for Monte Carlo Engine — betatp.io
10 tests covering correctness, convergence, and performance.
"""
import time
import math
import pytest
import numpy as np

from engine.monte_carlo import MonteCarloEngine, MatchConfig, SimulationResult


# Shared engine (N=100_000 for convergence tests)
@pytest.fixture(scope="module")
def engine_100k():
    return MonteCarloEngine(n_simulations=100_000, seed=42)


@pytest.fixture(scope="module")
def engine_10k():
    return MonteCarloEngine(n_simulations=10_000, seed=42)


@pytest.fixture(scope="module")
def base_config():
    return MatchConfig(p_serve_a=0.65, p_serve_b=0.63)


@pytest.fixture(scope="module")
def result_100k(engine_100k, base_config):
    return engine_100k.simulate_match(base_config)


# --- Test 1: p_win_a + p_win_b == 1.0 ---
def test_probabilities_sum_to_one(result_100k):
    """p_win_a + p_win_b must equal exactly 1.0."""
    r = result_100k
    assert abs(r.p_win_a + r.p_win_b - 1.0) < 1e-9, (
        f"p_win_a + p_win_b = {r.p_win_a + r.p_win_b}")


# --- Test 2: Symmetry — equal serve probs → p_win_a ≈ 0.5 ---
def test_symmetry(engine_100k):
    """When p_serve_a == p_serve_b, first-server advantage is tiny → p_win_a ≈ 0.5 ± 0.01."""
    config = MatchConfig(p_serve_a=0.65, p_serve_b=0.65)
    r = engine_100k.simulate_match(config)
    assert abs(r.p_win_a - 0.5) < 0.01, f"p_win_a={r.p_win_a:.4f} (expected ≈ 0.5)"


# --- Test 3: SE < 0.002 for N=100,000 ---
def test_standard_error_convergence(result_100k):
    """CLT convergence: SE = sqrt(p*(1-p)/N) < 0.002 for N=100k."""
    p = result_100k.p_win_a
    n = result_100k.n_simulations
    se = math.sqrt(p * (1 - p) / n)
    assert se < 0.002, f"SE={se:.5f} (expected < 0.002, N={n})"


# --- Test 4: p_set_scores sum to 1.0 ---
def test_set_scores_sum(result_100k):
    """All set score probabilities must sum to 1.0."""
    total = sum(result_100k.p_set_scores.values())
    assert abs(total - 1.0) < 1e-3, f"p_set_scores sum = {total:.6f}"


# --- Test 5: expected_games ∈ [12, 50] ---
def test_expected_games_range(result_100k):
    """Expected number of games should be reasonable for ATP matches."""
    eg = result_100k.expected_games
    assert 12 <= eg <= 50, f"expected_games={eg:.1f} (expected ∈ [12, 50])"


# --- Test 6: Monotonicity — higher p_serve_a → higher p_win_a ---
def test_monotonicity(engine_10k):
    """Higher serve win probability for A should lead to higher match win probability."""
    configs = [
        MatchConfig(p_serve_a=0.55, p_serve_b=0.63),
        MatchConfig(p_serve_a=0.65, p_serve_b=0.63),
        MatchConfig(p_serve_a=0.75, p_serve_b=0.63),
    ]
    results = [engine_10k.simulate_match(c) for c in configs]
    p_wins = [r.p_win_a for r in results]
    for i in range(len(p_wins) - 1):
        assert p_wins[i] < p_wins[i + 1], (
            f"Monotonicity failed: p_win_a[{i}]={p_wins[i]:.4f} >= p_win_a[{i+1}]={p_wins[i+1]:.4f}")


# --- Test 7: BO5 expected_games > BO3 expected_games ---
def test_bo5_more_games(engine_10k):
    """Best-of-5 should produce more expected games than best-of-3."""
    config3 = MatchConfig(p_serve_a=0.65, p_serve_b=0.63, best_of=3)
    config5 = MatchConfig(p_serve_a=0.65, p_serve_b=0.63, best_of=5)
    r3 = engine_10k.simulate_match(config3)
    r5 = engine_10k.simulate_match(config5)
    assert r5.expected_games > r3.expected_games, (
        f"BO5 expected_games={r5.expected_games:.1f} <= BO3 expected_games={r3.expected_games:.1f}")


# --- Test 8: LUT lookup vs MC — max diff < 0.01 ---
def test_lut_vs_mc_consistency(engine_100k, base_config):
    """LUT (exact DP) and MC simulation should agree within 0.01."""
    lut = engine_100k.precompute_lut(base_config)
    # Start state
    start = (0, 0, 0, 0, 0, 0, 0)
    lut_val = lut.get(start, None)
    assert lut_val is not None, "Start state not found in LUT"

    # Also get MC estimate
    r = engine_100k.simulate_match(base_config)
    mc_val = r.p_win_a

    diff = abs(lut_val - mc_val)
    assert diff < 0.01, (
        f"LUT={lut_val:.4f} vs MC={mc_val:.4f}, diff={diff:.4f} (max allowed: 0.01)")


# --- Test 9: LUT terminal states V=1.0 or V=0.0 ---
def test_lut_terminal_states(engine_100k, base_config):
    """Terminal states in LUT must be exactly 1.0 (A wins) or 0.0 (B wins)."""
    lut = engine_100k.precompute_lut(base_config)
    sets_to_win = (base_config.best_of + 1) // 2

    terminal_values = set()
    for (sa, sb, *_), v in lut.items():
        if sa >= sets_to_win or sb >= sets_to_win:
            terminal_values.add(round(v, 9))

    # Terminal states must be 0.0 or 1.0
    for tv in terminal_values:
        assert tv in (0.0, 1.0), f"Terminal state has value {tv} (expected 0.0 or 1.0)"

    assert len(terminal_values) > 0, "No terminal states found in LUT"


# --- Test 10: Performance — N=100,000 in < 5 seconds ---
def test_performance():
    """N=100,000 simulations must complete in under 5 seconds."""
    engine = MonteCarloEngine(n_simulations=100_000, seed=0)
    config = MatchConfig(p_serve_a=0.65, p_serve_b=0.63)

    t0 = time.perf_counter()
    r = engine.simulate_match(config)
    elapsed = time.perf_counter() - t0

    assert elapsed < 5.0, f"Simulation took {elapsed:.2f}s (limit: 5s)"
    assert r.computation_time_ms < 5000, f"Reported time {r.computation_time_ms:.0f}ms (limit: 5000ms)"
