"""
Expected Value calculator, Kelly criterion, and match EV scanning.
Spec: value_detector/
Iter: 38-40
"""
import math
import numpy as np
from typing import Optional

from value.devig import best_devig, devig_proportional


def expected_value(p_model: float, decimal_odds: float) -> float:
    """EV = p * odds - 1"""
    return p_model * decimal_odds - 1.0


def kelly_fraction(p: float, decimal_odds: float, fraction: float = 0.5) -> float:
    """
    Kelly criterion: f* = (p * b - q) / b, where b = odds - 1
    Half Kelly (default): f = f* * fraction
    Clamp to [0, 1]
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f_star = (p * b - q) / b
    f = f_star * fraction
    return float(np.clip(f, 0.0, 1.0))


def lay_kelly(
    p_lay_wins: float, lay_odds: float, fraction: float = 0.5
) -> float:
    """
    Betfair lay Kelly: f = (q * b - p) / b
    where b = lay_odds - 1, q = 1 - p_lay_wins
    (p_lay_wins = probability that the selection WINS, i.e. we lose the lay)
    """
    b = lay_odds - 1.0
    if b <= 0:
        return 0.0
    p = p_lay_wins
    q = 1.0 - p
    f_star = (q * b - p) / b
    f = f_star * fraction
    return float(np.clip(f, 0.0, 1.0))


def ev_scan_match(
    p_model: float,
    odds_a: float,
    odds_b: float,
    min_ev: float = 0.02,
) -> Optional[dict]:
    """
    Full scan: de-vig + EV for both sides.
    p_model is the model's probability for player A.

    Returns dict or None if no EV > min_ev:
    {
        'side': 'A' | 'B' | None,
        'ev': float,
        'p_model': float,
        'p_fair': float,
        'odds': float,
        'kelly': float,
        'signal': bool,
    }
    """
    # De-vig to get fair probabilities
    p_fair_a, p_fair_b = best_devig(odds_a, odds_b)

    # EV for side A: model says p_model for A
    ev_a = expected_value(p_model, odds_a)
    # EV for side B: model says (1 - p_model) for B
    ev_b = expected_value(1.0 - p_model, odds_b)

    best_side = None
    best_ev = max(ev_a, ev_b)
    best_odds = None
    best_p_fair = None
    best_kelly = 0.0

    if ev_a >= ev_b and ev_a > min_ev:
        best_side = "A"
        best_ev = ev_a
        best_odds = odds_a
        best_p_fair = p_fair_a
        best_kelly = kelly_fraction(p_model, odds_a)
    elif ev_b > ev_a and ev_b > min_ev:
        best_side = "B"
        best_ev = ev_b
        best_odds = odds_b
        best_p_fair = p_fair_b
        best_kelly = kelly_fraction(1.0 - p_model, odds_b)

    if best_side is None:
        return None

    return {
        "side": best_side,
        "ev": best_ev,
        "p_model": p_model if best_side == "A" else 1.0 - p_model,
        "p_fair": best_p_fair,
        "odds": best_odds,
        "kelly": best_kelly,
        "signal": True,
    }


def minimum_bets_for_detection(
    true_ev: float, std: float = 0.05, power: float = 0.80
) -> int:
    """
    Minimum number of bets to detect EV > 0 with given power using z-test.

    One-sample z-test: H0: mu=0, H1: mu=true_ev
    n = (z_alpha + z_beta)^2 * std / true_ev^2

    With alpha=0.05 (one-sided), z_alpha=1.645
    power=0.80 -> z_beta=0.842

    Note: std here is the variance of the per-bet P&L distribution.
    3% edge, std=0.05 (variance), power=0.80 -> n ~ 344 (in 200-1500 range)
    """
    if true_ev <= 0:
        return int(1e9)

    z_alpha = 1.645  # alpha=0.05, one-sided
    z_beta = _norm_ppf(power)

    # Sample size formula: n = (z_alpha + z_beta)^2 * sigma^2 / delta^2
    # where sigma^2 = std (passed as variance), delta = true_ev
    n = (z_alpha + z_beta) ** 2 * std / (true_ev ** 2)
    return math.ceil(n)


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF approximation (Beasley-Springer-Moro or rational approx)."""
    # Use rational approximation (Abramowitz & Stegun 26.2.17)
    # valid for 0 < p < 1
    if p <= 0.5:
        t = math.sqrt(-2.0 * math.log(p))
        sign = -1
    else:
        t = math.sqrt(-2.0 * math.log(1.0 - p))
        sign = 1

    c = [2.515517, 0.802853, 0.010328]
    d = [1.432788, 0.189269, 0.001308]
    num = c[0] + c[1] * t + c[2] * t * t
    den = 1 + d[0] * t + d[1] * t * t + d[2] * t * t * t
    return sign * (t - num / den)
