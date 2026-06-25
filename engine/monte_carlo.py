"""
Monte Carlo Engine for betatp.io
Vectorized NumPy simulation of N=100,000 ATP tennis matches simultaneously.
Mathematical foundation: (Omega, F, P) product measure Bernoulli iid
"""
import time
from collections import Counter
from typing import Literal

import numpy as np
from dataclasses import dataclass, field


@dataclass
class MatchConfig:
    p_serve_a: float  # P(server A wins a serve point)
    p_serve_b: float  # P(server B wins a serve point)
    best_of: Literal[3, 5] = 3
    serve_first: Literal['A', 'B'] = 'A'
    final_set_format: Literal['tiebreak', 'advantage', 'super_tiebreak'] = 'tiebreak'


@dataclass
class SimulationResult:
    p_win_a: float
    p_win_b: float
    p_set_scores: dict          # {"2-0": 0.45, "2-1": 0.30, "0-2": 0.15, "1-2": 0.10}
    p_tiebreak_by_set: list     # [P(TB set1), P(TB set2), ...]
    p_tiebreak_any: float
    expected_games: float
    expected_sets: float
    expected_duration_minutes: float  # using 4.5 min/game heuristic
    p_match_goes_max_sets: float      # P(3-set BO3 or 5-set BO5)
    p_a_wins_first_set: float
    confidence_interval_95: tuple     # (p_win_a_low, p_win_a_high)
    n_simulations: int
    computation_time_ms: float


# ---------------------------------------------------------------------------
# Exact probability computations (closed-form / DP)
# ---------------------------------------------------------------------------

def _game_win_prob(p: float) -> float:
    """
    Exact P(server wins a game) with point probability p.
    Uses: no-deuce path + deuce path.
    """
    q = 1.0 - p
    # Win 4-0, 4-1, 4-2
    no_deuce = p**4 + 4*p**4*q + 10*p**4*q**2
    # Reach 3-3 deuce, then P(win from deuce) = p^2/(p^2+q^2)
    p_deuce = 20 * p**3 * q**3
    p_win_deuce = p**2 / (p**2 + q**2)
    return no_deuce + p_deuce * p_win_deuce


