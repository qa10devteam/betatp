"""
scripts/run_daily_pipeline.py — Dzienny pipeline betatp.io (h5)
================================================================
CLI:
  python3 scripts/run_daily_pipeline.py [--edge 0.15] [--max-picks 3] [--output coupons/daily.json]

Steps:
  1. Load Elo ratings from models/elo_ratings_2025.joblib
  2. Load model v14 from models/ (find lgbm_v14*.joblib)
  3. Generate mock matches for today (5 ATP matches)
  4. For each match: compute p_win via Elo (simplified)
  5. Filter edge > --edge threshold
  6. Build coupon via DailyCouponBuilder
  7. Save JSON to --output
  8. Print summary table
"""
import argparse
import glob
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# ── Ensure project root is in path ────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("daily_pipeline")


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(
        description="betatp.io — Daily ATP Coupon Pipeline"
    )
    p.add_argument(
        "--edge", type=float, default=0.15,
        help="Minimum edge threshold (default: 0.15)",
    )
    p.add_argument(
        "--max-picks", type=int, default=3,
        help="Maximum number of picks in coupon (default: 3)",
    )
    p.add_argument(
        "--output", type=str, default="coupons/daily.json",
        help="Output path for coupon JSON (default: coupons/daily.json)",
    )
    # legacy aliases
    p.add_argument("--min-edge", type=float, default=None, dest="min_edge_legacy",
                   help=argparse.SUPPRESS)
    p.add_argument("--date", type=str, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--telegram", action="store_true")
    return p.parse_args()


# ── Model loading (graceful ImportError) ──────────────────────────────────────
def _find_file(name_glob: str) -> Path | None:
    """Find file in models/ dir or BASE_DIR."""
    models_dir = BASE_DIR / "models"
    for search_dir in [models_dir, BASE_DIR]:
        matches = sorted(search_dir.glob(name_glob))
        if matches:
            return matches[-1]  # latest
    return None


def load_elo_ratings() -> dict:
    """Load Elo ratings from models/elo_ratings_2025.joblib. Returns dict or {}."""
    path = _find_file("elo_ratings_2025.joblib")
    if path is None:
        log.warning("elo_ratings_2025.joblib not found — using empty ratings")
        return {}
    try:
        import joblib
        ratings = joblib.load(path)
        log.info(f"Elo ratings loaded from {path} ({len(ratings)} entries)")
        return ratings if isinstance(ratings, dict) else {}
    except ImportError:
        log.warning("joblib not available — skipping Elo load")
        return {}
    except Exception as e:
        log.warning(f"Failed to load Elo ratings: {e}")
        return {}


def load_model_v14():
    """Load LightGBM v14 model. Returns model object or None."""
    path = _find_file("lgbm_v14*.joblib")
    if path is None:
        log.warning("lgbm_v14*.joblib not found in models/")
        return None
    try:
        import joblib
        model = joblib.load(path)
        log.info(f"Model v14 loaded from {path}")
        return model
    except ImportError:
        log.warning("joblib not available — skipping model load")
        return None
    except Exception as e:
        log.warning(f"Failed to load model v14: {e}")
        return None


# ── Mock matches ──────────────────────────────────────────────────────────────
MOCK_MATCHES = [
    {
        "match_id": "mock_001",
        "player_a": "Carlos Alcaraz",
        "player_b": "Holger Rune",
        "surface": "Clay",
        "tourney_name": "Roland Garros",
        "tourney_level": "G",
        "best_of": 3,
        "odds_a": 1.62,
        "odds_b": 2.45,
        "elo_a": 2180,
        "elo_b": 2050,
    },
    {
        "match_id": "mock_002",
        "player_a": "Jannik Sinner",
        "player_b": "Alexander Zverev",
        "surface": "Hard",
        "tourney_name": "Australian Open",
        "tourney_level": "G",
        "best_of": 5,
        "odds_a": 1.75,
        "odds_b": 2.15,
        "elo_a": 2160,
        "elo_b": 2090,
    },
    {
        "match_id": "mock_003",
        "player_a": "Novak Djokovic",
        "player_b": "Casper Ruud",
        "surface": "Hard",
        "tourney_name": "US Open",
        "tourney_level": "G",
        "best_of": 5,
        "odds_a": 1.55,
        "odds_b": 2.65,
        "elo_a": 2200,
        "elo_b": 2020,
    },
    {
        "match_id": "mock_004",
        "player_a": "Daniil Medvedev",
        "player_b": "Stefanos Tsitsipas",
        "surface": "Hard",
        "tourney_name": "ATP 1000 Paris",
        "tourney_level": "M",
        "best_of": 3,
        "odds_a": 1.90,
        "odds_b": 1.95,
        "elo_a": 2100,
        "elo_b": 2080,
    },
    {
        "match_id": "mock_005",
        "player_a": "Taylor Fritz",
        "player_b": "Ben Shelton",
        "surface": "Hard",
        "tourney_name": "ATP 500 Dubai",
        "tourney_level": "A",
        "best_of": 3,
        "odds_a": 1.85,
        "odds_b": 2.00,
        "elo_a": 2000,
        "elo_b": 1980,
    },
]


def generate_mock_matches(target_date: date) -> list[dict]:
    """Generate 5 ATP mock matches for today."""
    today_str = str(target_date)
    matches = []
    for m in MOCK_MATCHES:
        m_copy = dict(m)
        m_copy["date"] = today_str
        matches.append(m_copy)
    log.info(f"Generated {len(matches)} mock matches for {today_str}")
    return matches


# ── Elo-based p_win ───────────────────────────────────────────────────────────
ELO_K = 400.0  # standard Elo divisor


def elo_p_win(elo_a: float, elo_b: float) -> float:
    """Simplified Elo expected win probability for player A."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / ELO_K))


def get_elo_for_player(player: str, elo_ratings: dict, default: float = 1500.0) -> float:
    """Look up Elo rating for a player by name (partial match)."""
    if not elo_ratings:
        return default

    # Direct lookup
    if player in elo_ratings:
        r = elo_ratings[player]
        return float(r) if isinstance(r, (int, float)) else float(r.get("overall", default))

    # Case-insensitive partial match (last name)
    player_lower = player.lower()
    for key, val in elo_ratings.items():
        if isinstance(key, str) and player_lower in key.lower():
            return float(val) if isinstance(val, (int, float)) else float(val.get("overall", default))

    return default


# ── Compute picks ─────────────────────────────────────────────────────────────
def compute_picks(
    matches: list[dict],
    elo_ratings: dict,
    edge_threshold: float,
    max_picks: int,
) -> list[dict]:
    """Compute p_win via Elo and filter by edge threshold."""
    picks = []

    for m in matches:
        odds_a = m.get("odds_a")
        odds_b = m.get("odds_b")
        if not odds_a or not odds_b or odds_a <= 1.0 or odds_b <= 1.0:
            continue

        # Elo ratings
        elo_a = m.get("elo_a") or get_elo_for_player(m["player_a"], elo_ratings)
        elo_b = m.get("elo_b") or get_elo_for_player(m["player_b"], elo_ratings)

        # p_win via Elo
        p_model_a = elo_p_win(elo_a, elo_b)
        p_model_b = 1.0 - p_model_a

        # De-vig (proportional)
        imp_a = 1.0 / odds_a
        imp_b = 1.0 / odds_b
        total_imp = imp_a + imp_b
        p_pin_a = imp_a / total_imp
        p_pin_b = imp_b / total_imp

        # Edge
        edge_a = p_model_a - p_pin_a
        edge_b = p_model_b - p_pin_b
        ev_a = (p_model_a * odds_a - 1.0) * 100.0
        ev_b = (p_model_b * odds_b - 1.0) * 100.0

        # Best side
        if edge_a >= edge_b and edge_a >= edge_threshold:
            picks.append({
                "match_id": m["match_id"],
                "player_backed": m["player_a"],
                "opponent": m["player_b"],
                "surface": m.get("surface", "Hard"),
                "tourney_name": m.get("tourney_name", "ATP"),
                "tourney_level": m.get("tourney_level", "250"),
                "date": m.get("date"),
                "odds": round(odds_a, 3),
                "p_model": round(p_model_a, 4),
                "p_pin": round(p_pin_a, 4),
                "edge": round(edge_a, 4),
                "ev_pct": round(ev_a, 2),
                "elo_a": round(elo_a, 1),
                "elo_b": round(elo_b, 1),
                # fields for DailyCouponBuilder (uses ev, p_model, odds)
                "ev": round(edge_a, 4),
                "player": m["player_a"],
                "kelly": max(0.0, round(edge_a / (odds_a - 1.0) * 0.5, 4)),
            })
        elif edge_b > edge_a and edge_b >= edge_threshold:
            picks.append({
                "match_id": m["match_id"],
                "player_backed": m["player_b"],
                "opponent": m["player_a"],
                "surface": m.get("surface", "Hard"),
                "tourney_name": m.get("tourney_name", "ATP"),
                "tourney_level": m.get("tourney_level", "250"),
                "date": m.get("date"),
                "odds": round(odds_b, 3),
                "p_model": round(p_model_b, 4),
                "p_pin": round(p_pin_b, 4),
                "edge": round(edge_b, 4),
                "ev_pct": round(ev_b, 2),
                "elo_a": round(elo_b, 1),
                "elo_b": round(elo_a, 1),
                "ev": round(edge_b, 4),
                "player": m["player_b"],
                "kelly": max(0.0, round(edge_b / (odds_b - 1.0) * 0.5, 4)),
            })

    picks.sort(key=lambda x: x["edge"], reverse=True)
    return picks[:max_picks]


# ── Coupon building ───────────────────────────────────────────────────────────
def build_coupon(picks: list[dict], target_date: date) -> dict:
    """Build coupon using DailyCouponBuilder if available, else fallback."""
    try:
        from engine.daily_coupon import DailyCouponBuilder
        builder = DailyCouponBuilder()
        coupon = builder.build(picks, min_ev=0.0)
    except ImportError as e:
        log.warning(f"DailyCouponBuilder not available: {e} — using raw picks")
        coupon = {
            "date": str(target_date),
            "top_singles": picks,
            "system_2_3": None,
            "system_3_4": None,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        log.warning(f"DailyCouponBuilder error: {e} — using raw picks")
        coupon = {
            "date": str(target_date),
            "top_singles": picks,
            "system_2_3": None,
            "system_3_4": None,
            "generated_at": datetime.now().isoformat(),
        }

    # Enrich with pipeline metadata
    coupon["pipeline_picks"] = picks
    coupon["n_picks"] = len(picks)
    coupon["avg_edge"] = (
        round(sum(p["edge"] for p in picks) / len(picks), 4) if picks else 0.0
    )
    return coupon


# ── Summary table ─────────────────────────────────────────────────────────────
def print_summary(picks: list[dict], coupon: dict):
    """Print a formatted summary table."""
    log.info("=" * 70)
    log.info(f"DAILY PIPELINE SUMMARY | {len(picks)} picks")
    log.info("=" * 70)
    if not picks:
        log.info("  No picks above edge threshold.")
    else:
        log.info(f"  {'Player':22s} {'Opponent':22s} {'Odds':>6} {'Edge':>8} {'EV%':>8}")
        log.info("  " + "-" * 68)
        for p in picks:
            log.info(
                f"  {p['player_backed']:22s} {p['opponent']:22s} "
                f"{p['odds']:6.2f} {p['edge']:8.1%} {p['ev_pct']:+7.2f}%"
            )
    log.info(f"  avg_edge={coupon.get('avg_edge', 0):.1%}  "
             f"top_singles={len(coupon.get('top_singles', []))}")
    log.info("=" * 70)


# ── Save output ───────────────────────────────────────────────────────────────
def save_output(coupon: dict, output_path: str):
    """Save coupon JSON to output path."""
    out = Path(output_path)
    if not out.is_absolute():
        out = BASE_DIR / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(coupon, f, indent=2, default=str, ensure_ascii=False)
    log.info(f"Coupon saved to {out}")
    return out


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # Resolve edge (support legacy --min-edge alias)
    edge_threshold = args.min_edge_legacy if args.min_edge_legacy is not None else args.edge
    target_date = date.fromisoformat(args.date) if args.date else date.today()

    log.info("=" * 70)
    log.info(f"DAILY PIPELINE — {target_date} | edge>{edge_threshold:.0%} | max-picks={args.max_picks}")
    log.info("=" * 70)

    # STEP 1: Load Elo ratings
    log.info("=== STEP 1: Loading Elo ratings ===")
    elo_ratings = load_elo_ratings()

    # STEP 2: Load model v14
    log.info("=== STEP 2: Loading model v14 ===")
    model = load_model_v14()
    if model is None:
        log.info("  Model v14 not loaded — using Elo-only predictions")

    # STEP 3: Generate mock matches
    log.info("=== STEP 3: Generating mock matches ===")
    matches = generate_mock_matches(target_date)

    # STEP 4+5: Compute Elo p_win and filter by edge
    log.info(f"=== STEP 4+5: Computing Elo predictions | edge>{edge_threshold:.0%} ===")
    picks = compute_picks(matches, elo_ratings, edge_threshold, args.max_picks)
    log.info(f"  Picks above edge threshold: {len(picks)}")

    # STEP 6: Build coupon
    log.info("=== STEP 6: Building coupon ===")
    coupon = build_coupon(picks, target_date)

    # STEP 7: Save JSON
    if not args.dry_run:
        log.info("=== STEP 7: Saving output ===")
        save_output(coupon, args.output)
    else:
        log.info("=== STEP 7: [DRY RUN] — not saving")
        print(json.dumps(coupon, indent=2, default=str, ensure_ascii=False))

    # STEP 8: Print summary
    log.info("=== STEP 8: Summary ===")
    print_summary(picks, coupon)

    return coupon


if __name__ == "__main__":
    main()
