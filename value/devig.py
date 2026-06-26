"""
De-vigging methods for converting bookmaker odds to true probabilities.
Spec: value_detector/
Iter: 36-37
"""
import math
import numpy as np
from scipy.optimize import brentq


def overround(odds_a: float, odds_b: float) -> float:
    """overround = 1/odds_a + 1/odds_b"""
    return 1.0 / odds_a + 1.0 / odds_b


def devig_proportional(odds_a: float, odds_b: float) -> tuple[float, float]:
    """
    Proportional (additive margin) method.
    p_true_A = implied_A / (implied_A + implied_B)
    """
    imp_a = 1.0 / odds_a
    imp_b = 1.0 / odds_b
    total = imp_a + imp_b
    p_a = imp_a / total
    p_b = imp_b / total
    return p_a, p_b


def devig_additive(odds_a: float, odds_b: float) -> tuple[float, float]:
    """
    Additive (subtract half margin from each implied probability).
    p_true_A = implied_A - margin/2
    """
    imp_a = 1.0 / odds_a
    imp_b = 1.0 / odds_b
    margin = imp_a + imp_b - 1.0
    p_a = imp_a - margin / 2.0
    p_b = imp_b - margin / 2.0
    # Clamp to valid probabilities
    p_a = max(0.0, min(1.0, p_a))
    p_b = max(0.0, min(1.0, p_b))
    # Renormalize
    total = p_a + p_b
    return p_a / total, p_b / total


def devig_power_shin(odds_a: float, odds_b: float, tol: float = 1e-8) -> tuple[float, float]:
    """
    Power/Shin method: find z such that implied_A^z + implied_B^z = 1.
    Use brentq root-finding.
    Returns (p_a, p_b) = (implied_A^z, implied_B^z).
    Minimizes favourite-longshot bias.
    """
    imp_a = 1.0 / odds_a
    imp_b = 1.0 / odds_b

    # If already fair (sum == 1), z=1
    total = imp_a + imp_b
    if abs(total - 1.0) < tol:
        return imp_a, imp_b

    def f(z):
        return imp_a ** z + imp_b ** z - 1.0

    # Find bracket: when z > 1, sums decrease toward 0
    # when z < 1, sums increase above 1
    # We need f(z)=0 where z > 0
    try:
        z = brentq(f, 0.01, 10.0, xtol=tol)
    except ValueError:
        # Fallback to proportional
        return devig_proportional(odds_a, odds_b)

    p_a = imp_a ** z
    p_b = imp_b ** z
    # Normalize for numerical stability
    total = p_a + p_b
    return p_a / total, p_b / total


def devig_multiplicative(odds_a: float, odds_b: float) -> tuple[float, float]:
    """
    Multiplicative method: divide each implied probability by overround.
    p_true_A = implied_A / overround
    """
    imp_a = 1.0 / odds_a
    imp_b = 1.0 / odds_b
    ov = imp_a + imp_b  # overround
    p_a = imp_a / ov
    p_b = imp_b / ov
    return p_a, p_b


def best_devig(odds_a: float, odds_b: float) -> tuple[float, float]:
    """Default: Power/Shin method. Returns (p_a, p_b)."""
    return devig_power_shin(odds_a, odds_b)
