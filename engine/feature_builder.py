"""
engine/feature_builder.py — Feature builder for atpbet.io champion stack

Extracts 103 features per match from PostgreSQL historical data.
Used by both the coupon generator and the prediction service.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2

from config import PG_DSN

logger = logging.getLogger(__name__)


# ── PostgreSQL connection ──────────────────────────────────────────────────────

def get_conn():
    """Return a fresh psycopg2 connection (close after use)."""
    return psycopg2.connect(PG_DSN)


# ── Player stats from PG ───────────────────────────────────────────────────────

PLAYER_STATS_QUERY = """
    SELECT m.w_ace, m.l_ace, m.w_df, m.l_df,
           m.w_svpt, m.l_svpt,
           m.w_1stin, m.w_1stwon, m.w_2ndwon,
           m.l_1stin, m.l_1stwon, m.l_2ndwon,
           m.w_bpsaved, m.w_bpfaced, m.l_bpsaved, m.l_bpfaced,
           te.surface, m.score, m.best_of, m.winner_id, m.loser_id,
           p_w.full_name AS winner_name, p_l.full_name AS loser_name,
           m.match_date
    FROM matches m
    JOIN tournament_editions te ON m.edition_id = te.edition_id
    JOIN players p_w ON m.winner_id = p_w.player_id
    JOIN players p_l ON m.loser_id = p_l.player_id
    WHERE (p_w.full_name ILIKE %s OR p_l.full_name ILIKE %s)
      AND m.match_date >= '2023-01-01'
    ORDER BY m.match_date DESC
    LIMIT 40
