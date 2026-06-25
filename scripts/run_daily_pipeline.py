"""
scripts/run_daily_pipeline.py — Główny script dzienny dla betatp.io
Iter 126-128

Pipeline:
1. Wczytaj dzisiejsze mecze ATP (z pliku lub dummy data)
2. Oblicz predykcje Elo
3. Uruchom Monte Carlo dla top 20 meczów
4. Wygeneruj kupony
5. Zapisz do JSON + opcjonalnie do DB
6. Wyślij Telegram alert (jeśli token)
"""
import json
import sys
import os
import math
from pathlib import Path
from datetime import date, datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Dummy data ─────────────────────────────────────────────────────────────────

DUMMY_MATCHES = [
    {
        "match_id": f"atp_{i:04d}",
        "player_a": f"Player_A_{i}",
        "player_b": f"Player_B_{i}",
        "surface": ["hard", "clay", "grass"][i % 3],
        "tourney_name": "ATP Mock Tournament",
        "tourney_level": "250",
        "best_of": 3,
        "odds_a": round(1.60 + i * 0.1, 2),
        "odds_b": round(2.40 - i * 0.05, 2),
    }
    for i in range(25)
]


# ── Elo prediction logic (simplified) ─────────────────────────────────────────

def elo_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def compute_predictions(matches: list[dict]) -> list[dict]:
    """Step 2: Oblicz predykcje Elo dla każdego meczu."""
    results = []
    for m in matches:
        # Mock Elo ratings (w produkcji: z EloEngine)
        elo_a = 1550.0 + (hash(m["player_a"]) % 200)
        elo_b = 1500.0 + (hash(m["player_b"]) % 200)
        p_win_a = elo_win_prob(elo_a, elo_b)
        ev_a = (p_win_a * m["odds_a"] - 1.0) * 100
        ev_b = ((1 - p_win_a) * m["odds_b"] - 1.0) * 100
        results.append({
            **m,
            "elo_a": round(elo_a, 1),
            "elo_b": round(elo_b, 1),
            "p_win_a": round(p_win_a, 6),
            "p_win_b": round(1 - p_win_a, 6),
            "ev_a": round(ev_a, 4),
            "ev_b": round(ev_b, 4),
        })
    return results


def run_monte_carlo_top20(predictions: list[dict]) -> list[dict]:
    """Step 3: Monte Carlo dla top 20 meczów (wg. EV)."""
    # Sort by max EV descending
    sorted_preds = sorted(predictions, key=lambda x: max(x["ev_a"], x["ev_b"]), reverse=True)
    top20 = sorted_preds[:20]

    for m in top20:
        p = m["p_win_a"]
        q = 1 - p
        # Simple MC: sets distribution BO3
        p_a_20 = round(p ** 2, 4)
        p_a_21 = round(2 * p ** 2 * q, 4)
        p_b_02 = round(q ** 2, 4)
        p_b_12 = round(2 * q ** 2 * p, 4)
        m["mc"] = {
            "p_20": p_a_20,
            "p_21": p_a_21,
            "p_02": p_b_02,
            "p_12": p_b_12,
            "ci95": [round(p - 1.96 * math.sqrt(p * q / 10000), 4),
                     round(p + 1.96 * math.sqrt(p * q / 10000), 4)],
        }
    return top20


def generate_coupons(top20: list[dict], coupon_date: date) -> list[dict]:
    """Step 4: Wygeneruj kupony z top 20 predykcji."""
    # Pick top 3 with EV > 5%
    value_picks = [m for m in top20 if max(m["ev_a"], m["ev_b"]) > 5.0][:5]

    coupons = []
    if value_picks:
        selections = []
        for m in value_picks[:3]:
            bet_a = m["ev_a"] > m["ev_b"]
            selections.append({
                "match_id": m["match_id"],
                "player_backed": m["player_a"] if bet_a else m["player_b"],
                "opponent": m["player_b"] if bet_a else m["player_a"],
                "surface": m["surface"],
                "bk_odds": m["odds_a"] if bet_a else m["odds_b"],
                "p_model": m["p_win_a"] if bet_a else m["p_win_b"],
                "ev_pct": m["ev_a"] if bet_a else m["ev_b"],
            })

        coupons.append({
            "coupon_id": f"cp-{coupon_date}-top",
            "coupon_date": str(coupon_date),
            "coupon_type": "MIXED",
            "priority": "TOP PICK",
            "headline": f"Top {len(selections)} ATP picks — {coupon_date}",
            "total_ev": round(sum(s["ev_pct"] for s in selections), 2),
            "selections": selections,
        })

    return coupons


