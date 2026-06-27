"""
tasks/daily_pipeline.py - Scheduled Celery tasks for betatp.io daily pipeline.

Tasks
-----
task_update_elos()       -- recompute all Elo ratings from latest CSV data
task_generate_coupons()  -- build and persist the daily bet coupon
task_scan_derivatives()  -- scan active matches for derivative opportunities
task_send_alerts()       -- dispatch pending value alerts to subscribers
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from tasks.celery_app import app, CELERY_AVAILABLE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Update Elo ratings
# ---------------------------------------------------------------------------

@app.task
def task_update_elos():
    """Recompute Elo ratings from the latest TML-Database CSVs."""
    logger.info("[task_update_elos] Starting Elo computation...")
    try:
        from scripts.compute_elos import run_compute_elos
        result = run_compute_elos(source=None, output=str(_HERE / "models" / "elo_ratings.joblib"))
        logger.info(
            "[task_update_elos] Done. players=%d matches=%d output=%s",
            result["n_players"],
            result["n_matches"],
            result["output_path"],
        )
        return {
            "status": "ok",
            "n_players": result["n_players"],
            "n_matches": result["n_matches"],
        }
    except Exception as exc:
        logger.exception("[task_update_elos] FAILED: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# 2. Generate daily coupons
# ---------------------------------------------------------------------------

@app.task
def task_generate_coupons():
    """Build and persist the daily bet coupon for all active matches."""
    logger.info("[task_generate_coupons] Starting coupon generation...")
    try:
        from engine.coupon import DailyCouponBuilder
        import joblib

        # Load active matches - prefer elo engine as source of active players
        elo_path = _HERE / "models" / "elo_ratings.joblib"
        matches = []
        if elo_path.exists():
            elo_engine = joblib.load(str(elo_path))
            # DailyCouponBuilder accepts a list/iterable of match dicts or BetSelection-ready objects
            logger.info("[task_generate_coupons] Elo engine loaded.")

        builder = DailyCouponBuilder()
        coupon = builder.build(matches)
        logger.info("[task_generate_coupons] Coupon built: %r", coupon)
        return {"status": "ok", "coupon_summary": repr(coupon)}
    except ImportError as exc:
        logger.warning("[task_generate_coupons] Import error (module not ready): %s", exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.exception("[task_generate_coupons] FAILED: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# 3. Scan derivatives
# ---------------------------------------------------------------------------

@app.task
def task_scan_derivatives():
    """Scan currently active matches for derivative (in-play) opportunities."""
    logger.info("[task_scan_derivatives] Starting derivative scan...")
    try:
        from engine.live_engine import DerivativeScanner
        import joblib

        elo_path = _HERE / "models" / "elo_ratings.joblib"
        elo_engine = None
        if elo_path.exists():
            elo_engine = joblib.load(str(elo_path))

        scanner = DerivativeScanner(elo_engine=elo_engine)
        active_matches = scanner.get_active_matches()
        results = scanner.scan(active_matches)
        logger.info("[task_scan_derivatives] Scanned %d active matches.", len(active_matches))
        return {"status": "ok", "n_matches_scanned": len(active_matches), "n_opportunities": len(results)}
    except ImportError as exc:
        logger.warning("[task_scan_derivatives] Import error: %s", exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.exception("[task_scan_derivatives] FAILED: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# 4. Send alerts
# ---------------------------------------------------------------------------

@app.task
def task_send_alerts():
    """Dispatch all active value alerts to subscribers via AlertNotifier."""
    logger.info("[task_send_alerts] Dispatching alerts...")
    try:
        from value.alerts import AlertEngine

        engine = AlertEngine()
        active = engine.get_active_alerts()
        dispatched = 0
        for alert in active:
            try:
                engine.dispatch(alert)
                dispatched += 1
            except Exception as inner_exc:
                logger.warning("[task_send_alerts] Failed to send alert %s: %s", getattr(alert, "id", "?"), inner_exc)
        logger.info("[task_send_alerts] Dispatched %d / %d alerts.", dispatched, len(active))
        return {"status": "ok", "dispatched": dispatched, "total": len(active)}
    except ImportError as exc:
        logger.warning("[task_send_alerts] Import error: %s", exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.exception("[task_send_alerts] FAILED: %s", exc)
        return {"status": "error", "error": str(exc)}


__all__ = [
    "task_update_elos",
    "task_generate_coupons",
    "task_scan_derivatives",
    "task_send_alerts",
]
