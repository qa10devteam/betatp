"""
api/routes/predictions.py — Prediction endpoints dla betatp.io API
"""
from fastapi import APIRouter, HTTPException
import time
import math

from api.schemas import (
    MatchPredictionRequest,
    MatchPredictionResponse,
    PlayerEloResponse,
    EloRatings,
    MonteCarloResult,
)

router = APIRouter()

# Surface-aware Elo boost factors
SURFACE_ELO_FIELD = {
    "hard": "hard",
    "clay": "clay",
    "grass": "grass",
}

# Mock player DB for demo
_MOCK_PLAYERS = {
    1: {"name": "Novak Djokovic", "elo": EloRatings(overall=2180, hard=2150, clay=2120, grass=2200, serve=2100, return_elo=2200), "n_matches": 1200, "is_provisional": False},
    2: {"name": "Carlos Alcaraz", "elo": EloRatings(overall=2100, hard=2080, clay=2150, grass=2060, serve=2050, return_elo=2120), "n_matches": 350, "is_provisional": False},
    3: {"name": "Jannik Sinner", "elo": EloRatings(overall=2090, hard=2110, clay=2050, grass=2040, serve=2000, return_elo=2150), "n_matches": 400, "is_provisional": False},
    4: {"name": "Daniil Medvedev", "elo": EloRatings(overall=2050, hard=2100, clay=1980, grass=1990, serve=1980, return_elo=2100), "n_matches": 600, "is_provisional": False},
    5: {"name": "Alexander Zverev", "elo": EloRatings(overall=2000, hard=2020, clay=2010, grass=1960, serve=2000, return_elo=1980), "n_matches": 550, "is_provisional": False},
}


def _elo_win_prob(elo_a: float, elo_b: float) -> float:
    """Standard Elo win probability."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def _ev(p_win: float, odds: float) -> float:
    """Expected value percentage."""
    return round((p_win * odds - 1.0) * 100.0, 4)


def _simple_signal(ev_a: float, ev_b: float) -> str:
    if ev_a > 5.0 and ev_a > ev_b:
        return "BET_A"
    if ev_b > 5.0 and ev_b > ev_a:
        return "BET_B"
    return "NO_BET"


def _monte_carlo_stub(p_win_a: float, best_of: int = 3) -> MonteCarloResult:
    """Simplified Monte Carlo for sets distribution."""
    # Best of 3: player A needs 2 sets
    # P(A wins 2-0) = p^2, P(A wins 2-1) = 2*p^2*(1-p), etc.
    p = p_win_a
    q = 1.0 - p
    if best_of == 3:
        p_a_20 = p ** 2
        p_a_21 = 2 * (p ** 2) * q
        p_b_02 = q ** 2
        p_b_12 = 2 * (q ** 2) * p
        return MonteCarloResult(
            p_win_sets=[round(p_a_20, 4), round(p_a_21, 4), round(p_b_12, 4), round(p_b_02, 4)],
            simulations=10000,
            confidence_interval_95=[round(p - 1.96 * math.sqrt(p * q / 10000), 4),
                                    round(p + 1.96 * math.sqrt(p * q / 10000), 4)],
        )
    else:
        # Best of 5
        p_win = sum(
            math.comb(2 + k, k) * (p ** 3) * (q ** k)
            for k in range(3)
        )
        p_win = min(max(p_win, 0.0), 1.0)
        return MonteCarloResult(
            p_win_sets=[round(p_win, 4), round(1.0 - p_win, 4)],
            simulations=10000,
            confidence_interval_95=[round(p_win - 0.02, 4), round(p_win + 0.02, 4)],
        )


def _lookup_elo_for_player(name: str, surface: str) -> float:
    """Look up or estimate Elo for a player by name."""
    for pid, data in _MOCK_PLAYERS.items():
        if data["name"].lower() == name.lower():
            elo_obj = data["elo"]
            surface_field = SURFACE_ELO_FIELD.get(surface.lower(), "overall")
            return getattr(elo_obj, surface_field, elo_obj.overall)
    return 1500.0  # default


@router.post("/match", response_model=MatchPredictionResponse)
async def predict_match(body: MatchPredictionRequest):
    """
    B2B endpoint: podany mecz -> predykcja.
    Latency target: < 200ms.
    """
    t0 = time.perf_counter()

    surface = body.surface.lower()
    elo_a = _lookup_elo_for_player(body.player_a_name, surface)
    elo_b = _lookup_elo_for_player(body.player_b_name, surface)

    p_win_a = round(_elo_win_prob(elo_a, elo_b), 6)
    p_win_b = round(1.0 - p_win_a, 6)

    ev_a = _ev(p_win_a, body.odds_a)
    ev_b = _ev(p_win_b, body.odds_b)

    mc = _monte_carlo_stub(p_win_a, body.best_of)
    signal = _simple_signal(ev_a, ev_b)

    # Build EloRatings objects (mock full ratings)
    def _full_elo(base: float) -> EloRatings:
        return EloRatings(
            overall=base,
            hard=round(base + 10 if surface == "hard" else base - 5, 1),
            clay=round(base + 10 if surface == "clay" else base - 5, 1),
            grass=round(base + 10 if surface == "grass" else base - 5, 1),
            serve=round(base - 20, 1),
            return_elo=round(base + 20, 1),
        )

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    return MatchPredictionResponse(
        player_a_name=body.player_a_name,
        player_b_name=body.player_b_name,
        p_win_a=p_win_a,
        p_win_b=p_win_b,
        ev_a=ev_a,
        ev_b=ev_b,
        monte_carlo_result=mc,
        elo_ratings_a=_full_elo(elo_a),
        elo_ratings_b=_full_elo(elo_b),
        signal=signal,
        latency_ms=latency_ms,
    )


@router.get("/player/{player_id}/elo", response_model=PlayerEloResponse)
async def get_player_elo(player_id: int):
    """
    Pobierz aktualne Elo gracza (wszystkie 6 wariantów).
    """
    if player_id not in _MOCK_PLAYERS:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
    p = _MOCK_PLAYERS[player_id]
    return PlayerEloResponse(
        player_id=player_id,
        player_name=p["name"],
        elo=p["elo"],
        n_matches=p["n_matches"],
        is_provisional=p["is_provisional"],
        last_match_date=None,
    )
