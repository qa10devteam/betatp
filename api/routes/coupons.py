"""
api/routes/coupons.py — Coupon endpoints dla betatp.io API
"""
from fastapi import APIRouter, HTTPException
from datetime import date as date_type
from typing import Optional
import uuid

from api.schemas import CouponResponse, SelectionDetail

router = APIRouter()


def _mock_selection(i: int, surface: str = "hard") -> dict:
    players = [
        ("Novak Djokovic", "Carlos Alcaraz"),
        ("Jannik Sinner", "Alexander Zverev"),
        ("Daniil Medvedev", "Andrey Rublev"),
        ("Casper Ruud", "Holger Rune"),
        ("Stefanos Tsitsipas", "Taylor Fritz"),
    ]
    backed, opp = players[i % len(players)]
    return {
        "match_id": f"atp_{i:04d}",
        "player_backed": backed,
        "opponent": opp,
        "surface": surface,
        "tourney_name": "ATP Wimbledon" if surface == "grass" else "ATP Roland Garros" if surface == "clay" else "ATP US Open",
        "tourney_level": "G",
        "bk_odds": round(1.75 + i * 0.15, 2),
        "p_model": round(0.62 - i * 0.02, 4),
        "ev_pct": round(8.5 - i * 0.5, 2),
        "confidence": "HIGH" if i == 0 else "MEDIUM" if i < 3 else "LOW",
        "kelly_stake_pct": round(4.2 - i * 0.3, 2),
        "recommended_stake_units": round(2.1 - i * 0.1, 2),
        "reasoning": f"Elo advantage +{120 - i*15} pts na nawierzchni; forma 4/5 ostatnich meczów.",
        "form_last5": "WWWLW" if i == 0 else "WWLWL",
        "h2h_summary": f"H2H: {3 + i}-{1} korzyść",
        "elo_diff": round(120.0 - i * 15.0, 1),
        "fatigue_flag": i > 3,
    }


def _mock_coupon(coupon_date: date_type, priority: str = "TOP PICK", n_selections: int = 3) -> CouponResponse:
    cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-{coupon_date}-{priority}"))
    selections = [_mock_selection(i) for i in range(n_selections)]
    return CouponResponse(
        coupon_id=cid,
        coupon_date=coupon_date,
        coupon_type="MIXED",
        priority=priority,
        headline=f"Top {n_selections} ATP picks — {coupon_date}",
        summary="Kupony z najwyższym EV na dziś. Model Elo + Monte Carlo.",
        total_ev=round(sum(s["ev_pct"] for s in selections), 2),
        recommended_total_stake=5.0,
        selections=selections,
    )


@router.get("/daily", response_model=list[CouponResponse])
async def get_daily_coupons(date: Optional[date_type] = None):
    """
    Pobierz kupony na dziś (lub podaną datę).
    MVP: zwraca mock data.
    """
    target_date = date or date_type.today()
    coupons = [
        _mock_coupon(target_date, "TOP PICK", 3),
        _mock_coupon(target_date, "RECOMMENDED", 5),
    ]
    return coupons


@router.get("/history")
async def get_coupon_history(limit: int = 30, offset: int = 0):
    """Historia kuponów z wynikami (retrospektywnie)."""
    from datetime import timedelta
    today = date_type.today()
    history = []
    for i in range(min(limit, 30)):
        d = today - timedelta(days=i + offset + 1)
        c = _mock_coupon(d, "TOP PICK" if i % 2 == 0 else "RECOMMENDED", 3)
        history.append({
            **c.model_dump(),
            "actual_return": round(1.85 - i * 0.05, 2),
            "result": "WIN" if i % 3 != 2 else "LOSS",
        })
    return {"total": 90, "limit": limit, "offset": offset, "items": history}


@router.get("/{coupon_id}", response_model=CouponResponse)
async def get_coupon(coupon_id: str):
    """Pobierz jeden kupon z pełnymi detalami."""
    # MVP: only serve mock coupons with known IDs
    today = date_type.today()
    mock_coupons = {
        str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-{today}-TOP PICK")): _mock_coupon(today, "TOP PICK", 3),
        str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-{today}-RECOMMENDED")): _mock_coupon(today, "RECOMMENDED", 5),
    }
    if coupon_id not in mock_coupons:
        raise HTTPException(status_code=404, detail=f"Coupon '{coupon_id}' not found")
    return mock_coupons[coupon_id]
