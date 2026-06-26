"""
betatp.io — Training Framework v5→v22
======================================
Każda wersja testuje konkretną hipotezę.
Wspólna infrastruktura: walk-forward CV, holdout 2024-2026, zapis metadanych.

MAPA WERSJI:
  v5  — +weather features (ERA5: temp/rain/wind/humidity/harsh)
  v6  — +player×weather interaction (jak gracz historycznie radzi w upale/deszczu)
  v7  — +surface×weather interaction terms
  v8  — +fatigue upgrade (dni odpoczynku, podróże, turnieje w 14d)
  v9  — +H2H features (wygrane last-3, surface H2H)
  v10 — +ranking trajectory (rank_delta_90d, trend)
  v11 — +serve dominance index (ace%, df%, 1st_won%)
  v12 — +return game index (break%, return_won%)
  v13 — +momentum (win_streak, ewma_short)
  v14 — +age×surface interaction
  v15 — +draw difficulty (avg rank opponentów)
  v16 — +market consensus divergence (max/avg vs pinnacle spread)
  v17 — feature selection: SHAP top-30 z v16
  v18 — ensemble: LightGBM + LogReg meta (v4 + v5 + v9)
  v19 — XGBoost zamiast LightGBM (porównanie)
  v20 — surface-specific models (4×LightGBM)
  v21 — deep feature engineering: polynomial + ratio features
  v22 — final champion: best arch + best features + calibration

Uruchomienie:
  python scripts/train_versions.py --versions 5,6,7   # konkretne
  python scripts/train_versions.py --versions all     # wszystkie
  python scripts/train_versions.py --versions 5-10    # zakres
"""

import sys, os, json, warnings, argparse, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
import lightgbm as lgb

# ─── CONFIG ───────────────────────────────────────────────────────────────────
MODELS_PATH = Path("/home/ubuntu/betatp/models")
DATA_PATH   = Path("/home/ubuntu/betatp/data")
TML_PATH    = Path("/home/ubuntu/TML-Database")
ODDS_PAR    = DATA_PATH / "matches_with_odds.parquet"
WFEAT_PAR   = DATA_PATH / "weather_features.parquet"
V4_MODEL    = MODELS_PATH / "lgbm_v4_20260625_2011.joblib"
V4_FEATS    = MODELS_PATH / "feat_cols_v4_20260625_2011.joblib"
V4_META     = MODELS_PATH / "model_meta_v4_20260625_2011.json"
RESULTS_F   = MODELS_PATH / "versions_results.json"
MODELS_PATH.mkdir(exist_ok=True)

HOLDOUT_START = 2024
WF_SPLITS = [
    (2004, 2014, 2017),
    (2004, 2017, 2020),
    (2004, 2020, 2023),
    (2004, 2023, 2024),
]

LGBM_PARAMS_BASE = {
    "objective": "binary", "metric": "auc",
    "learning_rate": 0.04, "num_leaves": 63,
    "min_child_samples": 30, "subsample": 0.8,
    "colsample_bytree": 0.8, "reg_alpha": 0.1,
    "reg_lambda": 1.0, "n_estimators": 2000,
    "random_state": 42, "n_jobs": -1,
    "verbose": -1,
}

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── DATA LOADING ─────────────────────────────────────────────────────────────
def load_base():
    """Wczytuje pełny dataset (mecze + odds + weather)"""
    log("Wczytywanie danych...")
    df = pd.read_parquet(ODDS_PAR)
    df["tourney_date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    df["year"] = df["tourney_date"].dt.year.fillna(df["year"]).astype(int)

    # Wczytaj weather features
    wf = pd.read_parquet(WFEAT_PAR)
    wf_cols = [c for c in wf.columns if c not in ("tourney_name","year")]
    df = df.merge(
        wf[["tourney_name","year"] + wf_cols],
        on=["tourney_name","year"],
        how="left",
        suffixes=("","_wf")
    )
    log(f"  Dataset: {len(df):,} meczów | {len(df.columns)} kolumn")
    return df

def load_tml_stats():
    """Wczytuje TML z pełnymi statystykami serwisowymi"""
    dfs = []
    for f in sorted(TML_PATH.glob("[0-9]*.csv")):
        d = pd.read_csv(f, low_memory=False)
        d["year"] = int(f.stem)
        dfs.append(d)
    raw = pd.concat(dfs, ignore_index=True)
    raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    return raw

# ─── FEATURE BUILDERS ─────────────────────────────────────────────────────────

def build_elo(df):
    """Buduje Elo ratings inkrementalnie"""
    elo = {}
    def get_elo(pid): return elo.get(pid, 1500)
    def update_elo(w, l, K=32):
        ew = get_elo(w); el = get_elo(l)
        exp_w = 1/(1 + 10**((el-ew)/400))
        elo[w] = ew + K*(1-exp_w)
        elo[l] = el + K*(0-1+exp_w)

    elo_w, elo_l = [], []
    df_sorted = df.sort_values("tourney_date").reset_index(drop=True)
    for _, row in df_sorted.iterrows():
        wid = row.get("winner_id",""); lid = row.get("loser_id","")
        elo_w.append(get_elo(wid)); elo_l.append(get_elo(lid))
        update_elo(wid, lid)

    df_sorted["elo_w"] = elo_w; df_sorted["elo_l"] = elo_l
    df_sorted["elo_diff"] = df_sorted["elo_w"] - df_sorted["elo_l"]
    return df_sorted

def build_h2h(df):
    """H2H: wygrane last-3 mecze, wygrane na nawierzchni"""
    df = df.sort_values("tourney_date").reset_index(drop=True)
    h2h = {}  # (p1,p2) → list of (date, winner_id, surface)

    h2h_wins_3 = []
    h2h_surf_w = []

    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        surf = str(row.get("surface",""))
        key = tuple(sorted([wid, lid]))

        history = h2h.get(key, [])
        # policz ostatnie 3
        last3 = history[-3:] if len(history) >= 3 else history
        wins_as_w = sum(1 for (_, winner, _) in last3 if winner == wid)
        h2h_wins_3.append(wins_as_w - (len(last3) - wins_as_w))  # delta

        # wygrane na nawierzchni
        surf_hist = [(d,w,s) for d,w,s in history if s == surf]
        surf_wins = sum(1 for (_,w,_) in surf_hist if w == wid)
        surf_total = len(surf_hist)
        h2h_surf_w.append(surf_wins / (surf_total + 1))

        h2h.setdefault(key, []).append((row["tourney_date"], wid, surf))

    df["h2h_wins_delta_3"] = h2h_wins_3
    df["h2h_surf_winrate"]  = h2h_surf_w
    return df

def build_serve_return(df):
    """Serwis + return stats per gracz (rolling 10 meczów)"""
    stats = {}  # player_id → deque(10) of stats

    from collections import deque
    def pct(a, b): return a / b if b and b > 0 else np.nan

    def get_stats(pid, cols):
        hist = stats.get(pid, deque(maxlen=10))
        if not hist: return {c: np.nan for c in cols}
        arr = pd.DataFrame(list(hist))
        return {c: arr[c].mean() for c in cols if c in arr.columns}

    SERVE_COLS = ["ace_pct","df_pct","1st_in_pct","1st_won_pct","2nd_won_pct","hold_pct"]
    RET_COLS   = ["break_pct","ret_won_pct"]

    results = {f"a_{c}": [] for c in SERVE_COLS+RET_COLS}
    results.update({f"b_{c}": [] for c in SERVE_COLS+RET_COLS})

    df_sorted = df.sort_values("tourney_date").reset_index(drop=True)
    for _, row in df_sorted.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))

        sw = get_stats(wid, SERVE_COLS+RET_COLS)
        sl = get_stats(lid, SERVE_COLS+RET_COLS)
        for c in SERVE_COLS+RET_COLS:
            results[f"a_{c}"].append(sw.get(c, np.nan))
            results[f"b_{c}"].append(sl.get(c, np.nan))

        # Zapisz statsy z tego meczu (winner)
        svpt_w = row.get("w_svpt",0) or 0
        rec = {
            "ace_pct":     pct(row.get("w_ace",0) or 0, svpt_w),
            "df_pct":      pct(row.get("w_df",0) or 0, svpt_w),
            "1st_in_pct":  pct(row.get("w_1stIn",0) or 0, svpt_w),
            "1st_won_pct": pct(row.get("w_1stWon",0) or 0, row.get("w_1stIn",0) or 1),
            "2nd_won_pct": pct(row.get("w_2ndWon",0) or 0, svpt_w - (row.get("w_1stIn",0) or 0)),
            "hold_pct":    pct(row.get("w_SvGms",0) or 0 - (row.get("w_bpFaced",0) or 0), row.get("w_SvGms",0) or 1),
            "break_pct":   pct(row.get("l_bpFaced",0) or 0 - (row.get("l_bpSaved",0) or 0), row.get("l_bpFaced",0) or 1),
            "ret_won_pct": pct(row.get("l_svpt",0) or 0 - (row.get("l_1stWon",0) or 0) - (row.get("l_2ndWon",0) or 0), row.get("l_svpt",0) or 1),
        }
        stats.setdefault(wid, deque(maxlen=10)).append(rec)

    for col, vals in results.items():
        df_sorted[col] = vals
    return df_sorted

