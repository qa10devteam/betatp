"""
tasks/daily_coupon_scheduler.py — Daily coupon generation for atpbet.io

Usage:
    python3 tasks/daily_coupon_scheduler.py            # run once
    python3 tasks/daily_coupon_scheduler.py --schedule # run loop at 07:30 UTC daily
    python3 tasks/daily_coupon_scheduler.py --telegram  # push to Telegram after generation
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COUPONS_DIR = Path("/home/ubuntu/betatp/coupons")
COUPONS_DIR.mkdir(exist_ok=True)


# ── Coupon generation ──────────────────────────────────────────────────────────

def generate_daily_coupons() -> dict:
    """
    Run the champion stack on today's scheduled ATP matches.

    Loads match data from scripts/generate_coupons.py logic,
    runs PredictionService, then uses ValueDetector + CouponBuilder.

    Falls back to demo data if DB is unavailable.
    """
    logger.info("Generating daily coupons...")

    try:
        import psycopg2
        from config import PG_DSN, COUPONS_DIR as CFG_DIR
        from engine.feature_builder import build_features, _default_player_stats, get_conn, get_player_stats
        from engine.prediction_service import PredictionService, prediction_to_dict
        from engine.value_detector import ValueDetector, CouponBuilder, value_bet_to_dict, coupon_to_dict

        # Attempt to load today's matches from DB
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT p_w.full_name, p_l.full_name, te.surface,
                   t.tourney_name, m.round
            FROM matches m
            JOIN tournament_editions te ON m.edition_id = te.edition_id
            JOIN tournaments t ON te.tournament_id = t.tournament_id
            JOIN players p_w ON m.winner_id = p_w.player_id
            JOIN players p_l ON m.loser_id = p_l.player_id
            WHERE m.match_date = CURRENT_DATE
            LIMIT 30
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            logger.warning("No matches found for today — using demo data")
            return _demo_payload()

        # Build predictions
        svc = PredictionService()
        detector = ValueDetector()
        builder = CouponBuilder()
        predictions = []

        for winner, loser, surface, tourney, round_num in rows:
            try:
                from engine.feature_builder import build_features_for_match
                features, stats_a, stats_b = build_features_for_match(
                    player_a=winner,
                    player_b=loser,
                    surface=surface or "Hard",
                    round_num=round_num or "R1",
                    odds_a=1.60,
                    odds_b=2.30,
                )
                pred = svc.predict(
                    player_a=winner,
                    player_b=loser,
                    surface=surface or "Hard",
                    tournament=tourney or "ATP",
                    round_num=round_num or "R1",
                    features=features,
                )
                predictions.append(pred)
            except Exception as e:
                logger.warning(f"  Skip {winner} vs {loser}: {e}")

        value_bets = detector.scan(predictions)
        coupons = builder.build(value_bets)

        payload = {
            "date": date.today().isoformat(),
            "is_demo": False,
            "n_matches_scanned": len(rows),
            "n_value_bets": len(value_bets),
            "value_bets": [value_bet_to_dict(v) for v in value_bets],
            "coupons": [coupon_to_dict(c) for c in coupons],
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"DB/engine error — falling back to demo: {e}")
        payload = _demo_payload()

    # Save to file
    out_path = COUPONS_DIR / "daily.json"
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"Saved {payload['n_value_bets']} value bets + {len(payload['coupons'])} coupons → {out_path}")

    return payload


def _demo_payload() -> dict:
    """Return the hardcoded demo payload for days with no live DB data."""
    return {
        "date": date.today().isoformat(),
        "tournament": "Wimbledon",
        "surface": "Grass",
        "round": "R2",
        "is_demo": True,
        "demo_note": "Live predictions available on match days (08:00 UTC)",
        "n_value_bets": 4,
        "value_bets": [
            {
                "match": "DJOKOVIC N. vs WU Y.",
                "player_a": "Djokovic N.", "player_b": "Wu Y.",
                "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
                "market_id": "ou36", "market_label": "Over/Under 36.5 Games",
                "model_prob": 0.684, "implied_prob": 0.532, "edge": 0.152,
                "ev": 0.286, "sts_odds": 1.88, "kelly_pct": 0.030, "auc": 0.8925,
                "confidence": "MEDIUM", "is_value": True,
            },
            {
                "match": "MEDVEDEV D. vs CILIC M.",
                "player_a": "Medvedev D.", "player_b": "Cilic M.",
                "surface": "Grass", "tournament": "Wimbledon", "round": "R2",
                "market_id": "straight", "market_label": "Straight Sets",
                "model_prob": 0.712, "implied_prob": 0.541, "edge": 0.171,
                "ev": 0.316, "sts_odds": 1.85, "kelly_pct": 0.035, "auc": 0.9354,
                "confidence": "HIGH", "is_value": True,
            },
        ],
        "coupons": [
            {
                "name": "MAX VALUE AKO 2-fold",
                "total_odds": 3.48,
                "stake": 5.0,
                "potential_win": 17.40,
                "picks": [],
            },
        ],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ── Telegram push ──────────────────────────────────────────────────────────────

def push_to_telegram(payload: dict) -> bool:
    """
    Format daily coupon payload and push to Telegram channel.

    Uses config.TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID.
    Returns True on success.
    """
    import os
    import requests

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "")

    if not token or not channel:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set — skip push")
        return False

    # Format message
    today = payload.get("date", date.today().isoformat())
    n_vb = payload.get("n_value_bets", 0)
    coupons = payload.get("coupons", [])
    is_demo = payload.get("is_demo", False)

    lines = [
        f"🎾 *atpbet.io — Daily Picks* | {today}",
        f"📊 {n_vb} value bets found (champion stack)" + (" _(demo)_" if is_demo else ""),
        "",
    ]

    for i, vb in enumerate(payload.get("value_bets", [])[:5], 1):
        edge_pct = int(vb.get("edge", 0) * 100)
        ev_pct = int(vb.get("ev", 0) * 100)
        conf = vb.get("confidence", "MED")[:3]
        lines.append(
            f"*{i}.* {vb.get('match', 'N/A')}\n"
            f"   Market: {vb.get('market_label', 'N/A')}\n"
            f"   Odds: `{vb.get('sts_odds', '-')}` | Edge: `+{edge_pct}%` | EV: `+{ev_pct}%` | {conf}"
        )

    if coupons:
        lines.append("")
        lines.append("*📋 Coupons (15 PLN total):*")
        for c in coupons[:3]:
            lines.append(
                f"• {c.get('name', 'Coupon')} — odds `{c.get('total_odds', '-')}`"
                f" → win `{c.get('potential_win', '-')} PLN`"
            )

    lines.append("")
    lines.append("_atpbet.io · ATP Intelligence. Real Edge._")

    text = "\n".join(lines)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": channel, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.ok:
            logger.info(f"Telegram push OK (message_id={r.json().get('result', {}).get('message_id')})")
            return True
        else:
            logger.warning(f"Telegram push failed: {r.status_code} {r.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram push error: {e}")
        return False


# ── Scheduler loop ─────────────────────────────────────────────────────────────

def run_scheduler(target_hour: int = 7, target_minute: int = 30, push: bool = True) -> None:
    """
    Simple infinite loop that generates coupons daily at target_hour:target_minute UTC.
    """
    logger.info(f"Scheduler started — runs daily at {target_hour:02d}:{target_minute:02d} UTC")
    last_run_date = None

    while True:
        now = datetime.utcnow()
        if (
            now.hour == target_hour
            and now.minute >= target_minute
            and now.date() != last_run_date
        ):
            logger.info(f"Triggering daily run at {now.isoformat()}")
            try:
                payload = generate_daily_coupons()
                if push:
                    push_to_telegram(payload)
                last_run_date = now.date()
            except Exception as e:
                logger.error(f"Daily run failed: {e}")

        time.sleep(30)


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="atpbet.io daily coupon scheduler")
    parser.add_argument("--schedule", action="store_true", help="Run loop (daily at 07:30 UTC)")
    parser.add_argument("--telegram", action="store_true", help="Push to Telegram after generation")
    parser.add_argument("--hour", type=int, default=7)
    parser.add_argument("--minute", type=int, default=30)
    args = parser.parse_args()

    if args.schedule:
        run_scheduler(target_hour=args.hour, target_minute=args.minute, push=args.telegram)
    else:
        payload = generate_daily_coupons()
        if args.telegram:
            push_to_telegram(payload)
        print(f"\n✅ Generated: {payload['n_value_bets']} value bets, {len(payload.get('coupons', []))} coupons")
