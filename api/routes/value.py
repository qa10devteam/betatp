"""
api/routes/value.py — Value betting endpoints for betatp.io
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["value"])

# ── Lazy-load value engine modules ─────────────────────────────────────────────

def _get_ev_calc():
    try:
        from value.ev_calculator import expected_value, kelly_fraction  # type: ignore
        return expected_value, kelly_fraction
    except ImportError:
        return None, None


def _get_devig():
    try:
        from value.devig import best_devig  # type: ignore
        return best_devig
    except ImportError:
        try:
            from value.devig import devig_proportional  # type: ignore
            return devig_proportional
        except ImportError:
            return None


def _get_alert_engine():
    try:
        from value.alerts import AlertEngine  # type: ignore
        return AlertEngine()
    except Exception:
        return None


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class ValueCheckRequest(BaseModel):
    player_a: str = Field(..., description="Name of player A")
    player_b: str = Field(..., description="Name of player B")
    p_model: float = Field(..., ge=0.0, le=1.0, description="Model probability for player A (0-1)")
    decimal_odds_a: float = Field(..., gt=1.0, description="Decimal odds for player A")
    decimal_odds_b: float = Field(..., gt=1.0, description="Decimal odds for player B")


class ValueCheckResponse(BaseModel):
    ev_pct: float
    kelly_stake: float
    devigged_p: float
    recommendation: str
    confidence: str


# ── Helper: compute recommendation ────────────────────────────────────────────

def _compute_value(
    p_model: float,
    decimal_odds_a: float,
    decimal_odds_b: float,
) -> dict:
    """Core value computation. Returns raw floats."""
    # De-vig to get true probability
    best_devig = _get_devig()
    if best_devig:
        try:
            result = best_devig(decimal_odds_a, decimal_odds_b)
            # best_devig may return (p_a, p_b) tuple or dict
            if isinstance(result, (tuple, list)):
                devigged_p = float(result[0])
            elif isinstance(result, dict):
                devigged_p = float(list(result.values())[0])
            else:
                devigged_p = float(result)
        except Exception:
            # Fallback proportional
            imp_a = 1.0 / decimal_odds_a
            imp_b = 1.0 / decimal_odds_b
            devigged_p = imp_a / (imp_a + imp_b)
    else:
        imp_a = 1.0 / decimal_odds_a
        imp_b = 1.0 / decimal_odds_b
        devigged_p = imp_a / (imp_a + imp_b)

    # EV calculation
    expected_value, kelly_fraction = _get_ev_calc()
    if expected_value:
        ev_raw = expected_value(p_model, decimal_odds_a)
    else:
        ev_raw = p_model * decimal_odds_a - 1.0

    ev_pct = ev_raw * 100.0

    # Kelly stake
    if kelly_fraction:
        kelly = kelly_fraction(p_model, decimal_odds_a)
    else:
        b = decimal_odds_a - 1.0
        q = 1.0 - p_model
        f_star = (p_model * b - q) / b if b > 0 else 0.0
        kelly = max(0.0, min(1.0, f_star * 0.5))

    return {
        "ev_pct": round(ev_pct, 2),
        "kelly_stake": round(kelly * 100, 2),  # as % of bankroll
        "devigged_p": round(devigged_p, 4),
    }


def _get_recommendation(ev_pct: float, kelly_stake: float) -> tuple[str, str]:
    """Return (recommendation, confidence) based on EV and Kelly."""
    if ev_pct >= 8.0:
        return "STRONG BET", "HIGH"
    elif ev_pct >= 5.0:
        return "BET", "MEDIUM"
    elif ev_pct >= 2.0:
        return "MARGINAL BET", "LOW"
    elif ev_pct >= 0.0:
        return "NO EDGE", "NONE"
    else:
        return "AVOID", "NONE"


# ── POST /value/check ──────────────────────────────────────────────────────────

@router.post("/value/check", response_model=ValueCheckResponse)
async def check_value(body: ValueCheckRequest):
    """
    Compute Expected Value, Kelly stake, and de-vigged probability for a match.
    """
    try:
        computed = _compute_value(body.p_model, body.decimal_odds_a, body.decimal_odds_b)
    except Exception as exc:
        logger.exception("Value computation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Value computation error: {exc}",
        )

    recommendation, confidence = _get_recommendation(
        computed["ev_pct"], computed["kelly_stake"]
    )

    return ValueCheckResponse(
        ev_pct=computed["ev_pct"],
        kelly_stake=computed["kelly_stake"],
        devigged_p=computed["devigged_p"],
        recommendation=recommendation,
        confidence=confidence,
    )


# ── GET /alerts ────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def get_alerts():
    """Return active value alerts as a JSON list."""
    engine = _get_alert_engine()
    if engine is None:
        return []

    try:
        alerts = engine.get_active_alerts() if hasattr(engine, "get_active_alerts") else []
    except Exception:
        alerts = []

    # Serialize dataclasses/objects to dicts
    result = []
    for a in alerts:
        if hasattr(a, "__dict__"):
            d = {k: v for k, v in a.__dict__.items() if not k.startswith("_")}
            # Serialize datetime and enums
            for key, val in d.items():
                if hasattr(val, "isoformat"):
                    d[key] = val.isoformat()
                elif hasattr(val, "value"):
                    d[key] = val.value
            result.append(d)
        elif isinstance(a, dict):
            result.append(a)

    return result


# ── GET /alerts/stream (SSE) ──────────────────────────────────────────────────

@router.get("/alerts/stream")
async def stream_alerts():
    """
    Server-Sent Events endpoint. Streams new alerts as they arrive.
    Connect with EventSource in the browser.
    """
    engine = _get_alert_engine()

    async def event_generator():
        seen_ids: set = set()
        # Send initial connection event
        yield "event: connected\ndata: {\"status\": \"listening\"}\n\n"

        while True:
            try:
                if engine and hasattr(engine, "get_active_alerts"):
                    alerts = engine.get_active_alerts()
                else:
                    alerts = []

                for a in alerts:
                    alert_id = getattr(a, "id", None) or (a.get("id") if isinstance(a, dict) else None)
                    if alert_id and alert_id not in seen_ids:
                        seen_ids.add(alert_id)
                        if hasattr(a, "__dict__"):
                            d = {k: v for k, v in a.__dict__.items() if not k.startswith("_")}
                            for key, val in d.items():
                                if hasattr(val, "isoformat"):
                                    d[key] = val.isoformat()
                                elif hasattr(val, "value"):
                                    d[key] = val.value
                        else:
                            d = a if isinstance(a, dict) else {}
                        yield f"event: alert\ndata: {json.dumps(d)}\n\n"

                # Heartbeat every 30 s
                yield ": heartbeat\n\n"
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("SSE alert stream error: %s", exc)
                yield f"event: error\ndata: {{\"error\": \"{exc}\"}}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
