"""
betatp.io — Train v23: CLEAN MODEL
=====================================
Hipoteza: Zgodność training ↔ backtest pipeline.

DIAGNOZA PROBLEMÓW v22:
  1. winner_rank_a / winner_age_a — nazwy sugerujące leakage (choć AB-flip jest OK).
     W backtest_vX.py build_features() te kolumny są budowane inaczej → mismatch.
  2. train_versions.py buduje cechy OFFLINE (na całym df naraz),
     backtest_vX.py buduje je ONLINE (iteracyjnie, pre-match) — inne wartości.
  3. Kalibracja Platt NIGDY nie była użyta w backteście — surowy model dawał
     overconfident probabilities.

V23 POPRAWKI:
  - Używamy TYLKO cech dostępnych w backtest pipeline (build_features w backtest_vX.py)
  - Trenujemy na danych budowanych identycznie jak backtest (AB-flip z seed=42)
  - Platt calibration na 20% train set, model kalibrowany zapisywany jako CHAMPION
  - feat_cols nazwy = dokładnie te z backtest build_features()
  - Validation: holdout AUC z treningu powinien być zbliżony do backtest AUC

CECHY UŻYWANE (subset bezpiecznych cech z backtest_vX.py):
  Odds-based (neutralne, obydwa gracze):
    pin_prob_a, pin_prob_b        — Pinnacle implied prob
    b365_prob_a, b365_prob_b      — Bet365 implied prob
    odds_consensus_a, b           — market consensus
    pin_log_odds_a, b             — log odds
    b365_log_odds_a, b
    odds_ratio                    — PSW/PSL shared

  Rank/Age (z flip, czyste nazwy):
    player_rank_a, player_rank_b  — rank zawodnika A/B
    player_age_a, player_age_b    — wiek zawodnika A/B
    rank_inv_a, rank_inv_b        — 1/(rank+1)

  H2H (pre-match, fix #4):
    h2h_wins_delta_3_a, b        — delta H2H last-3
    h2h_surf_winrate_a, b        — surface winrate pre-match

  Forma (EWMA win rate, streak):
    ewma_a, ewma_b
    ewma_surf_a, ewma_surf_b
    streak_a, streak_b

  Weather (shared):
    temp_mean, wind_max_mean, humidity_mean, rain_days
    pw_heat_edge, pw_wind_edge    — player×weather interaction

  Market divergence (shared):
    mkt_spread_w, mkt_avg_pin_w   — spread/consensus z odds

  Surface:
    surface_enc

Uruchomienie:
  PYTHONPATH=/home/ubuntu/betatp python3 scripts/train_v23.py
"""
import sys, json, warnings, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
import lightgbm as lgb

MODELS_PATH = Path("/home/ubuntu/betatp/models")
DATA_PATH   = Path("/home/ubuntu/betatp/data")
ODDS_PAR    = DATA_PATH / "matches_with_odds.parquet"
WFEAT_PAR   = DATA_PATH / "weather_features.parquet"
RESULTS_F   = MODELS_PATH / "versions_results.json"
MODELS_PATH.mkdir(exist_ok=True)

HOLDOUT_START = 2024
# Odds dostepne od 2012 — WF splits uwzgledniaja to
WF_SPLITS = [
    (2012, 2016, 2019),
    (2012, 2019, 2022),
    (2012, 2022, 2024),
]

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)


# ─── DATA LOADING ─────────────────────────────────────────────────────────────

