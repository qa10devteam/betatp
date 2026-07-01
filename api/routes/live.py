"""
api/routes/live.py — WebSocket live in-play endpoint for atpbet.io
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import time
import math

router = APIRouter()


def _in_play_win_prob(
    sets_a: int, sets_b: int,
    games_a: int, games_b: int,
    pts_a: int, pts_b: int,
    server: str,
    best_of: int = 3,
) -> float:
    """
    Simplified in-play win probability via score-state estimation.
    Real model would use Markov chain / point-by-point model.
    MVP: Elo-based prior adjusted for current score.
    """
    sets_to_win = math.ceil(best_of / 2)

    # Score advantage heuristic
    score_advantage = (
        (sets_a - sets_b) * 0.20
        + (games_a - games_b) * 0.04
        + (pts_a - pts_b) * 0.01
    )

    # Base probability (50/50 if no prior Elo info)
    base_p = 0.50

    # Server slight advantage
    serve_bonus = 0.03 if server == "A" else -0.03

    raw = base_p + score_advantage + serve_bonus
    # Clamp
    return min(max(round(raw, 6), 0.01), 0.99)


@router.websocket("/ws/{match_id}")
async def live_match(websocket: WebSocket, match_id: str):
    """
    WebSocket live in-play.
    Client sends: {sets_a, sets_b, games_a, games_b, pts_a, pts_b, server}
    Server responds: {p_win_a, p_win_b, latency_ms}
    Latency target: < 50ms per update.
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            t0 = time.perf_counter()
            try:
                data = json.loads(raw)
                p_win_a = _in_play_win_prob(
                    sets_a=int(data.get("sets_a", 0)),
                    sets_b=int(data.get("sets_b", 0)),
                    games_a=int(data.get("games_a", 0)),
                    games_b=int(data.get("games_b", 0)),
                    pts_a=int(data.get("pts_a", 0)),
                    pts_b=int(data.get("pts_b", 0)),
                    server=str(data.get("server", "A")),
                )
                latency_ms = round((time.perf_counter() - t0) * 1000, 3)
                response = {
                    "p_win_a": p_win_a,
                    "p_win_b": round(1.0 - p_win_a, 6),
                    "latency_ms": latency_ms,
                    "match_id": match_id,
                }
                await websocket.send_text(json.dumps(response))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                await websocket.send_text(json.dumps({"error": str(e)}))
    except WebSocketDisconnect:
        pass
