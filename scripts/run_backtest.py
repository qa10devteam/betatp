"""
Backtest betatp.io — Elo predykcja na danych ATP 1968-2025.

Protokół Walk-Forward:
- Trening Elo: 1968-2018 (kalibracja ratingów)
- Test: 2019-2025 (~18k meczów)

Metryki:
- Accuracy (% poprawnych predykcji wyższego Elo)
- Brier Score (im niższy tym lepiej, losowy = 0.25)
- Log Loss
- ROI przy Half Kelly vs zawsze-faworyt vs zawsze-1u
- Kalibracja: predicted probability vs actual win rate

Symulowane kursy: Pinnacle-style margin 2.5%
  odds_fav = 1 / (true_prob + margin/2)
  odds_dog = 1 / (1 - true_prob + margin/2)
"""
import sys
import json
import math
import time
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from data.loader import load_all_matches
from engine.elo import EloEngine
from engine.elo_runner import compute_all_elos


def simulate_odds(p_true: float, margin: float = 0.025) -> tuple[float, float]:
    """Simulate bookmaker odds from true probability (Pinnacle-style)."""
    p_fav = p_true + margin / 2
    p_dog = (1 - p_true) + margin / 2
    return 1 / p_fav, 1 / p_dog


def brier_score(probs: list[float], outcomes: list[int]) -> float:
    """Brier Score = mean((p - y)^2). Random baseline = 0.25."""
    return float(np.mean([(p - y) ** 2 for p, y in zip(probs, outcomes)]))


def log_loss(probs: list[float], outcomes: list[int], eps: float = 1e-7) -> float:
    """Binary cross-entropy."""
    n = len(probs)
    ll = 0.0
    for p, y in zip(probs, outcomes):
        p = max(eps, min(1 - eps, p))
        ll += y * math.log(p) + (1 - y) * math.log(1 - p)
    return -ll / n


def calibration_table(probs: list[float], outcomes: list[int], n_bins: int = 10) -> list[dict]:
    """Bucket predictions into bins and compute actual win rate."""
    bins = np.linspace(0, 1, n_bins + 1)
    table = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        idx = [j for j, p in enumerate(probs) if lo <= p < hi]
        if not idx:
            continue
        avg_pred = np.mean([probs[j] for j in idx])
        actual = np.mean([outcomes[j] for j in idx])
        table.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "n": len(idx),
            "avg_pred": round(float(avg_pred), 3),
            "actual_win": round(float(actual), 3),
            "diff": round(float(actual - avg_pred), 3),
        })
    return table


def run_betting_simulation(
    records: list[dict],
    bankroll: float = 1000.0,
    half_kelly: bool = True,
    min_ev: float = 0.02,
) -> dict:
    """
    Simulate betting on matches where EV > min_ev.
    Uses Half Kelly staking.
    Returns ROI, final bankroll, Sharpe, max drawdown.
    """
    equity = [bankroll]
    curr = bankroll
    bets = 0
    won = 0
    total_wagered = 0.0

    for rec in records:
        p_model = rec["p_win_a"]
        odds = rec["odds_a"]  # backing player_a (winner in our data)
        # EV check
        ev = p_model * odds - 1
        if ev < min_ev:
            equity.append(curr)
            continue

        # Half Kelly
        b = odds - 1
        f_full = (b * p_model - (1 - p_model)) / b
        f_half = max(0, f_full * 0.5)
        stake = min(curr * f_half, curr * 0.03, 50.0)  # cap at 3% AND max 50 units
        if stake < 1.0 or curr < 10:
            equity.append(curr)
            continue

        bets += 1
        total_wagered += stake
        outcome = rec["outcome"]  # 1 = winner (player_a) won, 0 = lost
        if outcome == 1:
            curr += stake * b
            won += 1
        else:
            curr -= stake
        equity.append(curr)

    if bets == 0:
        return {"bets": 0, "roi": 0.0, "final_bankroll": bankroll}

    roi = (curr - bankroll) / total_wagered * 100
    returns = np.diff(equity) / np.array(equity[:-1])
    sharpe = (np.mean(returns) / np.std(returns) * math.sqrt(252)) if np.std(returns) > 0 else 0

    # Max drawdown
    peak = bankroll
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "bets": bets,
        "won": won,
        "win_rate": round(won / bets, 3),
        "roi": round(roi, 2),
        "final_bankroll": round(curr, 2),
        "total_wagered": round(total_wagered, 2),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown": round(max_dd, 3),
    }


