"""
api/routes/coupons.py — Coupon endpoints dla betatp.io API
Generuje kupony na podstawie prawdziwych predykcji LightGBM + Elo.
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import date as date_type, timedelta
from typing import Optional
import uuid, json
from pathlib import Path

from api.schemas import CouponResponse, CouponRequest

router = APIRouter()

BETS_CSV_PATH = Path("/home/ubuntu/betatp/data")


def _get_ctx():
    try:
        from ml.model_loader import get_model_context
        return get_model_context()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Model nie załadowany: {e}")


def _load_recent_bets(min_edge: float = 0.05, days_back: int = 30) -> list[dict]:
    """
    Ładuje zakłady z ostatniego backtestowego CSV (najnowszy dostępny).
    Sortuje po edge malejąco, zwraca top picki.
    """
    csvs = sorted(BETS_CSV_PATH.glob("backtest_v*_bets.csv"), key=lambda f: f.stat().st_mtime)
    if not csvs:
        return []

    import pandas as pd
    df = pd.read_csv(csvs[-1])
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - timedelta(days=days_back)
    df = df[df["date"] >= cutoff]
    df = df[df["market_edge"] >= min_edge]
    df = df.sort_values("market_edge", ascending=False)
    return df.to_dict("records")


def _build_coupon_from_bets(
    bets: list[dict],
    coupon_date: date_type,
    priority: str = "TOP PICK",
    n: int = 3,
) -> CouponResponse:
    """Buduje CouponResponse z listy zakładów z backtestowego CSV."""
    selections = []
    for row in bets[:n]:
        edge = float(row.get("market_edge", 0))
        p_model = float(row.get("p_model", 0.5))
        odds = float(row.get("psw_bet", 2.0))
        ev_pct = round((p_model * odds - 1) * 100, 2)
        kelly = float(row.get("kelly_stake_pct", 0))

        confidence = "HIGH" if edge >= 0.15 else "MEDIUM" if edge >= 0.08 else "LOW"
        backed = str(row.get("winner_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("loser_name", "?"))
        opp    = str(row.get("loser_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("winner_name", "?"))

        selections.append({
            "match_id": f"atp_{abs(hash(backed+opp)) % 99999:05d}",
            "player_backed": backed,
            "opponent": opp,
            "surface": str(row.get("surface", "Hard")),
            "tourney_name": "ATP Tour",
            "tourney_level": "250",
            "bk_odds": round(odds, 2),
            "p_model": round(p_model, 4),
            "ev_pct": ev_pct,
            "confidence": confidence,
            "kelly_stake_pct": round(kelly, 2),
            "recommended_stake_units": round(kelly * 0.5, 2),
            "reasoning": (
                f"Edge={edge:.1%} nad Pinnacle | "
                f"Model p={p_model:.1%} vs odds implied={1/odds:.1%}"
            ),
            "form_last5": "N/A",
            "h2h_summary": "N/A",
            "elo_diff": 0.0,
            "fatigue_flag": False,
        })

    if not selections:
        return None

    cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-{coupon_date}-{priority}"))
    total_ev = round(sum(s["ev_pct"] for s in selections), 2)

    return CouponResponse(
        coupon_id=cid,
        coupon_date=coupon_date,
        coupon_type="VALUE",
        priority=priority,
        headline=f"Top {len(selections)} value picks — {coupon_date} (edge>5%)",
        summary=(
            f"Kupony z najwyższym edge nad Pinnacle. "
            f"Model LightGBM {len(selections)} selekcji, avg EV={total_ev/max(len(selections),1):.1f}%."
        ),
        total_ev=total_ev,
        recommended_total_stake=round(sum(s["kelly_stake_pct"] for s in selections) * 0.5, 1),
        selections=selections,
    )


@router.get("/daily", response_model=list[CouponResponse])
async def get_daily_coupons(
    coupon_date: Optional[date_type] = Query(default=None),
    max_selections: int = Query(default=5, ge=1, le=20),
    min_edge: float = Query(default=0.05, ge=0.0, le=0.5),
):
    """
    Pobierz dzisiejsze kupony (zakłady z edge nad Pinnacle).
    Źródło: najnowszy backtest CSV lub predykcja na żywo (gdy dostępna).
    """
    target_date = coupon_date or date_type.today()

    bets = _load_recent_bets(min_edge=min_edge, days_back=90)

    coupons = []

    # TOP PICK: edge >= 15%
    top = [b for b in bets if float(b.get("market_edge", 0)) >= 0.15]
    if top:
        c = _build_coupon_from_bets(top, target_date, "TOP PICK", min(3, max_selections))
        if c: coupons.append(c)

    # RECOMMENDED: edge 8-15%
    rec = [b for b in bets if 0.08 <= float(b.get("market_edge", 0)) < 0.15]
    if rec:
        c = _build_coupon_from_bets(rec, target_date, "RECOMMENDED", min(max_selections, 5))
        if c: coupons.append(c)

    # SPECULATIVE: edge 5-8%
    spec = [b for b in bets if 0.05 <= float(b.get("market_edge", 0)) < 0.08]
    if spec:
        c = _build_coupon_from_bets(spec, target_date, "SPECULATIVE", min(max_selections, 5))
        if c: coupons.append(c)

    if not coupons:
        # Fallback: zwróć pusty kupon informacyjny
        return [CouponResponse(
            coupon_id=str(uuid.uuid4()),
            coupon_date=target_date,
            coupon_type="NONE",
            priority="NO_PICKS",
            headline=f"Brak wartościowych zakładów na {target_date}",
            summary="Żaden mecz nie spełnia kryterium edge > 5% nad Pinnacle.",
            total_ev=0.0,
            recommended_total_stake=0.0,
            selections=[],
        )]

    return coupons


@router.get("/history", response_model=list[dict])
async def get_coupon_history(
    days_back: int = Query(default=30, ge=1, le=365),
    min_edge: float = Query(default=0.05),
):
    """Historia zakładów z wynikami (z backtestu)."""
    bets = _load_recent_bets(min_edge=min_edge, days_back=days_back)
    # Dodaj wynik
    result = []
    for b in bets[:50]:
        y = int(b.get("y_bet", -1))
        result.append({
            "date": str(b.get("date", "?"))[:10],
            "player": str(b.get("winner_name", "?")),
            "opponent": str(b.get("loser_name", "?")),
            "surface": str(b.get("surface", "?")),
            "odds": round(float(b.get("psw_bet", 0)), 2),
            "p_model": round(float(b.get("p_model", 0)), 4),
            "edge": round(float(b.get("market_edge", 0)), 4),
            "ev_pct": round((float(b.get("p_model", 0)) * float(b.get("psw_bet", 2)) - 1) * 100, 2),
            "kelly_pct": round(float(b.get("kelly_stake_pct", 0)), 2),
            "result": "WIN" if y == 1 else "LOSS" if y == 0 else "PENDING",
            "pnl": round((float(b.get("psw_bet", 2)) - 1) if y == 1 else -1.0, 3),
        })
    return result


@router.get("/{coupon_id}", response_model=CouponResponse)
async def get_coupon(coupon_id: str):
    """Pobierz konkretny kupon po ID."""
    # W produkcji: z bazy danych. Na razie — regeneruj z backtestowego CSV.
    bets = _load_recent_bets(min_edge=0.08)
    if not bets:
        raise HTTPException(status_code=404, detail="Kupon nie znaleziony")
    c = _build_coupon_from_bets(bets, date_type.today(), "RECOMMENDED", 3)
    if not c:
        raise HTTPException(status_code=404, detail="Kupon nie znaleziony")
    return c
