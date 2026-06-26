"""
Elo Engine — 6 variants: overall, hard, clay, grass, serve, return.
Spec: AX-03, AX-04, AX-20, ELO-01..ELO-08
"""
from dataclasses import dataclass
from datetime import date
import math

# K-factors (from ELO-02 spec)
K_FACTORS = {"G": 48, "M": 36, "500": 28, "250": 24, "D": 16, "F": 40, "A": 24, "C": 16}
ELO_MEAN = 1500.0
ELO_FLOOR = 1000.0
ELO_CEILING = 2800.0
HALFLIFE_DAYS = 365.0
SURFACE_BLEND_N0 = 30.0
K_SERVE = 24.0
K_RETURN = 24.0

SURFACE_MAP = {
    "hard": "hard",
    "Hard": "hard",
    "HARD": "hard",
    "clay": "clay",
    "Clay": "clay",
    "CLAY": "clay",
    "grass": "grass",
    "Grass": "grass",
    "GRASS": "grass",
}


@dataclass
class PlayerElo:
    player_id: str
    overall: float = 1500.0
    hard: float = 1500.0
    clay: float = 1500.0
    grass: float = 1500.0
    serve: float = 1500.0
    return_elo: float = 1500.0
    n_matches: int = 0
    n_hard: int = 0
    n_clay: int = 0
    n_grass: int = 0
    last_match_date: date | None = None
    is_provisional: bool = True  # True for first 30 matches


