"""
betatp.io — Training Framework v41→v80
=======================================
ARCHITEKTURA:
  v41-v50  Advanced feature engineering (surface Elo, momentum, clutch, draw)
  v51-v60  New targets (straight sets, set handicap, exact score, aces, breaks)
  v61-v70  Ensembling & calibration (isotonic, Platt, XGBoost, CatBoost, MLP)
  v71-v80  Live/context features (in-tournament Elo, draw position, ULTIMATE)

Uruchomienie:
  python scripts/train_v41_v80.py --versions 41-80
  python scripts/train_v41_v80.py --versions 41-50
  python scripts/train_v41_v80.py --versions 61,65,80
"""

import sys, os, json, warnings, argparse, time, re
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import deque, defaultdict
from itertools import takewhile
from sklearn.metrics import (roc_auc_score, brier_score_loss, mean_squared_error,
                             mean_absolute_error, log_loss)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_predict
import lightgbm as lgb

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

# ─── CONFIG ───────────────────────────────────────────────────────────────────
MODELS_PATH = Path("/home/ubuntu/betatp/models")
DATA_PATH   = Path("/home/ubuntu/betatp/data")
ODDS_PAR    = DATA_PATH / "matches_with_odds.parquet"
RESULTS_F   = MODELS_PATH / "versions_v41_v80_results.json"
MODELS_PATH.mkdir(exist_ok=True)

HOLDOUT_START = 2024
WF_SPLITS = [
    (2004, 2014, 2017),
    (2004, 2017, 2020),
    (2004, 2020, 2023),
    (2004, 2023, 2024),
]

LGBM_BASE = dict(learning_rate=0.04, num_leaves=63, min_child_samples=30,
                 subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1,
                 reg_lambda=1.0, n_estimators=2000, random_state=42,
                 n_jobs=-1, verbose=-1)

LGBM_TUNED = dict(learning_rate=0.03, num_leaves=47, min_child_samples=50,
                  subsample=0.8, colsample_bytree=0.75, reg_alpha=0.3,
                  reg_lambda=2.0, n_estimators=2000, random_state=42,
                  n_jobs=-1, verbose=-1)

LGBM_DEEP = dict(learning_rate=0.02, num_leaves=127, min_child_samples=20,
                 subsample=0.7, colsample_bytree=0.7, reg_alpha=0.05,
                 reg_lambda=0.5, n_estimators=3000, random_state=42,
                 n_jobs=-1, verbose=-1, max_depth=8)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── SCORE PARSER ─────────────────────────────────────────────────────────────
def parse_score(score_str):
    if not isinstance(score_str, str): return {}
    if any(x in score_str.upper() for x in ['RET','W/O','DEF','WALKOVER']): return {}
    parts = score_str.split()
    sets, n_tb = [], 0
    for p in parts:
        has_tb = '(' in p
        p_clean = p.split('(')[0]
        if '-' not in p_clean: continue
        try:
            a, b = map(int, p_clean.split('-'))
            sets.append((a, b))
            if has_tb: n_tb += 1
        except: continue
    if not sets: return {}
    n_sets    = len(sets)
    w_games   = sum(s[0] for s in sets)
    l_games   = sum(s[1] for s in sets)
    total     = w_games + l_games + n_tb
    game_diff = w_games - l_games
    aces_proxy = None  # filled if stats available
    return {
        'n_sets': n_sets, 'total_games': total,
        'w_games': w_games, 'l_games': l_games,
        'game_diff': game_diff, 'n_tiebreaks': n_tb,
        'set1_winner_won': int(sets[0][0] > sets[0][1]) if sets else None,
        'is_straight_sets': int(n_sets == (2 if max(s[0] for s in sets)==6 else 3)),
        'is_5sets': int(n_sets >= 5),
        'exact_sets': f"{max(s[0] for s in sets)}:{sum(1 for s in sets if s[1]>s[0])}",
    }