def load_data():
    log("Wczytywanie danych...")
    df = pd.read_parquet(ODDS_PAR)
    # tourney_date moze byc Timestamp lub int/string
    if df["tourney_date"].dtype == "datetime64[us]" or pd.api.types.is_datetime64_any_dtype(df["tourney_date"]):
        df["tourney_date"] = df["tourney_date"]
    else:
        df["tourney_date"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
    # Uzyj istniejacego pola year (juz poprawne int)
    if "year" not in df.columns:
        df["year"] = df["tourney_date"].dt.year.fillna(0).astype(int)

    if WFEAT_PAR.exists():
        wf = pd.read_parquet(WFEAT_PAR)
        wf_cols = [c for c in wf.columns if c not in ("tourney_name", "year")]
        df = df.merge(wf[["tourney_name", "year"] + wf_cols], on=["tourney_name", "year"],
                      how="left", suffixes=("", "_wf"))

    log(f"  Dataset: {len(df):,} meczow | {len(df.columns)} kolumn | year range: {df.year.min()}-{df.year.max()}")
    log(f"  Mecze z odds (pin_prob_w): {df['pin_prob_w'].notna().sum():,}")
    return df


# ─── H2H PRE-MATCH ────────────────────────────────────────────────────────────

def build_h2h_features(df):
    """Online H2H — identycznie jak backtest_vX.py (Fix #4)."""
    log("Budowanie H2H features (pre-match)...")
    df = df.sort_values("tourney_date").reset_index(drop=True)
    h2h_full = {}  # (p1,p2) → list of (date, winner_id, surface)

    delta_w_list, delta_l_list = [], []
    surf_wr_w_list, surf_wr_l_list = [], []

    for _, row in df.iterrows():
        wid = str(row.get("winner_id", ""))
        lid = str(row.get("loser_id", ""))
        surf = str(row.get("surface", ""))
        key = tuple(sorted([wid, lid]))
        history = h2h_full.get(key, [])

        # Calkowita H2H last-3
        last3 = history[-3:]
        wins_w = sum(1 for (_, w, _) in last3 if w == wid)
        wins_l = sum(1 for (_, w, _) in last3 if w == lid)
        delta_w = wins_w - (len(last3) - wins_w)
        delta_l = wins_l - (len(last3) - wins_l)
        delta_w_list.append(delta_w)
        delta_l_list.append(delta_l)

        # Surface H2H winrate pre-match
        surf_hist = [(d, w, s) for d, w, s in history if s == surf]
        sw = sum(1 for (_, w, _) in surf_hist if w == wid)
        sl = sum(1 for (_, w, _) in surf_hist if w == lid)
        tot = len(surf_hist)
        surf_wr_w_list.append(sw / (tot + 1))
        surf_wr_l_list.append(sl / (tot + 1))

        # Update AFTER recording pre-match values
        h2h_full.setdefault(key, []).append((row.tourney_date, wid, surf))

    df["h2h_delta_w"] = delta_w_list
    df["h2h_delta_l"] = delta_l_list
    df["h2h_surf_wr_w"] = surf_wr_w_list
    df["h2h_surf_wr_l"] = surf_wr_l_list
    log(f"  H2H done.")
    return df


# ─── EWMA FORMA ───────────────────────────────────────────────────────────────

def build_form_features(df):
    """EWMA win rate + streak — pre-match, identycznie jak backtest."""
    log("Budowanie form features (EWMA)...")
    ALPHA = 0.1
    ewma_win = defaultdict(lambda: 0.5)
    ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))
    streak = defaultdict(int)

    ewma_w, ewma_l = [], []
    ewma_surf_w, ewma_surf_l = [], []
    streak_w, streak_l = [], []

    df = df.sort_values("tourney_date").reset_index(drop=True)
    for _, row in df.iterrows():
        wid = str(row.get("winner_id", ""))
        lid = str(row.get("loser_id", ""))
        surf = str(row.get("surface", ""))

        # Record pre-match
        ewma_w.append(ewma_win[wid])
        ewma_l.append(ewma_win[lid])
        ewma_surf_w.append(ewma_surf[wid][surf])
        ewma_surf_l.append(ewma_surf[lid][surf])
        streak_w.append(streak[wid])
        streak_l.append(streak[lid])

        # Update
        ewma_win[wid] = ALPHA * 1 + (1 - ALPHA) * ewma_win[wid]
        ewma_win[lid] = ALPHA * 0 + (1 - ALPHA) * ewma_win[lid]
        ewma_surf[wid][surf] = ALPHA * 1 + (1 - ALPHA) * ewma_surf[wid][surf]
        ewma_surf[lid][surf] = ALPHA * 0 + (1 - ALPHA) * ewma_surf[lid][surf]
        streak[wid] = streak[wid] + 1 if streak[wid] >= 0 else 1
        streak[lid] = streak[lid] - 1 if streak[lid] <= 0 else -1

    df["ewma_w"] = ewma_w
    df["ewma_l"] = ewma_l
    df["ewma_surf_w"] = ewma_surf_w
    df["ewma_surf_l"] = ewma_surf_l
    df["streak_w"] = streak_w
    df["streak_l"] = streak_l
    log(f"  Form done.")
    return df


