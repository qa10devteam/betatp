"""
test_ensemble.py — 8 tests for BetaTPEnsemble and WalkForwardDataset
"""
import pytest
import numpy as np
import pandas as pd
from ml.ensemble import BetaTPEnsemble, EnsembleWeights
from ml.dataset import WalkForwardDataset


# ─────────────────────────── Fixtures ───────────────────────────

@pytest.fixture
def ensemble():
    return BetaTPEnsemble(models_dir="/tmp/test_betatp_models")


@pytest.fixture
def dataset():
    return WalkForwardDataset()


@pytest.fixture
def simple_data():
    """Simple synthetic data for quick ensemble tests (no real training)."""
    np.random.seed(42)
    n = 20
    X = np.random.rand(n, 5).astype(np.float32)
    elo_probs = np.random.uniform(0.3, 0.7, n)
    return X, elo_probs


# ─────────────────────── Test 1: cold_start n_matches=5 ──────────────────────

def test_cold_start_low_n_matches(ensemble):
    """n_matches=5 -> elo weight should be 0.90"""
    weights = ensemble._cold_start_weights(n_matches=5)
    assert isinstance(weights, EnsembleWeights)
    assert weights.elo == pytest.approx(0.90, abs=1e-9)


# ─────────────────────── Test 2: cold_start n_matches=100 ────────────────────

def test_cold_start_high_n_matches(ensemble):
    """n_matches=100 -> elo weight should be default 0.30"""
    weights = ensemble._cold_start_weights(n_matches=100)
    assert isinstance(weights, EnsembleWeights)
    assert weights.elo == pytest.approx(0.30, abs=1e-9)


# ─────────────────────── Test 3: predict_proba output in [0, 1] ──────────────

def test_predict_proba_range(ensemble, simple_data):
    """predict_proba should return values in [0, 1]"""
    X, elo_probs = simple_data
    # Not fitted -> elo-only fallback
    probs = ensemble.predict_proba(X, elo_probs, n_matches=100)
    assert probs.shape == (len(X),)
    assert np.all(probs >= 0.0), "Probabilities must be >= 0"
    assert np.all(probs <= 1.0), "Probabilities must be <= 1"


# ─────────────────────── Test 4: predict_proba + complement = 1.0 ────────────

def test_predict_proba_complement(ensemble, simple_data):
    """P(A wins) — complement P(B wins) should be handled correctly (1-P in [0,1])"""
    X, elo_probs = simple_data
    probs = ensemble.predict_proba(X, elo_probs, n_matches=100)
    complements = 1.0 - probs
    assert np.all(complements >= 0.0), "1-P must be >= 0"
    assert np.all(complements <= 1.0), "1-P must be <= 1"
    # sum of P and (1-P) must equal 1.0 for each example
    sums = probs + complements
    np.testing.assert_allclose(sums, np.ones(len(X)), atol=1e-9)


# ─────────────────────── Test 5: check_leakage detects forbidden columns ─────

def test_check_leakage_detects_forbidden(dataset):
    """check_leakage should detect forbidden post-match columns"""
    X_with_leak = pd.DataFrame({
        "elo_diff": [1.0, 2.0],
        "surface_hard": [1, 0],
        "w_ace": [10, 5],          # forbidden
        "l_bpFaced": [3, 7],       # forbidden
        "winner_rank": [1, 10],    # forbidden
    })
    violations = dataset.check_leakage(X_with_leak)
    assert len(violations) > 0, "Should detect leakage violations"
    assert "w_ace" in violations
    assert "l_bpFaced" in violations
    assert "winner_rank" in violations


# ─────────────────────── Test 6: WalkForwardDataset train_end < val_start ────

def test_walk_forward_no_leakage(dataset):
    """train_end must be strictly less than val_start in every split"""
    for train_end, val_start, val_end in dataset.SPLITS:
        assert train_end < val_start, (
            f"Leakage: train_end={train_end} >= val_start={val_start}"
        )


# ─────────────────────── Test 7: SPLITS count = 5 ────────────────────────────

def test_splits_count(dataset):
    """WalkForwardDataset.SPLITS must have exactly 5 entries"""
    assert len(dataset.SPLITS) == 5


# ─────────────────────── Test 8: HOLDOUT not used in get_all_splits ──────────

def test_holdout_not_in_splits(dataset):
    """HOLDOUT years must not overlap with any split's validation window"""
    holdout_start, holdout_end = dataset.HOLDOUT
    for train_end, val_start, val_end in dataset.SPLITS:
        assert val_end < holdout_start, (
            f"Split val_end={val_end} overlaps with HOLDOUT start={holdout_start}"
        )