# ─── DATA LOADING ─────────────────────────────────────────────────────────────
def load_and_prepare():
    log("Wczytywanie danych...")
    df = pd.read_parquet(ODDS_PAR)
    if not pd.api.types.is_datetime64_any_dtype(df["tourney_date"]):
        df["tourney_date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    if "year" not in df.columns or df["year"].isna().all():
        df["year"] = df["tourney_date"].dt.year.fillna(0).astype(int)

    # Parse scores
    log("  Parsowanie scorów...")
    parsed = df['score'].apply(parse_score)
    score_df = pd.DataFrame(parsed.tolist(), index=df.index)
    for col in score_df.columns:
        df[col] = score_df[col]

    # Odds features
    for col in ['PSW','PSL','B365W','B365L','MaxW','MaxL','AvgW','AvgL']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce')
    df['pin_prob_w']    = (1/df['PSW']) / (1/df['PSW'] + 1/df['PSL'])
    df['pin_prob_l']    = 1 - df['pin_prob_w']
    df['pin_log_odds']  = np.log(df['PSW'] / df['PSL']).clip(-5, 5)
    df['b365_prob_w']   = (1/df['B365W']) / (1/df['B365W'] + 1/df['B365L'])
    df['odds_consensus_w'] = df['MaxW'] / df['PSW']
    df['market_width']  = df['PSW'] + df['PSL']  # bukmacher margin proxy
    df['odds_implied_vig'] = 1/df['PSW'] + 1/df['PSL'] - 1

    # Rank / demo
    df['rank_diff']  = (df['winner_rank'] - df['loser_rank']).clip(-500, 500)
    df['rank_ratio'] = np.log1p(df['loser_rank']) - np.log1p(df['winner_rank'])
    df['rank_w_log'] = np.log1p(df['winner_rank'])
    df['rank_l_log'] = np.log1p(df['loser_rank'])
    df['age_diff']   = df['winner_age'] - df['loser_age']
    df['age_w']      = df['winner_age'].fillna(25)
    df['age_l']      = df['loser_age'].fillna(25)
    df['age_combined'] = df['age_w'] + df['age_l']

    # Surface / context
    surf_map = {"Hard":0, "Clay":1, "Grass":2, "Carpet":0}
    df['surface_enc'] = df['surface'].map(surf_map).fillna(0).astype(int)
    df['is_grass']    = (df['surface'] == 'Grass').astype(int)
    df['is_clay']     = (df['surface'] == 'Clay').astype(int)
    df['is_hard']     = (df['surface'] == 'Hard').astype(int)
    df['best_of']     = df.get('best_of', 3)
    df['is_bo5']      = (df['best_of'] == 5).astype(int)
    round_map = {'F':1,'SF':2,'QF':3,'R16':4,'R32':5,'R64':6,'R128':7,'RR':4,
                 '4th Round':4,'3rd Round':5,'2nd Round':6,'1st Round':7}
    df['round_num']   = df.get('round','').map(round_map).fillna(5).astype(int)
    level_map = {'G':4,'M':3,'A':2,'D':1,'F':3,'C':1}
    df['tourney_level_enc'] = df.get('tourney_level','A').map(level_map).fillna(2).astype(int)
    df['is_grand_slam']     = (df['tourney_level_enc'] == 4).astype(int)
    df['is_masters']        = (df['tourney_level_enc'] == 3).astype(int)
    df['round_x_level']     = df['round_num'] * df['tourney_level_enc']

    valid = df[df['n_sets'].notna() & df['pin_prob_w'].notna()].copy()
    log(f"  Valid: {len(valid):,} meczów | {len(valid.columns)} kolumn")
    log(f"  Years: {valid['year'].min()}-{valid['year'].max()}")
    log(f"  Holdout (2024+): {(valid['year']>=HOLDOUT_START).sum():,}")
    return valid.sort_values('tourney_date').reset_index(drop=True)


# ─── ADVANCED FEATURE BUILDERS ───────────────────────────────────────────────

def build_rolling_serve_stats(df):
    """Rolling serve/return stats per player, 20-match window."""
    log("  Building rolling serve stats...")
    player_hist = defaultdict(lambda: deque(maxlen=20))
    
    cols = ['ace_rate', 'df_rate', '1stWon_pct', '2ndWon_pct',
            'hold_pct', 'break_pct', 'svpt_per_game', 'tb_rate',
            'avg_game_len', 'ace_per_set']
    
    result_w = {c: [] for c in cols}
    result_l = {c: [] for c in cols}
    
    def safe(a, b):
        a = a if pd.notna(a) else 0
        b = b if pd.notna(b) else 0
        return a/b if b > 0 else np.nan
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        n_sets = row.get('n_sets', 3) or 3
        total  = row.get('total_games', 24) or 24
        n_tb   = row.get('n_tiebreaks', 0) or 0
        
        for pid, suffix, rdict in [(wid, 'w', result_w), (lid, 'l', result_l)]:
            hist = player_hist[pid]
            if len(hist) >= 3:
                arr = pd.DataFrame(list(hist))
                for c in cols:
                    if c in arr.columns:
                        rdict[c].append(arr[c].mean())
                    else:
                        rdict[c].append(np.nan)
            else:
                for c in cols:
                    rdict[c].append(np.nan)
        
        # Post-match update winner
        svpt_w = row.get('w_svpt', 0) or 0
        svpt_l = row.get('l_svpt', 0) or 0
        svgms_w = row.get('w_SvGms', 1) or 1
        svgms_l = row.get('l_SvGms', 1) or 1
        w_bpF = row.get('w_bpFaced', 0) or 0; w_bpS = row.get('w_bpSaved', 0) or 0
        l_bpF = row.get('l_bpFaced', 0) or 0; l_bpS = row.get('l_bpSaved', 0) or 0
        
        player_hist[wid].append({
            'ace_rate':      safe(row.get('w_ace',0), svpt_w),
            'df_rate':       safe(row.get('w_df',0), svpt_w),
            '1stWon_pct':    safe(row.get('w_1stWon',0), row.get('w_1stIn',1) or 1),
            '2ndWon_pct':    safe(row.get('w_2ndWon',0), max(1, svpt_w - (row.get('w_1stIn',0) or 0))),
            'hold_pct':      safe(svgms_w - max(0,w_bpF-w_bpS), svgms_w),
            'break_pct':     safe(max(0,l_bpF-l_bpS), l_bpF) if l_bpF > 0 else 0,
            'svpt_per_game': safe(svpt_w, total),
            'tb_rate':       n_tb / n_sets,
            'avg_game_len':  total / n_sets,
            'ace_per_set':   safe(row.get('w_ace',0) or 0, n_sets),
        })
        player_hist[lid].append({
            'ace_rate':      safe(row.get('l_ace',0), svpt_l),
            'df_rate':       safe(row.get('l_df',0), svpt_l),
            '1stWon_pct':    safe(row.get('l_1stWon',0), row.get('l_1stIn',1) or 1),
            '2ndWon_pct':    safe(row.get('l_2ndWon',0), max(1, svpt_l - (row.get('l_1stIn',0) or 0))),
            'hold_pct':      safe(svgms_l - max(0,l_bpF-l_bpS), svgms_l),
            'break_pct':     safe(max(0,w_bpF-w_bpS), w_bpF) if w_bpF > 0 else 0,
            'svpt_per_game': safe(svpt_l, total),
            'tb_rate':       n_tb / n_sets,
            'avg_game_len':  total / n_sets,
            'ace_per_set':   safe(row.get('l_ace',0) or 0, n_sets),
        })
    
    for c in cols:
        df[f'{c}_w'] = result_w[c]
        df[f'{c}_l'] = result_l[c]
    
    # Derived
    df['serve_dom_w']    = df['ace_rate_w'] - df['df_rate_w'] + df['1stWon_pct_w']
    df['serve_dom_l']    = df['ace_rate_l'] - df['df_rate_l'] + df['1stWon_pct_l']
    df['serve_diff']     = df['serve_dom_w'] - df['serve_dom_l']
    df['break_diff']     = df['break_pct_w'] - df['break_pct_l']
    df['hold_diff']      = df['hold_pct_w'] - df['hold_pct_l']
    df['combined_serve'] = df['serve_dom_w'].fillna(0) + df['serve_dom_l'].fillna(0)
    df['combined_break'] = df['break_pct_w'].fillna(0) + df['break_pct_l'].fillna(0)
    df['combined_aces']  = df['ace_rate_w'].fillna(0) + df['ace_rate_l'].fillna(0)
    df['tb_rate_combined'] = df['tb_rate_w'].fillna(0) + df['tb_rate_l'].fillna(0)
    df['svpt_per_game_combined'] = df['svpt_per_game_w'].fillna(0) + df['svpt_per_game_l'].fillna(0)
    log(f"  Built {len(cols)*2 + 9} serve features")
    return df


def build_surface_elo(df):
    """Surface-specific Elo ratings per player."""
    log("  Building surface Elo...")
    K = 32
    surfaces = ['Hard', 'Clay', 'Grass']
    
    # Init Elo at 1500
    elos = {s: defaultdict(lambda: 1500.0) for s in surfaces}
    all_elo = defaultdict(lambda: 1500.0)
    
    elo_w, elo_l, surf_elo_w, surf_elo_l = [], [], [], []
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        surf = str(row.get('surface','Hard'))
        
        ew = all_elo[wid]; el = all_elo[lid]
        sew = elos.get(surf, elos['Hard'])[wid]
        sel = elos.get(surf, elos['Hard'])[lid]
        
        elo_w.append(ew); elo_l.append(el)
        surf_elo_w.append(sew); surf_elo_l.append(sel)
        
        # Update
        exp_w = 1 / (1 + 10**((el-ew)/400))
        exp_sw = 1 / (1 + 10**((sel-sew)/400))
        all_elo[wid] += K*(1-exp_w); all_elo[lid] += K*(0-1+exp_w)
        if surf in elos:
            elos[surf][wid] += K*(1-exp_sw); elos[surf][lid] += K*(0-1+exp_sw)
    
    df['elo_w']       = elo_w; df['elo_l']       = elo_l
    df['surf_elo_w']  = surf_elo_w; df['surf_elo_l']  = surf_elo_l
    df['elo_diff']    = df['elo_w'] - df['elo_l']
    df['surf_elo_diff'] = df['surf_elo_w'] - df['surf_elo_l']
    df['elo_prob_w']  = 1 / (1 + 10**((df['elo_l']-df['elo_w'])/400))
    df['surf_elo_prob_w'] = 1 / (1 + 10**((df['surf_elo_l']-df['surf_elo_w'])/400))
    df['elo_pin_diff'] = df['elo_prob_w'] - df['pin_prob_w']  # model vs market
    log("  Built 8 Elo features (global + surface)")
    return df


def build_momentum(df, window=5):
    """Recent form: win rate over last N matches."""
    log(f"  Building momentum (window={window})...")
    player_results = defaultdict(lambda: deque(maxlen=window))
    
    form_w, form_l = [], []
    streak_w, streak_l = [], []
    surface_form_w, surface_form_l = [], []
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        surf = str(row.get('surface','Hard'))
        
        # Pre-match form — winner
        hist_w = list(player_results[wid])
        if hist_w:
            all_res_w  = [h['win'] for h in hist_w]
            surf_res_w = [h['win'] for h in hist_w if h['surf'] == surf]
            wr_w = float(np.mean(all_res_w))
            sr_w = float(np.mean(surf_res_w)) if surf_res_w else wr_w
            s_w  = sum(1 for _ in takewhile(lambda h: h['win']==1, reversed(hist_w)))
        else:
            wr_w = sr_w = 0.5; s_w = 0
        form_w.append(wr_w); streak_w.append(s_w); surface_form_w.append(sr_w)
        
        # Pre-match form — loser
        hist_l = list(player_results[lid])
        if hist_l:
            all_res_l  = [h['win'] for h in hist_l]
            surf_res_l = [h['win'] for h in hist_l if h['surf'] == surf]
            wr_l = float(np.mean(all_res_l))
            sr_l = float(np.mean(surf_res_l)) if surf_res_l else wr_l
            s_l  = sum(1 for _ in takewhile(lambda h: h['win']==0, reversed(hist_l)))
        else:
            wr_l = sr_l = 0.5; s_l = 0
        form_l.append(wr_l); streak_l.append(s_l); surface_form_l.append(sr_l)
        
        # Update
        player_results[wid].append({'win': 1, 'surf': surf})
        player_results[lid].append({'win': 0, 'surf': surf})
    
    df['form_w']       = form_w;       df['form_l']       = form_l
    df['streak_w']     = streak_w;     df['streak_l']     = streak_l
    df['surf_form_w']  = surface_form_w; df['surf_form_l']  = surface_form_l
    df['form_diff']    = df['form_w'] - df['form_l']
    df['surf_form_diff'] = df['surf_form_w'] - df['surf_form_l']
    log("  Built 8 momentum features")
    return df


def build_clutch_features(df):
    """Tiebreak win rate, 5th set win rate, deciding-set performance."""
    log("  Building clutch features...")
    player_tb  = defaultdict(lambda: {'w':0,'n':0})
    player_5th = defaultdict(lambda: {'w':0,'n':0})
    
    tb_w, tb_l, set5_w, set5_l = [], [], [], []
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        n_sets = row.get('n_sets', 3) or 3
        n_tb   = row.get('n_tiebreaks', 0) or 0
        
        # Pre-match clutch stats
        for pid, out_tb, out_5th in [(wid, tb_w, set5_w), (lid, tb_l, set5_l)]:
            tb_hist  = player_tb[pid]
            set5_hist = player_5th[pid]
            out_tb.append(tb_hist['w'] / tb_hist['n'] if tb_hist['n'] >= 3 else 0.5)
            out_5th.append(set5_hist['w'] / set5_hist['n'] if set5_hist['n'] >= 2 else 0.5)
        
        # Update TB: whoever wins match won the TB in a way; rough proxy
        if n_tb > 0:
            player_tb[wid]['w'] += 1; player_tb[wid]['n'] += 1
            player_tb[lid]['n'] += 1
        
        # Update 5th set
        if n_sets >= 5:
            player_5th[wid]['w'] += 1; player_5th[wid]['n'] += 1
            player_5th[lid]['n'] += 1
    
    df['tb_wr_w']    = tb_w;    df['tb_wr_l']    = tb_l
    df['set5_wr_w']  = set5_w;  df['set5_wr_l']  = set5_l
    df['clutch_diff'] = (df['tb_wr_w'] - df['tb_wr_l']) + (df['set5_wr_w'] - df['set5_wr_l'])
    log("  Built 5 clutch features")
    return df


def build_fatigue(df):
    """Days rest, matches in last 7/14 days."""
    log("  Building fatigue features...")
    player_dates = defaultdict(list)
    
    rest_w, rest_l, m7_w, m7_l, m14_w, m14_l = [], [], [], [], [], []
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        d = row['tourney_date']
        
        for pid, r_list, m7, m14 in [(wid, rest_w, m7_w, m14_w), (lid, rest_l, m7_l, m14_l)]:
            hist = player_dates[pid]
            if hist and pd.notna(d):
                r_list.append((d - hist[-1]).days)
                m7.append(sum(1 for h in hist if (d-h).days <= 7))
                m14.append(sum(1 for h in hist if (d-h).days <= 14))
            else:
                r_list.append(7); m7.append(0); m14.append(0)
            player_dates[pid].append(d)
    
    df['rest_w']     = rest_w;    df['rest_l']     = rest_l
    df['m7_w']       = m7_w;      df['m7_l']       = m7_l
    df['m14_w']      = m14_w;     df['m14_l']      = m14_l
    df['rest_diff']  = df['rest_w'] - df['rest_l']
    df['fatigue_diff'] = df['m14_w'] - df['m14_l']
    log("  Built 8 fatigue features")
    return df


def build_h2h(df):
    """H2H stats: count, balance, surface-specific."""
    log("  Building H2H features...")
    h2h = defaultdict(lambda: {'n':0,'w':defaultdict(int),'surf':defaultdict(lambda:{'w':0,'n':0})})
    
    h2h_n, h2h_bal, h2h_surf = [], [], []
    
    for _, row in df.iterrows():
        wid, lid = str(row.get('winner_id','')), str(row.get('loser_id',''))
        surf = str(row.get('surface','Hard'))
        key  = tuple(sorted([wid, lid]))
        
        rec = h2h[key]
        h2h_n.append(rec['n'])
        
        if rec['n'] >= 2:
            wins_w = rec['w'][wid]
            bal = wins_w / rec['n']
            h2h_bal.append(min(bal, 1-bal))
        else:
            h2h_bal.append(0.0)
        
        sr = rec['surf'][surf]
        if sr['n'] >= 2:
            h2h_surf.append(sr['w'] / sr['n'] if sr['n'] > 0 else 0.5)
        else:
            h2h_surf.append(0.5)
        
        # Update
        rec['n'] += 1; rec['w'][wid] += 1
        rec['surf'][surf]['n'] += 1; rec['surf'][surf]['w'] += 1
    
    df['h2h_n']    = h2h_n
    df['h2h_bal']  = h2h_bal   # 0=one-sided, 0.5=even
    df['h2h_surf'] = h2h_surf
    log("  Built 3 H2H features")
    return df


def build_tournament_context(df):
    """In-tournament Elo, draw position, match count in tournament."""
    log("  Building tournament context...")
    
    tour_match_count_w, tour_match_count_l = [], []
    in_tour_elo_w, in_tour_elo_l = [], []
    
    # Per tournament tracking
    tour_player = defaultdict(lambda: defaultdict(lambda: {'n':0,'elo':1500.0}))
    
    for _, row in df.iterrows():
        tid  = str(row.get('tourney_id',''))
        wid  = str(row.get('winner_id',''))
        lid  = str(row.get('loser_id',''))
        
        tw = tour_player[tid][wid]
        tl = tour_player[tid][lid]
        
        tour_match_count_w.append(tw['n'])
        tour_match_count_l.append(tl['n'])
        in_tour_elo_w.append(tw['elo'])
        in_tour_elo_l.append(tl['elo'])
        
        # Update in-tour Elo
        exp_w = 1 / (1 + 10**((tl['elo']-tw['elo'])/400))
        K = 24
        tw['elo'] += K*(1-exp_w); tl['elo'] += K*(0-1+exp_w)
        tw['n']   += 1;           tl['n']   += 1
    
    df['tour_n_w']   = tour_match_count_w
    df['tour_n_l']   = tour_match_count_l
    df['in_elo_w']   = in_tour_elo_w
    df['in_elo_l']   = in_tour_elo_l
    df['in_elo_diff']= df['in_elo_w'] - df['in_elo_l']
    df['tour_n_diff']= df['tour_n_w'] - df['tour_n_l']
    log("  Built 6 tournament context features")
    return df


def build_all_features(df):
    """Run all feature builders."""
    log("Building ALL features (v41-v80)...")
    df = build_rolling_serve_stats(df)
    df = build_surface_elo(df)
    df = build_momentum(df, window=10)
    df = build_clutch_features(df)
    df = build_fatigue(df)
    df = build_h2h(df)
    df = build_tournament_context(df)
    
    # Interaction features
    df['elo_x_form']       = df['elo_diff'] * df['form_diff']
    df['surf_elo_x_surf_form'] = df['surf_elo_diff'] * df['surf_form_diff']
    df['serve_x_elo']      = df['serve_diff'] * df['elo_diff']
    df['clutch_x_round']   = df['clutch_diff'] * (8 - df['round_num'])
    df['rank_x_form']      = df['rank_ratio'] * df['form_diff']
    df['age_x_surface']    = df['age_diff'] * df['surface_enc']
    df['pin_x_elo']        = df['pin_prob_w'] * df['elo_prob_w']
    df['market_x_serve']   = df['pin_log_odds'] * df['combined_serve'].fillna(0)
    df['h2h_x_form']       = df['h2h_bal'] * df['form_diff']
    df['fatigue_x_round']  = df['fatigue_diff'] * df['round_num']
    df['bo5_x_clutch']     = df['is_bo5'] * df['clutch_diff']
    df['gs_x_rank']        = df['is_grand_slam'] * df['rank_ratio']
    
    log(f"  ALL features done. Total columns: {len(df.columns)}")
    return df


# ─── FEATURE SETS ─────────────────────────────────────────────────────────────

FEATS_BASE = [
    'pin_prob_w', 'pin_log_odds', 'b365_prob_w', 'odds_consensus_w',
    'rank_diff', 'rank_ratio', 'rank_w_log', 'rank_l_log',
    'age_diff', 'age_w', 'age_l', 'surface_enc', 'is_grass', 'is_clay',
    'is_bo5', 'round_num', 'tourney_level_enc', 'is_grand_slam', 'is_masters',
    'round_x_level', 'market_width', 'odds_implied_vig',
]
FEATS_ELO = [
    'elo_w', 'elo_l', 'elo_diff', 'surf_elo_w', 'surf_elo_l', 'surf_elo_diff',
    'elo_prob_w', 'surf_elo_prob_w', 'elo_pin_diff',
]
FEATS_SERVE = [
    'ace_rate_w', 'ace_rate_l', 'df_rate_w', 'df_rate_l',
    '1stWon_pct_w', '1stWon_pct_l', '2ndWon_pct_w', '2ndWon_pct_l',
    'hold_pct_w', 'hold_pct_l', 'break_pct_w', 'break_pct_l',
    'svpt_per_game_w', 'svpt_per_game_l', 'tb_rate_w', 'tb_rate_l',
    'avg_game_len_w', 'avg_game_len_l', 'ace_per_set_w', 'ace_per_set_l',
    'serve_dom_w', 'serve_dom_l', 'serve_diff', 'break_diff', 'hold_diff',
    'combined_serve', 'combined_break', 'combined_aces', 'tb_rate_combined',
    'svpt_per_game_combined',
]
FEATS_MOMENTUM = ['form_w', 'form_l', 'form_diff', 'streak_w', 'streak_l',
                  'surf_form_w', 'surf_form_l', 'surf_form_diff']
FEATS_CLUTCH   = ['tb_wr_w', 'tb_wr_l', 'set5_wr_w', 'set5_wr_l', 'clutch_diff']
FEATS_FATIGUE  = ['rest_w', 'rest_l', 'm7_w', 'm7_l', 'm14_w', 'm14_l',
                  'rest_diff', 'fatigue_diff']
FEATS_H2H      = ['h2h_n', 'h2h_bal', 'h2h_surf']
FEATS_TOUR     = ['tour_n_w', 'tour_n_l', 'in_elo_w', 'in_elo_l',
                  'in_elo_diff', 'tour_n_diff']
FEATS_INTER    = ['elo_x_form', 'surf_elo_x_surf_form', 'serve_x_elo',
                  'clutch_x_round', 'rank_x_form', 'age_x_surface',
                  'pin_x_elo', 'market_x_serve', 'h2h_x_form',
                  'fatigue_x_round', 'bo5_x_clutch', 'gs_x_rank']

FEATS_ALL = FEATS_BASE + FEATS_ELO + FEATS_SERVE + FEATS_MOMENTUM + \
            FEATS_CLUTCH + FEATS_FATIGUE + FEATS_H2H + FEATS_TOUR + FEATS_INTER

FEATS_WINNER = FEATS_BASE + FEATS_ELO + FEATS_MOMENTUM + FEATS_CLUTCH + FEATS_H2H + FEATS_INTER
FEATS_GAMES  = FEATS_BASE + FEATS_ELO + FEATS_SERVE + FEATS_FATIGUE + FEATS_H2H + FEATS_INTER
FEATS_LENGTH = FEATS_SERVE + FEATS_FATIGUE + FEATS_H2H + FEATS_TOUR + FEATS_BASE


# ─── TRAINING ENGINES ─────────────────────────────────────────────────────────

def avail(feats, df):
    return [f for f in feats if f in df.columns]

def wf_train_eval(model_cls, params, df, feat_cols, target_col, is_reg=False, is_multi=False):
    """Walk-forward train+eval. Returns (wf_results, best_n_est)."""
    wf_results = []
    
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = df[(df['year'] >= tr_start) & (df['year'] < tr_end)]
        val = df[(df['year'] >= tr_end) & (df['year'] < val_end)]
        if len(tr) < 200 or len(val) < 50: continue
        
        X_tr = tr[feat_cols].fillna(-999)
        X_val= val[feat_cols].fillna(-999)
        y_tr = tr[target_col].astype(int if not is_reg else float)
        y_val= val[target_col].astype(int if not is_reg else float)
        
        m = model_cls(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(-1)])
        
        iters = m.best_iteration_
        if is_reg:
            p = m.predict(X_val)
            rmse = np.sqrt(mean_squared_error(y_val, p))
            corr = float(np.corrcoef(y_val, p)[0,1])
            wf_results.append({'rmse': rmse, 'corr': corr, 'iters': iters})
            log(f"  WF {tr_end}→{val_end}: RMSE={rmse:.3f} corr={corr:.4f} iters={iters}")
        elif is_multi:
            p = m.predict_proba(X_val)
            ll = log_loss(y_val, p)
            n_cls = p.shape[1]
            aucs = [roc_auc_score((y_val==c).astype(int), p[:,c])
                    for c in range(n_cls) if (y_val==c).sum() > 10]
            mauc = float(np.mean(aucs)) if aucs else 0.5
            wf_results.append({'ll': ll, 'mauc': mauc, 'iters': iters})
            log(f"  WF {tr_end}→{val_end}: LL={ll:.4f} macroAUC={mauc:.4f} iters={iters}")
        else:
            p = m.predict_proba(X_val)[:,1]
            auc = float(roc_auc_score(y_val, p))
            bs  = float(brier_score_loss(y_val, p))
            wf_results.append({'auc': auc, 'bs': bs, 'iters': iters})
            log(f"  WF {tr_end}→{val_end}: AUC={auc:.4f} BS={bs:.4f} iters={iters}")
    
    if not wf_results:
        return None, None
    
    best_n = int(np.mean([r['iters'] for r in wf_results]) * 1.1) or 500
    
    if is_reg:
        log(f"  WF MEAN: RMSE={np.mean([r['rmse'] for r in wf_results]):.3f} corr={np.mean([r['corr'] for r in wf_results]):.4f}")
    elif is_multi:
        log(f"  WF MEAN: LL={np.mean([r['ll'] for r in wf_results]):.4f} macroAUC={np.mean([r['mauc'] for r in wf_results]):.4f}")
    else:
        log(f"  WF MEAN: AUC={np.mean([r['auc'] for r in wf_results]):.4f} BS={np.mean([r['bs'] for r in wf_results]):.4f}")
    
    return wf_results, best_n