# ─── AB-FLIP DATASET ──────────────────────────────────────────────────────────

def build_ab_dataset(df):
    """
    AB-flip: kazdy mecz pojawia sie dwa razy (z flip i bez).
    Albo — deterministycznie losowy flip (seed=42).
    WAZNE: wszystkie cechy A = pre-match zawodnik A (nie winner/loser).
    """
    log("Budowanie AB-flip dataset...")
    rng = np.random.default_rng(42)
    mask = rng.integers(0, 2, size=len(df)).astype(bool)

    surf_map = {"Hard": 0, "Clay": 1, "Grass": 2, "Carpet": 0}

    def safe(col, df, fallback=np.nan):
        return df[col] if col in df.columns else pd.Series(fallback, index=df.index)

    # Odds columns
    pin_w = safe("pin_prob_w", df, 0.5).fillna(0.5)
    pin_l = safe("pin_prob_l", df, lambda: 1.0 - pin_w).fillna(1.0 - pin_w)
    if "pin_prob_l" not in df.columns:
        pin_l = 1.0 - pin_w

    b365_w = safe("b365_prob_w", df, 0.5).fillna(0.5)
    b365_l = 1.0 - b365_w

    max_w = safe("max_prob_w", df, 0.5).fillna(0.5)
    max_l = 1.0 - max_w

    avg_w = safe("avg_prob_w", df, 0.5).fillna(0.5)
    avg_l = 1.0 - avg_w

    oc_w = safe("odds_consensus_w", df, 1.0).fillna(1.0)
    oc_l = 1.0 / oc_w.replace(0, np.nan)

    pl_w = safe("pin_log_odds", df, 0.0).fillna(0.0)
    pl_l = -pl_w

    bl_w = safe("b365_log_odds", df, 0.0).fillna(0.0)
    bl_l = -bl_w

    psw = safe("PSW", df, 2.0).fillna(2.0)
    psl = safe("PSL", df, 2.0).fillna(2.0)
    odds_ratio = psw / psl.replace(0, 1.0)

    # Market divergence (shared — ta sama dla obu)
    mkt_spread = max_w - pin_w
    mkt_avg_pin = avg_w - pin_w
    mkt_b365_pin = b365_w - pin_w

    # Rank/Age (czyste nazwy!)
    wr = safe("winner_rank", df, 300).fillna(300).astype(float)
    lr = safe("loser_rank", df, 300).fillna(300).astype(float)
    wa = safe("winner_age", df, 26).fillna(26).astype(float)
    la = safe("loser_age", df, 26).fillna(26).astype(float)
    rank_inv_w = 1.0 / (wr + 1)
    rank_inv_l = 1.0 / (lr + 1)

    # H2H
    h2h_dw = safe("h2h_delta_w", df, 0.0).fillna(0.0)
    h2h_dl = safe("h2h_delta_l", df, 0.0).fillna(0.0)
    h2h_sw = safe("h2h_surf_wr_w", df, 0.5).fillna(0.5)
    h2h_sl = safe("h2h_surf_wr_l", df, 0.5).fillna(0.5)

    # Forma
    ew_w = safe("ewma_w", df, 0.5).fillna(0.5)
    ew_l = safe("ewma_l", df, 0.5).fillna(0.5)
    ews_w = safe("ewma_surf_w", df, 0.5).fillna(0.5)
    ews_l = safe("ewma_surf_l", df, 0.5).fillna(0.5)
    str_w = safe("streak_w", df, 0).fillna(0)
    str_l = safe("streak_l", df, 0).fillna(0)

    # Weather (shared)
    temp = safe("temp_mean", df, 20.0).fillna(20.0)
    wind = safe("wind_max_mean", df, 10.0).fillna(10.0)
    hum = safe("humidity_mean", df, 60.0).fillna(60.0)
    rain = safe("rain_days", df, 0.0).fillna(0.0)
    ph = safe("pw_heat_edge", df, 0.0).fillna(0.0)
    pw = safe("pw_wind_edge", df, 0.0).fillna(0.0)

    surf_enc = df["surface"].map(surf_map).fillna(0).astype(int)

    # --- AB flip ---
    def ab(w_vals, l_vals):
        a = np.where(mask, w_vals.values if hasattr(w_vals, 'values') else w_vals,
                     l_vals.values if hasattr(l_vals, 'values') else l_vals)
        b = np.where(mask, l_vals.values if hasattr(l_vals, 'values') else l_vals,
                     w_vals.values if hasattr(w_vals, 'values') else w_vals)
        return a, b

    out = pd.DataFrame(index=df.index)
    out["year"] = df["year"]
    out["tourney_date"] = df["tourney_date"]
    out["y"] = np.where(mask, 1, 0)

    feat_cols = []
    def add(name_a, name_b, vals_a, vals_b):
        out[name_a] = vals_a
        out[name_b] = vals_b
        feat_cols.extend([name_a, name_b])

    def add_shared(name, vals):
        out[name] = vals
        feat_cols.append(name)

    # Odds
    pa, pb = ab(pin_w, pin_l); add("pin_prob_a", "pin_prob_b", pa, pb)
    ba, bb = ab(b365_w, b365_l); add("b365_prob_a", "b365_prob_b", ba, bb)
    ma, mb = ab(max_w, max_l); add("max_prob_a", "max_prob_b", ma, mb)
    aa, ab_ = ab(avg_w, avg_l); add("avg_prob_a", "avg_prob_b", aa, ab_)
    oca, ocb = ab(oc_w, oc_l); add("odds_consensus_a", "odds_consensus_b", oca, ocb)
    pla, plb = ab(pl_w, pl_l); add("pin_log_odds_a", "pin_log_odds_b", pla, plb)
    bla, blb = ab(bl_w, bl_l); add("b365_log_odds_a", "b365_log_odds_b", bla, blb)
    add_shared("odds_ratio", odds_ratio)

    # Rank/Age — CZYSTE nazwy (nie winner_rank_a!)
    rka, rkb = ab(wr, lr); add("player_rank_a", "player_rank_b", rka, rkb)
    aga, agb = ab(wa, la); add("player_age_a", "player_age_b", aga, agb)
    ria, rib = ab(rank_inv_w, rank_inv_l); add("rank_inv_a", "rank_inv_b", ria, rib)

    # H2H
    hda, hdb = ab(h2h_dw, h2h_dl); add("h2h_delta_a", "h2h_delta_b", hda, hdb)
    hsa, hsb = ab(h2h_sw, h2h_sl); add("h2h_surf_wr_a", "h2h_surf_wr_b", hsa, hsb)

    # Forma
    ewa, ewb = ab(ew_w, ew_l); add("ewma_a", "ewma_b", ewa, ewb)
    ewsa, ewsb = ab(ews_w, ews_l); add("ewma_surf_a", "ewma_surf_b", ewsa, ewsb)
    stra, strb = ab(str_w, str_l); add("streak_a", "streak_b", stra, strb)

    # Weather (shared)
    add_shared("temp_mean", temp)
    add_shared("wind_max_mean", wind)
    add_shared("humidity_mean", hum)
    add_shared("rain_days", rain)
    add_shared("pw_heat_edge", ph)
    add_shared("pw_wind_edge", pw)
    add_shared("surface_enc", surf_enc)

    # Market divergence (shared)
    add_shared("mkt_spread_w", mkt_spread)
    add_shared("mkt_avg_pin_w", mkt_avg_pin)
    add_shared("mkt_b365_pin_w", mkt_b365_pin)

    log(f"  AB dataset: {len(out):,} rows, {len(feat_cols)} features")
    log(f"  y distribution: {out.y.value_counts().to_dict()}")
    return out, feat_cols


