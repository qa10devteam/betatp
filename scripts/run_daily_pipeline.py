"""
scripts/run_daily_pipeline.py — Dzienny pipeline betatp.io
============================================================
1. Wczytaj mecze na dziś (ATP schedule z pliku/DB lub ostatnie z TML)
2. Załaduj ModelContext (LightGBM + Elo state)
3. Oblicz predykcje dla każdego meczu + edge nad Pinnacle
4. Filtruj value bety (edge > MIN_EDGE)
5. Wygeneruj kupony JSON
6. Zapisz do data/daily_picks_YYYY-MM-DD.json
7. Wyślij Telegram alert (jeśli TELEGRAM_TOKEN ustawiony)

Użycie:
  PYTHONPATH=. python scripts/run_daily_pipeline.py
  PYTHONPATH=. python scripts/run_daily_pipeline.py --date 2026-06-26
  PYTHONPATH=. python scripts/run_daily_pipeline.py --min-edge 0.08 --telegram
"""
import json, sys, os, argparse
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

MIN_EDGE_DEFAULT = 0.05
OUT_DIR = Path("/home/ubuntu/betatp/data")

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)


# ─── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, help="Data YYYY-MM-DD (default: today)")
    p.add_argument("--min-edge", type=float, default=MIN_EDGE_DEFAULT)
    p.add_argument("--telegram", action="store_true", help="Wyślij Telegram alert")
    p.add_argument("--dry-run", action="store_true", help="Nie zapisuj, tylko wypisz")
    p.add_argument("--max-picks", type=int, default=10)
    return p.parse_args()


# ─── Źródło meczów ────────────────────────────────────────────────────────────
def load_todays_matches(target_date: date) -> list[dict]:
    """
    Ładuje mecze na dziś.
    Priorytety:
    1. data/schedule_YYYY-MM-DD.json (ręcznie wczytane)
    2. data/atp_schedule.json (ciągły feed)
    3. Ostatnie mecze z TML-Database (ostatni tydzień) — dla backtestingu/demo
    """
    # 1. Dzienny schedule
    schedule_file = OUT_DIR / f"schedule_{target_date}.json"
    if schedule_file.exists():
        log(f"  Ładuję schedule z {schedule_file.name}")
        with open(schedule_file) as f:
            return json.load(f)

    # 2. Globalny feed
    atp_feed = OUT_DIR / "atp_schedule.json"
    if atp_feed.exists():
        log("  Ładuję ATP feed z atp_schedule.json")
        with open(atp_feed) as f:
            all_matches = json.load(f)
        return [m for m in all_matches
                if m.get("date", "")[:10] == str(target_date)]

    # 3. Fallback: ostatnie mecze z TML (demo/backtesting)
    log("  Brak schedula — używam ostatnich meczów z TML jako demo")
    return load_recent_tml_matches(target_date)


