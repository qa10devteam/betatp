"""
End-to-end integration test dla betatp.io.
Test że cały pipeline działa od danych do kuponów.
"""
import sys
import json

# Raise recursion limit to handle MC DP computations
sys.setrecursionlimit(50000)

from datetime import date


def test_elo_pipeline():
    """Iter 1-18: Elo pipeline"""
    from engine.elo import EloEngine
    engine = EloEngine()
    # Symuluj 100 meczów
    for i in range(100):
        engine.update_match(
            winner_id=1, loser_id=2,
            surface='Hard', tourney_level='250',
            match_date=date(2024, 1, i % 28 + 1),
        )
        engine.update_match(
            winner_id=2, loser_id=3,
            surface='Clay', tourney_level='G',
            match_date=date(2024, 2, i % 28 + 1),
        )
    pred = engine.predict_match(1, 3, 'Hard')
    assert 0 < pred['p_win_a'] < 1, f"p_win_a={pred['p_win_a']}"
    assert abs(pred['p_win_a'] + (1 - pred['p_win_a']) - 1.0) < 1e-6
    print(f"✓ Elo pipeline: p(1 beats 3 on Hard)={pred['p_win_a']:.3f}")
    return pred


def test_monte_carlo_pipeline():
    """Iter 19-25: Monte Carlo pipeline"""
    from engine.monte_carlo import MonteCarloEngine, MatchConfig
    mc = MonteCarloEngine(n_simulations=10_000, seed=42)
    config = MatchConfig(p_serve_a=0.65, p_serve_b=0.62)
    result = mc.simulate_match(config)
    assert abs(result.p_win_a + result.p_win_b - 1.0) < 1e-6
    assert result.expected_games > 0
    print(f"✓ MC pipeline: p_win_a={result.p_win_a:.3f}, E[games]={result.expected_games:.1f}")
    return result


def test_value_pipeline():
    """Iter 36-40: De-vig + EV + Kelly"""
    from value.devig import devig_power_shin, best_devig
    from value.ev_calculator import expected_value, kelly_fraction, ev_scan_match
    # Devig Djokovic 1.80 vs opponent 2.10
    p_djok, p_opp = best_devig(1.80, 2.10)
    assert abs(p_djok + p_opp - 1.0) < 1e-6
    ev = expected_value(p_djok + 0.05, 1.80)  # model gives +5% edge
    kelly = kelly_fraction(p_djok + 0.05, 1.80)
    print(f"✓ Value pipeline: p_djok={p_djok:.3f}, EV={ev:.3f}, Kelly={kelly:.3f}")
    return {"p_djok": p_djok, "ev": ev, "kelly": kelly}


def test_coupon_pipeline():
    """Iter 71-86: CouponGenerator"""
    from engine.coupon import CouponGenerator
    gen = CouponGenerator(min_ev=0.02)
    # Mock 5 match predictions
    matches = [
        {
            "match_id": f"m{i}",
            "player_a": f"PlayerA{i}",
            "player_b": f"PlayerB{i}",
            "surface": "Hard",
            "tourney": "Australian Open",
            "tourney_level": "G",
            "match_date": date(2025, 1, 20),
            "p_model": 0.60 + i * 0.02,
            "bk_odds_a": 1.70 - i * 0.03,
            "bk_odds_b": 2.30,
            "elo_diff": 100.0 + i * 20,
            "form_a": "WWWWL",
            "form_b": "LWWLL",
            "fatigue_a": 0.2,
            "fatigue_b": 0.4,
            "h2h": {"wins": 3, "losses": 1},
            "n_matches_a": 200,
            "n_matches_b": 180,
        }
        for i in range(5)
    ]
    coupons = gen.generate_daily_coupons(matches, date(2025, 1, 20))
    assert 'singles' in coupons, "'singles' key missing from coupons"
    assert 'top_pick' in coupons, "'top_pick' key missing from coupons"
    print(f"✓ Coupon pipeline: {len(coupons.get('singles', []))} singles")
    if coupons.get('top_pick'):
        tp = coupons['top_pick']
        print(f"  TOP PICK: {tp.player_backed} (EV={tp.ev_pct:.1%})")
        print(f"  REASONING: {tp.reasoning[:100]}...")
    return coupons


def test_clv_pipeline():
    """Iter 66-70: CLV Tracker"""
    from value.clv_tracker import CLVTracker
    tracker = CLVTracker()
    for i in range(50):
        bid = tracker.record_bet(f"match_{i}", f"PlayerA", 100.0, 2.10 - i * 0.01)
        tracker.record_closing(bid, 2.00 - i * 0.01)  # systematically positive CLV
        tracker.record_result(bid, i % 3 != 0)  # 67% win rate
    summary = tracker.summary()
    assert 'roi' in summary, f"'roi' key missing from summary: {summary.keys()}"
    assert 'clv_alltime' in summary, f"'clv_alltime' key missing from summary: {summary.keys()}"
    print(f"✓ CLV pipeline: roi={summary.get('roi', 0):.1f}%, CLV={summary.get('clv_alltime', 0):.3f}")
    print(f"  Tier: {tracker.performance_tier()}")
    return summary


if __name__ == "__main__":
    results = {}
    tests = [
        ("elo", test_elo_pipeline),
        ("monte_carlo", test_monte_carlo_pipeline),
        ("value", test_value_pipeline),
        ("coupon", test_coupon_pipeline),
        ("clv", test_clv_pipeline),
    ]
    passed = 0
    for name, fn in tests:
        try:
            results[name] = fn()
            passed += 1
        except Exception as e:
            import traceback
            print(f"✗ {name}: {e}")
            traceback.print_exc()
            results[name] = {"error": str(e)}

    print(f"\n{'='*50}")
    print(f"INTEGRATION: {passed}/{len(tests)} passed")
    print(f"{'='*50}")
    sys.exit(0 if passed >= 3 else 1)