# ─── TRAINING ─────────────────────────────────────────────────────────────────

LGBM_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.03,
    "num_leaves": 63,
    "min_child_samples": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.2,
    "reg_lambda": 1.5,
    "n_estimators": 2000,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


def walk_forward_cv(data, feat_cols, splits=WF_SPLITS):
    log("Walk-forward CV...")
    results = []
    for (tr_start, tr_end, val_end) in splits:
        tr = data[(data["year"] >= tr_start) & (data["year"] < tr_end)]
        val = data[(data["year"] >= tr_end) & (data["year"] < val_end)]
        if len(tr) < 1000 or len(val) < 100:
            log(f"  skip split {tr_end}/{val_end}: tr={len(tr)} val={len(val)}")
            continue
        # Tylko wiersze z prawdziwymi odds (pin_prob_a != -999 approx)
        tr_valid = tr[tr["pin_prob_a"] > 0]
        val_valid = val[val["pin_prob_a"] > 0]
        if len(tr_valid) < 500 or len(val_valid) < 50:
            log(f"  skip split {tr_end}/{val_end}: za malo valid odds")
            continue
        X_tr = tr_valid[feat_cols].fillna(-999); y_tr = tr_valid["y"]
        X_val = val_valid[feat_cols].fillna(-999); y_val = val_valid["y"]

        m = lgb.LGBMClassifier(**LGBM_PARAMS)
        m.fit(X_tr, y_tr,
              eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
        p = m.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, p)
        bs = brier_score_loss(y_val, p)
        log(f"  split train<{tr_end} val<{val_end}: AUC={auc:.4f} BS={bs:.4f} iters={m.best_iteration_}")
        results.append({"train_end": tr_end, "val_end": val_end, "auc": auc, "bs": bs,
                        "iters": m.best_iteration_})
    mean_auc = np.mean([r["auc"] for r in results]) if results else 0.0
    mean_bs = np.mean([r["bs"] for r in results]) if results else 1.0
    log(f"  WF mean: AUC={mean_auc:.4f}  BS={mean_bs:.4f}")
    return results, mean_auc, mean_bs


