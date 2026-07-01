"""
betatp.io — Training Framework v23→v40
=======================================
NOWE MODELE: Multi-target predictions (nie tylko winner/loser)
  v23 — P(total_games > X) — model over/under gemów
  v24 — P(n_sets = 3,4,5) — model liczby setów (multinomial)  
  v25 — P(game_diff > X) — model handicapu gemowego
  v26 — P(tie_break w meczu) — model tie-breaków
  v27 — P(set1_winner = match_winner) — 1st set predictor
  v28 — Combined: all targets stacked → meta-ensemble
  v29 — Surface-specific total_games (oddzielny model per nawierzchnia)
  v30 — Serve dominance → total_games predictor
  v31 — Fatigue → n_sets predictor (zmęczony gracz = więcej setów)
  v32 — H2H closeness → over/under predictor
  v33 — Weather impact on game length
  v34 — Elo diff × surface → game_diff predictor
  v35 — Market-calibrated n_sets (użyj kursów Pinnacle jako feature)
  v36 — LightGBM regression: total_games bezpośrednio (nie classification)
  v37 — LightGBM regression: game_diff bezpośrednio
  v38 — Quantile regression: P(total_games percentile)
  v39 — Deep feature cross: all interactions × target stacked
  v40 — CHAMPION multi-target: best arch per target + calibration

Uruchomienie:
  python scripts/train_v23_v40.py --versions 23,24,25
  python scripts/train_v23_v40.py --versions all
  python scripts/train_v23_v40.py --versions 23-40
"""

import sys, os, json, warnings, argparse, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import deque
from sklearn.metrics import (roc_auc_score, brier_score_loss, mean_squared_error,
                             mean_absolute_error, log_loss)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
import lightgbm as lgb

# ─── CONFIG ───────────────────────────────────────────────────────────────────
MODELS_PATH = Path("/home/ubuntu/betatp/models")
DATA_PATH   = Path("/home/ubuntu/betatp/data")
ODDS_PAR    = DATA_PATH / "matches_with_odds.parquet"
WFEAT_PAR   = DATA_PATH / "weather_features.parquet"
RESULTS_F   = MODELS_PATH / "versions_v23_v40_results.json"
MODELS_PATH.mkdir(exist_ok=True)

HOLDOUT_START = 2024
WF_SPLITS = [
    (2004, 2014, 2017),
    (2004, 2017, 2020),
    (2004, 2020, 2023),
    (2004, 2023, 2024),
]

LGBM_PARAMS_REG = {
    "objective": "regression", "metric": "rmse",
    "learning_rate": 0.04, "num_leaves": 63,
    "min_child_samples": 30, "subsample": 0.8,
    "colsample_bytree": 0.8, "reg_alpha": 0.1,
    "reg_lambda": 1.0, "n_estimators": 2000,
    "random_state": 42, "n_jobs": -1, "verbose": -1,
}

LGBM_PARAMS_BIN = {
    "objective": "binary", "metric": "auc",
    "learning_rate": 0.04, "num_leaves": 63,
    "min_child_samples": 30, "subsample": 0.8,
    "colsample_bytree": 0.8, "reg_alpha": 0.1,
    "reg_lambda": 1.0, "n_estimators": 2000,
    "random_state": 42, "n_jobs": -1, "verbose": -1,
}

LGBM_PARAMS_MULTI = {
    "objective": "multiclass", "metric": "multi_logloss",
    "num_class": 3,
    "learning_rate": 0.04, "num_leaves": 63,
    "min_child_samples": 30, "subsample": 0.8,
    "colsample_bytree": 0.8, "reg_alpha": 0.1,
    "reg_lambda": 1.0, "n_estimators": 2000,
    "random_state": 42, "n_jobs": -1, "verbose": -1,
}

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── DATA LOADING + SCORE PARSING ─────────────────────────────────────────────

def parse_score(score_str):
    """Parse tennis score → (n_sets, total_games, winner_games, loser_games, n_tiebreaks, sets_detail)"""
    if not isinstance(score_str, str): return None
    if any(x in score_str.upper() for x in ['RET','W/O','DEF','WALKOVER']): return None
    parts = score_str.split()
    sets = []
    n_tb = 0
    for p in parts:
        has_tb = '(' in p
        p_clean = p.split('(')[0]
        if '-' not in p_clean: continue
        try:
            a, b = p_clean.split('-')
            a, b = int(a), int(b)
            sets.append((a, b))
            if has_tb: n_tb += 1
        except:
            continue
    if not sets: return None
    n_sets = len(sets)
    w_games = sum(s[0] for s in sets)
    l_games = sum(s[1] for s in sets)
    total = w_games + l_games + n_tb  # tie-break gem counts
    game_diff = w_games - l_games
    return {
        'n_sets': n_sets, 'total_games': total,
        'w_games': w_games, 'l_games': l_games,
        'game_diff': game_diff, 'n_tiebreaks': n_tb,
        'sets': sets,
        'set1_winner_won': sets[0][0] > sets[0][1] if sets else None,
    }