def load_recent_tml_matches(target_date: date, n: int = 30) -> list[dict]:
    """
    Zwraca N ostatnich meczów z TML-Database przed target_date.
    Używane jako demo gdy nie ma live schedula.
    """
    import pandas as pd
    TML_PATH = Path("/home/ubuntu/TML-Database")
    dfs = []
    for f in sorted(TML_PATH.glob("[0-9]*.csv")):
        yr = int(f.stem)
        if yr < 2024: continue
        df = pd.read_csv(f, low_memory=False); df["year"] = yr; dfs.append(df)
    if not dfs:
        return []

    raw = pd.concat(dfs, ignore_index=True)
    raw["tourney_date"] = pd.to_datetime(
        raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    raw = raw.dropna(subset=["tourney_date", "winner_id", "loser_id"])
    raw = raw.sort_values("tourney_date")

    # Weź mecze z tygodnia przed target_date
    cutoff = pd.Timestamp(target_date) - pd.Timedelta(days=7)
    subset = raw[raw["tourney_date"] >= cutoff].tail(n)

    matches = []
    for _, row in subset.iterrows():
        surf_map = {"Hard":"Hard","Clay":"Clay","Grass":"Grass",
                    "Carpet":"Hard","Indoor Hard":"Hard"}
        surf = surf_map.get(str(row.get("surface", "Hard")), "Hard")

        # Szukaj kursów z parquet
        matches.append({
            "match_id": f"tml_{row['winner_id']}_{row['loser_id']}",
            "player_a": str(row.get("winner_name", row["winner_id"])),
            "player_b": str(row.get("loser_name", row["loser_id"])),
            "player_a_id": str(row["winner_id"]),
            "player_b_id": str(row["loser_id"]),
            "surface": surf,
            "tourney_name": str(row.get("tourney_name", "ATP")),
            "tourney_level": str(row.get("tourney_level", "250")),
            "best_of": int(row.get("best_of", 3)),
            "date": str(row["tourney_date"].date()),
            # Odds — będzie uzupełnione z parquet lub brak
            "odds_a": None,
            "odds_b": None,
            # Prawdziwy wynik (tylko dla backtestingu)
            "_winner": str(row.get("winner_name", row["winner_id"])),
        })

    # Uzupełnij kursy z odds parquet
    _fill_odds_from_parquet(matches, raw)
    return matches


def _fill_odds_from_parquet(matches: list[dict], raw=None):
    """Uzupełnia kursy z matches_with_odds.parquet."""
    import pandas as pd
    odds_file = OUT_DIR / "matches_with_odds.parquet"
    if not odds_file.exists():
        return
    odds_df = pd.read_parquet(odds_file)
    odds_df = odds_df[odds_df["PSW"].notna() & odds_df["PSL"].notna()]
    # Index po (year, winner_last, loser_last)
    odds_idx = {}
    for _, row in odds_df.iterrows():
        key = (row.get("year"), str(row.get("wl","")).lower(), str(row.get("ll","")).lower())
        odds_idx[key] = (float(row["PSW"]), float(row["PSL"]))

    for m in matches:
        date_str = m.get("date", "")[:4]
        yr = int(date_str) if date_str.isdigit() else 2025
        wl = m["player_a"].strip().split()[-1].lower()
        ll = m["player_b"].strip().split()[-1].lower()
        found = odds_idx.get((yr, wl, ll)) or odds_idx.get((yr, ll, wl))
        if found:
            psw, psl = found
            if odds_idx.get((yr, wl, ll)):
                m["odds_a"] = psw; m["odds_b"] = psl
            else:
                m["odds_a"] = psl; m["odds_b"] = psw


# ─── Predykcje ────────────────────────────────────────────────────────────────
def run_predictions(matches: list[dict], ctx, min_edge: float, max_picks: int) -> list[dict]:
    """Oblicz predykcje + filtruj value bety."""
    picks = []
    for m in matches:
        odds_a = m.get("odds_a")
        odds_b = m.get("odds_b")
        if not odds_a or not odds_b or odds_a <= 1.0 or odds_b <= 1.0:
            continue  # Brak kursów — pomiń

        try:
            result = ctx.predict(
                player_a=m["player_a"],
                player_b=m["player_b"],
                surface=m.get("surface", "Hard"),
                odds_a=odds_a,
                odds_b=odds_b,
                tourney_level=m.get("tourney_level", "250"),
            )
        except Exception as e:
            log(f"  Błąd predykcji {m['player_a']} vs {m['player_b']}: {e}")
            continue

        edge_a = result["edge_a"]
        edge_b = result["p_b"] - (1.0 - result["pin_a"])

        best_edge = max(edge_a, edge_b)
        if best_edge < min_edge:
            continue

        if edge_a >= edge_b:
            pick = {
                "match_id": m.get("match_id"),
                "player_backed": m["player_a"],
                "opponent": m["player_b"],
                "surface": m.get("surface"),
                "tourney_name": m.get("tourney_name"),
                "tourney_level": m.get("tourney_level"),
                "date": m.get("date"),
                "odds": odds_a,
                "p_model": result["p_a"],
                "p_pin": result["pin_a"],
                "edge": round(edge_a, 4),
                "ev_pct": result["ev_a"],
                "kelly_half": result["kelly_a"],
                "signal": result["signal"],
                "elo_a": result["elo_a"], "elo_b": result["elo_b"],
                "rank_a": result["rank_a"], "rank_b": result["rank_b"],
                "fatigue_a": result["fatigue_a"],
                "h2h_summary": result["h2h_summary"],
                "model_version": result["model_version"],
                "_winner": m.get("_winner"),  # do backtestingu
            }
        else:
            pick = {
                "match_id": m.get("match_id"),
                "player_backed": m["player_b"],
                "opponent": m["player_a"],
                "surface": m.get("surface"),
                "tourney_name": m.get("tourney_name"),
                "tourney_level": m.get("tourney_level"),
                "date": m.get("date"),
                "odds": odds_b,
                "p_model": result["p_b"],
                "p_pin": 1.0 - result["pin_a"],
                "edge": round(edge_b, 4),
                "ev_pct": result["ev_b"],
                "kelly_half": result["kelly_b"],
                "signal": result["signal"],
                "elo_a": result["elo_b"], "elo_b": result["elo_a"],
                "rank_a": result["rank_b"], "rank_b": result["rank_a"],
                "fatigue_a": result["fatigue_b"],
                "h2h_summary": result["h2h_summary"],
                "model_version": result["model_version"],
                "_winner": m.get("_winner"),
            }

        picks.append(pick)

    picks.sort(key=lambda x: x["edge"], reverse=True)
    return picks[:max_picks]


# ─── Format output ─────────────────────────────────────────────────────────────
def format_picks(picks: list[dict], target_date: date, min_edge: float) -> dict:
    """Formatuje picks do JSON output."""
    top = [p for p in picks if p["edge"] >= 0.15]
    rec = [p for p in picks if 0.08 <= p["edge"] < 0.15]
    spec = [p for p in picks if min_edge <= p["edge"] < 0.08]

    return {
        "date": str(target_date),
        "generated_at": datetime.now().isoformat(),
        "min_edge": min_edge,
        "total_picks": len(picks),
        "summary": {
            "top_picks": len(top),
            "recommended": len(rec),
            "speculative": len(spec),
            "avg_edge": round(sum(p["edge"] for p in picks) / max(len(picks), 1), 4),
            "avg_ev": round(sum(p["ev_pct"] for p in picks) / max(len(picks), 1), 2),
        },
        "picks": picks,
        "top_picks": top,
        "recommended": rec,
        "speculative": spec,
    }


# ─── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(picks_data: dict, token: str, chat_id: str):
    """Wyślij alert Telegram z top pickami."""
    import urllib.request, urllib.parse
    picks = picks_data.get("top_picks", []) or picks_data.get("recommended", [])[:3]
    if not picks:
        msg = f"🎾 betatp.io — {picks_data['date']}\n\nBrak wartościowych zakładów dziś."
    else:
        lines = [f"🎾 *betatp.io — TOP PICKS {picks_data['date']}*\n"]
        for p in picks[:5]:
            lines.append(
                f"✅ *{p['player_backed']}* vs {p['opponent']}\n"
                f"   Odds: {p['odds']:.2f} | Edge: {p['edge']:.1%} | EV: {p['ev_pct']:+.1f}%\n"
                f"   Kelly: {p['kelly_half']:.1%} bankroll\n"
            )
        lines.append(f"\n_Model: {picks[0].get('model_version', 'vX')}_")
        msg = "\n".join(lines)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        log("  Telegram: wysłano ✓")
    except Exception as e:
        log(f"  Telegram błąd: {e}")


# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else date.today()

    log("=" * 60)
    log(f"DAILY PIPELINE — {target_date} | edge>{args.min_edge:.0%}")
    log("=" * 60)

    # 1. Mecze
    log("=== ETAP 1: Ładowanie meczów ===")
    matches = load_todays_matches(target_date)
    log(f"  Meczów znalezionych: {len(matches)}")
    if not matches:
        log("  BRAK MECZÓW — pipeline zakończony")
        return

    with_odds = [m for m in matches if m.get("odds_a") and m.get("odds_b")]
    log(f"  Z kursami: {len(with_odds)}/{len(matches)}")

    # 2. Model
    log("=== ETAP 2: Ładowanie modelu ===")
    from ml.model_loader import get_model_context
    ctx = get_model_context()
    log(f"  Model: v{ctx.version} | AUC={ctx.holdout_auc}")

    # 3. Predykcje
    log("=== ETAP 3: Predykcje ===")
    picks = run_predictions(with_odds, ctx, args.min_edge, args.max_picks)
    log(f"  Value picks (edge>{args.min_edge:.0%}): {len(picks)}")

    for p in picks:
        log(f"  ✓ {p['player_backed']:20s} vs {p['opponent']:20s} | "
            f"edge={p['edge']:.1%} EV={p['ev_pct']:+.1f}% odds={p['odds']:.2f}")

    # 4. Format
    log("=== ETAP 4: Formatowanie output ===")
    output = format_picks(picks, target_date, args.min_edge)

    # 5. Zapis
    if not args.dry_run:
        log("=== ETAP 5: Zapis ===")
        out_file = OUT_DIR / f"daily_picks_{target_date}.json"
        with open(out_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
        log(f"  Zapisano: {out_file}")

        # Aktualizuj latest
        latest_file = OUT_DIR / "daily_picks_latest.json"
        with open(latest_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
        log(f"  Zaktualizowano: {latest_file.name}")
    else:
        log("  [DRY RUN] — nie zapisuję")
        print(json.dumps(output, indent=2, default=str))

    # 6. Telegram
    if args.telegram:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if token and chat_id:
            log("=== ETAP 6: Telegram alert ===")
            send_telegram(output, token, chat_id)
        else:
            log("  Telegram: brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID")

    log("=" * 60)
    log(f"DONE | {len(picks)} picks | avg_edge={output['summary']['avg_edge']:.1%}")
    log("=" * 60)


if __name__ == "__main__":
    main()