class EloEngine:
    def __init__(self):
        self.ratings: dict[str, PlayerElo] = {}

    def get_or_create(self, player_id: str) -> PlayerElo:
        pid = str(player_id)
        if pid not in self.ratings:
            self.ratings[pid] = PlayerElo(player_id=pid)
        return self.ratings[pid]

    def win_probability(self, ra: float, rb: float) -> float:
        """P(A beats B) = 1 / (1 + 10^((Rb-Ra)/400))"""
        return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

    def apply_decay(self, elo: PlayerElo, match_date: date) -> PlayerElo:
        """Exponential decay toward ELO_MEAN with T_half=365 days.
        Modifies ALL 6 elo variants. Returns modified elo."""
        if elo.last_match_date is None:
            return elo
        delta_days = (match_date - elo.last_match_date).days
        if delta_days <= 0:
            return elo
        decay = math.exp(-math.log(2) / HALFLIFE_DAYS * delta_days)
        elo.overall = ELO_MEAN + (elo.overall - ELO_MEAN) * decay
        elo.hard = ELO_MEAN + (elo.hard - ELO_MEAN) * decay
        elo.clay = ELO_MEAN + (elo.clay - ELO_MEAN) * decay
        elo.grass = ELO_MEAN + (elo.grass - ELO_MEAN) * decay
        elo.serve = ELO_MEAN + (elo.serve - ELO_MEAN) * decay
        elo.return_elo = ELO_MEAN + (elo.return_elo - ELO_MEAN) * decay
        return elo

    def surface_blend(self, r_surface: float, r_overall: float, n_surface: int) -> float:
        """alpha = 1 - exp(-n_surface/30); return alpha*r_surface + (1-alpha)*r_overall"""
        alpha = 1.0 - math.exp(-n_surface / SURFACE_BLEND_N0)
        return alpha * r_surface + (1.0 - alpha) * r_overall

    def get_blended_surface_elo(self, player_id: str, surface: str) -> float:
        """Returns blended surface Elo: alpha*surface + (1-alpha)*overall"""
        elo = self.get_or_create(player_id)
        surf = SURFACE_MAP.get(surface, surface.lower())
        if surf == "hard":
            r_surface = elo.hard
            n_surface = elo.n_hard
        elif surf == "clay":
            r_surface = elo.clay
            n_surface = elo.n_clay
        elif surf == "grass":
            r_surface = elo.grass
            n_surface = elo.n_grass
        else:
            return elo.overall
        return self.surface_blend(r_surface, elo.overall, n_surface)

    def k_factor(self, tourney_level: str, n_matches: int) -> float:
        """K from table, *2 if provisional (n_matches < 30)"""
        k = float(K_FACTORS.get(tourney_level, 24))
        if n_matches < 30:
            k *= 2.0
        return k

    def _clamp(self, elo: float) -> float:
        return max(ELO_FLOOR, min(ELO_CEILING, elo))

    def update_match(
        self,
        winner_id: str,
        loser_id: str,
        surface: str,
        tourney_level: str,
        match_date: date,
        w_svpt: int | None = None,
        w_1stWon: int | None = None,
        w_2ndWon: int | None = None,
        l_svpt: int | None = None,
        l_1stWon: int | None = None,
        l_2ndWon: int | None = None,
    ) -> tuple[PlayerElo, PlayerElo]:
        """Update all 6 Elo variants for both players."""
        w = self.get_or_create(winner_id)
        l = self.get_or_create(loser_id)

        # 1. Apply decay
        self.apply_decay(w, match_date)
        self.apply_decay(l, match_date)

        # 2. Compute expected scores (overall)
        e_w = self.win_probability(w.overall, l.overall)
        e_l = 1.0 - e_w

        k_w = self.k_factor(tourney_level, w.n_matches)
        k_l = self.k_factor(tourney_level, l.n_matches)

        # 3. Update overall Elo
        overall_w_before = w.overall
        overall_l_before = l.overall
        w.overall = self._clamp(w.overall + k_w * (1.0 - e_w))
        l.overall = self._clamp(l.overall + k_l * (0.0 - e_l))

        # 4. Update surface Elo
        surf = SURFACE_MAP.get(surface, surface.lower() if surface else "")
        if surf in ("hard", "clay", "grass"):
            if surf == "hard":
                e_w_s = self.win_probability(w.hard, l.hard)
                e_l_s = 1.0 - e_w_s
                w.hard = self._clamp(w.hard + k_w * (1.0 - e_w_s))
                l.hard = self._clamp(l.hard + k_l * (0.0 - e_l_s))
                w.n_hard += 1
                l.n_hard += 1
            elif surf == "clay":
                e_w_s = self.win_probability(w.clay, l.clay)
                e_l_s = 1.0 - e_w_s
                w.clay = self._clamp(w.clay + k_w * (1.0 - e_w_s))
                l.clay = self._clamp(l.clay + k_l * (0.0 - e_l_s))
                w.n_clay += 1
                l.n_clay += 1
            elif surf == "grass":
                e_w_s = self.win_probability(w.grass, l.grass)
                e_l_s = 1.0 - e_w_s
                w.grass = self._clamp(w.grass + k_w * (1.0 - e_w_s))
                l.grass = self._clamp(l.grass + k_l * (0.0 - e_l_s))
                w.n_grass += 1
                l.n_grass += 1

        # 5 & 6. Update serve/return Elo if stats available
        have_w_stats = (w_svpt is not None and w_svpt > 0
                        and w_1stWon is not None and w_2ndWon is not None)
        have_l_stats = (l_svpt is not None and l_svpt > 0
                        and l_1stWon is not None and l_2ndWon is not None)

        if have_w_stats and have_l_stats:
            # Winner's serve win rate
            actual_w_svw = (w_1stWon + w_2ndWon) / w_svpt
            # Loser's serve win rate
            actual_l_svw = (l_1stWon + l_2ndWon) / l_svpt

            # Expected serve win rate via serve Elo
            e_w_svw = self.win_probability(w.serve, l.return_elo)
            e_l_svw = self.win_probability(l.serve, w.return_elo)

            # Serve Elo update
            w.serve = self._clamp(w.serve + K_SERVE * (actual_w_svw - e_w_svw))
            l.serve = self._clamp(l.serve + K_SERVE * (actual_l_svw - e_l_svw))

            # Return Elo update: actual return win = 1 - opponent_svw
            actual_w_rpw = 1.0 - actual_l_svw  # winner's return win rate
            actual_l_rpw = 1.0 - actual_w_svw  # loser's return win rate

            e_w_rpw = 1.0 - e_l_svw  # winner's expected return win
            e_l_rpw = 1.0 - e_w_svw  # loser's expected return win

            w.return_elo = self._clamp(w.return_elo + K_RETURN * (actual_w_rpw - e_w_rpw))
            l.return_elo = self._clamp(l.return_elo + K_RETURN * (actual_l_rpw - e_l_rpw))

        # 7. Increment n_matches, update last_match_date
        w.n_matches += 1
        l.n_matches += 1
        w.last_match_date = match_date
        l.last_match_date = match_date

        # 8. Update is_provisional
        w.is_provisional = w.n_matches < 30
        l.is_provisional = l.n_matches < 30

        return w, l

    def predict_match(
        self, player_a_id: str, player_b_id: str, surface: str
    ) -> dict:
        """
        Returns probabilities and Elo info for a matchup.
        """
        a = self.get_or_create(player_a_id)
        b = self.get_or_create(player_b_id)

        # Overall Elo probability
        p_overall = self.win_probability(a.overall, b.overall)

        # Blended surface Elo probability
        surf_elo_a = self.get_blended_surface_elo(player_a_id, surface)
        surf_elo_b = self.get_blended_surface_elo(player_b_id, surface)
        p_surface = self.win_probability(surf_elo_a, surf_elo_b)

        # Serve/Return matchup: A serve vs B return, B serve vs A return
        # Combined: P(A wins) from serve/return angle
        # A's advantage = serve_a vs return_b, and return_a vs serve_b
        p_a_serve = self.win_probability(a.serve, b.return_elo)
        p_a_return = self.win_probability(a.return_elo, b.serve)
        # Average of both perspectives
        p_serve_return = (p_a_serve + p_a_return) / 2.0

        elo_diff = a.overall - b.overall

        return {
            "p_win_a": p_surface,
            "p_win_a_overall": p_overall,
            "p_win_a_serve_return": p_serve_return,
            "elo_diff": elo_diff,
            "surface_elo_a": surf_elo_a,
            "surface_elo_b": surf_elo_b,
            "serve_elo_a": a.serve,
            "return_elo_a": a.return_elo,
            "serve_elo_b": b.serve,
            "return_elo_b": b.return_elo,
        }
