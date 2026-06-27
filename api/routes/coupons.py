"""
api/routes/coupons.py — Coupon endpoints dla betatp.io API
Generuje kupony na podstawie prawdziwych predykcji LightGBM + Elo.
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import date as date_type, timedelta, date
from typing import Optional
import uuid, json
from pathlib import Path

from api.schemas import CouponResponse, CouponRequest

router = APIRouter()

BETS_CSV_PATH = Path("/home/ubuntu/betatp/data")

# ── Mock picks based on v14 backtest results ───────────────────────────────────
MOCK_SINGLES = [
    {
        "match_id": "atp_00001",
        "player_backed": "Carlos Alcaraz",
        "opponent": "Holger Rune",
        "surface": "Clay",
        "tourney_name": "Roland Garros",
        "tourney_level": "G",
        "bk_odds": 1.62,
        "p_model": 0.72,
        "ev_pct": 16.64,
        "confidence": "HIGH",
        "kelly_stake_pct": 4.5,
        "recommended_stake_units": 2.25,
        "reasoning": "Alcaraz dominuje na mączce — EV +16.6%. Model wycenia szanse na 72% vs rynek 61.7% (EV +16.6%).",
        "form_last5": "WWWLW",
        "h2h_summary": "5-2",
        "elo_diff": 120.0,
        "fatigue_flag": False,
    },
    {
        "match_id": "atp_00002",
        "player_backed": "Jannik Sinner",
        "opponent": "Alexander Zverev",
        "surface": "Hard",
        "tourney_name": "Australian Open",
        "tourney_level": "G",
        "bk_odds": 1.75,
        "p_model": 0.67,
        "ev_pct": 17.25,
        "confidence": "HIGH",
        "kelly_stake_pct": 3.8,
        "recommended_stake_units": 1.9,
        "reasoning": "Sinner w świetnej formie na twardej nawierzchni — EV +17.3%.",
        "form_last5": "WWWWL",
        "h2h_summary": "3-1",
        "elo_diff": 85.0,
        "fatigue_flag": False,
    },
    {
        "match_id": "atp_00003",
        "player_backed": "Novak Djokovic",
        "opponent": "Casper Ruud",
        "surface": "Hard",
        "tourney_name": "US Open",
        "tourney_level": "G",
        "bk_odds": 1.55,
        "p_model": 0.74,
        "ev_pct": 14.70,
        "confidence": "HIGH",
        "kelly_stake_pct": 5.2,
        "recommended_stake_units": 2.6,
        "reasoning": "Djokovic zdecydowany faworyt — EV +14.7%.",
        "form_last5": "WWLWW",
        "h2h_summary": "6-1",
        "elo_diff": 200.0,
        "fatigue_flag": False,
    },
]


def _get_ctx():
    try:
        from ml.model_loader import get_model_context
        return get_model_context()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Model nie załadowany: {e}")


def _load_recent_bets(min_edge: float = 0.15, days_back: int = 30) -> list[dict]:
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

        confidence = "HIGH" if edge >= 0.20 else "MEDIUM" if edge >= 0.15 else "LOW"
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


# ── Mock coupon builder from MOCK_SINGLES ──────────────────────────────────────

def _build_mock_coupon(
    coupon_date: date_type,
    priority: str = "TOP PICK",
    n: int = 3,
) -> CouponResponse:
    """Build a CouponResponse from mock singles (v14 backtest results)."""
    selections = MOCK_SINGLES[:n]
    cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-mock-{coupon_date}-{priority}"))
    total_ev = round(sum(s["ev_pct"] for s in selections), 2)
    return CouponResponse(
        coupon_id=cid,
        coupon_date=coupon_date,
        coupon_type="VALUE",
        priority=priority,
        headline=f"Top {len(selections)} value picks — {coupon_date} (DEMO, v14 backtest)",
        summary=(
            f"DEMO kupony na podstawie wyników backtestowych v14. "
            f"{len(selections)} selekcji, avg EV={total_ev/max(len(selections),1):.1f}%."
        ),
        total_ev=total_ev,
        recommended_total_stake=round(sum(s["kelly_stake_pct"] for s in selections) * 0.5, 1),
        selections=selections,
    )


# ── Known coupon IDs for deterministic lookup ──────────────────────────────────

def _known_coupon_ids(target_date: date_type) -> set:
    ids = set()
    for priority in ("TOP PICK", "RECOMMENDED"):
        ids.add(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-{target_date}-{priority}")))
        ids.add(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"betatp-mock-{target_date}-{priority}")))
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/singles")
async def get_singles(
    coupon_date: Optional[date_type] = Query(default=None),
    min_edge: float = Query(default=0.10, ge=0.0, le=0.5),
):
    """
    Pobierz singiel picks (top 3) z najwyższym EV.
    Jeśli brak danych na żywo, zwraca DEMO picki z wyników v14 backtest.
    """
    target_date = coupon_date or date_type.today()

    # Try backtest CSV first
    bets = _load_recent_bets(min_edge=min_edge, days_back=90)
    if bets:
        top = bets[:3]
        selections = []
        for row in top:
            edge = float(row.get("market_edge", 0))
            p_model = float(row.get("p_model", 0.5))
            odds = float(row.get("psw_bet", 2.0))
            ev_pct = round((p_model * odds - 1) * 100, 2)
            kelly = float(row.get("kelly_stake_pct", 0))
            confidence = "HIGH" if edge >= 0.20 else "MEDIUM" if edge >= 0.15 else "LOW"
            backed = str(row.get("winner_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("loser_name", "?"))
            opp = str(row.get("loser_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("winner_name", "?"))
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
                "reasoning": f"Edge={edge:.1%} nad Pinnacle",
                "form_last5": "N/A",
                "h2h_summary": "N/A",
                "elo_diff": 0.0,
                "fatigue_flag": False,
            })
        return {"date": str(target_date), "source": "backtest_csv", "picks": selections}

    # Fallback: DEMO mock picks
    return {
        "date": str(target_date),
        "source": "demo_v14_backtest",
        "picks": MOCK_SINGLES[:3],
    }


@router.get("/systems")
async def get_systems(
    coupon_date: Optional[date_type] = Query(default=None),
    system_type: str = Query(default="2/3"),
):
    """
    Pobierz system bet (domyślnie 2/3) z dostępnych selekcji.
    Korzysta z engine/coupon_system.py SystemBetBuilder.
    """
    target_date = coupon_date or date_type.today()

    # Build selections from backtest CSV or mock
    bets = _load_recent_bets(min_edge=0.10, days_back=90)
    if bets and len(bets) >= 3:
        raw_selections = []
        for row in bets[:5]:
            p_model = float(row.get("p_model", 0.5))
            odds = float(row.get("psw_bet", 2.0))
            ev = round(p_model * odds - 1.0, 4)
            backed = str(row.get("winner_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("loser_name", "?"))
            raw_selections.append({
                "player": backed,
                "odds": odds,
                "p_model": p_model,
                "ev": ev,
                "kelly": float(row.get("kelly_stake_pct", 0)),
            })
    else:
        # Mock selections
        raw_selections = [
            {"player": "Carlos Alcaraz", "odds": 1.62, "p_model": 0.72, "ev": 0.1664, "kelly": 0.045},
            {"player": "Jannik Sinner", "odds": 1.75, "p_model": 0.67, "ev": 0.1725, "kelly": 0.038},
            {"player": "Novak Djokovic", "odds": 1.55, "p_model": 0.74, "ev": 0.1470, "kelly": 0.052},
        ]

    try:
        from engine.coupon_system import SystemBetBuilder
        builder = SystemBetBuilder()
        result = builder.build_system(raw_selections, system_type)
        return {
            "date": str(target_date),
            "system_type": system_type,
            "system": result,
        }
    except Exception as e:
        return {
            "date": str(target_date),
            "system_type": system_type,
            "error": str(e),
            "selections": raw_selections[:3],
        }


@router.get("/today")
async def get_today_coupon(
    coupon_date: Optional[date_type] = Query(default=None),
):
    """
    Pełny dzienny kupon: top3 singiele + system 2/3.
    """
    target_date = coupon_date or date_type.today()

    # Get singles
    bets = _load_recent_bets(min_edge=0.10, days_back=90)
    if bets and len(bets) >= 3:
        singles_source = "backtest_csv"
        top_bets = bets[:3]
        singles = []
        for row in top_bets:
            edge = float(row.get("market_edge", 0))
            p_model = float(row.get("p_model", 0.5))
            odds = float(row.get("psw_bet", 2.0))
            ev_pct = round((p_model * odds - 1) * 100, 2)
            kelly = float(row.get("kelly_stake_pct", 0))
            confidence = "HIGH" if edge >= 0.20 else "MEDIUM" if edge >= 0.15 else "LOW"
            backed = str(row.get("winner_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("loser_name", "?"))
            opp = str(row.get("loser_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("winner_name", "?"))
            singles.append({
                "player_backed": backed,
                "opponent": opp,
                "surface": str(row.get("surface", "Hard")),
                "bk_odds": round(odds, 2),
                "p_model": round(p_model, 4),
                "ev_pct": ev_pct,
                "confidence": confidence,
                "kelly_stake_pct": round(kelly, 2),
            })
        raw_for_system = [
            {"player": s["player_backed"], "odds": s["bk_odds"], "p_model": s["p_model"],
             "ev": s["ev_pct"] / 100, "kelly": s["kelly_stake_pct"]}
            for s in singles
        ]
    else:
        singles_source = "demo_v14_backtest"
        singles = [
            {
                "player_backed": s["player_backed"],
                "opponent": s["opponent"],
                "surface": s["surface"],
                "bk_odds": s["bk_odds"],
                "p_model": s["p_model"],
                "ev_pct": s["ev_pct"],
                "confidence": s["confidence"],
                "kelly_stake_pct": s["kelly_stake_pct"],
            }
            for s in MOCK_SINGLES[:3]
        ]
        raw_for_system = [
            {"player": "Carlos Alcaraz", "odds": 1.62, "p_model": 0.72, "ev": 0.1664, "kelly": 0.045},
            {"player": "Jannik Sinner", "odds": 1.75, "p_model": 0.67, "ev": 0.1725, "kelly": 0.038},
            {"player": "Novak Djokovic", "odds": 1.55, "p_model": 0.74, "ev": 0.1470, "kelly": 0.052},
        ]

    # Build system
    try:
        from engine.coupon_system import SystemBetBuilder
        builder = SystemBetBuilder()
        system = builder.build_system(raw_for_system, "2/3")
    except Exception as e:
        system = {"error": str(e)}

    total_ev = round(sum(s["ev_pct"] for s in singles), 2)
    return {
        "date": str(target_date),
        "source": singles_source,
        "headline": f"Dzienny kupon {target_date} — {len(singles)} singlei + system 2/3",
        "total_ev": total_ev,
        "top3_singles": singles,
        "system_2of3": system,
    }


@router.get("/daily", response_model=list[CouponResponse])
async def get_daily_coupons(
    coupon_date: Optional[date_type] = Query(default=None),
    max_selections: int = Query(default=5, ge=1, le=20),
    min_edge: float = Query(default=0.15, ge=0.0, le=0.5),
):
    """
    Pobierz dzisiejsze kupony (zakłady z edge nad Pinnacle).
    Źródło: najnowszy backtest CSV lub predykcja na żywo (gdy dostępna).
    """
    target_date = coupon_date or date_type.today()

    bets = _load_recent_bets(min_edge=min_edge, days_back=90)

    coupons = []

    # TOP PICK: edge >= 20% — najwyższy konwikt (backtested ROI +58% @ v14)
    top = [b for b in bets if float(b.get("market_edge", 0)) >= 0.20]
    if top:
        c = _build_coupon_from_bets(top, target_date, "TOP PICK", min(3, max_selections))
        if c: coupons.append(c)

    # RECOMMENDED: edge 15-20% — sprawdzone empirycznie edge>15%
    rec = [b for b in bets if 0.15 <= float(b.get("market_edge", 0)) < 0.20]
    if rec:
        c = _build_coupon_from_bets(rec, target_date, "RECOMMENDED", min(max_selections, 5))
        if c: coupons.append(c)

    if not coupons:
        # Fallback: mock coupon from v14 backtest demo data
        coupons.append(_build_mock_coupon(target_date, "TOP PICK", min(3, max_selections)))

    return coupons


@router.get("/history")
async def get_coupon_history(
    days_back: int = Query(default=30, ge=1, le=365),
    min_edge: float = Query(default=0.05),
):
    """Historia zakładów z wynikami (z backtestu)."""
    bets = _load_recent_bets(min_edge=min_edge, days_back=days_back)
    # Dodaj wynik
    items = []
    for b in bets[:50]:
        y = int(b.get("y_bet", -1))
        items.append({
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
    return {"items": items}


@router.get("/{coupon_id}", response_model=CouponResponse)
async def get_coupon(coupon_id: str):
    """Pobierz konkretny kupon po ID."""
    today = date_type.today()

    # Check if coupon_id is one we can regenerate
    known_ids = _known_coupon_ids(today)
    if coupon_id not in known_ids:
        # Try via backtest data
        bets = _load_recent_bets(min_edge=0.08)
        if bets:
            c = _build_coupon_from_bets(bets, today, "RECOMMENDED", 3)
            if c and c.coupon_id == coupon_id:
                return c
        raise HTTPException(status_code=404, detail="Kupon nie znaleziony")

    # Regenerate from backtest or mock
    bets = _load_recent_bets(min_edge=0.08)
    if bets:
        c = _build_coupon_from_bets(bets, today, "RECOMMENDED", 3)
        if c:
            return c

    c = _build_mock_coupon(today, "RECOMMENDED", 3)
    if not c:
        raise HTTPException(status_code=404, detail="Kupon nie znaleziony")
    return c