def build_ranking_trajectory(df):
    """Ranking delta w 90 dniach: rosnący=faworyt coraz bardziej dominant"""
    df = df.sort_values("tourney_date").reset_index(drop=True)
    rank_hist = {}  # player_id → list(date, rank)

    delta_w, delta_l = [], []
    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        d = row["tourney_date"]
        rw = row.get("winner_rank"); rl = row.get("loser_rank")

        def get_delta(pid, now_rank, now_date):
            hist = rank_hist.get(pid, [])
            cutoff = now_date - pd.Timedelta(days=90)
            old = [(dd, rr) for dd, rr in hist if dd >= cutoff]
            if not old or now_rank != now_rank: return 0.0
            avg_old = np.mean([rr for _, rr in old])
            return float(avg_old - now_rank)  # pozytywny = poprawiał ranking

        delta_w.append(get_delta(wid, rw, d) if rw else 0.0)
        delta_l.append(get_delta(lid, rl, d) if rl else 0.0)

        if rw: rank_hist.setdefault(wid, []).append((d, rw))
        if rl: rank_hist.setdefault(lid, []).append((d, rl))

    df["rank_traj_w"] = delta_w
    df["rank_traj_l"] = delta_l
    df["rank_traj_diff"] = df["rank_traj_w"] - df["rank_traj_l"]
    return df

def build_draw_difficulty(df):
    """Trudność drabinki: średni ranking pokonanych wcześniej w turnieju"""
    df = df.sort_values("tourney_date").reset_index(drop=True)
    beaten = {}  # (year, tourney, player_id) → list ranks beaten

    diff_w, diff_l = [], []
    for _, row in df.iterrows():
        yr = row.get("year"); tn = row.get("tourney_name","")
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        rl = row.get("loser_rank")

        key_w = (yr, tn, wid); key_l = (yr, tn, lid)
        beaten_w = beaten.get(key_w, []); beaten_l = beaten.get(key_l, [])

        diff_w.append(np.mean(beaten_w) if beaten_w else 200)
        diff_l.append(np.mean(beaten_l) if beaten_l else 200)

        if rl: beaten.setdefault(key_w, []).append(rl)

    df["draw_diff_w"] = diff_w
    df["draw_diff_l"] = diff_l
    df["draw_diff_delta"] = df["draw_diff_w"] - df["draw_diff_l"]
    return df

def build_player_weather_interaction(df):
    """Jak gracz historycznie radzi sobie w różnych warunkach pogodowych.
    WAŻNE: tylko dane PRE-MATCH (expanding window BEZ obecnego meczu).
    AUC v6=0.9991 był data leakage — tu naprawione.
    """
    df = df.sort_values("tourney_date").reset_index(drop=True)

    from collections import deque
    heat_hist = {}
    rain_hist = {}
    wind_hist = {}

    hw, hl, rw, rl, ww, wl = [], [], [], [], [], []
    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        temp  = row.get("temp_max_mean",  np.nan)
        rain  = row.get("rain_days",      np.nan)
        wind  = row.get("wind_max_mean",  np.nan)

        def get_wr(pid, hist_dict):
            h = hist_dict.get(pid, deque(maxlen=30))
            return np.mean(list(h)) if len(h) >= 3 else 0.5

        # NAJPIERW zapisz poprzednie statystyki (pre-match)
        hw.append(get_wr(wid, heat_hist)); hl.append(get_wr(lid, heat_hist))
        rw.append(get_wr(wid, rain_hist)); rl.append(get_wr(lid, rain_hist))
        ww.append(get_wr(wid, wind_hist)); wl.append(get_wr(lid, wind_hist))

        # POTEM zaktualizuj (post-match) — brak leakage
        is_hot  = bool(temp > 28)  if temp == temp else False
        is_rain = bool(rain > 2)   if rain == rain else False
        is_wind = bool(wind > 25)  if wind == wind else False

        if is_hot:
            heat_hist.setdefault(wid, deque(maxlen=30)).append(1)
            heat_hist.setdefault(lid, deque(maxlen=30)).append(0)
        if is_rain:
            rain_hist.setdefault(wid, deque(maxlen=30)).append(1)
            rain_hist.setdefault(lid, deque(maxlen=30)).append(0)
        if is_wind:
            wind_hist.setdefault(wid, deque(maxlen=30)).append(1)
            wind_hist.setdefault(lid, deque(maxlen=30)).append(0)

    df["pw_heat_wr_w"] = hw; df["pw_heat_wr_l"] = hl
    df["pw_rain_wr_w"] = rw; df["pw_rain_wr_l"] = rl
    df["pw_wind_wr_w"] = ww; df["pw_wind_wr_l"] = wl
    df["pw_heat_edge"] = df["pw_heat_wr_w"] - df["pw_heat_wr_l"]
    df["pw_rain_edge"] = df["pw_rain_wr_w"] - df["pw_rain_wr_l"]
    df["pw_wind_edge"] = df["pw_wind_wr_w"] - df["pw_wind_wr_l"]
    return df

# ─── AB RANDOMIZATION (z train_v4.py) ────────────────────────────────────────
STATIC_COLS_W = ["winner_id","winner_name","winner_rank","winner_age",
                 "w_ace","w_df","w_svpt","w_1stIn","w_1stWon","w_2ndWon","w_SvGms","w_bpSaved","w_bpFaced"]
STATIC_COLS_L = ["loser_id","loser_name","loser_rank","loser_age",
                 "l_ace","l_df","l_svpt","l_1stIn","l_1stWon","l_2ndWon","l_SvGms","l_bpSaved","l_bpFaced"]

def randomize_ab(df, feat_cols_w, feat_cols_l, rng=None):
    """Losowo przypisuje A/B żeby model nie wiedział kto wygrał"""
    if rng is None: rng = np.random.default_rng(42)
    mask = rng.integers(0, 2, size=len(df)).astype(bool)
    result = pd.DataFrame(index=df.index)
    for fw, fl in zip(feat_cols_w, feat_cols_l):
        col = fw.replace("_w","_a") if fw.endswith("_w") else fw+"_a"
        result[col.replace("_a","_a")] = np.where(mask, df[fw], df[fl])
        col2 = fl.replace("_l","_b") if fl.endswith("_l") else fl+"_b"
        result[col2.replace("_b","_b")] = np.where(mask, df[fl], df[fw])
    result["y"] = np.where(mask, 1, 0)  # 1 = A wygrał (czyli original winner)
    return result, mask

# ─── TRAINING ENGINE ─────────────────────────────────────────────────────────