"""

COLS = [
    'ace_w', 'ace_l', 'df_w', 'df_l', 'svpt_w', 'svpt_l',
    '1stIn_w', '1stWon_w', '2ndWon_w', '1stIn_l', '1stWon_l', '2ndWon_l',
    'bpSaved_w', 'bpFaced_w', 'bpSaved_l', 'bpFaced_l',
    'surface', 'score', 'best_of', 'w_id', 'l_id', 'winner_name', 'loser_name',
    'match_date',
]


def get_player_stats(cur, player_name: str) -> dict:
    """
    Fetch rolling serve/return stats for a player (last 40 matches from 2023+).

    Returns a dict of features: ace_rate, hold_pct, 1stWon_pct, etc.
    Uses player's last name for fuzzy ILIKE search.
    """
    last = player_name.split()[-1].rstrip('.')
    cur.execute(PLAYER_STATS_QUERY, (f'%{last}%', f'%{last}%'))
    rows = cur.fetchall()

    if not rows:
        return _default_player_stats()

    df = pd.DataFrame(rows, columns=COLS)

    # Compute rolling stats — player perspective
    ace_rates, df_rates, hold_pcts, first_won_pcts, bp_saved_pcts = [], [], [], [], []

    for _, row in df.iterrows():
        is_winner = player_name.split()[-1].lower() in str(row['winner_name']).lower()
        prefix = 'w' if is_winner else 'l'
        opp_prefix = 'l' if is_winner else 'w'

        svpt = row.get(f'svpt_{prefix}', 0) or 0
        ace = row.get(f'ace_{prefix}', 0) or 0
        df_cnt = row.get(f'df_{prefix}', 0) or 0
        fstin = row.get(f'1stIn_{prefix}', 0) or 0
        fstwon = row.get(f'1stWon_{prefix}', 0) or 0
        sndwon = row.get(f'2ndWon_{prefix}', 0) or 0
        bpfaced = row.get(f'bpFaced_{prefix}', 0) or 0
        bpsaved = row.get(f'bpSaved_{prefix}', 0) or 0

        if svpt > 0:
            ace_rates.append(ace / svpt)
            df_rates.append(df_cnt / svpt)
            first_in = fstin / svpt
            hold_pct = (fstwon + sndwon) / svpt
            hold_pcts.append(hold_pct)
            first_won_pcts.append(fstwon / max(fstin, 1))
        if bpfaced > 0:
            bp_saved_pcts.append(bpsaved / bpfaced)

    def safe_mean(lst):
        return float(np.mean(lst)) if lst else 0.0

    n_matches = len(df)
    n_grass = len(df[df['surface'] == 'Grass'])

    return {
        'n_matches': n_matches,
        'n_grass_matches': n_grass,
        'ace_rate': safe_mean(ace_rates),
        'df_rate': safe_mean(df_rates),
        'hold_pct': safe_mean(hold_pcts),
        'first_won_pct': safe_mean(first_won_pcts),
        'bp_saved_pct': safe_mean(bp_saved_pcts),
    }


def _default_player_stats() -> dict:
    """Fallback stats when no data available (unknown player)."""
    return {
        'n_matches': 0,
        'n_grass_matches': 0,
        'ace_rate': 0.072,
        'df_rate': 0.025,
        'hold_pct': 0.65,
        'first_won_pct': 0.72,
        'bp_saved_pct': 0.60,
    }


# ── Feature vector builder ─────────────────────────────────────────────────────

def build_features(
    player_a_stats: dict,
    player_b_stats: dict,
    elo_a: float,
    elo_b: float,
    surface_elo_a: float,
    surface_elo_b: float,
    odds_a: float,
    odds_b: float,
    surface: str = 'Grass',
    round_num: str = 'R1',
    rank_a: Optional[int] = None,
    rank_b: Optional[int] = None,
    age_a: Optional[float] = None,
    age_b: Optional[float] = None,
) -> np.ndarray:
    """
    Build a 103-element feature vector for a match prediction.

    Feature groups:
        0-9:   Elo features (global + surface)
       10-24:  Serve stats (ace, df, hold, 1st serve) per player
       25-39:  Return stats (break point, bp saved)
       40-49:  Odds features (Pinnacle implied probs, log-odds)
       50-59:  Rank and age
       60-69:  Surface indicators
       70-79:  Tournament features (round, level)
       80-103: Differential features (A - B)
    """

    def _s(val, default=0.0):
        return float(val) if val is not None else default

    # ── Elo ────────────────────────────────────────────────────────────────────
    elo_diff = elo_a - elo_b
    surf_elo_diff = surface_elo_a - surface_elo_b
    elo_prob_a = 1 / (1 + 10 ** (-elo_diff / 400))
    elo_prob_b = 1 - elo_prob_a
    surf_elo_prob_a = 1 / (1 + 10 ** (-surf_elo_diff / 400))

    # ── Odds features ──────────────────────────────────────────────────────────
    pin_prob_a = 1.0 / max(odds_a, 1.01)
    pin_prob_b = 1.0 / max(odds_b, 1.01)
    margin = pin_prob_a + pin_prob_b - 1.0
    pin_prob_a_fair = pin_prob_a / (pin_prob_a + pin_prob_b)
    pin_prob_b_fair = pin_prob_b / (pin_prob_a + pin_prob_b)
    pin_log_odds_a = float(np.log(max(pin_prob_a_fair, 0.01) / max(pin_prob_b_fair, 0.01)))
    pin_log_odds_b = -pin_log_odds_a

    # ── Surface one-hot ────────────────────────────────────────────────────────
    surf_grass = 1.0 if surface == 'Grass' else 0.0
    surf_clay = 1.0 if surface == 'Clay' else 0.0
    surf_hard = 1.0 if surface == 'Hard' else 0.0

    # ── Round encoding ─────────────────────────────────────────────────────────
    round_map = {'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4, 'QF': 5, 'SF': 6, 'F': 7}
    round_enc = float(round_map.get(round_num, 2)) / 7.0

    # ── Rank ───────────────────────────────────────────────────────────────────
    r_a = _s(rank_a, 50) / 200.0
    r_b = _s(rank_b, 50) / 200.0
    rank_diff = r_a - r_b

    # ── Age ────────────────────────────────────────────────────────────────────
    ag_a = _s(age_a, 27) / 40.0
    ag_b = _s(age_b, 27) / 40.0

    # ── Serve stats A ──────────────────────────────────────────────────────────
    ace_a = _s(player_a_stats.get('ace_rate'))
    df_a = _s(player_a_stats.get('df_rate'))
    hold_a = _s(player_a_stats.get('hold_pct'))
    first_a = _s(player_a_stats.get('first_won_pct'))
    bp_sv_a = _s(player_a_stats.get('bp_saved_pct'))

    # ── Serve stats B ──────────────────────────────────────────────────────────
    ace_b = _s(player_b_stats.get('ace_rate'))
    df_b = _s(player_b_stats.get('df_rate'))
    hold_b = _s(player_b_stats.get('hold_pct'))
    first_b = _s(player_b_stats.get('first_won_pct'))
    bp_sv_b = _s(player_b_stats.get('bp_saved_pct'))

    # ── Grass form ─────────────────────────────────────────────────────────────
    n_grass_a = _s(player_a_stats.get('n_grass_matches', 0)) / 50.0
    n_grass_b = _s(player_b_stats.get('n_grass_matches', 0)) / 50.0

    # ── Combined serve dominance ───────────────────────────────────────────────
    combined_serve = (hold_a + hold_b) / 2.0
    ace_diff = ace_a - ace_b
    hold_diff = hold_a - hold_b
    first_diff = first_a - first_b

    # ── Build feature array (103 elements) ─────────────────────────────────────
    features = np.array([
        # [0-9] Elo
        elo_a / 2000.0, elo_b / 2000.0, elo_diff / 400.0,
        surface_elo_a / 2000.0, surface_elo_b / 2000.0, surf_elo_diff / 400.0,
        elo_prob_a, surf_elo_prob_a, elo_prob_a - surf_elo_prob_a,
        (elo_a + elo_b) / 4000.0,

        # [10-19] Serve A
        ace_a, df_a, hold_a, first_a, bp_sv_a,
        ace_b, df_b, hold_b, first_b, bp_sv_b,

        # [20-29] Odds
        pin_prob_a, pin_prob_b, pin_prob_a_fair, pin_prob_b_fair,
        pin_log_odds_a, pin_log_odds_b,
        margin, odds_a / 10.0, odds_b / 10.0,
        (odds_a - odds_b) / 10.0,

        # [30-39] Rank and age
        r_a, r_b, rank_diff, ag_a, ag_b, ag_a - ag_b,
        r_a - r_b, (r_a + r_b) / 2.0, (ag_a + ag_b) / 2.0, 0.0,

        # [40-49] Surface + round
        surf_grass, surf_clay, surf_hard, round_enc,
        n_grass_a, n_grass_b, n_grass_a - n_grass_b,
        0.0, 0.0, 0.0,  # tournament level (placeholder)

        # [50-69] Differentials
        combined_serve, ace_diff, hold_diff, first_diff,
        bp_sv_a - bp_sv_b,
        elo_prob_a - pin_prob_a_fair,       # model vs market divergence
        surf_elo_prob_a - pin_prob_a_fair,
        hold_a * ace_a,                      # serve dominance composite A
        hold_b * ace_b,                      # serve dominance composite B
        (hold_a * ace_a) - (hold_b * ace_b), # composite diff

        # [60-79] Padding / derived
        elo_prob_a * hold_a, elo_prob_b * hold_b,
        elo_prob_a * ace_a, elo_prob_b * ace_b,
        pin_prob_a * hold_a, pin_prob_b * hold_b,
        elo_diff / 200.0, surf_elo_diff / 200.0,
        elo_diff * surf_grass, surf_elo_diff * surf_grass,
        elo_diff * r_a, surf_elo_diff * r_b,
        ace_a * surf_grass, ace_b * surf_grass,
        hold_a * surf_grass, hold_b * surf_grass,
        first_a * surf_grass, first_b * surf_grass,
        bp_sv_a * surf_grass, bp_sv_b * surf_grass,

        # [80-102] Cross-features
        ace_a * elo_prob_a, ace_b * elo_prob_b,
        hold_a * elo_prob_a, hold_b * elo_prob_b,
        first_a * pin_prob_a_fair, first_b * pin_prob_b_fair,
        ace_diff * surf_grass, hold_diff * surf_grass,
        elo_diff * combined_serve,
        pin_log_odds_a * elo_diff / 400.0,
        r_a * ace_a, r_b * ace_b,
        ag_a * hold_a, ag_b * hold_b,
        elo_prob_a ** 2, pin_prob_a_fair ** 2,
        np.sqrt(max(abs(elo_diff), 0)) / 20.0,
        np.sqrt(max(abs(surf_elo_diff), 0)) / 20.0,
        abs(rank_diff), abs(ace_diff), abs(hold_diff),
        round_enc * elo_prob_a, round_enc * pin_prob_a_fair,
        elo_prob_a * pin_prob_a_fair,  # agreement signal
    ], dtype=np.float32)

    # Ensure exactly 103 features
    if len(features) < 103:
        features = np.pad(features, (0, 103 - len(features)))
    elif len(features) > 103:
        features = features[:103]

    features = np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=-1.0)
    return features


def build_features_for_match(
    player_a: str,
    player_b: str,
    surface: str,
    round_num: str,
    odds_a: float,
    odds_b: float,
    conn=None,
) -> tuple[np.ndarray, dict, dict]:
    """
    High-level wrapper: fetch player stats from PG + build feature vector.

    Returns: (features, stats_a, stats_b)
    """
    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    try:
        cur = conn.cursor()
        stats_a = get_player_stats(cur, player_a)
        stats_b = get_player_stats(cur, player_b)
        cur.close()
    finally:
        if close_conn:
            conn.close()

    # Placeholder ELO values (can be updated from player_ratings table)
    elo_a = 1600.0
    elo_b = 1500.0
    surf_elo_a = 1600.0
    surf_elo_b = 1500.0

    features = build_features(
        player_a_stats=stats_a,
        player_b_stats=stats_b,
        elo_a=elo_a,
        elo_b=elo_b,
        surface_elo_a=surf_elo_a,
        surface_elo_b=surf_elo_b,
        odds_a=odds_a,
        odds_b=odds_b,
        surface=surface,
        round_num=round_num,
    )

    return features, stats_a, stats_b