def save_coupons(coupons: list[dict], coupon_date: date, output_dir: Path) -> Path:
    """Step 5: Zapisz kupony do JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"coupons_{coupon_date}.json"
    with open(output_path, "w") as f:
        json.dump(coupons, f, indent=2, default=str)
    return output_path


def send_telegram_alert(coupons: list[dict], token: Optional[str] = None) -> bool:
    """Step 6: Wyślij Telegram alert (jeśli token dostępny)."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[telegram] No TELEGRAM_BOT_TOKEN set, skipping alert.")
        return False

    try:
        import urllib.request
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            print("[telegram] No TELEGRAM_CHAT_ID set, skipping alert.")
            return False

        n = len(coupons)
        msg = f"🎾 betatp.io Daily Coupons ready! {n} coupon(s) generated."
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        print(f"[telegram] Alert sent: {msg}")
        return True
    except Exception as e:
        print(f"[telegram] Failed to send alert: {e}")
        return False


def run_daily_pipeline(target_date: date = None, dry_run: bool = True) -> dict:
    """
    Uruchamia pełny pipeline dla danego dnia.
    dry_run=True: tylko print, brak DB write.
    Zwraca wyniki.
    """
    started_at = datetime.now()
    target_date = target_date or date.today()

    print(f"[pipeline] Starting daily pipeline for {target_date} (dry_run={dry_run})")

    # Step 1: Load matches
    matches_file = Path(__file__).parent.parent / "data" / f"matches_{target_date}.json"
    if matches_file.exists():
        print(f"[pipeline] Loading matches from {matches_file}")
        with open(matches_file) as f:
            matches = json.load(f)
    else:
        print(f"[pipeline] No matches file found, using dummy data ({len(DUMMY_MATCHES)} matches)")
        matches = DUMMY_MATCHES

    # Step 2: Elo predictions
    predictions = compute_predictions(matches)
    print(f"[pipeline] Computed predictions for {len(predictions)} matches")

    # Step 3: Monte Carlo top 20
    top20 = run_monte_carlo_top20(predictions)
    print(f"[pipeline] Monte Carlo run for {len(top20)} top matches")

    # Step 4: Generate coupons
    coupons = generate_coupons(top20, target_date)
    print(f"[pipeline] Generated {len(coupons)} coupon(s)")

    # Step 5: Save
    output_path = None
    if not dry_run:
        output_dir = Path(__file__).parent.parent / "output" / "coupons"
        output_path = save_coupons(coupons, target_date, output_dir)
        print(f"[pipeline] Saved coupons to {output_path}")
    else:
        print("[pipeline] dry_run=True, skipping file write")

    # Step 6: Telegram
    alert_sent = False
    if not dry_run:
        alert_sent = send_telegram_alert(coupons)

    ended_at = datetime.now()
    duration_s = (ended_at - started_at).total_seconds()

    results = {
        "date": target_date,
        "dry_run": dry_run,
        "n_matches": len(matches),
        "n_predictions": len(predictions),
        "n_top20": len(top20),
        "n_coupons": len(coupons),
        "coupons": coupons,
        "output_path": str(output_path) if output_path else None,
        "alert_sent": alert_sent,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_s": round(duration_s, 3),
    }

    print(f"[pipeline] Done in {duration_s:.3f}s")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="betatp.io daily pipeline")
    parser.add_argument("--date", type=str, default=None, help="Date YYYY-MM-DD")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually save files")
    args = parser.parse_args()

    run_date = date.fromisoformat(args.date) if args.date else None
    results = run_daily_pipeline(target_date=run_date, dry_run=not args.no_dry_run)
    print(json.dumps(results, indent=2, default=str))