def train_model(name, df_train, df_hold, feat_cols, params=None, extra_info=None):
    """Trenuje LightGBM z walk-forward CV i evaluacją na holdoucie"""
    if params is None: params = LGBM_PARAMS_BASE.copy()
    start = time.time()
    log(f"\n{'='*60}")
    log(f"TRENING {name} | {len(feat_cols)} feats | train={len(df_train):,} | hold={len(df_hold):,}")

    # Walk-forward CV
    wf_results = []
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = df_train[(df_train["year"] >= tr_start) & (df_train["year"] < tr_end)]
        val = df_train[(df_train["year"] >= tr_end)   & (df_train["year"] < val_end)]
        if len(tr) < 100 or len(val) < 50: continue

        X_tr, y_tr   = tr[feat_cols].fillna(-999), tr["y"]
        X_val, y_val = val[feat_cols].fillna(-999), val["y"]

        m = lgb.LGBMClassifier(**params)
        m.fit(X_tr, y_tr,
              eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(80, verbose=False),
                         lgb.log_evaluation(-1)])
        p = m.predict_proba(X_val)[:,1]
        auc = roc_auc_score(y_val, p)
        bs  = brier_score_loss(y_val, p)
        wf_results.append({"train_end": tr_end, "val_end": val_end,
                           "auc": auc, "bs": bs, "iters": m.best_iteration_})
        log(f"  WF {tr_end}→{val_end}: AUC={auc:.4f}  BS={bs:.4f}  iters={m.best_iteration_}")

    mean_auc = np.mean([r["auc"] for r in wf_results])
    mean_bs  = np.mean([r["bs"]  for r in wf_results])
    log(f"  WF MEAN: AUC={mean_auc:.4f}  BS={mean_bs:.4f}")

    # Final model na całym train
    X_tr, y_tr  = df_train[feat_cols].fillna(-999), df_train["y"]
    X_ho, y_ho  = df_hold[feat_cols].fillna(-999),  df_hold["y"]
    final = lgb.LGBMClassifier(**{**params, "n_estimators": int(np.mean([r["iters"] for r in wf_results])*1.1) or 500})
    final.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])

    p_ho = final.predict_proba(X_ho)[:,1]
    auc_ho = roc_auc_score(y_ho, p_ho)
    bs_ho  = brier_score_loss(y_ho, p_ho)
    log(f"  HOLDOUT 2024-2026: AUC={auc_ho:.4f}  BS={bs_ho:.4f}")

    # Feature importance
    fi = pd.Series(final.feature_importances_, index=feat_cols).sort_values(ascending=False)
    log(f"  TOP-5 features: {', '.join(fi.head(5).index.tolist())}")

    # Zapis
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    mfile = MODELS_PATH / f"lgbm_{name}_{ts_str}.joblib"
    ffile = MODELS_PATH / f"feat_cols_{name}_{ts_str}.joblib"
    joblib.dump(final, mfile)
    joblib.dump(feat_cols, ffile)

    meta = {
        "version": name, "trained_at": ts_str,
        "train_period": f"2004-{HOLDOUT_START-1}",
        "holdout_period": f"{HOLDOUT_START}-2026",
        "n_train": len(df_train), "n_holdout": len(df_hold),
        "n_features": len(feat_cols),
        "mean_wf_auc": round(mean_auc, 4), "mean_wf_bs": round(mean_bs, 4),
        "holdout_auc": round(auc_ho, 4),   "holdout_bs": round(bs_ho, 4),
        "wf_splits": wf_results,
        "top_features": fi.head(20).to_dict(),
        "model_file": mfile.name,
        "duration_sec": round(time.time() - start, 1),
        **(extra_info or {})
    }
    with open(MODELS_PATH / f"model_meta_{name}_{ts_str}.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)

    log(f"  Zapisano: {mfile.name}")
    log(f"{'='*60}")
    return meta, final, feat_cols

# ─── WERSJE ───────────────────────────────────────────────────────────────────

def make_ab_dataset(df, feat_pairs):
    """feat_pairs: list of (col_w, col_l) → tworzy dataset A/B.

    Obsługuje 3 przypadki:
      (a) col_w != col_l — różne kolumny dla A i B (np. winner_rank / loser_rank)
          → kolumny wynikowe: {base}_a / {base}_b  gdzie base = col_w bez sufixu _w/_W
      (b) col_w == col_l — jedna kolumna "shared" (np. temp_mean, surface features)
          → AB flip zamienia wartości; wynikowe kolumny: {col}_a / {col}_b
          UWAGA: weather features są shared (ta sama wartość dla obu graczy) →
          obie kolumny mają tę samą wartość, ale LightGBM wymaga unikalnych nazw.
    Duplikaty kolumn są deduplikowane — ostatnia definicja wygrywa.
    """
    rng = np.random.default_rng(42)
    mask = rng.integers(0, 2, size=len(df)).astype(bool)
    out = pd.DataFrame(index=df.index)
    out["year"] = df["year"]
    out["tourney_date"] = df.get("tourney_date", pd.NaT)

    feat_cols = []
    seen = set()

    for fw, fl in feat_pairs:
        if fw not in df.columns and fl not in df.columns:
            continue

        vw = df[fw].values if fw in df.columns else np.full(len(df), np.nan)
        vl = df[fl].values if fl in df.columns else np.full(len(df), np.nan)

        if fw == fl:
            # Shared feature (np. weather, surface×weather interaction)
            # Obie strony mają tę samą wartość — bez flipu sensownego,
            # ale LightGBM potrzebuje unikalnych nazw.
            # Dodajemy tylko JEDNĄ kolumnę (bez sufixu) bo wartość jest identyczna.
            col = fw  # np. "temp_mean"
            if col not in seen:
                out[col] = vw
                feat_cols.append(col)
                seen.add(col)
        else:
            # Asymetryczna para (winner vs loser)
            # Generuj bazową nazwę usuwając sufix _w/_l/_W/_L
            base = fw
            for suf in ("_w","_W","_winner","_a"):
                if base.endswith(suf):
                    base = base[:-len(suf)]; break

            fa = base + "_a"
            fb = base + "_b"

            # Jeśli kolumna już istnieje (inna para wygenerowała ten sam base) → skip
            if fa in seen or fb in seen:
                # użyj pełnej nazwy żeby uniknąć kolizji
                fa = fw + "_a"
                fb = fl + "_b"

            out[fa] = np.where(mask, vw, vl)
            out[fb] = np.where(mask, vl, vw)
            if fa not in seen:
                feat_cols.append(fa); seen.add(fa)
            if fb not in seen:
                feat_cols.append(fb); seen.add(fb)

    # Surface encode
    if "surface" in df.columns:
        surf_map = {"Hard":0,"Clay":1,"Grass":2,"Carpet":0}
        out["surface_enc"] = df["surface"].map(surf_map).fillna(0).astype(int)
        if "surface_enc" not in seen:
            feat_cols.append("surface_enc")
            seen.add("surface_enc")

    out["y"] = np.where(mask, 1, 0)
    return out, feat_cols

# Bazowe pary cech (wspólne dla wszystkich wersji)
BASE_PAIRS = [
    ("pin_prob_w",   "pin_prob_l"),
    ("b365_prob_w",  "b365_prob_l") if False else ("b365_prob_w", "b365_prob_w"),  # placeholder
    ("max_prob_w",   "max_prob_w"),
    ("avg_prob_w",   "avg_prob_w"),
    ("odds_consensus_w", "odds_consensus_w"),
    ("pin_log_odds", "pin_log_odds"),
    ("b365_log_odds","b365_log_odds"),
    ("winner_rank",  "loser_rank"),
    ("winner_age",   "loser_age"),
]

def fix_base_pairs(df):
    """Popraw BASE_PAIRS dla faktycznych kolumn"""
    pairs = [
        ("pin_prob_w",       "pin_prob_l"),
        ("b365_prob_w",      "b365_prob_w"),   # brak _l w parquet, użyj tej samej
        ("max_prob_w",       "max_prob_w"),
        ("avg_prob_w",       "avg_prob_w"),
        ("odds_consensus_w", "odds_consensus_w"),
        ("pin_log_odds",     "pin_log_odds"),
        ("b365_log_odds",    "b365_log_odds"),
        ("winner_rank",      "loser_rank"),
        ("winner_age",       "loser_age"),
    ]
    # Tylko te co istnieją w df
    return [(fw, fl) for fw, fl in pairs if fw in df.columns or fl in df.columns]

WEATHER_PAIRS = [
    ("temp_mean",      "temp_mean"),
    ("temp_max_mean",  "temp_max_mean"),
    ("temp_extreme",   "temp_extreme"),
    ("temp_cold",      "temp_cold"),
    ("rain_days",      "rain_days"),
    ("rain_heavy",     "rain_heavy"),
    ("wind_max_mean",  "wind_max_mean"),
    ("wind_strong",    "wind_strong"),
    ("humidity_mean",  "humidity_mean"),
    ("harsh_conditions","harsh_conditions"),
    ("pct_storm",      "pct_storm"),
    ("pct_rain",       "pct_rain"),
    ("pct_clear",      "pct_clear"),
]

# ─── VERSION RUNNERS ─────────────────────────────────────────────────────────

def run_v5(df):
    """v5: v4 base + weather features"""
    log("\n" + "█"*60)
    log("v5: +WEATHER FEATURES (ERA5: temp/rain/wind/harsh)")
    log("█"*60)

    pairs = fix_base_pairs(df) + WEATHER_PAIRS
    data, feat_cols = make_ab_dataset(df, pairs)

    train = data[data["year"] < HOLDOUT_START].copy()
    hold  = data[data["year"] >= HOLDOUT_START].copy()
    return train_model("v5", train, hold, feat_cols,
                       extra_info={"hypothesis": "+weather ERA5 features"})

def run_v6(df):
    """v6: v5 + player×weather interaction"""
    log("\n" + "█"*60)
    log("v6: +PLAYER×WEATHER INTERACTION (historical perf in heat/rain/wind)")
    log("█"*60)

    df = build_player_weather_interaction(df)
    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("pw_heat_wr_w", "pw_heat_wr_l"),
        ("pw_rain_wr_w", "pw_rain_wr_l"),
        ("pw_wind_wr_w", "pw_wind_wr_l"),
        ("pw_heat_edge", "pw_heat_edge"),
        ("pw_rain_edge", "pw_rain_edge"),
        ("pw_wind_edge", "pw_wind_edge"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v6", train, hold, feat_cols,
                       extra_info={"hypothesis": "+player×weather interaction"})

def run_v7(df):
    """v7: v5 + surface×weather interaction terms"""
    log("\n" + "█"*60)
    log("v7: +SURFACE×WEATHER INTERACTION TERMS")
    log("█"*60)

    surf_map = {"Hard":0,"Clay":1,"Grass":2,"Carpet":0}
    df["surf_enc"] = df["surface"].map(surf_map).fillna(0)

    # Interakcje: Clay w deszczu jest bardziej niebezpieczna
    df["clay_rain"]   = (df["surf_enc"] == 1).astype(float) * df.get("rain_days", 0).fillna(0)
    df["grass_wind"]  = (df["surf_enc"] == 2).astype(float) * df.get("wind_max_mean", 0).fillna(0)
    df["hard_heat"]   = (df["surf_enc"] == 0).astype(float) * df.get("temp_max_mean", 25).fillna(25)
    df["clay_heat"]   = (df["surf_enc"] == 1).astype(float) * df.get("temp_max_mean", 25).fillna(25)

    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("clay_rain",  "clay_rain"),
        ("grass_wind", "grass_wind"),
        ("hard_heat",  "hard_heat"),
        ("clay_heat",  "clay_heat"),
        ("surf_enc",   "surf_enc"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v7", train, hold, feat_cols,
                       extra_info={"hypothesis": "+surface×weather cross-features"})

def run_v8(df):
    """v8: v4 base + improved fatigue (days_rest, 14d match count)"""
    log("\n" + "█"*60)
    log("v8: +FATIGUE UPGRADE (days_rest, matches_14d, travel_load)")
    log("█"*60)

    df = df.sort_values("tourney_date").reset_index(drop=True)
    from collections import deque

    last_match  = {}  # pid → last date
    matches_14d = {}  # pid → deque(dates)

    rest_w, rest_l, m14_w, m14_l = [], [], [], []
    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        d = row["tourney_date"]

        def get_rest(pid):
            lm = last_match.get(pid)
            if lm is None or pd.isna(lm): return 14.0
            delta = (d - lm).days if hasattr(d, 'days') or hasattr(d-lm,'days') else 14
            return min(float(delta), 30)

        def get_m14(pid):
            hist = list(matches_14d.get(pid, []))
            cutoff = d - pd.Timedelta(days=14)
            return sum(1 for dd in hist if dd >= cutoff)

        rest_w.append(get_rest(wid)); rest_l.append(get_rest(lid))
        m14_w.append(get_m14(wid));   m14_l.append(get_m14(lid))

        last_match[wid] = d; last_match[lid] = d
        matches_14d.setdefault(wid, deque(maxlen=30)).append(d)
        matches_14d.setdefault(lid, deque(maxlen=30)).append(d)

    df["days_rest_w"] = rest_w; df["days_rest_l"] = rest_l
    df["matches_14d_w"] = m14_w; df["matches_14d_l"] = m14_l
    df["fatigue_diff"]  = df["matches_14d_w"] - df["matches_14d_l"]
    df["rest_diff"]     = df["days_rest_w"]   - df["days_rest_l"]

    pairs = fix_base_pairs(df) + [
        ("days_rest_w",   "days_rest_l"),
        ("matches_14d_w", "matches_14d_l"),
        ("fatigue_diff",  "fatigue_diff"),
        ("rest_diff",     "rest_diff"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v8", train, hold, feat_cols,
                       extra_info={"hypothesis": "+fatigue: days_rest + matches_14d"})

def run_v9(df):
    """v9: v4 base + H2H features"""
    log("\n" + "█"*60)
    log("v9: +H2H FEATURES (last-3 H2H delta, surface H2H win rate)")
    log("█"*60)

    df = build_h2h(df)
    pairs = fix_base_pairs(df) + [
        ("h2h_wins_delta_3", "h2h_wins_delta_3"),
        ("h2h_surf_winrate", "h2h_surf_winrate"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v9", train, hold, feat_cols,
                       extra_info={"hypothesis": "+H2H last-3 + surface H2H"})

def run_v10(df):
    """v10: v4 base + ranking trajectory"""
    log("\n" + "█"*60)
    log("v10: +RANKING TRAJECTORY (90d delta: rośnie/spada w rankingu)")
    log("█"*60)

    df = build_ranking_trajectory(df)
    pairs = fix_base_pairs(df) + [
        ("rank_traj_w",    "rank_traj_l"),
        ("rank_traj_diff", "rank_traj_diff"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v10", train, hold, feat_cols,
                       extra_info={"hypothesis": "+ranking trajectory 90d"})

def run_v11(df):
    """v11: v4 base + serwis/return stats rolling"""
    log("\n" + "█"*60)
    log("v11: +SERVE/RETURN STATS (rolling 10 mecze: ace%, 1st_won%, break%)")
    log("█"*60)

    df = build_serve_return(df)
    new_cols = [c for c in df.columns if c.startswith("a_") or c.startswith("b_")]
    pairs = fix_base_pairs(df)
    for c in [c for c in new_cols if c.startswith("a_")]:
        pairs.append((c, c.replace("a_","b_")))

    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]
    hold  = data[data["year"] >= HOLDOUT_START]
    return train_model("v11", train, hold, feat_cols,
                       extra_info={"hypothesis": "+serve/return rolling stats"})

def run_v12(df):
    """v12: v4 + H2H + fatigue + weather (combo)"""
    log("\n" + "█"*60)
    log("v12: COMBO (H2H + fatigue + weather)")
    log("█"*60)

    df = build_h2h(df)
    df = build_ranking_trajectory(df)
    df = build_player_weather_interaction(df)

    df = df.sort_values("tourney_date").reset_index(drop=True)
    from collections import deque
    last_match  = {}; matches_14d = {}
    rest_w, rest_l, m14_w, m14_l = [], [], [], []
    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        d = row["tourney_date"]
        def get_rest(pid):
            lm = last_match.get(pid)
            if lm is None: return 14.0
            try: return min(float((d-lm).days), 30)
            except: return 14.0
        def get_m14(pid):
            hist = list(matches_14d.get(pid,[]))
            cutoff = d - pd.Timedelta(days=14)
            return sum(1 for dd in hist if dd >= cutoff)
        rest_w.append(get_rest(wid)); rest_l.append(get_rest(lid))
        m14_w.append(get_m14(wid));   m14_l.append(get_m14(lid))
        last_match[wid] = d; last_match[lid] = d
        matches_14d.setdefault(wid, deque(maxlen=30)).append(d)
        matches_14d.setdefault(lid, deque(maxlen=30)).append(d)
    df["days_rest_w"] = rest_w; df["days_rest_l"] = rest_l
    df["matches_14d_w"] = m14_w; df["matches_14d_l"] = m14_l

    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3", "h2h_wins_delta_3"),
        ("h2h_surf_winrate",  "h2h_surf_winrate"),
        ("rank_traj_w",       "rank_traj_l"),
        ("rank_traj_diff",    "rank_traj_diff"),
        ("days_rest_w",       "days_rest_l"),
        ("matches_14d_w",     "matches_14d_l"),
        ("pw_heat_edge",      "pw_heat_edge"),
        ("pw_rain_edge",      "pw_rain_edge"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]; hold = data[data["year"] >= HOLDOUT_START]
    return train_model("v12", train, hold, feat_cols,
                       extra_info={"hypothesis": "combo: H2H+fatigue+weather+rank_traj"})

def run_v13(df):
    """v13: v12 + draw difficulty"""
    log("\n" + "█"*60)
    log("v13: +DRAW DIFFICULTY (avg rank pokonanych w turnieju)")
    log("█"*60)

    df = build_h2h(df)
    df = build_ranking_trajectory(df)
    df = build_draw_difficulty(df)

    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3", "h2h_wins_delta_3"),
        ("rank_traj_diff",   "rank_traj_diff"),
        ("draw_diff_w",      "draw_diff_l"),
        ("draw_diff_delta",  "draw_diff_delta"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]; hold = data[data["year"] >= HOLDOUT_START]
    return train_model("v13", train, hold, feat_cols,
                       extra_info={"hypothesis": "+draw difficulty"})

def run_v14(df):
    """v14: v12 + age×surface interaction"""
    log("\n" + "█"*60)
    log("v14: +AGE×SURFACE INTERACTION")
    log("█"*60)

    df = build_h2h(df)
    df = build_ranking_trajectory(df)
    surf_map = {"Hard":0,"Clay":1,"Grass":2,"Carpet":0}
    df["surf_enc"] = df["surface"].map(surf_map).fillna(0)

    # Starsi gracze gorzej na szybkich nawierzchniach
    df["age_surf_w"] = df["winner_age"].fillna(26) * df["surf_enc"]
    df["age_surf_l"] = df["loser_age"].fillna(26)  * df["surf_enc"]
    df["age_surf_diff"] = df["age_surf_w"] - df["age_surf_l"]
    # Clay specialist = peak age later (31 vs 27)
    df["age_w"] = df["winner_age"].fillna(26)
    df["age_l"] = df["loser_age"].fillna(26)
    df["age_peak_dist_w"] = abs(df["age_w"] - 26)  # distance from typical peak
    df["age_peak_dist_l"] = abs(df["age_l"] - 26)

    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3", "h2h_wins_delta_3"),
        ("rank_traj_diff",   "rank_traj_diff"),
        ("age_surf_w",       "age_surf_l"),
        ("age_surf_diff",    "age_surf_diff"),
        ("age_peak_dist_w",  "age_peak_dist_l"),
        ("age_w",            "age_l"),
        ("surf_enc",         "surf_enc"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]; hold = data[data["year"] >= HOLDOUT_START]
    return train_model("v14", train, hold, feat_cols,
                       extra_info={"hypothesis": "+age×surface + peak_age_distance"})

def run_v15(df):
    """v15: v12 + market consensus divergence"""
    log("\n" + "█"*60)
    log("v15: +MARKET CONSENSUS DIVERGENCE (max vs avg vs pinnacle spread)")
    log("█"*60)

    df = build_h2h(df)
    df = build_ranking_trajectory(df)

    # Market disagreement = signal wartości
    pin = df.get("pin_prob_w", pd.Series(np.nan, index=df.index)).fillna(0.5)
    avg = df.get("avg_prob_w", pd.Series(np.nan, index=df.index)).fillna(0.5)
    mx  = df.get("max_prob_w", pd.Series(np.nan, index=df.index)).fillna(0.5)
    b365= df.get("b365_prob_w",pd.Series(np.nan, index=df.index)).fillna(0.5)

    df["mkt_spread_w"]   = mx - pin          # max > pin = soft money price
    df["mkt_avg_pin_w"]  = avg - pin         # avg > pin = book overreaction
    df["mkt_b365_pin_w"] = b365 - pin        # b365 vs pin divergence
    df["mkt_consensus_std"] = pd.concat([pin,avg,mx,b365],axis=1).std(axis=1)

    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3",  "h2h_wins_delta_3"),
        ("rank_traj_diff",    "rank_traj_diff"),
        ("mkt_spread_w",      "mkt_spread_w"),
        ("mkt_avg_pin_w",     "mkt_avg_pin_w"),
        ("mkt_b365_pin_w",    "mkt_b365_pin_w"),
        ("mkt_consensus_std", "mkt_consensus_std"),
    ]
    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]; hold = data[data["year"] >= HOLDOUT_START]
    return train_model("v15", train, hold, feat_cols,
                       extra_info={"hypothesis": "+market consensus divergence features"})

def run_v16(df):
    """v16: v15 + serve/return stats (kumulatywne z v11)"""
    log("\n" + "█"*60)
    log("v16: FULL FEATURE SET (v15 + serve/return rolling stats)")
    log("█"*60)

    df = build_h2h(df)
    df = build_ranking_trajectory(df)
    df = build_serve_return(df)
    df = build_player_weather_interaction(df)

    pin = df.get("pin_prob_w", pd.Series(0.5, index=df.index)).fillna(0.5)
    avg = df.get("avg_prob_w", pd.Series(0.5, index=df.index)).fillna(0.5)
    mx  = df.get("max_prob_w", pd.Series(0.5, index=df.index)).fillna(0.5)
    b365= df.get("b365_prob_w",pd.Series(0.5, index=df.index)).fillna(0.5)
    df["mkt_spread_w"]   = mx   - pin
    df["mkt_avg_pin_w"]  = avg  - pin
    df["mkt_b365_pin_w"] = b365 - pin
    df["mkt_consensus_std"] = pd.concat([pin,avg,mx,b365],axis=1).std(axis=1)

    serve_pairs = [(c, c.replace("a_","b_")) for c in df.columns
                   if c.startswith("a_") and c.replace("a_","b_") in df.columns]
    pairs = fix_base_pairs(df) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3",  "h2h_wins_delta_3"),
        ("rank_traj_diff",    "rank_traj_diff"),
        ("mkt_spread_w",      "mkt_spread_w"),
        ("mkt_avg_pin_w",     "mkt_avg_pin_w"),
        ("mkt_consensus_std", "mkt_consensus_std"),
        ("pw_heat_edge",      "pw_heat_edge"),
        ("pw_rain_edge",      "pw_rain_edge"),
    ] + serve_pairs[:8]  # top-8 serve/return pairs

    data, feat_cols = make_ab_dataset(df, pairs)
    train = data[data["year"] < HOLDOUT_START]; hold = data[data["year"] >= HOLDOUT_START]
    return train_model("v16", train, hold, feat_cols,
                       extra_info={"hypothesis": "full features: odds+weather+H2H+rank_traj+market_div+serve"})