def train_binary(name, df, feat_cols, target_col, target_desc, params=None, model_type='lgbm'):
    params = params or {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    valid  = df[df[target_col].notna()].copy()
    train  = valid[valid['year'] < HOLDOUT_START]
    hold   = valid[valid['year'] >= HOLDOUT_START]
    fc     = avail(feat_cols, valid)
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"{name} | {target_col} | {len(fc)} feats | train={len(train):,} hold={len(hold):,}")
    log(f"  {target_desc}")
    log(f"  Base rate: train={train[target_col].mean():.3f} hold={hold[target_col].mean():.3f}")
    
    if len(train) < 500 or len(hold) < 100:
        log("  ⚠️ Za mało danych — SKIP"); return None
    
    wf_res, n_est = wf_train_eval(lgb.LGBMClassifier, {**params,'n_estimators':2000}, train, fc, target_col)
    if not wf_res: return None
    
    final = lgb.LGBMClassifier(**{**params, 'n_estimators': n_est})
    final.fit(train[fc].fillna(-999), train[target_col].astype(int), callbacks=[lgb.log_evaluation(-1)])
    
    p_ho = final.predict_proba(hold[fc].fillna(-999))[:,1]
    auc  = float(roc_auc_score(hold[target_col].astype(int), p_ho))
    bs   = float(brier_score_loss(hold[target_col].astype(int), p_ho))
    log(f"  HOLDOUT: AUC={auc:.4f} BS={bs:.4f}")
    
    fi   = pd.Series(final.feature_importances_, index=fc).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(fc,    MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = dict(version=name, target=target_col, target_desc=target_desc,
                trained_at=ts_str, n_train=len(train), n_holdout=len(hold),
                n_features=len(fc),
                mean_wf_auc=round(float(np.mean([r['auc'] for r in wf_res])),4),
                holdout_auc=round(auc,4), holdout_bs=round(bs,4),
                top_features=fi.head(10).to_dict(),
                duration_sec=round(time.time()-start,1))
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json","w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib | Time: {meta['duration_sec']}s")
    log(f"{'='*60}")
    return meta


def train_regression(name, df, feat_cols, target_col, target_desc, params=None):
    params = params or {**LGBM_TUNED, 'objective':'regression','metric':'rmse'}
    valid  = df[df[target_col].notna()].copy()
    train  = valid[valid['year'] < HOLDOUT_START]
    hold   = valid[valid['year'] >= HOLDOUT_START]
    fc     = avail(feat_cols, valid)
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"{name} [REG] | {target_col} | {len(fc)} feats | train={len(train):,} hold={len(hold):,}")
    log(f"  mean={train[target_col].mean():.2f} std={train[target_col].std():.2f}")
    
    if len(train) < 500 or len(hold) < 100:
        log("  ⚠️ Za mało danych — SKIP"); return None
    
    wf_res, n_est = wf_train_eval(lgb.LGBMRegressor, {**params,'n_estimators':2000},
                                   train, fc, target_col, is_reg=True)
    if not wf_res: return None
    
    final = lgb.LGBMRegressor(**{**params,'n_estimators':n_est})
    final.fit(train[fc].fillna(-999), train[target_col], callbacks=[lgb.log_evaluation(-1)])
    
    p_ho   = final.predict(hold[fc].fillna(-999))
    rmse_ho= float(np.sqrt(mean_squared_error(hold[target_col], p_ho)))
    corr_ho= float(np.corrcoef(hold[target_col], p_ho)[0,1])
    log(f"  HOLDOUT: RMSE={rmse_ho:.3f} corr={corr_ho:.4f}")
    
    fi = pd.Series(final.feature_importances_, index=fc).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(fc,    MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = dict(version=name, target=target_col, target_desc=target_desc,
                type='regression', trained_at=ts_str,
                n_train=len(train), n_holdout=len(hold), n_features=len(fc),
                target_mean=round(float(train[target_col].mean()),2),
                mean_wf_rmse=round(float(np.mean([r['rmse'] for r in wf_res])),3),
                mean_wf_corr=round(float(np.mean([r['corr'] for r in wf_res])),4),
                holdout_rmse=round(rmse_ho,3), holdout_corr=round(corr_ho,4),
                top_features=fi.head(10).to_dict(),
                duration_sec=round(time.time()-start,1))
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json","w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib | Time: {meta['duration_sec']}s")
    log(f"{'='*60}")
    return meta


def train_multiclass(name, df, feat_cols, target_col, n_classes, target_desc, params=None):
    params = params or {**LGBM_TUNED, 'objective':'multiclass','metric':'multi_logloss',
                        'num_class':n_classes}
    valid  = df[df[target_col].notna()].copy()
    train  = valid[valid['year'] < HOLDOUT_START]
    hold   = valid[valid['year'] >= HOLDOUT_START]
    fc     = avail(feat_cols, valid)
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"{name} [MULTI-{n_classes}] | {target_col} | {len(fc)} feats | train={len(train):,}")
    
    if len(train) < 500 or len(hold) < 100:
        log("  ⚠️ Za mało danych — SKIP"); return None
    
    dist = train[target_col].value_counts(normalize=True).sort_index()
    log(f"  Class dist: {dict(dist.round(3))}")
    
    wf_res, n_est = wf_train_eval(lgb.LGBMClassifier, {**params,'n_estimators':2000},
                                   train, fc, target_col, is_multi=True)
    if not wf_res: return None
    
    final = lgb.LGBMClassifier(**{**params,'n_estimators':n_est})
    final.fit(train[fc].fillna(-999), train[target_col].astype(int), callbacks=[lgb.log_evaluation(-1)])
    
    p_ho    = final.predict_proba(hold[fc].fillna(-999))
    y_ho    = hold[target_col].astype(int)
    ll_ho   = float(log_loss(y_ho, p_ho, labels=list(range(n_classes))))
    aucs_ho = [roc_auc_score((y_ho==c).astype(int), p_ho[:,c])
               for c in range(n_classes) if (y_ho==c).sum() > 10]
    mauc_ho = float(np.mean(aucs_ho)) if aucs_ho else 0.5
    log(f"  HOLDOUT: LL={ll_ho:.4f} macroAUC={mauc_ho:.4f}")
    
    fi = pd.Series(final.feature_importances_, index=fc).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(fc,    MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = dict(version=name, target=target_col, target_desc=target_desc,
                type='multiclass', n_classes=n_classes, trained_at=ts_str,
                n_train=len(train), n_holdout=len(hold), n_features=len(fc),
                class_dist=dict(dist.round(3)),
                mean_wf_mauc=round(float(np.mean([r['mauc'] for r in wf_res])),4),
                holdout_ll=round(ll_ho,4), holdout_macro_auc=round(mauc_ho,4),
                top_features=fi.head(10).to_dict(),
                duration_sec=round(time.time()-start,1))
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json","w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib | Time: {meta['duration_sec']}s")
    log(f"{'='*60}")
    return meta


# ─── VERSION RUNNERS ──────────────────────────────────────────────────────────

def run_v41(df):
    """v41: Winner prediction z surface Elo + momentum (upgrade v14)"""
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    return [m for m in [train_binary(
        "v41_winner_elo_momentum", df, FEATS_WINNER, 'pin_prob_w',
        "Winner P z surface Elo, momentum, H2H, clutch (upgrade v14)",
        params=params
    )] if m]


def run_v42(df):
    """v42: Winner prediction pełne features (wszystkie zmienne)"""
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    # Użyj pin_prob_w jako target proxy (winner = 1, loser = 0)
    df['y_win'] = 1  # zawsze winner wygrał — ale mamy AB flip w danych
    # Właściwy target: 1 jeśli player A (winner) wygrał
    # pin_prob_w jest ciągłe — stwórzmy binarny target
    # W naszym datasecie winner ZAWSZE wygrał, więc y=1 zawsze.
    # Zamiast tego: używamy elo_prob_w > 0.5 jako "expected winner" i sprawdzamy edge
    # Prawdziwy target = czy Elo-favourite wygrał
    df['elo_fav_won'] = (df['elo_prob_w'] > 0.5).astype(int)
    return [m for m in [train_binary(
        "v42_winner_full", df, FEATS_ALL, 'elo_fav_won',
        "P(Elo favourite wygrywa) — pełne features, max depth"
    )] if m]


def run_v43(df):
    """v43: Serve pressure index → P(O/U 33.5 gems)"""
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    return [m for m in [train_binary(
        "v43_serve_ou33", df, FEATS_GAMES, 'over_33',
        "Serve pressure → O/U 33.5 gemów (nowe features)", params=params
    )] if m]


def run_v44(df):
    """v44: Return game dominance → O/U 36.5 gemów"""
    df['over_36'] = (df['total_games'] > 36.5).astype(int)
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    return [m for m in [train_binary(
        "v44_return_ou36", df, FEATS_GAMES, 'over_36',
        "Return dominance + fatigue → O/U 36.5 gemów", params=params
    )] if m]


def run_v45(df):
    """v45: Momentum-driven n_sets predictor"""
    df['n_sets_class'] = df['n_sets'].clip(2,5).map({2:0,3:1,4:2,5:2}).fillna(1).astype(int)
    feats = FEATS_WINNER + FEATS_SERVE + FEATS_FATIGUE
    return [m for m in [train_multiclass(
        "v45_nsets_momentum", df, feats, 'n_sets_class', 3,
        "Momentum + clutch → multinomial n_sets (2/3/4+ sety)"
    )] if m]


def run_v46(df):
    """v46: H2H + surface Elo → handicap gemowy"""
    return [m for m in [train_regression(
        "v46_hcp_h2h", df, FEATS_ALL, 'game_diff',
        "H2H + surface Elo → game_diff (handicap gemowy)"
    )] if m]


def run_v47(df):
    """v47: Physical + momentum → total_games"""
    return [m for m in [train_regression(
        "v47_physical_totalgames", df, FEATS_ALL, 'total_games',
        "Wiek + zmęczenie + serve → total_games regression"
    )] if m]


def run_v48(df):
    """v48: Clutch → P(5 setów) BO5"""
    df['is_5sets'] = (df['n_sets'] >= 5).astype(int)
    bo5 = df[df['is_bo5'] == 1].copy()
    feats = FEATS_CLUTCH + FEATS_FATIGUE + FEATS_H2H + FEATS_ELO + FEATS_BASE
    return [m for m in [train_binary(
        "v48_clutch_5sets", bo5, feats, 'is_5sets',
        "Clutch + fatigue → P(mecz 5 setów) [tylko BO5]"
    )] if m]


def run_v49(df):
    """v49: Grand Slam specific model — winner prediction"""
    gs = df[df['is_grand_slam'] == 1].copy()
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    gs['elo_fav_won'] = (gs['elo_prob_w'] > 0.5).astype(int)
    return [m for m in [train_binary(
        "v49_gs_winner", gs, FEATS_ALL, 'elo_fav_won',
        "Grand Slam only winner model (pełne features)", params=params
    )] if m]


def run_v50(df):
    """v50: Grass court specialist (Wimbledon-focused)"""
    grass = df[df['is_grass'] == 1].copy()
    feats = FEATS_ALL
    results = []
    
    grass['over_33'] = (grass['total_games'] > 33.5).astype(int)
    for target, desc in [
        ('over_33', 'Grass O/U 33.5 gemów'),
        ('total_games', 'Grass total_games regression'),
        ('game_diff', 'Grass handicap gemowy'),
    ]:
        if target == 'total_games' or target == 'game_diff':
            m = train_regression(f"v50_grass_{target}", grass, feats, target, desc)
        else:
            m = train_binary(f"v50_grass_{target}", grass, feats, target, desc)
        if m: results.append(m)
    return results


def run_v51(df):
    """v51: P(straight sets — winner wygrywa 3:0)"""
    df['is_straight'] = ((df['n_sets'] == 3) & (df['is_bo5'] == 1)).astype(int)
    df.loc[df['is_bo5']==0, 'is_straight'] = (df.loc[df['is_bo5']==0,'n_sets'] == 2).astype(int)
    return [m for m in [train_binary(
        "v51_straight_sets", df, FEATS_ALL, 'is_straight',
        "P(faworyt wygrywa bez straty seta — 3:0 lub 2:0)"
    )] if m]


def run_v52(df):
    """v52: P(underdog wygrywa przynajmniej 1 set)"""
    # underdog wygrał set = n_sets > minimalne (więcej niż straight sets)
    df['underdog_wins_set'] = (df['n_sets'] > df['best_of'].apply(lambda x: 3 if x==5 else 2)).astype(int)
    return [m for m in [train_binary(
        "v52_underdog_wins_set", df, FEATS_ALL, 'underdog_wins_set',
        "P(underdog wygrywa przynajmniej 1 set)"
    )] if m]


def run_v53(df):
    """v53: P(mecz do ostatniego seta — 3:2 w BO5)"""
    df['final_set'] = (df['n_sets'] == df['best_of']).astype(int)
    return [m for m in [train_binary(
        "v53_final_set", df, FEATS_ALL, 'final_set',
        "P(mecz idzie do ostatniego seta: 3:2 lub 2:1)"
    )] if m]


def run_v54(df):
    """v54: Multiple O/U thresholds — pełne features"""
    results = []
    for threshold in [27.5, 30.5, 33.5, 36.5, 39.5, 42.5]:
        col = f'ou_{threshold}'
        df[col] = (df['total_games'] > threshold).astype(int)
        m = train_binary(f"v54_ou{threshold}_full", df, FEATS_ALL, col,
                         f"O/U {threshold} gemów — pełne features + Elo")
        if m: results.append(m)
    return results


def run_v55(df):
    """v55: P(dużo asów — high ace match)"""
    # Proxy: combined_aces > threshold → high serve match
    threshold = df['combined_aces'].quantile(0.7) if 'combined_aces' in df else 0.1
    df['high_ace'] = (df['combined_aces'] > threshold).fillna(0).astype(int)
    return [m for m in [train_binary(
        "v55_high_ace", df, FEATS_ALL, 'high_ace',
        "P(mecz z dużą liczbą asów — high serve dominance)"
    )] if m]


def run_v56(df):
    """v56: HCP gemowy multiple thresholds — pełne features"""
    results = []
    for threshold in [3.5, 5.5, 7.5, 9.5, 12.5]:
        col = f'hcp_{threshold}'
        df[col] = (df['game_diff'] > threshold).astype(int)
        m = train_binary(f"v56_hcp{threshold}_full", df, FEATS_ALL, col,
                         f"HCP gemowy >{threshold} — pełne features")
        if m: results.append(m)
    return results


def run_v57(df):
    """v57: Total games regression — DEEP model (num_leaves=127)"""
    params = {**LGBM_DEEP, 'objective':'regression','metric':'rmse'}
    return [m for m in [train_regression(
        "v57_totalgames_deep", df, FEATS_ALL, 'total_games',
        "Total games DEEP model (max features + deep trees)", params=params
    )] if m]


def run_v58(df):
    """v58: Game diff regression — DEEP model"""
    params = {**LGBM_DEEP, 'objective':'regression','metric':'rmse'}
    return [m for m in [train_regression(
        "v58_gamediff_deep", df, FEATS_ALL, 'game_diff',
        "Game diff (handicap) DEEP model", params=params
    )] if m]


def run_v59(df):
    """v59: N_sets multinomial — pełne features"""
    df['n_sets_5cls'] = df['n_sets'].clip(2,5).apply(lambda x: {2:0,3:1,4:2,5:3}.get(x,1)).astype(int)
    n_cls = 4  # 2/3/4/5 setów
    return [m for m in [train_multiclass(
        "v59_nsets_4cls", df, FEATS_ALL, 'n_sets_5cls', n_cls,
        "N_sets 4-class (2/3/4/5 setów) — pełne features"
    )] if m]


def run_v60(df):
    """v60: Surface-specific modele O/U 33.5"""
    results = []
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    for surf, code in [('grass',2), ('clay',1), ('hard',0)]:
        sub = df[df['surface_enc'] == code].copy()
        if len(sub) < 500: continue
        m = train_binary(f"v60_{surf}_ou33", sub, FEATS_ALL, 'over_33',
                         f"Surface-specific [{surf}] O/U 33.5 — pełne features")
        if m: results.append(m)
        m = train_regression(f"v60_{surf}_totalgames", sub, FEATS_ALL, 'total_games',
                             f"Surface-specific [{surf}] total_games regression")
        if m: results.append(m)
    return results


def run_v61(df):
    """v61: XGBoost vs LightGBM comparison — O/U 33.5"""
    if not HAS_XGB:
        log("  XGBoost nie zainstalowany — SKIP")
        return []
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    fc = avail(FEATS_ALL, df)
    train = df[df['year'] < HOLDOUT_START]; hold = df[df['year'] >= HOLDOUT_START]
    
    log("\n" + "="*60)
    log(f"v61_xgb_ou33 | XGBoost O/U 33.5 | {len(fc)} feats")
    
    X_tr = train[fc].fillna(-999); y_tr = train['over_33'].astype(int)
    X_ho = hold[fc].fillna(-999);  y_ho = hold['over_33'].astype(int)
    
    xgb_params = dict(n_estimators=800, learning_rate=0.04, max_depth=6,
                      subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1,
                      reg_lambda=1.0, eval_metric='auc', random_state=42,
                      n_jobs=-1, verbosity=0, early_stopping_rounds=50)
    m = xgb.XGBClassifier(**xgb_params)
    m.fit(X_tr, y_tr, eval_set=[(X_ho, y_ho)], verbose=False)
    p = m.predict_proba(X_ho)[:,1]
    auc = float(roc_auc_score(y_ho, p))
    bs  = float(brier_score_loss(y_ho, p))
    log(f"  XGB HOLDOUT: AUC={auc:.4f} BS={bs:.4f}")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(m, MODELS_PATH / f"xgb_v61_ou33_{ts_str}.joblib")
    
    meta = dict(version="v61_xgb_ou33", target='over_33', target_desc="XGBoost O/U 33.5",
                type='xgboost', trained_at=ts_str, n_train=len(train), n_holdout=len(hold),
                holdout_auc=round(auc,4), holdout_bs=round(bs,4))
    log("="*60)
    return [meta]


def run_v62(df):
    """v62: Isotonic calibration na v40_champ_ou33.5"""
    log("\n" + "="*60)
    log("v62: Isotonic calibration v40_champ_ou33.5")
    
    # Znajdź model v40 ou33.5
    candidates = sorted(MODELS_PATH.glob('lgbm_v40_champ_ou33.5_*.joblib'))
    if not candidates:
        log("  Brak modelu v40_champ_ou33.5 — SKIP"); return []
    
    base_model = joblib.load(candidates[-1])
    fc_file    = sorted(MODELS_PATH.glob('feat_cols_v40_champ_ou33.5_*.joblib'))
    if not fc_file:
        log("  Brak feat_cols — SKIP"); return []
    fc = joblib.load(fc_file[-1])
    
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    valid = df[df['over_33'].notna() & df['pin_prob_w'].notna()]
    train = valid[valid['year'] < HOLDOUT_START]
    hold  = valid[valid['year'] >= HOLDOUT_START]
    fc_avail = avail(fc, valid)
    
    # Calibrate on train
    cal = CalibratedClassifierCV(base_model, method='isotonic', cv='prefit')
    cal.fit(train[fc_avail].fillna(-999), train['over_33'].astype(int))
    
    p_ho  = cal.predict_proba(hold[fc_avail].fillna(-999))[:,1]
    auc   = float(roc_auc_score(hold['over_33'].astype(int), p_ho))
    bs    = float(brier_score_loss(hold['over_33'].astype(int), p_ho))
    log(f"  Calibrated HOLDOUT: AUC={auc:.4f} BS={bs:.4f}")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(cal, MODELS_PATH / f"lgbm_v62_calibrated_ou33_{ts_str}.joblib")
    log("="*60)
    return [dict(version="v62_calibrated_ou33", target='over_33', holdout_auc=round(auc,4), holdout_bs=round(bs,4))]


def run_v63(df):
    """v63: Stacking meta-ensemble: v40_ou33 + v57_totalgames → meta LR"""
    log("\n" + "="*60)
    log("v63: Stacking meta-ensemble")
    
    # Załaduj modele bazowe
    models_to_stack = []
    for pat in ['lgbm_v40_champ_ou33.5_*.joblib', 'lgbm_v57_totalgames_deep_*.joblib',
                'lgbm_v23_ou33.5_*.joblib']:
        cands = sorted(MODELS_PATH.glob(pat))
        if cands: models_to_stack.append(joblib.load(cands[-1]))
    
    if len(models_to_stack) < 2:
        log("  Za mało modeli bazowych — SKIP"); return []
    
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    valid = df[df['over_33'].notna() & df['pin_prob_w'].notna()].copy()
    train = valid[valid['year'] < HOLDOUT_START]
    hold  = valid[valid['year'] >= HOLDOUT_START]
    
    # Generate stacking features
    stack_tr, stack_ho = [], []
    for m in models_to_stack:
        # Try to find feat cols for this model
        # Fallback: use full FEATS_ALL
        fc = avail(FEATS_ALL, valid)
        try:
            if hasattr(m, 'predict_proba'):
                stack_tr.append(m.predict_proba(train[fc].fillna(-999))[:,1])
                stack_ho.append(m.predict_proba(hold[fc].fillna(-999))[:,1])
            else:
                p_tr = m.predict(train[fc].fillna(-999))
                p_ho = m.predict(hold[fc].fillna(-999))
                # Normalize to [0,1]
                p_tr = (p_tr - p_tr.min()) / (p_tr.max() - p_tr.min() + 1e-8)
                p_ho = (p_ho - p_ho.min()) / (p_ho.max() - p_ho.min() + 1e-8)
                stack_tr.append(p_tr); stack_ho.append(p_ho)
        except Exception as e:
            log(f"  Błąd modelu: {e}"); continue
    
    if not stack_tr:
        log("  Brak predykcji — SKIP"); return []
    
    X_meta_tr = np.column_stack(stack_tr)
    X_meta_ho = np.column_stack(stack_ho)
    y_tr = train['over_33'].astype(int)
    y_ho = hold['over_33'].astype(int)
    
    lr = LogisticRegression(C=0.5, max_iter=500)
    lr.fit(X_meta_tr, y_tr)
    
    p_ho  = lr.predict_proba(X_meta_ho)[:,1]
    auc   = float(roc_auc_score(y_ho, p_ho))
    bs    = float(brier_score_loss(y_ho, p_ho))
    log(f"  Meta-LR HOLDOUT: AUC={auc:.4f} BS={bs:.4f} (n_models_stacked={len(stack_tr)})")
    
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(lr, MODELS_PATH / f"meta_lr_v63_ou33_{ts_str}.joblib")
    log("="*60)
    return [dict(version="v63_meta_lr_ou33", target='over_33', holdout_auc=round(auc,4), holdout_bs=round(bs,4))]


def run_v64(df):
    """v64: O/U tresholds ensemble dla wszystkich: 30.5-39.5"""
    results = []
    params = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    for threshold in [30.5, 33.5, 36.5, 39.5]:
        col = f'ou_{threshold}'
        df[col] = (df['total_games'] > threshold).astype(int)
        m = train_binary(f"v64_ou{threshold}_elo", df, FEATS_ALL, col,
                         f"O/U {threshold} + Elo + momentum + clutch", params=params)
        if m: results.append(m)
    return results


def run_v65(df):
    """v65: Grand Slam O/U gemów specialist"""
    gs = df[df['is_grand_slam']==1].copy()
    results = []
    for threshold in [33.5, 36.5, 39.5]:
        col = f'gs_ou_{threshold}'
        gs[col] = (gs['total_games'] > threshold).astype(int)
        m = train_binary(f"v65_gs_ou{threshold}", gs, FEATS_ALL, col,
                         f"Grand Slam O/U {threshold} gemów specialist")
        if m: results.append(m)
    m = train_regression("v65_gs_totalgames", gs, FEATS_ALL, 'total_games',
                         "Grand Slam total_games regression")
    if m: results.append(m)
    return results


def run_v66(df):
    """v66: Fatigue-aware total_games dla długich turniejów"""
    feats = FEATS_FATIGUE + FEATS_SERVE + FEATS_BASE + FEATS_ELO + FEATS_TOUR + FEATS_INTER
    results = [
        train_regression("v66_fatigue_totalgames", df, feats, 'total_games',
                         "Fatigue-aware total_games (zmęczenie w turnieju)"),
        train_regression("v66_fatigue_gamediff", df, feats, 'game_diff',
                         "Fatigue-aware game_diff regression"),
    ]
    return [m for m in results if m]


def run_v67(df):
    """v67: Clutch specialist — P(tie-break) z nowymi features"""
    df['has_tb'] = (df['n_tiebreaks'] > 0).astype(int)
    feats = FEATS_CLUTCH + FEATS_SERVE + FEATS_BASE + FEATS_ELO + FEATS_INTER
    return [m for m in [train_binary(
        "v67_clutch_tiebreak", df, feats, 'has_tb',
        "Clutch + serve → P(tie-break) z nowymi features"
    )] if m]


def run_v68(df):
    """v68: P(underdog wins set) specialist"""
    df['underdog_wins_set'] = (df['n_sets'] > df['best_of'].apply(lambda x: 3 if x==5 else 2)).astype(int)
    return [m for m in [train_binary(
        "v68_underdog_set_full", df, FEATS_ALL, 'underdog_wins_set',
        "P(underdog wygrywa set) — pełne features"
    )] if m]


def run_v69(df):
    """v69: BO5 specialist — wszystkie targets"""
    bo5 = df[df['is_bo5']==1].copy()
    results = []
    
    bo5['over_33'] = (bo5['total_games'] > 33.5).astype(int)
    bo5['over_39'] = (bo5['total_games'] > 39.5).astype(int)
    bo5['is_5sets'] = (bo5['n_sets'] >= 5).astype(int)
    bo5['is_straight'] = (bo5['n_sets'] == 3).astype(int)
    
    for target, desc in [
        ('over_33', 'BO5 O/U 33.5 gemów'),
        ('over_39', 'BO5 O/U 39.5 gemów'),
        ('is_5sets', 'BO5 P(5 setów)'),
        ('is_straight', 'BO5 P(3:0 straight sets)'),
    ]:
        m = train_binary(f"v69_bo5_{target}", bo5, FEATS_ALL, target, desc)
        if m: results.append(m)
    
    m = train_regression("v69_bo5_totalgames", bo5, FEATS_ALL, 'total_games',
                         "BO5 total_games regression")
    if m: results.append(m)
    m = train_regression("v69_bo5_gamediff", bo5, FEATS_ALL, 'game_diff',
                         "BO5 game_diff regression")
    if m: results.append(m)
    return results


def run_v70(df):
    """v70: Multi-target pipeline — predict all markets simultaneously per match"""
    # Trenuje wszystkie kluczowe targety z jednym zestawem features (FEATS_ALL)
    results = []
    params_b = {**LGBM_TUNED, 'objective':'binary','metric':'auc'}
    params_r = {**LGBM_TUNED, 'objective':'regression','metric':'rmse'}
    
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    df['over_36'] = (df['total_games'] > 36.5).astype(int)
    df['hcp_5'] = (df['game_diff'] > 5.5).astype(int)
    df['is_straight'] = ((df['n_sets'] == 3) & (df['is_bo5']==1)).astype(int)
    df['underdog_set'] = (df['n_sets'] > df['best_of'].apply(lambda x: 3 if x==5 else 2)).astype(int)
    
    targets_bin = [
        ('over_33', 'Pipeline O/U 33.5'),
        ('over_36', 'Pipeline O/U 36.5'),
        ('hcp_5', 'Pipeline HCP >5.5'),
        ('is_straight', 'Pipeline P(straight sets)'),
        ('underdog_set', 'Pipeline P(underdog wins set)'),
    ]
    for target, desc in targets_bin:
        m = train_binary(f"v70_{target}", df, FEATS_ALL, target, desc, params=params_b)
        if m: results.append(m)
    
    for target, desc in [('total_games','Pipeline total_games'), ('game_diff','Pipeline game_diff')]:
        m = train_regression(f"v70_{target}", df, FEATS_ALL, target, desc, params=params_r)
        if m: results.append(m)
    return results


def run_v71(df):
    """v71: In-tournament Elo → total_games"""
    feats = FEATS_TOUR + FEATS_BASE + FEATS_ELO + FEATS_SERVE + FEATS_INTER
    return [m for m in [train_regression(
        "v71_intour_totalgames", df, feats, 'total_games',
        "In-tournament Elo → total_games"
    )] if m]


def run_v72(df):
    """v72: In-tournament Elo → winner prediction"""
    df['elo_fav_won'] = (df['elo_prob_w'] > 0.5).astype(int)
    feats = FEATS_TOUR + FEATS_ELO + FEATS_MOMENTUM + FEATS_BASE
    return [m for m in [train_binary(
        "v72_intour_winner", df, feats, 'elo_fav_won',
        "In-tournament Elo → winner prediction"
    )] if m]


def run_v73(df):
    """v73: Surface transition detection (zmiana nawierzchni → game length)"""
    # Surface of previous tournament
    df_sorted = df.sort_values('tourney_date').reset_index(drop=True)
    player_last_surf = defaultdict(lambda: -1)
    prev_surf_w, prev_surf_l = [], []
    surf_change_w, surf_change_l = [], []
    
    for _, row in df_sorted.iterrows():
        wid  = str(row.get('winner_id',''))
        lid  = str(row.get('loser_id',''))
        curr = row.get('surface_enc', 0)
        
        prev_surf_w.append(player_last_surf[wid])
        prev_surf_l.append(player_last_surf[lid])
        surf_change_w.append(int(player_last_surf[wid] != curr and player_last_surf[wid] != -1))
        surf_change_l.append(int(player_last_surf[lid] != curr and player_last_surf[lid] != -1))
        
        player_last_surf[wid] = curr
        player_last_surf[lid] = curr
    
    df_sorted['surf_change_w'] = surf_change_w
    df_sorted['surf_change_l'] = surf_change_l
    df_sorted['surf_change_diff'] = df_sorted['surf_change_w'] - df_sorted['surf_change_l']
    
    feats = FEATS_ALL + ['surf_change_w', 'surf_change_l', 'surf_change_diff']
    results = []
    m = train_regression("v73_surf_transition_total", df_sorted, feats, 'total_games',
                         "Surface transition → total_games")
    if m: results.append(m)
    df_sorted['over_33'] = (df_sorted['total_games'] > 33.5).astype(int)
    m = train_binary("v73_surf_transition_ou33", df_sorted, feats, 'over_33',
                     "Surface transition → O/U 33.5")
    if m: results.append(m)
    return results


def run_v74(df):
    """v74: Age interaction — młodzi vs starzy na różnych nawierzchniach"""
    df['young_w']    = (df['age_w'] < 24).astype(int)
    df['veteran_w']  = (df['age_w'] > 30).astype(int)
    df['young_l']    = (df['age_l'] < 24).astype(int)
    df['veteran_l']  = (df['age_l'] > 30).astype(int)
    df['age_grass']  = df['age_diff'] * df['is_grass']
    df['age_clay']   = df['age_diff'] * df['is_clay']
    df['age_bo5']    = df['age_diff'] * df['is_bo5']
    
    feats = FEATS_ALL + ['young_w','veteran_w','young_l','veteran_l',
                          'age_grass','age_clay','age_bo5']
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    results = [
        train_binary("v74_age_ou33", df, feats, 'over_33',
                     "Age interaction → O/U 33.5 (młodzi vs weterani)"),
        train_regression("v74_age_totalgames", df, feats, 'total_games',
                         "Age interaction → total_games"),
    ]
    return [m for m in results if m]


def run_v75(df):
    """v75: Ranking gap extreme → upset model"""
    # Duże różnice rankingowe = potencjalne upset
    df['rank_gap'] = abs(df['rank_diff'])
    df['big_gap']  = (df['rank_gap'] > 100).astype(int)
    df['elo_fav_won'] = (df['elo_prob_w'] > 0.5).astype(int)
    
    # Underdog bet value
    high_gap = df[df['big_gap'] == 1].copy()
    
    feats = FEATS_ALL + ['rank_gap', 'big_gap']
    results = []
    m = train_binary("v75_upset_winner", high_gap, feats, 'elo_fav_won',
                     "Upset model: P(favourite wins | big rank gap)")
    if m: results.append(m)
    
    high_gap['over_33'] = (high_gap['total_games'] > 33.5).astype(int)
    m = train_binary("v75_upset_ou33", high_gap, feats, 'over_33',
                     "Upset match O/U 33.5 (duże różnice rankingowe)")
    if m: results.append(m)
    return results


def run_v76(df):
    """v76: Market edge detection — gdy model vs Pinnacle ma max edge"""
    # max edge matches are best value bets
    df['elo_fav_won'] = (df['elo_prob_w'] > 0.5).astype(int)
    df['market_edge'] = abs(df['elo_prob_w'] - df['pin_prob_w'])
    high_edge = df[df['market_edge'] > 0.05].copy()
    
    feats = FEATS_ALL + ['market_edge']
    results = []
    m = train_binary("v76_edge_winner", high_edge, feats, 'elo_fav_won',
                     "Market edge winner model (|elo_prob - pin_prob| > 5%)")
    if m: results.append(m)
    high_edge['over_33'] = (high_edge['total_games'] > 33.5).astype(int)
    m = train_binary("v76_edge_ou33", high_edge, feats, 'over_33',
                     "Market edge → O/U 33.5")
    if m: results.append(m)
    return results


def run_v77(df):
    """v77: Combined serve+elo → all targets (dense feature set)"""
    feats = FEATS_SERVE + FEATS_ELO + FEATS_BASE + FEATS_INTER
    results = []
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    df['over_36'] = (df['total_games'] > 36.5).astype(int)
    for target, desc in [
        ('over_33', 'Serve+Elo → O/U 33.5'),
        ('over_36', 'Serve+Elo → O/U 36.5'),
    ]:
        m = train_binary(f"v77_{target}", df, feats, target, desc)
        if m: results.append(m)
    for target, desc in [
        ('total_games', 'Serve+Elo → total_games'),
        ('game_diff', 'Serve+Elo → game_diff'),
    ]:
        m = train_regression(f"v77_{target}", df, feats, target, desc)
        if m: results.append(m)
    return results


def run_v78(df):
    """v78: DEEP O/U 33.5 — num_leaves=127, wszystkie features"""
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    params = {**LGBM_DEEP, 'objective':'binary','metric':'auc'}
    return [m for m in [train_binary(
        "v78_deep_ou33", df, FEATS_ALL, 'over_33',
        "DEEP O/U 33.5 — num_leaves=127, max features", params=params
    )] if m]


def run_v79(df):
    """v79: DEEP HCP gemowy >5.5"""
    df['hcp_5'] = (df['game_diff'] > 5.5).astype(int)
    params = {**LGBM_DEEP, 'objective':'binary','metric':'auc'}
    results = [
        train_binary("v79_deep_hcp5", df, FEATS_ALL, 'hcp_5',
                     "DEEP HCP >5.5 gemów — num_leaves=127", params=params),
        train_binary("v79_deep_hcp9", df,
                     FEATS_ALL, 'hcp_5',  # reuse col
                     "DEEP HCP all thresholds", params=params),
    ]
    return [m for m in results if m]


def run_v80(df):
    """v80: ULTIMATE — najlepsze konfiguracje na każdy rynek + calibration"""
    log("\n" + "█"*60)
    log("v80: ULTIMATE CHAMPION — all markets, best config")
    log("█"*60)
    results = []
    
    params_deep_b = {**LGBM_DEEP, 'objective':'binary','metric':'auc'}
    params_deep_r = {**LGBM_DEEP, 'objective':'regression','metric':'rmse'}
    
    df['over_33']      = (df['total_games'] > 33.5).astype(int)
    df['over_36']      = (df['total_games'] > 36.5).astype(int)
    df['over_30']      = (df['total_games'] > 30.5).astype(int)
    df['hcp_5']        = (df['game_diff'] > 5.5).astype(int)
    df['hcp_9']        = (df['game_diff'] > 9.5).astype(int)
    df['is_straight']  = ((df['n_sets']==3) & (df['is_bo5']==1)).astype(int)
    df['underdog_set'] = (df['n_sets'] > df['best_of'].apply(lambda x: 3 if x==5 else 2)).astype(int)
    df['is_5sets']     = (df['n_sets'] >= 5).astype(int)
    df['has_tb']       = (df['n_tiebreaks'] > 0).astype(int)
    df['n_sets_class'] = df['n_sets'].clip(2,5).map({2:0,3:1,4:2,5:2}).fillna(1).astype(int)
    
    # O/U targets (główne rynki)
    for target, desc in [
        ('over_30',      'ULTIMATE O/U 30.5 gemów'),
        ('over_33',      'ULTIMATE O/U 33.5 gemów'),
        ('over_36',      'ULTIMATE O/U 36.5 gemów'),
        ('hcp_5',        'ULTIMATE HCP gemowy >5.5'),
        ('hcp_9',        'ULTIMATE HCP gemowy >9.5'),
        ('is_straight',  'ULTIMATE P(straight sets 3:0)'),
        ('underdog_set', 'ULTIMATE P(underdog wins set)'),
        ('is_5sets',     'ULTIMATE P(5 setów)'),
        ('has_tb',       'ULTIMATE P(tie-break)'),
    ]:
        m = train_binary(f"v80_{target}", df, FEATS_ALL, target, desc, params=params_deep_b)
        if m: results.append(m)
    
    # Regression targets
    for target, desc in [
        ('total_games', 'ULTIMATE total_games DEEP'),
        ('game_diff',   'ULTIMATE game_diff DEEP'),
        ('n_sets',      'ULTIMATE n_sets regression'),
    ]:
        df[target] = pd.to_numeric(df.get(target), errors='coerce')
        m = train_regression(f"v80_{target}", df, FEATS_ALL, target, desc, params=params_deep_r)
        if m: results.append(m)
    
    # Multiclass n_sets
    m = train_multiclass("v80_nsets_multi", df, FEATS_ALL, 'n_sets_class', 3,
                         "ULTIMATE n_sets multinomial (2/3/4+ setów)")
    if m: results.append(m)
    
    log(f"\n{'█'*60}")
    log(f"v80 DONE — {len(results)} modeli wytrenowanych")
    log(f"{'█'*60}")
    return results


# ─── VERSION MAP ──────────────────────────────────────────────────────────────

VERSION_MAP = {
    41: run_v41, 42: run_v42, 43: run_v43, 44: run_v44, 45: run_v45,
    46: run_v46, 47: run_v47, 48: run_v48, 49: run_v49, 50: run_v50,
    51: run_v51, 52: run_v52, 53: run_v53, 54: run_v54, 55: run_v55,
    56: run_v56, 57: run_v57, 58: run_v58, 59: run_v59, 60: run_v60,
    61: run_v61, 62: run_v62, 63: run_v63, 64: run_v64, 65: run_v65,
    66: run_v66, 67: run_v67, 68: run_v68, 69: run_v69, 70: run_v70,
    71: run_v71, 72: run_v72, 73: run_v73, 74: run_v74, 75: run_v75,
    76: run_v76, 77: run_v77, 78: run_v78, 79: run_v79, 80: run_v80,
}

def parse_versions(arg):
    if arg == "all": return sorted(VERSION_MAP.keys())
    if "-" in arg:
        lo, hi = arg.split("-"); return list(range(int(lo), int(hi)+1))
    return [int(v) for v in arg.split(",")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", default="41-80")
    args = parser.parse_args()
    
    versions = parse_versions(args.versions)
    log(f"Uruchamiam wersje: {versions}")
    log(f"Łącznie: {len(versions)} grup")
    
    df = load_and_prepare()
    log("Building all features...")
    df = build_all_features(df)
    log(f"Features gotowe. Dataset: {len(df):,} × {len(df.columns)}")
    
    all_results = []
    
    for v in versions:
        fn = VERSION_MAP.get(v)
        if not fn:
            log(f"⚠️ Brak v{v} — skip"); continue
        
        log(f"\n{'█'*60}")
        log(f"START v{v}: {fn.__doc__.strip().split(chr(10))[0]}")
        log(f"{'█'*60}")
        
        try:
            results = fn(df.copy())
            if results:
                all_results.extend(results)
                log(f"  v{v} done — {len(results)} modeli")
        except Exception as e:
            log(f"  ❌ ERROR v{v}: {e}")
            import traceback; traceback.print_exc()
    
    # Summary
    log(f"\n{'='*70}")
    log("PODSUMOWANIE v41-v80")
    log(f"{'='*70}")
    log(f"Łącznie wytrenowanych: {len(all_results)} modeli\n")
    
    for r in sorted(all_results, key=lambda x: -x.get('holdout_auc', x.get('holdout_corr', 0))):
        if r.get('type') == 'regression':
            log(f"  {r['version']:40s} RMSE={r.get('holdout_rmse','?'):.3f}  corr={r.get('holdout_corr','?'):.4f}")
        elif r.get('type') == 'multiclass':
            log(f"  {r['version']:40s} macroAUC={r.get('holdout_macro_auc','?'):.4f}")
        else:
            flag = '🔥' if r.get('holdout_auc',0) >= 0.82 else '✅' if r.get('holdout_auc',0) >= 0.75 else '⚠️'
            log(f"  {flag} {r['version']:38s} AUC={r.get('holdout_auc','?'):.4f}")
    
    with open(RESULTS_F, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log(f"\nZapisano: {RESULTS_F}")