def load_full_dataset():
    """Wczytuje dataset z parsowanymi wynikami i features."""
    log("Wczytywanie danych...")
    df = pd.read_parquet(ODDS_PAR)
    # tourney_date is already Timestamp in parquet
    if not pd.api.types.is_datetime64_any_dtype(df["tourney_date"]):
        df["tourney_date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    if "year" not in df.columns or df["year"].isna().all():
        df["year"] = df["tourney_date"].dt.year.fillna(0).astype(int)
    
    # Weather
    if WFEAT_PAR.exists():
        wf = pd.read_parquet(WFEAT_PAR)
        wf_cols = [c for c in wf.columns if c not in ("tourney_name","year")]
        df = df.merge(wf[["tourney_name","year"] + wf_cols], on=["tourney_name","year"],
                     how="left", suffixes=("","_wf"))
    
    # Parse scores
    log("  Parsowanie wyników meczów...")
    parsed = df['score'].apply(parse_score)
    # parse_score returns dict or None — replace None with empty dict for DataFrame
    parsed_clean = parsed.apply(lambda x: x if x is not None else {})
    score_df = pd.DataFrame(parsed_clean.tolist(), index=df.index)
    for col in ['n_sets','total_games','w_games','l_games','game_diff','n_tiebreaks','set1_winner_won']:
        if col in score_df.columns:
            df[col] = score_df[col]
    
    # Odds features
    for col in ['PSW','PSL','B365W','B365L','MaxW','MaxL','AvgW','AvgL']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce')
    
    df['pin_prob_w'] = (1/df['PSW']) / (1/df['PSW'] + 1/df['PSL'])
    df['pin_prob_l'] = 1 - df['pin_prob_w']
    df['pin_log_odds'] = np.log(df['PSW'] / df['PSL']).clip(-5, 5)
    df['b365_prob_w'] = (1/df['B365W']) / (1/df['B365W'] + 1/df['B365L'])
    df['odds_consensus_w'] = df['MaxW'] / df['PSW']
    df['rank_diff'] = (df['winner_rank'] - df['loser_rank']).clip(-500, 500)
    df['rank_ratio'] = np.log1p(df['loser_rank']) - np.log1p(df['winner_rank'])
    df['age_diff'] = df['winner_age'] - df['loser_age']
    
    # Surface encode
    surf_map = {"Hard":0, "Clay":1, "Grass":2, "Carpet":0}
    df['surface_enc'] = df['surface'].map(surf_map).fillna(0).astype(int)
    
    # Best-of indicator
    df['best_of'] = df.get('best_of', 3)
    df['is_bo5'] = (df['best_of'] == 5).astype(int)
    
    # Round encode (distance from final)
    round_map = {'F':1, 'SF':2, 'QF':3, 'R16':4, 'R32':5, 'R64':6, 'R128':7, 'RR':4,
                 '4th Round':4, '3rd Round':5, '2nd Round':6, '1st Round':7}
    df['round_num'] = df.get('round','').map(round_map).fillna(5).astype(int)
    
    # Tourney level
    level_map = {'G':4, 'M':3, 'A':2, 'D':1, 'F':3, 'C':1}
    df['tourney_level_enc'] = df.get('tourney_level','A').map(level_map).fillna(2).astype(int)
    
    valid = df[df['n_sets'].notna() & df['pin_prob_w'].notna()].copy()
    log(f"  Dataset valid: {len(valid):,} meczów | {len(valid.columns)} kolumn")
    log(f"  Score parsed: n_sets range {valid['n_sets'].min():.0f}-{valid['n_sets'].max():.0f}")
    log(f"  Total games: mean={valid['total_games'].mean():.1f} std={valid['total_games'].std():.1f}")
    return valid


def build_features_multi(df):
    """Buduje pełny zestaw features dla multi-target models."""
    log("  Building multi-target features...")
    
    # Serve stats rolling (expanding mean z pre-match)
    df = df.sort_values("tourney_date").reset_index(drop=True)
    
    # Rolling stats per gracz
    player_stats = {}  # pid → deque of dicts
    
    cols_to_build = [
        'ace_rate_w', 'ace_rate_l', 'df_rate_w', 'df_rate_l',
        '1st_won_w', '1st_won_l', '2nd_won_w', '2nd_won_l',
        'hold_pct_w', 'hold_pct_l', 'break_pct_w', 'break_pct_l',
        'avg_game_len_w', 'avg_game_len_l',
        'tb_rate_w', 'tb_rate_l',
    ]
    results = {c: [] for c in cols_to_build}
    
    for idx, row in df.iterrows():
        wid = str(row.get("winner_id",""))
        lid = str(row.get("loser_id",""))
        
        # Pre-match stats
        for pid, suffix in [(wid, '_w'), (lid, '_l')]:
            hist = player_stats.get(pid, deque(maxlen=20))
            if len(hist) >= 3:
                arr = pd.DataFrame(list(hist))
                results[f'ace_rate{suffix}'].append(arr['ace_rate'].mean())
                results[f'df_rate{suffix}'].append(arr['df_rate'].mean())
                results[f'1st_won{suffix}'].append(arr['1st_won'].mean())
                results[f'2nd_won{suffix}'].append(arr['2nd_won'].mean())
                results[f'hold_pct{suffix}'].append(arr['hold_pct'].mean())
                results[f'break_pct{suffix}'].append(arr['break_pct'].mean())
                results[f'avg_game_len{suffix}'].append(arr.get('avg_game_len', pd.Series([30])).mean())
                results[f'tb_rate{suffix}'].append(arr['tb_rate'].mean())
            else:
                for c in cols_to_build:
                    if c.endswith(suffix):
                        results[c].append(np.nan)
        
        # Post-match update
        svpt_w = row.get("w_svpt", 0) or 0
        svpt_l = row.get("l_svpt", 0) or 0
        n_sets = row.get("n_sets", 3)
        total_games = row.get("total_games", 24)
        n_tb = row.get("n_tiebreaks", 0)
        
        def safe_div(a, b):
            a = a if pd.notna(a) else 0
            b = b if pd.notna(b) else 0
            return a/b if b > 0 else np.nan
        
        w_rec = {
            'ace_rate': safe_div(row.get("w_ace",0), svpt_w),
            'df_rate': safe_div(row.get("w_df",0), svpt_w),
            '1st_won': safe_div(row.get("w_1stWon",0), row.get("w_1stIn",0) or 1),
            '2nd_won': safe_div(row.get("w_2ndWon",0), max(1, svpt_w - (row.get("w_1stIn",0) or 0))),
            'hold_pct': safe_div(
                (row.get("w_SvGms",0) or 0) - max(0, (row.get("w_bpFaced",0) or 0) - (row.get("w_bpSaved",0) or 0)),
                row.get("w_SvGms",0) or 1),
            'break_pct': safe_div(
                max(0, (row.get("l_bpFaced",0) or 0) - (row.get("l_bpSaved",0) or 0)),
                row.get("l_bpFaced",0) or 1),
            'avg_game_len': total_games / max(n_sets, 1) if n_sets else 30,
            'tb_rate': n_tb / max(n_sets, 1) if n_sets else 0,
        }
        l_rec = {
            'ace_rate': safe_div(row.get("l_ace",0), svpt_l),
            'df_rate': safe_div(row.get("l_df",0), svpt_l),
            '1st_won': safe_div(row.get("l_1stWon",0), row.get("l_1stIn",0) or 1),
            '2nd_won': safe_div(row.get("l_2ndWon",0), max(1, svpt_l - (row.get("l_1stIn",0) or 0))),
            'hold_pct': safe_div(
                (row.get("l_SvGms",0) or 0) - max(0, (row.get("l_bpFaced",0) or 0) - (row.get("l_bpSaved",0) or 0)),
                row.get("l_SvGms",0) or 1),
            'break_pct': safe_div(
                max(0, (row.get("w_bpFaced",0) or 0) - (row.get("w_bpSaved",0) or 0)),
                row.get("w_bpFaced",0) or 1),
            'avg_game_len': total_games / max(n_sets, 1) if n_sets else 30,
            'tb_rate': n_tb / max(n_sets, 1) if n_sets else 0,
        }
        player_stats.setdefault(wid, deque(maxlen=20)).append(w_rec)
        player_stats.setdefault(lid, deque(maxlen=20)).append(l_rec)
    
    for col, vals in results.items():
        df[col] = vals
    
    # Derived features
    df['serve_dominance_w'] = df['ace_rate_w'] - df['df_rate_w'] + df['1st_won_w']
    df['serve_dominance_l'] = df['ace_rate_l'] - df['df_rate_l'] + df['1st_won_l']
    df['serve_diff'] = df['serve_dominance_w'] - df['serve_dominance_l']
    df['break_diff'] = df['break_pct_w'] - df['break_pct_l']
    df['hold_diff'] = df['hold_pct_w'] - df['hold_pct_l']
    df['combined_serve'] = df['serve_dominance_w'] + df['serve_dominance_l']  # high = serwisowy mecz
    df['combined_break'] = df['break_pct_w'] + df['break_pct_l']  # high = dużo breaków
    df['tb_rate_combined'] = df['tb_rate_w'] + df['tb_rate_l']
    df['avg_game_len_combined'] = (df['avg_game_len_w'] + df['avg_game_len_l']) / 2
    
    log(f"  Built {len(cols_to_build)+8} multi-target features")
    return df


# ─── FEATURE SETS PER TARGET ─────────────────────────────────────────────────

FEATS_BASE = [
    'pin_prob_w', 'pin_log_odds', 'rank_diff', 'rank_ratio',
    'age_diff', 'surface_enc', 'is_bo5', 'round_num', 'tourney_level_enc',
]

FEATS_SERVE = [
    'ace_rate_w', 'ace_rate_l', 'df_rate_w', 'df_rate_l',
    '1st_won_w', '1st_won_l', '2nd_won_w', '2nd_won_l',
    'hold_pct_w', 'hold_pct_l', 'break_pct_w', 'break_pct_l',
    'serve_dominance_w', 'serve_dominance_l', 'serve_diff',
    'break_diff', 'hold_diff',
]

FEATS_GAME_LENGTH = [
    'combined_serve', 'combined_break', 'tb_rate_combined',
    'avg_game_len_w', 'avg_game_len_l', 'avg_game_len_combined',
    'tb_rate_w', 'tb_rate_l',
]

FEATS_WEATHER = [c for c in ['temp_max_mean','rain_days','humidity_mean','wind_max_mean']
                 if True]  # filled at runtime

FEATS_ODDS = ['b365_prob_w', 'odds_consensus_w']

# ─── TRAINING ENGINES ─────────────────────────────────────────────────────────

def train_binary_target(name, df, feat_cols, target_col, target_desc, params=None):
    """Trenuj binary classification (y=0/1) z walk-forward."""
    if params is None: params = LGBM_PARAMS_BIN.copy()
    
    valid = df[df[target_col].notna()].copy()
    train = valid[valid['year'] < HOLDOUT_START]
    hold  = valid[valid['year'] >= HOLDOUT_START]
    
    avail_feats = [f for f in feat_cols if f in valid.columns]
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"TRENING {name} | target={target_col} | {len(avail_feats)} feats | train={len(train):,} | hold={len(hold):,}")
    log(f"  {target_desc}")
    log(f"  Base rate train: {train[target_col].mean():.3f} | hold: {hold[target_col].mean():.3f}")
    
    if len(train) < 500 or len(hold) < 100:
        log(f"  ⚠️ Za mało danych — SKIP")
        return None
    
    # Walk-forward
    wf_results = []
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = train[(train['year'] >= tr_start) & (train['year'] < tr_end)]
        val = train[(train['year'] >= tr_end) & (train['year'] < val_end)]
        if len(tr) < 200 or len(val) < 50: continue
        
        X_tr = tr[avail_feats].fillna(-999)
        y_tr = tr[target_col].astype(int)
        X_val = val[avail_feats].fillna(-999)
        y_val = val[target_col].astype(int)
        
        m = lgb.LGBMClassifier(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(-1)])
        p = m.predict_proba(X_val)[:,1]
        auc = roc_auc_score(y_val, p)
        bs = brier_score_loss(y_val, p)
        wf_results.append({"auc": auc, "bs": bs, "iters": m.best_iteration_})
        log(f"  WF {tr_end}→{val_end}: AUC={auc:.4f}  BS={bs:.4f}  iters={m.best_iteration_}")
    
    if not wf_results:
        log(f"  ⚠️ No valid WF folds — SKIP")
        return None
    
    mean_auc = np.mean([r['auc'] for r in wf_results])
    mean_bs  = np.mean([r['bs'] for r in wf_results])
    log(f"  WF MEAN: AUC={mean_auc:.4f}  BS={mean_bs:.4f}")
    
    # Final model
    X_tr = train[avail_feats].fillna(-999)
    y_tr = train[target_col].astype(int)
    X_ho = hold[avail_feats].fillna(-999)
    y_ho = hold[target_col].astype(int)
    
    n_est = int(np.mean([r['iters'] for r in wf_results]) * 1.1) or 500
    final = lgb.LGBMClassifier(**{**params, "n_estimators": n_est})
    final.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])
    
    p_ho = final.predict_proba(X_ho)[:,1]
    auc_ho = roc_auc_score(y_ho, p_ho)
    bs_ho  = brier_score_loss(y_ho, p_ho)
    log(f"  HOLDOUT: AUC={auc_ho:.4f}  BS={bs_ho:.4f}")
    
    # Feature importance
    fi = pd.Series(final.feature_importances_, index=avail_feats).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    # Save
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(avail_feats, MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = {
        "version": name, "target": target_col, "target_desc": target_desc,
        "trained_at": ts_str, "n_train": len(train), "n_holdout": len(hold),
        "n_features": len(avail_feats), "base_rate_train": round(float(y_tr.mean()), 4),
        "mean_wf_auc": round(mean_auc, 4), "holdout_auc": round(auc_ho, 4),
        "holdout_bs": round(bs_ho, 4), "top_features": fi.head(10).to_dict(),
        "duration_sec": round(time.time() - start, 1),
    }
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib")
    log(f"{'='*60}")
    return meta


def train_regression_target(name, df, feat_cols, target_col, target_desc, params=None):
    """Trenuj regression (continuous target) z walk-forward."""
    if params is None: params = LGBM_PARAMS_REG.copy()
    
    valid = df[df[target_col].notna()].copy()
    train = valid[valid['year'] < HOLDOUT_START]
    hold  = valid[valid['year'] >= HOLDOUT_START]
    
    avail_feats = [f for f in feat_cols if f in valid.columns]
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"TRENING {name} [REG] | target={target_col} | {len(avail_feats)} feats | train={len(train):,} | hold={len(hold):,}")
    log(f"  {target_desc}")
    log(f"  Target stats: mean={train[target_col].mean():.2f} std={train[target_col].std():.2f}")
    
    if len(train) < 500 or len(hold) < 100:
        log(f"  ⚠️ Za mało danych — SKIP")
        return None
    
    # Walk-forward
    wf_results = []
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = train[(train['year'] >= tr_start) & (train['year'] < tr_end)]
        val = train[(train['year'] >= tr_end) & (train['year'] < val_end)]
        if len(tr) < 200 or len(val) < 50: continue
        
        X_tr = tr[avail_feats].fillna(-999)
        y_tr = tr[target_col]
        X_val = val[avail_feats].fillna(-999)
        y_val = val[target_col]
        
        m = lgb.LGBMRegressor(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(-1)])
        p = m.predict(X_val)
        rmse = np.sqrt(mean_squared_error(y_val, p))
        mae  = mean_absolute_error(y_val, p)
        # Correlation as proxy for "predictive power"
        corr = np.corrcoef(y_val, p)[0,1]
        wf_results.append({"rmse": rmse, "mae": mae, "corr": corr, "iters": m.best_iteration_})
        log(f"  WF {tr_end}→{val_end}: RMSE={rmse:.3f}  MAE={mae:.3f}  corr={corr:.4f}  iters={m.best_iteration_}")
    
    if not wf_results:
        log(f"  ⚠️ No valid WF folds — SKIP")
        return None
    
    mean_rmse = np.mean([r['rmse'] for r in wf_results])
    mean_corr = np.mean([r['corr'] for r in wf_results])
    log(f"  WF MEAN: RMSE={mean_rmse:.3f}  corr={mean_corr:.4f}")
    
    # Final model
    X_tr = train[avail_feats].fillna(-999)
    y_tr = train[target_col]
    X_ho = hold[avail_feats].fillna(-999)
    y_ho = hold[target_col]
    
    n_est = int(np.mean([r['iters'] for r in wf_results]) * 1.1) or 500
    final = lgb.LGBMRegressor(**{**params, "n_estimators": n_est})
    final.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])
    
    p_ho = final.predict(X_ho)
    rmse_ho = np.sqrt(mean_squared_error(y_ho, p_ho))
    mae_ho  = mean_absolute_error(y_ho, p_ho)
    corr_ho = np.corrcoef(y_ho, p_ho)[0,1]
    log(f"  HOLDOUT: RMSE={rmse_ho:.3f}  MAE={mae_ho:.3f}  corr={corr_ho:.4f}")
    
    # Feature importance
    fi = pd.Series(final.feature_importances_, index=avail_feats).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    # Save
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(avail_feats, MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = {
        "version": name, "target": target_col, "target_desc": target_desc,
        "type": "regression", "trained_at": ts_str,
        "n_train": len(train), "n_holdout": len(hold), "n_features": len(avail_feats),
        "target_mean": round(float(y_tr.mean()), 2), "target_std": round(float(y_tr.std()), 2),
        "mean_wf_rmse": round(mean_rmse, 3), "mean_wf_corr": round(mean_corr, 4),
        "holdout_rmse": round(rmse_ho, 3), "holdout_corr": round(corr_ho, 4),
        "top_features": fi.head(10).to_dict(),
        "duration_sec": round(time.time() - start, 1),
    }
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib")
    log(f"{'='*60}")
    return meta


def train_multiclass_target(name, df, feat_cols, target_col, n_classes, target_desc, params=None):
    """Trenuj multiclass (3+ klasy) z walk-forward."""
    if params is None: params = {**LGBM_PARAMS_MULTI, "num_class": n_classes}
    
    valid = df[df[target_col].notna()].copy()
    train = valid[valid['year'] < HOLDOUT_START]
    hold  = valid[valid['year'] >= HOLDOUT_START]
    
    avail_feats = [f for f in feat_cols if f in valid.columns]
    
    start = time.time()
    log(f"\n{'='*60}")
    log(f"TRENING {name} [MULTI-{n_classes}] | target={target_col} | {len(avail_feats)} feats | train={len(train):,}")
    log(f"  {target_desc}")
    
    if len(train) < 500 or len(hold) < 100:
        log(f"  ⚠️ Za mało danych — SKIP")
        return None
    
    # Class distribution
    dist = train[target_col].value_counts(normalize=True).sort_index()
    log(f"  Class distribution: {dict(dist.round(3))}")
    
    # Walk-forward
    wf_results = []
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = train[(train['year'] >= tr_start) & (train['year'] < tr_end)]
        val = train[(train['year'] >= tr_end) & (train['year'] < val_end)]
        if len(tr) < 200 or len(val) < 50: continue
        
        X_tr = tr[avail_feats].fillna(-999)
        y_tr = tr[target_col].astype(int)
        X_val = val[avail_feats].fillna(-999)
        y_val = val[target_col].astype(int)
        
        m = lgb.LGBMClassifier(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(-1)])
        p = m.predict_proba(X_val)
        ll = log_loss(y_val, p, labels=list(range(n_classes)))
        # AUC per class (macro)
        aucs = []
        for c in range(n_classes):
            y_bin = (y_val == c).astype(int)
            if y_bin.sum() > 10:
                aucs.append(roc_auc_score(y_bin, p[:, c]))
        macro_auc = np.mean(aucs) if aucs else 0.5
        wf_results.append({"log_loss": ll, "macro_auc": macro_auc, "iters": m.best_iteration_})
        log(f"  WF {tr_end}→{val_end}: LL={ll:.4f}  macroAUC={macro_auc:.4f}  iters={m.best_iteration_}")
    
    if not wf_results:
        return None
    
    mean_ll  = np.mean([r['log_loss'] for r in wf_results])
    mean_auc = np.mean([r['macro_auc'] for r in wf_results])
    log(f"  WF MEAN: LL={mean_ll:.4f}  macroAUC={mean_auc:.4f}")
    
    # Final model
    X_tr = train[avail_feats].fillna(-999)
    y_tr = train[target_col].astype(int)
    X_ho = hold[avail_feats].fillna(-999)
    y_ho = hold[target_col].astype(int)
    
    n_est = int(np.mean([r['iters'] for r in wf_results]) * 1.1) or 500
    final = lgb.LGBMClassifier(**{**params, "n_estimators": n_est})
    final.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])
    
    p_ho = final.predict_proba(X_ho)
    ll_ho = log_loss(y_ho, p_ho, labels=list(range(n_classes)))
    aucs_ho = []
    for c in range(n_classes):
        y_bin = (y_ho == c).astype(int)
        if y_bin.sum() > 10:
            aucs_ho.append(roc_auc_score(y_bin, p_ho[:, c]))
    macro_auc_ho = np.mean(aucs_ho) if aucs_ho else 0.5
    log(f"  HOLDOUT: LL={ll_ho:.4f}  macroAUC={macro_auc_ho:.4f}")
    
    # Feature importance
    fi = pd.Series(final.feature_importances_, index=avail_feats).sort_values(ascending=False)
    log(f"  TOP-5: {', '.join(fi.head(5).index.tolist())}")
    
    # Save
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(final, MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib")
    joblib.dump(avail_feats, MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib")
    
    meta = {
        "version": name, "target": target_col, "target_desc": target_desc,
        "type": "multiclass", "n_classes": n_classes, "trained_at": ts_str,
        "n_train": len(train), "n_holdout": len(hold), "n_features": len(avail_feats),
        "class_dist": dict(dist.round(3)),
        "mean_wf_ll": round(mean_ll, 4), "mean_wf_macro_auc": round(mean_auc, 4),
        "holdout_ll": round(ll_ho, 4), "holdout_macro_auc": round(macro_auc_ho, 4),
        "top_features": fi.head(10).to_dict(),
        "duration_sec": round(time.time() - start, 1),
    }
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"  Zapisano: lgbm_{name}_{ts_str}.joblib")
    log(f"{'='*60}")
    return meta


# ─── VERSION RUNNERS ──────────────────────────────────────────────────────────

def run_v23(df):
    """v23: P(over/under total_games) — multiple thresholds"""
    results = []
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    for threshold in [30.5, 33.5, 36.5, 39.5]:
        col = f"over_{threshold}"
        df[col] = (df['total_games'] > threshold).astype(int)
        meta = train_binary_target(
            f"v23_ou{threshold}", df, feats, col,
            f"Over/Under {threshold} total gemów w meczu")
        if meta: results.append(meta)
    return results

def run_v24(df):
    """v24: P(n_sets) — multinomial (3 klasy: 2-set, 3-set, 4/5-set)"""
    # Map: 2 sety→0, 3 sety→1, 4+ setów→2
    df['n_sets_class'] = df['n_sets'].clip(2, 5).map({2:0, 3:1, 4:2, 5:2}).fillna(1).astype(int)
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    meta = train_multiclass_target(
        "v24_nsets", df, feats, 'n_sets_class', 3,
        "Multinomial: P(2 sety) vs P(3 sety) vs P(4+ setów)")
    return [meta] if meta else []

def run_v25(df):
    """v25: P(game_diff > threshold) — handicap gemowy"""
    results = []
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    for threshold in [3.5, 5.5, 7.5, 9.5]:
        col = f"hcp_gem_{threshold}"
        df[col] = (df['game_diff'] > threshold).astype(int)
        meta = train_binary_target(
            f"v25_hcp{threshold}", df, feats, col,
            f"Handicap gemowy: faworyt wygrywa >{threshold} gemami")
        if meta: results.append(meta)
    return results

def run_v26(df):
    """v26: P(tie-break w meczu)"""
    df['has_tiebreak'] = (df['n_tiebreaks'] > 0).astype(int)
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    meta = train_binary_target(
        "v26_tiebreak", df, feats, 'has_tiebreak',
        "Czy w meczu będzie przynajmniej 1 tie-break?")
    return [meta] if meta else []

def run_v27(df):
    """v27: P(zwycięzca 1 seta = zwycięzca meczu)"""
    df['set1_predicts_match'] = df['set1_winner_won'].astype(float)
    feats = FEATS_BASE + FEATS_SERVE + FEATS_ODDS
    meta = train_binary_target(
        "v27_set1winner", df, feats, 'set1_predicts_match',
        "Czy zwycięzca 1. seta wygrywa mecz?")
    return [meta] if meta else []

def run_v28(df):
    """v28: Stacking — OOF preds z v23-v27 jako features → meta model total_games"""
    # Uproszczone: użyj predykcji z v23 thresholds jako features
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    # Additional: encode previous model scores jako proxy
    meta = train_regression_target(
        "v28_stack_totalgames", df, feats, 'total_games',
        "Stacking ensemble → total_games regression (will be improved with OOF)")
    return [meta] if meta else []

def run_v29(df):
    """v29: Surface-specific total_games (oddzielne modele)"""
    results = []
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    for surf, code in [('Hard', 0), ('Clay', 1), ('Grass', 2)]:
        sub = df[df['surface_enc'] == code].copy()
        if len(sub) < 1000: continue
        meta = train_regression_target(
            f"v29_{surf.lower()}_totalgames", sub, feats, 'total_games',
            f"Surface-specific total_games regression [{surf}]")
        if meta: results.append(meta)
    return results

def run_v30(df):
    """v30: Serve dominance → total_games predictor (serwis dominuje = mniej breaków = mniej gemów)"""
    feats = FEATS_SERVE + FEATS_GAME_LENGTH + ['pin_prob_w','rank_diff','surface_enc','is_bo5','round_num']
    meta = train_regression_target(
        "v30_serve_totalgames", df, feats, 'total_games',
        "Serve-focused: dominacja serwisu → predykcja total gemów")
    return [meta] if meta else []

def run_v31(df):
    """v31: Fatigue → n_sets predictor (zmęczeni gracze = dłuższe mecze?)"""
    # Build fatigue features inline
    df_sorted = df.sort_values('tourney_date').reset_index(drop=True)
    match_hist = {}  # player_id → list of dates
    
    days_rest_w, days_rest_l = [], []
    matches_14d_w, matches_14d_l = [], []
    
    for _, row in df_sorted.iterrows():
        wid = str(row.get("winner_id",""))
        lid = str(row.get("loser_id",""))
        d = row["tourney_date"]
        
        for pid, rest_list, m14d_list in [(wid, days_rest_w, matches_14d_w), 
                                           (lid, days_rest_l, matches_14d_l)]:
            hist = match_hist.get(pid, [])
            if hist:
                last = hist[-1]
                rest_list.append((d - last).days if pd.notna(d) and pd.notna(last) else 7)
                cutoff = d - pd.Timedelta(days=14) if pd.notna(d) else d
                m14d_list.append(sum(1 for h in hist if h >= cutoff))
            else:
                rest_list.append(7)
                m14d_list.append(0)
            match_hist.setdefault(pid, []).append(d)
    
    df_sorted['days_rest_w'] = days_rest_w
    df_sorted['days_rest_l'] = days_rest_l
    df_sorted['matches_14d_w'] = matches_14d_w
    df_sorted['matches_14d_l'] = matches_14d_l
    df_sorted['fatigue_diff'] = df_sorted['matches_14d_w'] - df_sorted['matches_14d_l']
    df_sorted['rest_diff'] = df_sorted['days_rest_w'] - df_sorted['days_rest_l']
    
    feats = FEATS_BASE + FEATS_SERVE + ['days_rest_w','days_rest_l','matches_14d_w','matches_14d_l',
                                          'fatigue_diff','rest_diff'] + FEATS_GAME_LENGTH
    
    # Target: P(5 setów) = long match
    df_sorted['is_5sets'] = (df_sorted['n_sets'] >= 5).astype(int)
    meta = train_binary_target(
        "v31_fatigue_5sets", df_sorted, feats, 'is_5sets',
        "Fatigue-focused: P(mecz idzie do 5 setów)")
    return [meta] if meta else []

def run_v32(df):
    """v32: H2H closeness → over/under (mecze z historią = ciasne?)"""
    # Build H2H features
    df_sorted = df.sort_values('tourney_date').reset_index(drop=True)
    h2h = {}
    h2h_count = []
    h2h_balance = []  # jak wyrównane H2H (close to 0.5 = tight)
    
    for _, row in df_sorted.iterrows():
        wid = str(row.get("winner_id",""))
        lid = str(row.get("loser_id",""))
        key = tuple(sorted([wid, lid]))
        
        hist = h2h.get(key, [])
        h2h_count.append(len(hist))
        if len(hist) >= 2:
            wins_w = sum(1 for _, winner in hist if winner == wid)
            balance = wins_w / len(hist)
            h2h_balance.append(min(balance, 1-balance))  # 0.5 = max balanced
        else:
            h2h_balance.append(0.5)
        
        h2h.setdefault(key, []).append((row['tourney_date'], wid))
    
    df_sorted['h2h_count'] = h2h_count
    df_sorted['h2h_balance'] = h2h_balance
    
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + ['h2h_count','h2h_balance'] + FEATS_ODDS
    
    df_sorted['over_33'] = (df_sorted['total_games'] > 33.5).astype(int)
    meta = train_binary_target(
        "v32_h2h_over33", df_sorted, feats, 'over_33',
        "H2H closeness: wyrównane H2H → więcej gemów?")
    return [meta] if meta else []

def run_v33(df):
    """v33: Weather impact on game length"""
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_WEATHER + FEATS_ODDS
    meta = train_regression_target(
        "v33_weather_games", df, feats, 'total_games',
        "Weather-augmented total_games regression")
    return [meta] if meta else []

def run_v34(df):
    """v34: Elo diff × surface → game_diff predictor"""
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    meta = train_regression_target(
        "v34_gamediff", df, feats, 'game_diff',
        "Elo/rank diff → game difference regression (handicap)")
    return [meta] if meta else []

def run_v35(df):
    """v35: Market-calibrated n_sets (Pinnacle odds as primary feature)"""
    feats = FEATS_BASE + FEATS_ODDS + ['pin_prob_w','pin_log_odds','b365_prob_w','odds_consensus_w',
                                         'surface_enc','is_bo5','round_num','tourney_level_enc']
    # N_sets regression
    meta = train_regression_target(
        "v35_market_nsets", df, feats, 'n_sets',
        "Market-calibrated: Pinnacle odds → expected number of sets")
    return [meta] if meta else []

def run_v36(df):
    """v36: LightGBM regression: total_games directly (full features)"""
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS + FEATS_WEATHER
    meta = train_regression_target(
        "v36_total_games_full", df, feats, 'total_games',
        "Full-feature total_games regression (all available features)")
    return [meta] if meta else []

def run_v37(df):
    """v37: LightGBM regression: game_diff (full features)"""
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS + FEATS_WEATHER
    meta = train_regression_target(
        "v37_game_diff_full", df, feats, 'game_diff',
        "Full-feature game_diff regression (handicap target)")
    return [meta] if meta else []

def run_v38(df):
    """v38: Quantile regression — P(total_games < 30/33/36/39)"""
    results = []
    feats = FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS
    for q_val in [30, 33, 36, 39]:
        col = f"under_{q_val}"
        df[col] = (df['total_games'] <= q_val).astype(int)
        meta = train_binary_target(
            f"v38_under{q_val}", df, feats, col,
            f"Quantile: P(total_games ≤ {q_val})")
        if meta: results.append(meta)
    return results

def run_v39(df):
    """v39: Deep feature crosses: all interactions → stacked targets"""
    # Interaction features
    df['pin_x_serve'] = df['pin_prob_w'] * df.get('combined_serve', 0)
    df['rank_x_tb'] = df['rank_diff'] * df.get('tb_rate_combined', 0)
    df['elo_x_surface'] = df['rank_ratio'] * df['surface_enc']
    df['serve_x_break'] = df.get('serve_diff', 0) * df.get('break_diff', 0)
    df['age_x_fatigue'] = df['age_diff'] * df.get('avg_game_len_combined', 30)
    
    feats = (FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS +
             ['pin_x_serve','rank_x_tb','elo_x_surface','serve_x_break','age_x_fatigue'])
    
    results = []
    # Multi-target: total_games + game_diff + has_tiebreak
    for target, desc in [('total_games', 'Deep crosses → total_games'),
                          ('game_diff', 'Deep crosses → game_diff')]:
        meta = train_regression_target(f"v39_cross_{target}", df, feats, target, desc)
        if meta: results.append(meta)
    
    df['over_33'] = (df['total_games'] > 33.5).astype(int)
    meta = train_binary_target("v39_cross_over33", df, feats, 'over_33',
                               "Deep crosses → P(over 33.5 gems)")
    if meta: results.append(meta)
    return results

def run_v40(df):
    """v40: CHAMPION multi-target — best config per target + Platt calibration"""
    feats = (FEATS_BASE + FEATS_SERVE + FEATS_GAME_LENGTH + FEATS_ODDS + FEATS_WEATHER +
             ['pin_x_serve','rank_x_tb','elo_x_surface','serve_x_break','age_x_fatigue'])
    
    # Ensure interaction features exist
    for col, expr in [
        ('pin_x_serve', lambda: df['pin_prob_w'] * df.get('combined_serve', 0)),
        ('rank_x_tb', lambda: df['rank_diff'] * df.get('tb_rate_combined', 0)),
        ('elo_x_surface', lambda: df['rank_ratio'] * df['surface_enc']),
        ('serve_x_break', lambda: df.get('serve_diff', 0) * df.get('break_diff', 0)),
        ('age_x_fatigue', lambda: df['age_diff'] * df.get('avg_game_len_combined', 30)),
    ]:
        if col not in df.columns:
            df[col] = expr()
    
    results = []
    
    # Tuned params (smaller leaves, more regularization for stability)
    tuned_bin = {**LGBM_PARAMS_BIN, "num_leaves": 47, "min_child_samples": 50,
                 "reg_alpha": 0.3, "reg_lambda": 2.0, "learning_rate": 0.03}
    tuned_reg = {**LGBM_PARAMS_REG, "num_leaves": 47, "min_child_samples": 50,
                 "reg_alpha": 0.3, "reg_lambda": 2.0, "learning_rate": 0.03}
    
    # Over/Under targets
    for threshold in [30.5, 33.5, 36.5]:
        col = f"champ_over_{threshold}"
        df[col] = (df['total_games'] > threshold).astype(int)
        meta = train_binary_target(f"v40_champ_ou{threshold}", df, feats, col,
                                   f"CHAMPION O/U {threshold} gemów (tuned + full feats)",
                                   params=tuned_bin)
        if meta: results.append(meta)
    
    # Game diff regression
    meta = train_regression_target("v40_champ_gamediff", df, feats, 'game_diff',
                                   "CHAMPION game_diff (handicap) — tuned + full feats",
                                   params=tuned_reg)
    if meta: results.append(meta)
    
    # Total games regression
    meta = train_regression_target("v40_champ_totalgames", df, feats, 'total_games',
                                   "CHAMPION total_games regression — tuned + full feats",
                                   params=tuned_reg)
    if meta: results.append(meta)
    
    # Tie-break
    df['has_tb'] = (df['n_tiebreaks'] > 0).astype(int)
    meta = train_binary_target("v40_champ_tiebreak", df, feats, 'has_tb',
                               "CHAMPION tie-break prediction — tuned + full feats",
                               params=tuned_bin)
    if meta: results.append(meta)
    
    return results


# ─── VERSION MAP + RUNNER ─────────────────────────────────────────────────────

VERSION_MAP = {
    23: run_v23, 24: run_v24, 25: run_v25, 26: run_v26,
    27: run_v27, 28: run_v28, 29: run_v29, 30: run_v30,
    31: run_v31, 32: run_v32, 33: run_v33, 34: run_v34,
    35: run_v35, 36: run_v36, 37: run_v37, 38: run_v38,
    39: run_v39, 40: run_v40,
}

def parse_versions(arg):
    if arg == "all": return sorted(VERSION_MAP.keys())
    if "-" in arg:
        lo, hi = arg.split("-"); return list(range(int(lo), int(hi)+1))
    return [int(v) for v in arg.split(",")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", default="23-40")
    args = parser.parse_args()
    
    versions = parse_versions(args.versions)
    log(f"Uruchamiam wersje: {versions}")
    
    # Load and prepare data
    df = load_full_dataset()
    df = build_features_multi(df)
    
    all_results = []
    
    for v in versions:
        fn = VERSION_MAP.get(v)
        if not fn:
            log(f"⚠️ Brak wersji v{v} — skip")
            continue
        
        log(f"\n{'█'*60}")
        log(f"v{v}: {fn.__doc__.strip().split(chr(10))[0] if fn.__doc__ else 'no desc'}")
        log(f"{'█'*60}")
        
        try:
            results = fn(df.copy())
            if results:
                all_results.extend(results)
        except Exception as e:
            log(f"  ❌ ERROR v{v}: {e}")
            import traceback; traceback.print_exc()
    
    # Summary
    log(f"\n{'='*60}")
    log("PODSUMOWANIE WSZYSTKICH WERSJI v23-v40")
    log(f"{'='*60}")
    for r in all_results:
        if r.get('type') == 'regression':
            log(f"  {r['version']:30s} RMSE={r['holdout_rmse']:.3f}  corr={r['holdout_corr']:.4f}  | {r['target_desc'][:50]}")
        elif r.get('type') == 'multiclass':
            log(f"  {r['version']:30s} macroAUC={r['holdout_macro_auc']:.4f}  LL={r['holdout_ll']:.4f}  | {r['target_desc'][:50]}")
        else:
            log(f"  {r['version']:30s} AUC={r['holdout_auc']:.4f}  BS={r['holdout_bs']:.4f}  | {r['target_desc'][:50]}")
    
    # Save results
    with open(RESULTS_F, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log(f"\nZapisano: {RESULTS_F}")
    log(f"{'='*60}")