def run_v17(df):
    """v17: v16 z SHAP feature selection (top-30)"""
    log("\n" + "█"*60)
    log("v17: SHAP TOP-30 SELECTION z v16")
    log("█"*60)
    try:
        import shap
    except ImportError:
        log("  shap not installed — pip install shap")
        return None, None, None

    # Wczytaj model v16 (ostatni)
    v16_files = sorted(MODELS_PATH.glob("lgbm_v16_*.joblib"))
    if not v16_files:
        log("  Brak modelu v16 — uruchom najpierw v16"); return None, None, None

    m16 = joblib.load(v16_files[-1])
    f16_file = sorted(MODELS_PATH.glob("feat_cols_v16_*.joblib"))[-1]
    f16 = joblib.load(f16_file)

    # Rebuild v16 dataset
    df2 = build_h2h(df.copy())
    df2 = build_ranking_trajectory(df2)
    df2 = build_serve_return(df2)
    df2 = build_player_weather_interaction(df2)
    pin = df2.get("pin_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    avg = df2.get("avg_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    mx  = df2.get("max_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    b365= df2.get("b365_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    df2["mkt_spread_w"]=mx-pin; df2["mkt_avg_pin_w"]=avg-pin
    df2["mkt_b365_pin_w"]=b365-pin
    df2["mkt_consensus_std"]=pd.concat([pin,avg,mx,b365],axis=1).std(axis=1)

    serve_pairs = [(c,c.replace("a_","b_")) for c in df2.columns
                   if c.startswith("a_") and c.replace("a_","b_") in df2.columns]
    pairs = fix_base_pairs(df2)+WEATHER_PAIRS+[
        ("h2h_wins_delta_3","h2h_wins_delta_3"),("rank_traj_diff","rank_traj_diff"),
        ("mkt_spread_w","mkt_spread_w"),("mkt_avg_pin_w","mkt_avg_pin_w"),
        ("mkt_consensus_std","mkt_consensus_std"),("pw_heat_edge","pw_heat_edge"),
        ("pw_rain_edge","pw_rain_edge"),]+serve_pairs[:8]
    data, all_feats = make_ab_dataset(df2, pairs)
    train = data[data["year"]<HOLDOUT_START]
    X_sample = train[all_feats].fillna(-999).sample(min(5000,len(train)), random_state=42)

    explainer = shap.TreeExplainer(m16)
    shap_vals  = explainer.shap_values(X_sample)
    if isinstance(shap_vals, list): shap_vals = shap_vals[1]
    mean_abs = pd.Series(np.abs(shap_vals).mean(axis=0), index=all_feats).sort_values(ascending=False)
    top30 = mean_abs.head(30).index.tolist()
    log(f"  SHAP TOP-30: {top30}")

    hold = data[data["year"]>=HOLDOUT_START]
    return train_model("v17", train, hold, top30,
                       extra_info={"hypothesis": "SHAP top-30 feature selection",
                                   "shap_ranking": mean_abs.head(30).to_dict()})

def run_v18(df):
    """v18: Ensemble LightGBM + stacking z v4 i v9"""
    log("\n" + "█"*60)
    log("v18: ENSEMBLE STACKING (v4 + v9 + v12 → LogReg meta)")
    log("█"*60)

    # Zbierz modele bazowe
    base_models = []
    for vn in ["v4","v9","v12"]:
        files = sorted(MODELS_PATH.glob(f"lgbm_{vn}_*.joblib"))
        feat_files = sorted(MODELS_PATH.glob(f"feat_cols_{vn}_*.joblib"))
        if files and feat_files:
            m = joblib.load(files[-1]); feats = joblib.load(feat_files[-1])
            base_models.append((vn, m, feats))
            log(f"  Załadowano {vn}: {feat_files[-1].name}")

    if len(base_models) < 2:
        log("  Za mało modeli bazowych — uruchom najpierw v4, v9, v12"); return None, None, None

    # Buduj pełny dataset (max feats)
    df2 = build_h2h(df.copy())
    df2 = build_ranking_trajectory(df2)
    pairs = fix_base_pairs(df2)+WEATHER_PAIRS+[
        ("h2h_wins_delta_3","h2h_wins_delta_3"),("rank_traj_diff","rank_traj_diff")]
    data, all_feats = make_ab_dataset(df2, pairs)

    # Generuj OOF predictions z każdego modelu bazowego
    # Kluczowe: dobieramy tylko te feats które istnieją w data (ta sama kolejność co w treningu)
    meta_feats = []
    for vn, m, feats in base_models:
        avail = [f for f in feats if f in data.columns]
        if len(avail) < len(feats) * 0.5:
            log(f"  {vn}: za mało pasujących features ({len(avail)}/{len(feats)}) — skip")
            continue
        # Pad missing features with -999
        X_pred = data.reindex(columns=feats, fill_value=-999).fillna(-999)
        p = m.predict_proba(X_pred)[:,1]
        data[f"oof_{vn}"] = p
        meta_feats.append(f"oof_{vn}")
        log(f"  {vn}: {len(avail)}/{len(feats)} feats matched, pred range [{p.min():.3f},{p.max():.3f}]")
    meta_feats += ["surface_enc"] if "surface_enc" in data.columns else []

    train = data[data["year"]<HOLDOUT_START]; hold = data[data["year"]>=HOLDOUT_START]
    X_tr = train[meta_feats].fillna(0.5); y_tr = train["y"]
    X_ho = hold[meta_feats].fillna(0.5);  y_ho = hold["y"]

    meta = LogisticRegression(C=1.0, max_iter=500)
    meta.fit(X_tr, y_tr)
    p_ho = meta.predict_proba(X_ho)[:,1]
    auc_ho = roc_auc_score(y_ho, p_ho)
    bs_ho  = brier_score_loss(y_ho, p_ho)

    log(f"  Meta LR coefs: {dict(zip(meta_feats, meta.coef_[0].round(3)))}")
    log(f"  HOLDOUT: AUC={auc_ho:.4f}  BS={bs_ho:.4f}")

    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    mfile = MODELS_PATH / f"lgbm_v18_{ts_str}.joblib"
    joblib.dump(meta, mfile)
    meta_info = {
        "version": "v18", "trained_at": ts_str,
        "holdout_auc": round(auc_ho,4), "holdout_bs": round(bs_ho,4),
        "model_file": mfile.name,
        "hypothesis": "stacking ensemble: v4+v9+v12 → LogReg meta",
        "meta_feats": meta_feats, "meta_coefs": dict(zip(meta_feats, meta.coef_[0].round(4))),
        "base_models": [vn for vn,_,_ in base_models],
    }
    with open(MODELS_PATH/f"model_meta_v18_{ts_str}.json","w") as f:
        json.dump(meta_info, f, indent=2)
    log(f"  Zapisano: {mfile.name}")
    return meta_info, meta, meta_feats

def run_v19(df):
    """v19: XGBoost zamiast LightGBM (v16 feats)"""
    log("\n" + "█"*60)
    log("v19: XGBOOST (vs LightGBM — benchmark algorytmu)")
    log("█"*60)
    try:
        import xgboost as xgb
    except ImportError:
        log("  xgboost not installed — pip install xgboost"); return None, None, None

    df2 = build_h2h(df.copy()); df2 = build_ranking_trajectory(df2)
    pin=df2.get("pin_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    avg=df2.get("avg_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    mx =df2.get("max_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    df2["mkt_spread_w"]=mx-pin; df2["mkt_avg_pin_w"]=avg-pin
    df2["mkt_consensus_std"]=pd.concat([pin,avg,mx],axis=1).std(axis=1)
    pairs=fix_base_pairs(df2)+WEATHER_PAIRS+[
        ("h2h_wins_delta_3","h2h_wins_delta_3"),
        ("rank_traj_diff","rank_traj_diff"),
        ("mkt_spread_w","mkt_spread_w"),("mkt_consensus_std","mkt_consensus_std")]
    data, feat_cols = make_ab_dataset(df2, pairs)
    train=data[data["year"]<HOLDOUT_START]; hold=data[data["year"]>=HOLDOUT_START]

    xgb_params = {
        "n_estimators":1000,"learning_rate":0.04,"max_depth":6,
        "subsample":0.8,"colsample_bytree":0.8,
        "use_label_encoder":False,"eval_metric":"logloss",
        "random_state":42,"n_jobs":-1,"verbosity":0,
    }
    wf_results = []
    for tr_start, tr_end, val_end in WF_SPLITS:
        tr  = train[(train["year"]>=tr_start)&(train["year"]<tr_end)]
        val = train[(train["year"]>=tr_end)  &(train["year"]<val_end)]
        if len(tr)<100 or len(val)<50: continue
        X_tr,y_tr   = tr[feat_cols].fillna(-999),tr["y"]
        X_val,y_val = val[feat_cols].fillna(-999),val["y"]
        m = xgb.XGBClassifier(**xgb_params)
        m = xgb.XGBClassifier(**{**xgb_params, "early_stopping_rounds": 80})
        m.fit(X_tr,y_tr,eval_set=[(X_val,y_val)],verbose=False)
        p = m.predict_proba(X_val)[:,1]
        auc=roc_auc_score(y_val,p); bs=brier_score_loss(y_val,p)
        wf_results.append({"auc":auc,"bs":bs,"iters":m.best_iteration})
        log(f"  WF {tr_end}→{val_end}: AUC={auc:.4f}  BS={bs:.4f}")

    mean_iters = int(np.mean([r["iters"] for r in wf_results])*1.1) or 300
    final = xgb.XGBClassifier(**{**xgb_params,"n_estimators":mean_iters,"early_stopping_rounds":None})
    X_tr,y_tr  = train[feat_cols].fillna(-999),train["y"]
    X_ho,y_ho  = hold[feat_cols].fillna(-999),  hold["y"]
    final.fit(X_tr,y_tr,verbose=False)
    p_ho = final.predict_proba(X_ho)[:,1]
    auc_ho=roc_auc_score(y_ho,p_ho); bs_ho=brier_score_loss(y_ho,p_ho)
    mean_auc=np.mean([r["auc"] for r in wf_results])
    log(f"  WF MEAN AUC={mean_auc:.4f} | HOLDOUT AUC={auc_ho:.4f} BS={bs_ho:.4f}")

    ts_str=datetime.now().strftime("%Y%m%d_%H%M")
    mfile=MODELS_PATH/f"lgbm_v19_{ts_str}.joblib"
    joblib.dump(final, mfile)
    meta={"version":"v19","holdout_auc":round(auc_ho,4),"holdout_bs":round(bs_ho,4),
          "mean_wf_auc":round(mean_auc,4),"model_file":mfile.name,
          "hypothesis":"XGBoost benchmark vs LightGBM","trained_at":ts_str}
    with open(MODELS_PATH/f"model_meta_v19_{ts_str}.json","w") as f:
        json.dump(meta,f,indent=2)
    return meta, final, feat_cols

def run_v20(df):
    """v20: Surface-specific models (4×LightGBM)"""
    log("\n" + "█"*60)
    log("v20: SURFACE-SPECIFIC MODELS (Hard/Clay/Grass/Carpet osobno)")
    log("█"*60)

    df2 = build_h2h(df.copy()); df2 = build_ranking_trajectory(df2)
    pin=df2.get("pin_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    avg=df2.get("avg_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    mx =df2.get("max_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    df2["mkt_spread_w"]=mx-pin; df2["mkt_avg_pin_w"]=avg-pin
    pairs=fix_base_pairs(df2)+WEATHER_PAIRS+[
        ("h2h_wins_delta_3","h2h_wins_delta_3"),
        ("rank_traj_diff","rank_traj_diff"),
        ("mkt_spread_w","mkt_spread_w"),("mkt_avg_pin_w","mkt_avg_pin_w")]
    data, feat_cols = make_ab_dataset(df2, pairs)
    data["surface"] = df2["surface"].values if "surface" in df2.columns else "Hard"
    if "surface_enc" in feat_cols: feat_cols = [f for f in feat_cols if f != "surface_enc"]

    surf_models = {}
    all_aucs = []
    SURFACES = {"Hard":["Hard","Carpet"],"Clay":["Clay"],"Grass":["Grass"]}
    for surf_name, surf_vals in SURFACES.items():
        sd = data[data["surface"].isin(surf_vals)]
        tr = sd[sd["year"]<HOLDOUT_START]; ho = sd[sd["year"]>=HOLDOUT_START]
        if len(tr)<200 or len(ho)<30:
            log(f"  {surf_name}: za mało danych ({len(tr)}/{len(ho)}) — skip"); continue

        X_tr,y_tr = tr[feat_cols].fillna(-999),tr["y"]
        X_ho,y_ho = ho[feat_cols].fillna(-999),ho["y"]
        p_surf = {k:LGBM_PARAMS_BASE.copy() for k in ["params"]}["params"]
        m = lgb.LGBMClassifier(**{**LGBM_PARAMS_BASE,"n_estimators":800})
        m.fit(X_tr,y_tr,eval_set=[(X_ho,y_ho)],
              callbacks=[lgb.early_stopping(60,verbose=False),lgb.log_evaluation(-1)])
        p_ho = m.predict_proba(X_ho)[:,1]
        auc=roc_auc_score(y_ho,p_ho); bs=brier_score_loss(y_ho,p_ho)
        log(f"  {surf_name:8s}: n_train={len(tr):,} n_hold={len(ho):,} AUC={auc:.4f} BS={bs:.4f}")
        surf_models[surf_name] = (m, auc, bs)
        all_aucs.append(auc)

    mean_auc = np.mean(all_aucs) if all_aucs else 0
    ts_str=datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(surf_models, MODELS_PATH/f"lgbm_v20_{ts_str}.joblib")
    joblib.dump(feat_cols,   MODELS_PATH/f"feat_cols_v20_{ts_str}.joblib")
    meta={"version":"v20","mean_holdout_auc":round(mean_auc,4),
          "by_surface":{s:(round(a,4),round(b,4)) for s,(m,a,b) in surf_models.items()},
          "hypothesis":"surface-specific LightGBM (Hard/Clay/Grass)","trained_at":ts_str}
    with open(MODELS_PATH/f"model_meta_v20_{ts_str}.json","w") as f:
        json.dump(meta,f,indent=2)
    log(f"  MEAN AUC: {mean_auc:.4f}")
    return meta, surf_models, feat_cols

def run_v21(df):
    """v21: Polynomial + ratio features z v16 base"""
    log("\n" + "█"*60)
    log("v21: POLYNOMIAL + RATIO FEATURES")
    log("█"*60)

    df2 = build_h2h(df.copy()); df2 = build_ranking_trajectory(df2)
    pin=df2.get("pin_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    avg=df2.get("avg_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    mx =df2.get("max_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    df2["mkt_spread_w"]=mx-pin; df2["mkt_consensus_std"]=pd.concat([pin,avg,mx],axis=1).std(axis=1)

    # Polynomial: pin² (non-linear market confidence)
    # WAŻNE: rank_ratio musi być dla winner i loser osobno (nie dzielić winner/loser przed AB flip)
    df2["pin_sq_w"]      = pin**2
    df2["pin_sq_l"]      = (1-pin)**2
    df2["rank_inv_w"]    = 1.0 / (df2["winner_rank"].fillna(200)+1)
    df2["rank_inv_l"]    = 1.0 / (df2["loser_rank"].fillna(200)+1)
    df2["odds_ratio"]    = df2.get("PSW",pd.Series(1.0,index=df2.index)).fillna(2.0) / \
                           df2.get("PSL",pd.Series(1.0,index=df2.index)).fillna(2.0)
    # odds_ratio = PSW/PSL — to jest shared (ta sama wartość dla obu stron po normalizacji)
    # Jako shared feature (fw==fl) nie leakuje po AB flip
    pairs = fix_base_pairs(df2)+WEATHER_PAIRS+[
        ("h2h_wins_delta_3","h2h_wins_delta_3"),("rank_traj_diff","rank_traj_diff"),
        ("mkt_spread_w","mkt_spread_w"),("mkt_consensus_std","mkt_consensus_std"),
        ("pin_sq_w","pin_sq_l"),   # asymetryczna: pin² dla zwycięzcy vs przegranego
        ("rank_inv_w","rank_inv_l"),  # 1/rank — asymetryczna
        ("odds_ratio","odds_ratio")]  # shared
    data, feat_cols = make_ab_dataset(df2, pairs)
    train=data[data["year"]<HOLDOUT_START]; hold=data[data["year"]>=HOLDOUT_START]
    return train_model("v21", train, hold, feat_cols,
                       extra_info={"hypothesis": "+polynomial (pin², rank_ratio, odds_ratio)"})

def run_v22(df):
    """v22: CHAMPION MODEL — best features + tuned hyperparams + Platt calibration"""
    log("\n" + "█"*60)
    log("v22: CHAMPION MODEL — best features + hyperopt + calibration")
    log("█"*60)

    # Wczytaj wyniki wszystkich poprzednich wersji
    results_files = sorted(MODELS_PATH.glob("model_meta_v*.json"))
    version_aucs = {}
    for f in results_files:
        try:
            m = json.load(open(f))
            v = m.get("version","")
            auc = m.get("holdout_auc",0)
            if v and auc: version_aucs[v] = auc
        except: pass
    log(f"  Poprzednie wersje AUC: {dict(sorted(version_aucs.items(), key=lambda x:-x[1])[:5])}")

    # Buduj najlepszy znany feature set (v16 + poly + H2H + weather)
    df2 = build_h2h(df.copy())
    df2 = build_ranking_trajectory(df2)
    df2 = build_draw_difficulty(df2)
    df2 = build_player_weather_interaction(df2)

    pin=df2.get("pin_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    avg=df2.get("avg_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    mx =df2.get("max_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)
    b365=df2.get("b365_prob_w",pd.Series(0.5,index=df2.index)).fillna(0.5)

    df2["mkt_spread_w"]    = mx   - pin
    df2["mkt_avg_pin_w"]   = avg  - pin
    df2["mkt_b365_pin_w"]  = b365 - pin
    df2["mkt_consensus_std"]= pd.concat([pin,avg,mx,b365],axis=1).std(axis=1)
    # pin² asymetryczne — osobno dla winner i loser (bez leakage)
    df2["pin_sq_w"]         = pin**2
    df2["pin_sq_l"]         = (1-pin)**2
    df2["rank_inv_w"]       = 1.0/(df2["winner_rank"].fillna(200)+1)
    df2["rank_inv_l"]       = 1.0/(df2["loser_rank"].fillna(200)+1)
    df2["odds_ratio"]       = df2.get("PSW",pd.Series(2.0,index=df2.index)).fillna(2.0) / \
                              df2.get("PSL",pd.Series(2.0,index=df2.index)).fillna(2.0)

    surf_map={"Hard":0,"Clay":1,"Grass":2,"Carpet":0}
    df2["surf_enc"]   = df2["surface"].map(surf_map).fillna(0)
    df2["clay_rain"]  = (df2["surf_enc"]==1).astype(float)*df2.get("rain_days",pd.Series(0,index=df2.index)).fillna(0)
    df2["grass_wind"] = (df2["surf_enc"]==2).astype(float)*df2.get("wind_max_mean",pd.Series(0,index=df2.index)).fillna(0)
    df2["age_w"]  = df2["winner_age"].fillna(26)
    df2["age_l"]  = df2["loser_age"].fillna(26)

    pairs = fix_base_pairs(df2) + WEATHER_PAIRS + [
        ("h2h_wins_delta_3",  "h2h_wins_delta_3"),
        ("h2h_surf_winrate",   "h2h_surf_winrate"),
        ("rank_traj_diff",     "rank_traj_diff"),
        ("draw_diff_w",        "draw_diff_l"),
        ("mkt_spread_w",       "mkt_spread_w"),
        ("mkt_avg_pin_w",      "mkt_avg_pin_w"),
        ("mkt_b365_pin_w",     "mkt_b365_pin_w"),
        ("mkt_consensus_std",  "mkt_consensus_std"),
        ("pw_heat_edge",       "pw_heat_edge"),
        ("pw_rain_edge",       "pw_rain_edge"),
        ("pw_wind_edge",       "pw_wind_edge"),
        ("pin_sq_w",           "pin_sq_l"),   # asymetryczna
        ("rank_inv_w",         "rank_inv_l"), # asymetryczna
        ("odds_ratio",         "odds_ratio"), # shared
        ("clay_rain",          "clay_rain"),
        ("grass_wind",         "grass_wind"),
        ("age_w",              "age_l"),
        ("surf_enc",           "surf_enc"),
    ]
    data, feat_cols = make_ab_dataset(df2, pairs)

    # Tuned hyperparams (based on WF CV from best previous version)
    tuned_params = {
        **LGBM_PARAMS_BASE,
        "learning_rate": 0.03,
        "num_leaves": 127,
        "min_child_samples": 20,
        "subsample": 0.75,
        "colsample_bytree": 0.75,
        "reg_alpha": 0.3,
        "reg_lambda": 2.0,
        "n_estimators": 3000,
    }

    train=data[data["year"]<HOLDOUT_START]; hold=data[data["year"]>=HOLDOUT_START]
    meta_result, model, feat_cols = train_model("v22", train, hold, feat_cols, params=tuned_params,
                        extra_info={"hypothesis":"champion: full features + tuned hyperparams + calibration",
                                    "prev_version_aucs": version_aucs})

    # Platt calibration
    if model is not None:
        # sklearn 1.9 usunął cv="prefit" — używamy osobnego cal set (20%)
        from sklearn.model_selection import train_test_split
        X_full = train[feat_cols].fillna(-999); y_full = train["y"]
        X_cal_tr, X_cal_val, y_cal_tr, y_cal_val = train_test_split(
            X_full, y_full, test_size=0.2, random_state=42)
        cal = CalibratedClassifierCV(model, cv=5, method="sigmoid")
        cal.fit(X_cal_tr, y_cal_tr)
        X_ho = hold[feat_cols].fillna(-999);  y_ho = hold["y"]
        p_cal = cal.predict_proba(X_ho)[:,1]
        auc_cal = roc_auc_score(y_ho, p_cal); bs_cal = brier_score_loss(y_ho, p_cal)
        log(f"  Po kalibracji Platt: AUC={auc_cal:.4f}  BS={bs_cal:.4f}")
        ts_str=datetime.now().strftime("%Y%m%d_%H%M")
        joblib.dump(cal, MODELS_PATH/f"lgbm_v22_calibrated_{ts_str}.joblib")
        if meta_result: meta_result["calibrated_auc"] = round(auc_cal,4)

    return meta_result, model, feat_cols

# ─── RUNNER ───────────────────────────────────────────────────────────────────
VERSION_MAP = {
    5:  run_v5,  6:  run_v6,  7:  run_v7,  8:  run_v8,
    9:  run_v9,  10: run_v10, 11: run_v11, 12: run_v12,
    13: run_v13, 14: run_v14, 15: run_v15, 16: run_v16,
    17: run_v17, 18: run_v18, 19: run_v19, 20: run_v20,
    21: run_v21, 22: run_v22,
}

def parse_versions(arg):
    if arg == "all": return sorted(VERSION_MAP.keys())
    if "-" in arg:
        lo, hi = arg.split("-"); return list(range(int(lo), int(hi)+1))
    return [int(v) for v in arg.split(",")]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", default="5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22")
    args = parser.parse_args()

    versions = parse_versions(args.versions)
    log(f"Uruchamiam wersje: {versions}")

    # Wczytaj raz
    df = load_base()

    all_results = []
    for v in versions:
        fn = VERSION_MAP.get(v)
        if not fn: log(f"  Nieznana wersja {v} — skip"); continue
        try:
            meta, model, feats = fn(df.copy())
            if meta: all_results.append(meta)
        except Exception as e:
            import traceback
            log(f"  ERROR v{v}: {e}")
            traceback.print_exc()

    # Podsumowanie
    log("\n" + "="*60)
    log("PODSUMOWANIE WSZYSTKICH WERSJI")
    log("="*60)
    for r in sorted(all_results, key=lambda x: x.get("holdout_auc",0), reverse=True):
        v   = r.get("version","?")
        auc = r.get("holdout_auc",0)
        bs  = r.get("holdout_bs",0)
        hyp = r.get("hypothesis","")
        log(f"  {v:5s}  AUC={auc:.4f}  BS={bs:.4f}  | {hyp}")

    # Zapis zbiorczy
    with open(RESULTS_F, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log(f"\nZapisano: {RESULTS_F}")
    log("="*60)