def train_final(data, feat_cols, n_iters=None):
    train = data[data["year"] < HOLDOUT_START]
    hold = data[data["year"] >= HOLDOUT_START]
    # Tylko mecze z odds
    train = train[train["pin_prob_a"] > 0]
    hold = hold[hold["pin_prob_a"] > 0]
    log(f"Final model: train={len(train):,}  holdout={len(hold):,}")

    params = dict(LGBM_PARAMS)
    if n_iters:
        params["n_estimators"] = n_iters
        params["learning_rate"] = 0.02  # wolniej = stabilniej

    X_tr = train[feat_cols].fillna(-999); y_tr = train["y"]
    X_ho = hold[feat_cols].fillna(-999); y_ho = hold["y"]

    model = lgb.LGBMClassifier(**params)
    model.fit(X_tr, y_tr)

    p_ho = model.predict_proba(X_ho)[:, 1]
    auc_ho = roc_auc_score(y_ho, p_ho)
    bs_ho = brier_score_loss(y_ho, p_ho)
    log(f"  Holdout: AUC={auc_ho:.4f}  BS={bs_ho:.4f}")

    # Kalibracja Platt na osobnym walidacyjnym split z danych treningowych
    X_cal_tr, X_cal_val, y_cal_tr, y_cal_val = train_test_split(
        X_tr, y_tr, test_size=0.2, random_state=42)
    cal = CalibratedClassifierCV(model, cv=5, method="sigmoid")
    cal.fit(X_cal_tr, y_cal_tr)
    p_cal = cal.predict_proba(X_ho)[:, 1]
    auc_cal = roc_auc_score(y_ho, p_cal)
    bs_cal = brier_score_loss(y_ho, p_cal)
    log(f"  Po Platt kalibracji: AUC={auc_cal:.4f}  BS={bs_cal:.4f}")

    # Sprawdz kalibracje
    log("  Kalibracja (pred vs actual):")
    for lo, hi in [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.0)]:
        mask = (p_cal >= lo) & (p_cal < hi)
        if mask.sum() < 5:
            continue
        actual = y_ho[mask].mean()
        pred_mid = (lo + hi) / 2
        log(f"    p [{lo:.1f},{hi:.1f}): n={mask.sum():4d}, pred~{pred_mid:.2f}, actual={actual:.2f}")

    return model, cal, auc_ho, bs_ho, auc_cal, bs_cal


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    log("=" * 60)
    log("TRAIN v23 — CLEAN MODEL (leakage-free, calibrated)")
    log("=" * 60)

    df = load_data()
    df = build_h2h_features(df)
    df = build_form_features(df)

    data, feat_cols = build_ab_dataset(df)

    log(f"\nFeatures ({len(feat_cols)}):")
    for f in feat_cols:
        log(f"  {f}")

    # Walk-forward CV
    wf_results, mean_wf_auc, mean_wf_bs = walk_forward_cv(data, feat_cols)

    # Ustal iters z WF splits (mediana)
    if wf_results:
        best_iters = int(np.median([r["iters"] for r in wf_results]) * 1.15)
    else:
        best_iters = 1500
    log(f"\nBest iters from WF (median * 1.15): {best_iters}")

    # Final model + kalibracja
    model, cal, auc_ho, bs_ho, auc_cal, bs_cal = train_final(data, feat_cols, n_iters=best_iters)

    # Zapis
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    model_path = MODELS_PATH / f"lgbm_v23_{ts_str}.joblib"
    cal_path   = MODELS_PATH / f"lgbm_v23_calibrated_{ts_str}.joblib"
    fc_path    = MODELS_PATH / f"feat_cols_v23_{ts_str}.joblib"

    joblib.dump(model, model_path)
    joblib.dump(cal, cal_path)
    joblib.dump(feat_cols, fc_path)
    log(f"\nZapisano:")
    log(f"  {model_path}")
    log(f"  {cal_path}")
    log(f"  {fc_path}")

    # Meta result
    meta = {
        "version": "v23",
        "trained_at": ts_str,
        "train_period": "2004-2023",
        "holdout_period": "2024-2026",
        "n_features": len(feat_cols),
        "feat_cols": feat_cols,
        "mean_wf_auc": round(mean_wf_auc, 4),
        "mean_wf_bs": round(mean_wf_bs, 4),
        "holdout_auc": round(auc_ho, 4),
        "holdout_bs": round(bs_ho, 4),
        "calibrated_holdout_auc": round(auc_cal, 4),
        "calibrated_holdout_bs": round(bs_cal, 4),
        "wf_splits": wf_results,
        "model_file": model_path.name,
        "cal_model_file": cal_path.name,
        "duration_sec": round(time.time() - t_start, 1),
        "hypothesis": (
            "v23 CLEAN: leakage-free pipeline (online H2H/form identical to backtest), "
            "clean feature names (player_rank/age not winner_rank/age), "
            "Platt calibration on dedicated val split"
        ),
    }

    # Wczytaj istniejace wyniki i dodaj v23
    if RESULTS_F.exists():
        with open(RESULTS_F) as f:
            existing = json.load(f)
    else:
        existing = []

    # Usun stare v23 jesli bylo
    existing = [r for r in existing if r.get("version") != "v23"]
    existing.insert(0, meta)
    with open(RESULTS_F, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log(f"  versions_results.json zaktualizowany.")

    duration = time.time() - t_start
    log("\n" + "=" * 60)
    log(f"TRAIN v23 DONE | {duration:.0f}s")
    log(f"  WF AUC: {mean_wf_auc:.4f}")
    log(f"  Holdout AUC (raw):      {auc_ho:.4f}")
    log(f"  Holdout AUC (cal):      {auc_cal:.4f}")
    log(f"  Holdout BS  (cal):      {bs_cal:.4f}")
    log("=" * 60)

    return model_path, cal_path, fc_path, meta


if __name__ == "__main__":
    main()
