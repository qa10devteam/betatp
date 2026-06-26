"""
engine/live_engine.py — In-play probability engine with LUT precomputation.
Target latency: < 50ms per update (target < 18ms via O(1) LUT lookup).
"""
import time
from typing import Optional


class LiveStateEngine:
    """
    In-play probability engine z LUT precomputation.
    Latencja: < 50ms per update (target < 18ms).
    """

    def __init__(self, mc_engine=None):
        self.mc = mc_engine
        self._luts: dict = {}   # match_id -> {"params": {...}, "table": {...}}

    # ------------------------------------------------------------------
    # LUT precomputation (DP backward induction)
    # ------------------------------------------------------------------

    def prepare_match(
        self,
        match_id: str,
        p_serve_a: float,
        p_serve_b: float,
        best_of: int = 3,
    ) -> None:
        """
        Precompute LUT dla meczu PRZED jego rozpoczęciem.
        State: (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server)
          server: 0 = A serves, 1 = B serves
        Uses backward induction via DP.
        """
        sets_to_win = (best_of + 1) // 2   # 2 for BO3, 3 for BO5
        lut: dict = {}

        def p_win_point(server: int) -> tuple:
            """Returns (p_a_wins_point, p_b_wins_point) given server."""
            if server == 0:
                return p_serve_a, 1.0 - p_serve_a
            else:
                return 1.0 - p_serve_b, p_serve_b

        # --- Terminal: sets ---
        def p_win_game(pa: int, pb: int, server: int) -> float:
            """P(A wins game) given score (pa, pb) and server, via DP."""
            memo: dict = {}

            def dp(a: int, b: int) -> float:
                if (a, b) in memo:
                    return memo[(a, b)]
                # Deuce-aware tennis scoring: 0,1,2,3=40, then deuce/adv
                # Points: 0,1,2,3 -> 4 = win (unless tied at 3-3 -> deuce)
                if a >= 4 and b >= 4:
                    # deuce situation: a - b represents advantage
                    diff = a - b
                    if diff >= 2:
                        return 1.0
                    if diff <= -2:
                        return 0.0
                else:
                    if a >= 4:
                        return 1.0
                    if b >= 4:
                        return 0.0
                pa_pt, pb_pt = p_win_point(server)
                val = pa_pt * dp(a + 1, b) + pb_pt * dp(a, b + 1)
                memo[(a, b)] = val
                return val

            return dp(pa, pb)

        def p_win_tiebreak(pa: int, pb: int, server: int) -> float:
            """P(A wins tiebreak) at score pa-pb."""
            memo: dict = {}

            def dp(a: int, b: int, srv: int) -> float:
                if (a, b, srv) in memo:
                    return memo[(a, b, srv)]
                if a >= 7 and b >= 7:
                    diff = a - b
                    if diff >= 2:
                        return 1.0
                    if diff <= -2:
                        return 0.0
                else:
                    if a >= 7:
                        return 1.0
                    if b >= 7:
                        return 0.0
                # Server alternates every 2 points (after first point)
                pa_pt, pb_pt = p_win_point(srv)
                # Next server: changes every 2 points from start
                total = a + b
                next_srv = srv if (total + 1) % 2 == total % 2 else (1 - srv)
                val = pa_pt * dp(a + 1, b, next_srv) + pb_pt * dp(a, b + 1, next_srv)
                memo[(a, b, srv)] = val
                return val

            return dp(pa, pb, server)

        def p_win_set(ga: int, gb: int, pa_pts: int, pb_pts: int, server: int) -> float:
            """P(A wins set) given game score (ga, gb) and current game points."""
            memo: dict = {}

            def dp(g_a: int, g_b: int, srv: int) -> float:
                if (g_a, g_b, srv) in memo:
                    return memo[(g_a, g_b, srv)]
                # Terminal: set won
                if g_a >= 6 and g_b <= 4:
                    return 1.0
                if g_b >= 6 and g_a <= 4:
                    return 0.0
                if g_a == 7:
                    return 1.0
                if g_b == 7:
                    return 0.0
                # 6-6: tiebreak
                if g_a == 6 and g_b == 6:
                    return p_win_tiebreak(0, 0, srv)
                # P(A wins current game)
                p_a_game = p_win_game(0, 0, srv)
                next_srv = 1 - srv
                val = p_a_game * dp(g_a + 1, g_b, next_srv) + (1 - p_a_game) * dp(g_a, g_b + 1, next_srv)
                memo[(g_a, g_b, srv)] = val
                return val

            # Incorporate current game points into set prob
            p_a_finish_game = p_win_game(pa_pts, pb_pts, server)
            next_srv = 1 - server
            return p_a_finish_game * dp(ga + 1, gb, next_srv) + (1 - p_a_finish_game) * dp(ga, gb + 1, next_srv)

        def p_win_match(sa: int, sb: int, ga: int, gb: int, pa_pts: int, pb_pts: int, server: int) -> float:
            """P(A wins match) given full state."""
            memo: dict = {}

            def dp(s_a: int, s_b: int, srv: int) -> float:
                if (s_a, s_b, srv) in memo:
                    return memo[(s_a, s_b, srv)]
                if s_a >= sets_to_win:
                    return 1.0
                if s_b >= sets_to_win:
                    return 0.0
                p_a_set = p_win_set(0, 0, 0, 0, srv)
                next_srv = srv  # serve alternates per game inside set, set-level server is starting server
                val = p_a_set * dp(s_a + 1, s_b, next_srv) + (1 - p_a_set) * dp(s_a, s_b + 1, next_srv)
                memo[(s_a, s_b, srv)] = val
                return val

            # Current set prob
            p_a_current_set = p_win_set(ga, gb, pa_pts, pb_pts, server)
            next_srv = server  # simplified: same starting server per set

            def dp2(s_a: int, s_b: int) -> float:
                k = (s_a, s_b)
                if s_a >= sets_to_win:
                    return 1.0
                if s_b >= sets_to_win:
                    return 0.0
                if k in memo:
                    return memo[k]
                p_s = p_win_set(0, 0, 0, 0, server)
                val = p_s * dp2(s_a + 1, s_b) + (1 - p_s) * dp2(s_a, s_b + 1)
                memo[k] = val
                return val

            return p_a_current_set * dp2(sa + 1, sb) + (1 - p_a_current_set) * dp2(sa, sb + 1)

        # Build LUT for common states
        for sa in range(sets_to_win):
            for sb in range(sets_to_win):
                for ga in range(8):
                    for gb in range(8):
                        for pa_pts in range(8):
                            for pb_pts in range(8):
                                for srv in range(2):
                                    state = (sa, sb, ga, gb, pa_pts, pb_pts, srv)
                                    try:
                                        p = p_win_match(sa, sb, ga, gb, pa_pts, pb_pts, srv)
                                        lut[state] = round(p, 6)
                                    except Exception:
                                        lut[state] = 0.5

        self._luts[match_id] = {
            "params": {
                "p_serve_a": p_serve_a,
                "p_serve_b": p_serve_b,
                "best_of": best_of,
                "sets_to_win": sets_to_win,
            },
            "table": lut,
        }

    # ------------------------------------------------------------------
    # O(1) state update
    # ------------------------------------------------------------------

    def update_state(
        self,
        match_id: str,
        state: tuple,  # (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server)
    ) -> dict:
        """O(1) LUT lookup. Returns {p_win_a, p_win_b, current_state, latency_ms}."""
        t0 = time.perf_counter()

        if match_id not in self._luts:
            raise KeyError(f"Match {match_id} not prepared. Call prepare_match first.")

        lut_entry = self._luts[match_id]
        table = lut_entry["table"]

        # Normalize state to (sa, sb, ga, gb, pa, pb, server)
        if len(state) == 7:
            sa, sb, ga, gb, pa, pb, srv = state
        else:
            raise ValueError("State must be 7-tuple: (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server)")

        p_a = table.get((sa, sb, ga, gb, pa, pb, srv), 0.5)
        p_b = round(1.0 - p_a, 6)

        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "p_win_a": p_a,
            "p_win_b": p_b,
            "current_state": state,
            "latency_ms": round(latency_ms, 3),
        }

    # ------------------------------------------------------------------
    # Score parsing
    # ------------------------------------------------------------------

    POINT_MAP = {
        "0": 0, "15": 1, "30": 2, "40": 3,
        "AD": 4, "A": 4,
    }

    def parse_score_string(
        self,
        score: str,
        sets: list,
        current_server: str,
    ) -> tuple:
        """
        Parsuj score string '40-30' -> pts_a=3, pts_b=2 (zero-indexed).
        sets: list of (games_a, games_b) tuples for completed sets.
        current_server: 'a' or 'b'

        Returns: (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server_int)
        """
        # Determine sets won
        sets_a = 0
        sets_b = 0
        for (g_a, g_b) in sets:
            if g_a > g_b:
                sets_a += 1
            else:
                sets_b += 1

        # Current games — take last element or 0
        if sets:
            # Current set games could be provided via sets list as ongoing set
            # Assume sets contains only completed sets; current game score = 0-0
            games_a, games_b = 0, 0
        else:
            games_a, games_b = 0, 0

        # Parse point score
        pts_a, pts_b = self._parse_points(score)

        server_int = 0 if current_server.lower() in ("a", "0") else 1

        return (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server_int)

    def _parse_points(self, score: str) -> tuple:
        """Parse '40-30' -> (3, 2). Also handles 'AD-40' -> (4, 3)."""
        parts = score.strip().replace("–", "-").split("-")
        if len(parts) != 2:
            return (0, 0)
        left = parts[0].strip().upper()
        right = parts[1].strip().upper()
        pa = self.POINT_MAP.get(left, 0)
        pb = self.POINT_MAP.get(right, 0)
        return pa, pb