def main():
    t0 = time.time()
    print("=" * 60)
    print("betatp.io BACKTEST — Elo Walk-Forward 1968-2025")
    print("=" * 60)

    # 1. Load data
    print("\n[1/5] Ładowanie danych TML-Database...")
    df = load_all_matches("/home/ubuntu/TML-Database")
    print(f"  Załadowano: {len(df):,} meczów ({df.tourney_date.min().date()} → {df.tourney_date.max().date()})")

    # 2. Train Elo on 1968-2018
    print("\n[2/5] Trening Elo na danych 1968-2018...")
    train_df = df[df.tourney_date.dt.year <= 2018].copy()
    print(f"  Mecze treningowe: {len(train_df):,}")

    engine = EloEngine()
    engine = compute_all_elos(train_df, engine)
    print(f"  Graczy w bazie Elo: {len(engine.ratings):,}")

    # Distribution of ratings
    all_ratings = [r.overall for r in engine.ratings.values() if r.n_matches >= 5]
    print(f"  Elo (min 5 meczów): mean={np.mean(all_ratings):.0f}, "
          f"std={np.std(all_ratings):.0f}, "
          f"p10={np.percentile(all_ratings, 10):.0f}, "
          f"p90={np.percentile(all_ratings, 90):.0f}")

    # 3. Test on 2019-2025
    print("\n[3/5] Test na danych 2019-2025...")
    test_df = df[(df.tourney_date.dt.year >= 2019) & (df.tourney_date.dt.year <= 2025)].copy()
    test_df = test_df.sort_values("tourney_date").reset_index(drop=True)
    print(f"  Mecze testowe: {len(test_df):,}")

    probs = []          # predicted P(player_a wins)
    outcomes = []       # 1 if player_a won, 0 if lost
    records = []        # for betting sim

    for _, row in test_df.iterrows():
        w_id = str(row["winner_id"])
        l_id = str(row["loser_id"])
        surface = row.get("surface", "Hard") or "Hard"
        tourney_level = row.get("tourney_level", "250") or "250"
        tourney_date = row["tourney_date"]

        if pd.isna(tourney_date):
            continue

        match_date = tourney_date.date() if hasattr(tourney_date, "date") else tourney_date

        # Predict BEFORE updating — our Elo model
        pred = engine.predict_match(w_id, l_id, surface)
        p_winner = pred["p_win_a"]   # P(winner_id wins)

        # Simulate BOOKMAKER odds based on ATP ranking (weaker model)
        w_rank = row.get("winner_rank")
        l_rank = row.get("loser_rank")
        try:
            w_rank_f = float(w_rank) if pd.notna(w_rank) and w_rank else None
            l_rank_f = float(l_rank) if pd.notna(l_rank) and l_rank else None
        except (TypeError, ValueError):
            w_rank_f = l_rank_f = None

        if w_rank_f and l_rank_f and w_rank_f > 0 and l_rank_f > 0:
            rank_diff = l_rank_f - w_rank_f  # positive = winner better ranked
            p_bk = 1 / (1 + math.exp(-0.003 * rank_diff))
        else:
            p_bk = 0.5

        odds_w, odds_l = simulate_odds(p_bk, margin=0.025)

        # Record winner and loser perspectives for calibration
        probs.append(p_winner)
        outcomes.append(1)
        probs.append(1 - p_winner)
        outcomes.append(0)

        # Betting: compare OUR model vs BOOKMAKER for BOTH sides
        # Side A: bet on winner_id
        ev_w = p_winner * odds_w - 1
        # Side B: bet on loser_id  
        ev_l = (1 - p_winner) * odds_l - 1

        # Best edge side
        if ev_w > ev_l and ev_w > 0:
            records.append({
                "p_win_a": p_winner,
                "odds_a": odds_w,
                "outcome": 1,   # winner wins → we win
                "ev": ev_w,
                "surface": surface,
                "tourney_level": tourney_level,
            })
        elif ev_l > ev_w and ev_l > 0:
            records.append({
                "p_win_a": 1 - p_winner,
                "odds_a": odds_l,
                "outcome": 0,   # loser wins → we lose (outcome=0 means our pick lost)
                "ev": ev_l,
                "surface": surface,
                "tourney_level": tourney_level,
            })

        # Update Elo with this match
        def _safe_int(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        engine.update_match(
            winner_id=w_id,
            loser_id=l_id,
            surface=surface,
            tourney_level=tourney_level,
            match_date=match_date,
            w_svpt=_safe_int(row.get("w_svpt")),
            w_1stWon=_safe_int(row.get("w_1stWon")),
            w_2ndWon=_safe_int(row.get("w_2ndWon")),
            l_svpt=_safe_int(row.get("l_svpt")),
            l_1stWon=_safe_int(row.get("l_1stWon")),
            l_2ndWon=_safe_int(row.get("l_2ndWon")),
        )

    print(f"  Predykcji wykonano: {len(records):,}")

    # 4. Compute metrics
    print("\n[4/5] Metryki predykcji...")

    # Accuracy: did higher-Elo player win?
    correct = sum(1 for p in probs if p > 0.5)
    accuracy = correct / len(probs)
    print(f"  Accuracy (wyższy Elo = zwycięzca): {accuracy:.3f} ({accuracy*100:.1f}%)")
    print(f"  Baseline (zawsze 50%):              0.500 (50.0%)")

    bs = brier_score(probs, outcomes)
    bs_random = 0.25
    bs_perfect = 0.0
    print(f"  Brier Score: {bs:.4f} (random={bs_random}, perfect={bs_perfect})")

    ll = log_loss(probs, outcomes)
    print(f"  Log Loss: {ll:.4f}")

    # Avg confidence
    avg_conf = np.mean(probs)
    print(f"  Avg P(winner): {avg_conf:.3f} (calibrated → should be >0.5)")

    # Per-surface accuracy
    print("\n  Per-surface accuracy:")
    surf_stats = {}
    for rec, p in zip(records, probs):
        s = rec["surface"]
        if s not in surf_stats:
            surf_stats[s] = {"correct": 0, "total": 0}
        surf_stats[s]["total"] += 1
        if p > 0.5:
            surf_stats[s]["correct"] += 1
    for surf, st in sorted(surf_stats.items()):
        acc = st["correct"] / st["total"]
        print(f"    {surf:8s}: {acc:.3f} ({st['correct']}/{st['total']})")

    # Calibration
    print("\n  Kalibracja (predicted vs actual):")
    cal = calibration_table(probs, outcomes, n_bins=10)
    for row_c in cal:
        bar = "█" * int(abs(row_c["diff"]) * 100)
        direction = "+" if row_c["diff"] > 0 else "-"
        print(f"    [{row_c['bin']}] n={row_c['n']:4d}  pred={row_c['avg_pred']:.3f}  actual={row_c['actual_win']:.3f}  diff={direction}{abs(row_c['diff']):.3f} {bar}")

    # 5. Betting simulation
    print("\n[5/5] Symulacja zakładów (Half Kelly, EV>2%)...")
    bet_result = run_betting_simulation(records, bankroll=1000.0, min_ev=0.02)
    print(f"  Zakładów postawionych: {bet_result['bets']:,}")
    if bet_result["bets"] > 0:
        print(f"  Win rate: {bet_result['win_rate']:.3f}")
        print(f"  ROI: {bet_result['roi']:.2f}%")
        print(f"  Końcowy bankroll: {bet_result['final_bankroll']:.0f} (start=1000)")
        print(f"  Sharpe: {bet_result['sharpe']:.3f}")
        print(f"  Max Drawdown: {bet_result['max_drawdown']:.1%}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"BACKTEST COMPLETED in {elapsed:.1f}s")
    print(f"{'='*60}")

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "train_matches": len(train_df),
        "test_matches": len(test_df),
        "predictions": len(probs),
        "metrics": {
            "accuracy": round(accuracy, 4),
            "brier_score": round(bs, 4),
            "log_loss": round(ll, 4),
            "avg_p_winner": round(avg_conf, 4),
        },
        "surface_accuracy": {s: round(st["correct"]/st["total"], 4) for s, st in surf_stats.items()},
        "betting": bet_result,
        "calibration": cal,
        "elapsed_seconds": round(elapsed, 1),
    }

    out_path = Path("/home/ubuntu/betatp/backtest_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWyniki zapisane: {out_path}")

    return results


if __name__ == "__main__":
    main()