def _tiebreak_win_prob(p_a: float, p_b: float, target: int = 7) -> float:
    """
    P(A wins tiebreak) first-to-target win-by-2.
    A serves first point. Serve alternates every 2 points (every 1 after both reach target-1).
    Uses memoized DP with closed-form for deuce zone.
    """
    memo: dict = {}

    def _server(total: int) -> int:
        """0=A serves, 1=B serves. Alternates every 2 points; every 1 from 2*(target-1) on."""
        if total < 2 * (target - 1):
            return (total // 2) % 2
        else:
            return total % 2

    def dp(a: int, b: int) -> float:
        if a >= target and a - b >= 2:
            return 1.0
        if b >= target and b - a >= 2:
            return 0.0
        key = (a, b)
        if key in memo:
            return memo[key]

        # Deuce zone: a == b and both >= target-1 → closed-form to avoid infinite recursion
        if a == b and a >= target - 1:
            total = a + b
            s0 = _server(total)       # server at (a,b)
            s1 = _server(total + 1)   # server at (a+1,b) or (a,b+1)
            p1 = p_a if s0 == 0 else (1.0 - p_b)  # P(A wins this point)
            p2 = p_a if s1 == 0 else (1.0 - p_b)  # P(A wins next point)
            # Closed form: D = p1*p2 / (p1*p2 + (1-p1)*(1-p2))
            num = p1 * p2
            denom = num + (1.0 - p1) * (1.0 - p2)
            v = num / denom if denom > 0 else 0.5
            memo[key] = v
            return v

        total = a + b
        server = _server(total)
        p = p_a if server == 0 else (1.0 - p_b)
        v = p * dp(a + 1, b) + (1.0 - p) * dp(a, b + 1)
        memo[key] = v
        return v

    return dp(0, 0)


# ---------------------------------------------------------------------------
# DP for LUT
# ---------------------------------------------------------------------------

def _dp_match(p_a: float, p_b: float, sets_to_win: int, final_set_format: str) -> dict:
    """
    Compute P(A wins) for all reachable match states via recursive DP with memoization.
    State: (sa, sb, ga, gb, pa, pb, srv)
    Points 0-3: normal. Deuce handled with closed-form to avoid infinite recursion.
    Deuce states encoded as (3,3)=deuce, (4,3)=advA, (3,4)=advB.
    """
    memo: dict = {}

    # Closed-form: P(A wins game from deuce) given server srv
    def _p_game_from_deuce(srv: int) -> float:
        p = p_a if srv == 0 else (1.0 - p_b)
        q = 1.0 - p
        return p * p / (p * p + q * q)

    # P(A wins game from advantage A) given server srv
    def _p_game_from_adv_a(srv: int) -> float:
        p = p_a if srv == 0 else (1.0 - p_b)
        q = 1.0 - p
        # advA: A wins next point → wins game; B wins → deuce
        d = _p_game_from_deuce(srv)
        return p + q * d

    # P(A wins game from advantage B) given server srv
    def _p_game_from_adv_b(srv: int) -> float:
        p = p_a if srv == 0 else (1.0 - p_b)
        q = 1.0 - p
        # advB: B wins next → wins game; A wins → deuce
        d = _p_game_from_deuce(srv)
        return p * d  # A must win from deuce

    def _advance_game(sa, sb, ga, gb, srv):
        """After a game is won, resolve set completion."""
        nsa, nsb = sa, sb
        nga, ngb = ga, gb
        nsrv = srv
        # Check set win
        if nga == 7 and ngb == 6:
            nsa += 1; nga, ngb = 0, 0
        elif nga == 6 and ngb == 7:
            nsb += 1; nga, ngb = 0, 0
        elif nga >= 6 and nga - ngb >= 2:
            nsa += 1; nga, ngb = 0, 0
        elif ngb >= 6 and ngb - nga >= 2:
            nsb += 1; nga, ngb = 0, 0
        return nsa, nsb, nga, ngb, nsrv

    def V(sa: int, sb: int, ga: int, gb: int, pa: int, pb: int, srv: int) -> float:
        if sa >= sets_to_win:
            memo[(sa, sb, ga, gb, pa, pb, srv)] = 1.0
            return 1.0
        if sb >= sets_to_win:
            memo[(sa, sb, ga, gb, pa, pb, srv)] = 0.0
            return 0.0

        key = (sa, sb, ga, gb, pa, pb, srv)
        if key in memo:
            return memo[key]

        p_point = p_a if srv == 0 else (1.0 - p_b)
        q_point = 1.0 - p_point

        # ----- Handle special point states (deuce/adv) with closed form -----
        if pa == 3 and pb == 3:
            # Deuce: compute P(A wins game from here), then V after game
            p_a_wins_game = _p_game_from_deuce(srv)
            nsrv_after = 1 - srv
            # A wins game
            sa_aw, sb_aw, ga_aw, gb_aw, _ = _advance_game(sa, sb, ga + 1, gb, nsrv_after)
            # B wins game
            sa_bw, sb_bw, ga_bw, gb_bw, _ = _advance_game(sa, sb, ga, gb + 1, nsrv_after)
            v = p_a_wins_game * V(sa_aw, sb_aw, ga_aw, gb_aw, 0, 0, nsrv_after) + \
                (1 - p_a_wins_game) * V(sa_bw, sb_bw, ga_bw, gb_bw, 0, 0, nsrv_after)
            memo[key] = v
            return v

        if pa == 4 and pb == 3:
            # Advantage A
            p_a_wins_game = _p_game_from_adv_a(srv)
            nsrv_after = 1 - srv
            sa_aw, sb_aw, ga_aw, gb_aw, _ = _advance_game(sa, sb, ga + 1, gb, nsrv_after)
            sa_bw, sb_bw, ga_bw, gb_bw, _ = _advance_game(sa, sb, ga, gb + 1, nsrv_after)
            v = p_a_wins_game * V(sa_aw, sb_aw, ga_aw, gb_aw, 0, 0, nsrv_after) + \
                (1 - p_a_wins_game) * V(sa_bw, sb_bw, ga_bw, gb_bw, 0, 0, nsrv_after)
            memo[key] = v
            return v

        if pa == 3 and pb == 4:
            # Advantage B
            p_a_wins_game = _p_game_from_adv_b(srv)
            nsrv_after = 1 - srv
            sa_aw, sb_aw, ga_aw, gb_aw, _ = _advance_game(sa, sb, ga + 1, gb, nsrv_after)
            sa_bw, sb_bw, ga_bw, gb_bw, _ = _advance_game(sa, sb, ga, gb + 1, nsrv_after)
            v = p_a_wins_game * V(sa_aw, sb_aw, ga_aw, gb_aw, 0, 0, nsrv_after) + \
                (1 - p_a_wins_game) * V(sa_bw, sb_bw, ga_bw, gb_bw, 0, 0, nsrv_after)
            memo[key] = v
            return v

        # ----- Normal point states (0-3 pre-deuce) -----
        def step(a_wins_point: bool):
            npa = pa + (1 if a_wins_point else 0)
            npb = pb + (0 if a_wins_point else 1)
            nsa, nsb = sa, sb
            nga, ngb = ga, gb
            nsrv = srv

            game_over = False
            if npa >= 3 and npb >= 3:
                diff = npa - npb
                if diff >= 2:
                    game_over = True; nga += 1; npa, npb = 0, 0; nsrv = 1 - srv
                elif diff <= -2:
                    game_over = True; ngb += 1; npa, npb = 0, 0; nsrv = 1 - srv
                elif diff == 0:
                    npa, npb = 3, 3   # deuce → use closed form next call
                elif diff == 1:
                    npa, npb = 4, 3   # adv A
                else:
                    npa, npb = 3, 4   # adv B
            else:
                if npa >= 4:
                    game_over = True; nga += 1; npa, npb = 0, 0; nsrv = 1 - srv
                elif npb >= 4:
                    game_over = True; ngb += 1; npa, npb = 0, 0; nsrv = 1 - srv

            if game_over:
                nsa, nsb, nga, ngb, nsrv = _advance_game(nsa, nsb, nga, ngb, nsrv)

            return V(nsa, nsb, nga, ngb, npa, npb, nsrv)

        v = p_point * step(True) + q_point * step(False)
        memo[key] = v
        return v

    # Trigger computation from start state
    V(0, 0, 0, 0, 0, 0, 0)
    return memo


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------

class MonteCarloEngine:
    def __init__(self, n_simulations: int = 100_000, seed: int | None = None):
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)
        self._lut_cache: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_match(self, config: MatchConfig) -> SimulationResult:
        """
        Vectorized NumPy simulation of N matches simultaneously.
        ALL random numbers generated upfront as matrix.
        """
        t0 = time.perf_counter()
        n = self.n_simulations
        data = self._simulate_full(config, n)
        dt = (time.perf_counter() - t0) * 1000.0

        wins_a = data['wins_a']
        p_win_a = float(wins_a.mean())
        p_win_b = 1.0 - p_win_a

        se = np.sqrt(max(p_win_a * p_win_b, 1e-12) / n)
        ci = (max(0.0, p_win_a - 1.96 * se), min(1.0, p_win_a + 1.96 * se))

        p_set_scores = {f"{sa}-{sb}": cnt / n
                        for (sa, sb), cnt in data['set_score_counts'].items()}

        max_sets = config.best_of
        p_tb_by_set = [float(data['tb_by_set'][s].mean()) for s in range(max_sets)]
        p_tb_any = float((data['tb_any'] > 0).mean())

        return SimulationResult(
            p_win_a=p_win_a,
            p_win_b=p_win_b,
            p_set_scores=p_set_scores,
            p_tiebreak_by_set=p_tb_by_set,
            p_tiebreak_any=p_tb_any,
            expected_games=float(data['total_games'].mean()),
            expected_sets=float(data['total_sets'].mean()),
            expected_duration_minutes=float(data['total_games'].mean()) * 4.5,
            p_match_goes_max_sets=float(data['went_max_sets'].mean()),
            p_a_wins_first_set=float(data['a_wins_first_set'].mean()),
            confidence_interval_95=ci,
            n_simulations=n,
            computation_time_ms=dt,
        )

    def _simulate_vectorized(self, p_a: float, p_b: float, best_of: int, n: int) -> np.ndarray:
        """
        Returns array of shape (n,) with 1=A wins, 0=B wins.
        Core vectorized loop — all N simulations run simultaneously.
        """
        # Cast best_of for MatchConfig
        bo = 3 if best_of == 3 else 5
        config = MatchConfig(p_serve_a=p_a, p_serve_b=p_b, best_of=bo)  # type: ignore
        data = self._simulate_full(config, n)
        return data['wins_a'].astype(np.int8)

    # ------------------------------------------------------------------
    # Core vectorized simulation (game-level)
    # ------------------------------------------------------------------

    def _simulate_full(self, config: MatchConfig, n: int) -> dict:
        """
        Full vectorized simulation (game-level events).
        Returns rich statistics dict.
        """
        p_a = config.p_serve_a
        p_b = config.p_serve_b
        sets_to_win = (config.best_of + 1) // 2

        # Exact game-win probabilities
        p_ga_srv = _game_win_prob(p_a)         # P(A wins game | A serves)
        p_ga_ret = 1.0 - _game_win_prob(p_b)  # P(A wins game | B serves)
        p_tb_a = _tiebreak_win_prob(p_a, p_b, 7)
        p_super_tb_a = _tiebreak_win_prob(p_a, p_b, 10)

        # State arrays
        sets_a = np.zeros(n, dtype=np.int16)
        sets_b = np.zeros(n, dtype=np.int16)
        games_a = np.zeros(n, dtype=np.int16)
        games_b = np.zeros(n, dtype=np.int16)
        srv = np.zeros(n, dtype=np.int8)
        if config.serve_first == 'B':
            srv[:] = 1

        # Tracking
        total_games = np.zeros(n, dtype=np.int32)
        total_sets = np.zeros(n, dtype=np.int16)
        wins_a = np.zeros(n, dtype=np.int8)
        tb_any = np.zeros(n, dtype=np.int8)
        tb_by_set = [np.zeros(n, dtype=np.int8) for _ in range(config.best_of)]
        a_wins_first_set = np.zeros(n, dtype=np.int8)
        first_set_done = np.zeros(n, dtype=bool)

        active = np.ones(n, dtype=bool)
        set_scores_list = []  # will collect (sa, sb) at match end

        # Pre-generate random buffer: max_iter game outcomes
        max_iter = 250
        rand_buf = self.rng.random((max_iter, n))

        for step in range(max_iter):
            if not active.any():
                break

            act = active
            r = rand_buf[step]

            is_final_set = act & (sets_a == sets_to_win - 1) & (sets_b == sets_to_win - 1)
            is_tb = act & (games_a == 6) & (games_b == 6)
            is_adv_set = is_final_set & (config.final_set_format == 'advantage')
            is_super_tb = is_final_set & is_tb & (config.final_set_format == 'super_tiebreak')
            is_regular_tb = is_tb & ~is_adv_set & ~is_super_tb

            # P(A wins this game)
            p_game = np.where(srv == 0, p_ga_srv, p_ga_ret)
            p_game = np.where(is_regular_tb, p_tb_a, p_game)
            p_game = np.where(is_super_tb, p_super_tb_a, p_game)

            a_wins_game = act & (r < p_game)

            # Track tiebreak
            tb_now = is_tb & act
            tb_any[tb_now] = 1
            cur_set = (sets_a + sets_b).clip(0, config.best_of - 1)
            for s in range(config.best_of):
                tb_by_set[s][tb_now & (cur_set == s)] = 1

            # Update game scores
            games_a[a_wins_game] += 1
            games_b[~a_wins_game & act] += 1
            total_games[act] += 1

            # Determine set winner
            # Normal: 6+ games, 2-game lead (or 7-6 after TB)
            a_wins_set = (
                (act & (games_a == 7) & (games_b == 6)) |
                (act & (games_a >= 6) & (games_a - games_b >= 2) & ~is_adv_set)
            )
            b_wins_set = (
                (act & (games_b == 7) & (games_a == 6)) |
                (act & (games_b >= 6) & (games_b - games_a >= 2) & ~is_adv_set)
            )
            # Advantage set: keep going past 6-6
            a_wins_set_adv = is_adv_set & (games_a >= 6) & (games_a - games_b >= 2)
            b_wins_set_adv = is_adv_set & (games_b >= 6) & (games_b - games_a >= 2)
            a_wins_set = a_wins_set | a_wins_set_adv
            b_wins_set = b_wins_set | b_wins_set_adv

            set_done = a_wins_set | b_wins_set

            # Track first set
            first_now = set_done & ~first_set_done
            a_wins_first_set[first_now & a_wins_set] = 1
            first_set_done[first_now] = True

            # Update sets
            sets_a[a_wins_set] += 1
            sets_b[b_wins_set] += 1
            total_sets[set_done] += 1
            games_a[set_done] = 0
            games_b[set_done] = 0

            # Match over?
            match_a = act & (sets_a == sets_to_win)
            match_b = act & (sets_b == sets_to_win)
            match_done = match_a | match_b
            wins_a[match_a] = 1
            active[match_done] = False

            # Server rotates after each game
            srv[act & ~match_done] ^= 1

        # Collect set score distribution
        sc = Counter(zip(sets_a.tolist(), sets_b.tolist()))

        went_max_sets = (total_sets >= config.best_of).astype(np.int8)

        return {
            'wins_a': wins_a,
            'total_games': total_games,
            'total_sets': total_sets,
            'tb_any': tb_any,
            'tb_by_set': tb_by_set,
            'a_wins_first_set': a_wins_first_set,
            'set_score_counts': dict(sc),
            'went_max_sets': went_max_sets,
        }

    # ------------------------------------------------------------------
    # LUT / Dynamic Programming
    # ------------------------------------------------------------------

    def precompute_lut(self, config: MatchConfig) -> dict:
        """
        Precompute V(state) for ALL states using dynamic programming.
        V(s) = p_serve * V(s_win) + (1-p_serve) * V(s_lose)
        Base cases: V(A_wins) = 1.0, V(B_wins) = 0.0
        Returns LUT dict: state_tuple -> p_win_a (also cached in self._lut_cache)
        """
        key = (config.p_serve_a, config.p_serve_b, config.best_of,
               config.serve_first, config.final_set_format)
        if key in self._lut_cache:
            return self._lut_cache[key]

        sets_to_win = (config.best_of + 1) // 2
        lut = _dp_match(
            config.p_serve_a, config.p_serve_b,
            sets_to_win, config.final_set_format
        )
        self._lut_cache[key] = lut
        return lut

    def lookup_live(self, state: tuple, config: MatchConfig) -> float:
        """
        O(1) lookup for in-play probability.
        state = (sets_a, sets_b, games_a, games_b, pts_a, pts_b, server)
        pts encoding: 0=0, 1=15, 2=30, 3=40, 4=AD_A (adv for A), 3=deuce (3,3)
        Returns P(A wins match from current state).
        """
        lut = self.precompute_lut(config)
        if state in lut:
            return lut[state]
        # If state not in LUT (shouldn't happen for valid states), fall back to MC
        return self._mc_from_state(state, config, 10_000)

    def _mc_from_state(self, state: tuple, config: MatchConfig, n: int) -> float:
        """MC simulation from a given in-game state (point-level)."""
        sa0, sb0, ga0, gb0, pa0, pb0, srv0 = state
        sets_to_win = (config.best_of + 1) // 2
        p_a = config.p_serve_a
        p_b = config.p_serve_b

        sa = np.full(n, sa0, dtype=np.int16)
        sb = np.full(n, sb0, dtype=np.int16)
        ga = np.full(n, ga0, dtype=np.int16)
        gb = np.full(n, gb0, dtype=np.int16)
        pa = np.full(n, pa0, dtype=np.int16)
        pb = np.full(n, pb0, dtype=np.int16)
        srv = np.full(n, srv0, dtype=np.int8)
        active = np.ones(n, dtype=bool)
        wins_a = np.zeros(n, dtype=np.int8)

        for _ in range(800):
            if not active.any():
                break
            act = active
            r = self.rng.random(n)
            p_pt = np.where(srv == 0, p_a, 1.0 - p_b)
            aw = act & (r < p_pt)
            bw = act & ~aw

            pa[aw] += 1
            pb[bw] += 1

            # Resolve game
            adv = act & (pa >= 3) & (pb >= 3)
            norm = act & ~adv

            diff = pa.astype(np.int32) - pb.astype(np.int32)
            ga_wins = (norm & (pa >= 4)) | (adv & (diff >= 2))
            gb_wins = (norm & (pb >= 4)) | (adv & (diff <= -2))

            # Update deuce state
            at_d = adv & ~ga_wins & ~gb_wins & (diff == 0)
            at_aa = adv & ~ga_wins & ~gb_wins & (diff == 1)
            at_ab = adv & ~ga_wins & ~gb_wins & (diff == -1)
            pa[at_d] = 3; pb[at_d] = 3
            pa[at_aa] = 4; pb[at_aa] = 3
            pa[at_ab] = 3; pb[at_ab] = 4

            gd = ga_wins | gb_wins
            pa[gd] = 0; pb[gd] = 0
            ga[ga_wins] += 1; gb[gb_wins] += 1
            srv[gd] ^= 1

            # Resolve set
            sa_win = gd & (((ga >= 6) & (ga - gb >= 2)) | ((ga == 7) & (gb == 6)))
            sb_win = gd & (((gb >= 6) & (gb - ga >= 2)) | ((gb == 7) & (ga == 6)))
            sd = sa_win | sb_win
            sa[sa_win] += 1; sb[sb_win] += 1
            ga[sd] = 0; gb[sd] = 0

            ma = act & (sa >= sets_to_win)
            mb = act & (sb >= sets_to_win)
            wins_a[ma] = 1
            active[ma | mb] = False

        return float(wins_a.mean())

    # ------------------------------------------------------------------
    # Market analysis
    # ------------------------------------------------------------------

    def expected_value_total_games(
        self, config: MatchConfig, bk_line: float, bk_over_odds: float, bk_under_odds: float
    ) -> dict:
        """
        Scanner dla rynku Total Games.
        Returns: {our_expected: float, bk_line: float, diff: float,
                  over_ev: float, under_ev: float, signal: bool}
        """
        data = self._simulate_full(config, self.n_simulations)
        total_games = data['total_games']
        our_exp = float(total_games.mean())

        p_over = float((total_games > bk_line).mean())
        p_under = float((total_games <= bk_line).mean())

        over_ev = p_over * (bk_over_odds - 1) - p_under
        under_ev = p_under * (bk_under_odds - 1) - p_over
        signal = over_ev > 0.03 or under_ev > 0.03

        return {
            'our_expected': our_exp,
            'bk_line': bk_line,
            'diff': our_exp - bk_line,
            'over_ev': over_ev,
            'under_ev': under_ev,
            'signal': signal,
        }

    def tiebreak_probability(self, config: MatchConfig) -> float:
        """P(at least one tiebreak in match) via MC."""
        result = self.simulate_match(config)
        return result.p_tiebreak_any
