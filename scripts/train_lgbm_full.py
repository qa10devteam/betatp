"""
betatp.io — Full LightGBM Training Pipeline
Walk-Forward 1990-2025, ~40 minut
"""
import sys
import os
import time
import json
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime
from dataclasses import asdict

import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, brier_score_loss, log_loss, accuracy_score
)
import joblib

TML_PATH = Path("/home/ubuntu/TML-Database")
MODELS_PATH = Path("/home/ubuntu/betatp/models")
MODELS_PATH.mkdir(exist_ok=True)

LOG_FILE = Path("/home/ubuntu/betatp/models/training_log.jsonl")

def log(msg: str, data: dict = None):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
    if data is not None:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps({"ts": ts, "msg": msg, **data}) + "\n")

# ─────────────────────────────────────────────
# 1. WCZYTAJ DANE
# ─────────────────────────────────────────────
log("=== ETAP 1: Wczytywanie danych TML-Database ===")

dfs = []
for csv_file in sorted(TML_PATH.glob("[0-9]*.csv")):
    try:
        year = int(csv_file.stem)
    except ValueError:
        continue
    if year < 1990:
        continue
    try:
        df = pd.read_csv(csv_file, low_memory=False)
        df["year"] = year
        dfs.append(df)
    except Exception as e:
        log(f"  SKIP {csv_file.name}: {e}")

raw = pd.concat(dfs, ignore_index=True)
log(f"  Wczytano {len(raw):,} meczów (1990-2025)", {"n_raw": len(raw)})

# Normalizacja
raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
raw = raw.dropna(subset=["tourney_date", "winner_id", "loser_id"])
raw = raw.sort_values("tourney_date").reset_index(drop=True)

# Normalizuj surface
surface_map = {
    "Hard": "Hard", "Clay": "Clay", "Grass": "Grass",
    "Carpet": "Hard", "Indoor Hard": "Hard", "Acrylic": "Hard",
}
raw["surface"] = raw["surface"].map(surface_map).fillna("Hard")

# Normalizuj tourney_level
level_map = {
    "G": "G", "M": "M", "A": "500", "D": "250",
    "F": "F", "C": "250", "S": "500",
    "250": "250", "500": "500",
}
raw["tourney_level"] = raw["tourney_level"].map(level_map).fillna("250")

log(f"  Po normalizacji: {len(raw):,} meczów", {"n_clean": len(raw)})
log(f"  Zakres: {raw.tourney_date.min().date()} → {raw.tourney_date.max().date()}")
log(f"  Surface dist: {raw.surface.value_counts().to_dict()}")

# ─────────────────────────────────────────────
# 2. OBLICZ ELO CHRONOLOGICZNIE
# ─────────────────────────────────────────────
log("\n=== ETAP 2: Obliczanie Elo (6 wariantów) dla 198k meczów ===")
t0 = time.time()

from engine.elo import EloEngine

elo = EloEngine()

# Kolumny serve stats
SERVE_COLS = ["w_svpt", "w_1stWon", "w_2ndWon", "l_svpt", "l_1stWon", "l_2ndWon"]
for c in SERVE_COLS:
    if c not in raw.columns:
        raw[c] = np.nan
    raw[c] = pd.to_numeric(raw[c], errors="coerce")

# Przechowuj pre-match Elo dla każdego wiersza
records = []
log(f"  Przetwarzam {len(raw):,} meczów...")

for i, row in enumerate(raw.itertuples(index=False)):
    wid = str(row.winner_id)
    lid = str(row.loser_id)

    # Pobierz Elo PRZED meczem
    we = elo.get_or_create(wid)
    le = elo.get_or_create(lid)

    surf = str(row.surface)
    level = str(row.tourney_level)

    # Pre-match blended Elo
    w_surf_elo = elo.get_blended_surface_elo(wid, surf)
    l_surf_elo = elo.get_blended_surface_elo(lid, surf)
    elo_diff = w_surf_elo - l_surf_elo
    p_elo = elo.win_probability(w_surf_elo, l_surf_elo)

    records.append({
        "match_idx": i,
        "tourney_date": row.tourney_date,
        "year": row.year,
        "surface": surf,
        "tourney_level": level,
        "best_of": getattr(row, "best_of", 3),
        "winner_id": wid,
        "loser_id": lid,
        # Winner features
        "w_overall_elo": we.overall,
        "w_surf_elo": w_surf_elo,
        "w_serve_elo": we.serve,
        "w_return_elo": we.return_elo,
        "w_n_matches": we.n_matches,
        # Loser features
        "l_overall_elo": le.overall,
        "l_surf_elo": l_surf_elo,
        "l_serve_elo": le.serve,
        "l_return_elo": le.return_elo,
        "l_n_matches": le.n_matches,
        # Derived
        "elo_diff": elo_diff,
        "p_elo_winner": p_elo,
        "surface_hard": 1 if surf == "Hard" else 0,
        "surface_clay": 1 if surf == "Clay" else 0,
        "surface_grass": 1 if surf == "Grass" else 0,
        "level_G": 1 if level == "G" else 0,
        "level_M": 1 if level == "M" else 0,
        "best_of_5": 1 if getattr(row, "best_of", 3) == 5 else 0,
        # Serve/return elo matchup
        "serve_return_matchup": elo.win_probability(we.serve, le.return_elo),
        "w_is_provisional": 1 if we.is_provisional else 0,
        "l_is_provisional": 1 if le.is_provisional else 0,
    })

    # Aktualizuj Elo
    w_svpt = row.w_svpt if not pd.isna(row.w_svpt) else None
    w_1stWon = row.w_1stWon if not pd.isna(row.w_1stWon) else None
    w_2ndWon = row.w_2ndWon if not pd.isna(row.w_2ndWon) else None
    l_svpt = row.l_svpt if not pd.isna(row.l_svpt) else None
    l_1stWon = row.l_1stWon if not pd.isna(row.l_1stWon) else None
    l_2ndWon = row.l_2ndWon if not pd.isna(row.l_2ndWon) else None

    mdate = row.tourney_date.date() if hasattr(row.tourney_date, "date") else row.tourney_date
    elo.update_match(
        winner_id=wid, loser_id=lid,
        surface=surf, tourney_level=level,
        match_date=mdate,
        w_svpt=int(w_svpt) if w_svpt and not np.isnan(w_svpt) else None,
        w_1stWon=int(w_1stWon) if w_1stWon and not np.isnan(w_1stWon) else None,
        w_2ndWon=int(w_2ndWon) if w_2ndWon and not np.isnan(w_2ndWon) else None,
        l_svpt=int(l_svpt) if l_svpt and not np.isnan(l_svpt) else None,
        l_1stWon=int(l_1stWon) if l_1stWon and not np.isnan(l_1stWon) else None,
        l_2ndWon=int(l_2ndWon) if l_2ndWon and not np.isnan(l_2ndWon) else None,
    )

    if (i + 1) % 20000 == 0:
        elapsed = time.time() - t0
        log(f"  [{i+1:,}/{len(raw):,}] {elapsed:.0f}s — n_players={len(elo.ratings)}")

elapsed = time.time() - t0
log(f"  Elo gotowe w {elapsed:.1f}s — {len(elo.ratings)} graczy", {"elo_players": len(elo.ratings)})

df = pd.DataFrame(records)
log(f"  Dataset: {df.shape}")

# Zapisz Elo ratings
elo_path = MODELS_PATH / "elo_ratings_2025.joblib"
joblib.dump(elo.ratings, elo_path)
log(f"  Elo ratings zapisane: {elo_path}")

# ─────────────────────────────────────────────
# 3. BUDUJ DATASET ML
# ─────────────────────────────────────────────
log("\n=== ETAP 3: Budowanie dataset ML ===")

# Perspektywa symetryczna: dla każdego meczu 2 rzędy
# (raz z perspektywy zwycięzcy, raz przegranego)
# To zapobiega overfittingowi

rows_sym = []
for _, r in df.iterrows():
    # Perspektywa zwycięzcy (y=1)
    rows_sym.append({
        "year": r.year,
        "tourney_date": r.tourney_date,
        "a_overall_elo": r.w_overall_elo,
        "a_surf_elo": r.w_surf_elo,
        "a_serve_elo": r.w_serve_elo,
        "a_return_elo": r.w_return_elo,
        "a_n_matches": r.w_n_matches,
        "b_overall_elo": r.l_overall_elo,
        "b_surf_elo": r.l_surf_elo,
        "b_serve_elo": r.l_serve_elo,
        "b_return_elo": r.l_return_elo,
        "b_n_matches": r.l_n_matches,
        "elo_diff": r.elo_diff,
        "p_elo": r.p_elo_winner,
        "serve_return_matchup": r.serve_return_matchup,
        "surface_hard": r.surface_hard,
        "surface_clay": r.surface_clay,
        "surface_grass": r.surface_grass,
        "level_G": r.level_G,
        "level_M": r.level_M,
        "best_of_5": r.best_of_5,
        "a_is_prov": r.w_is_provisional,
        "b_is_prov": r.l_is_provisional,
        "y": 1,
    })
    # Perspektywa przegranego (y=0)
    rows_sym.append({
        "year": r.year,
        "tourney_date": r.tourney_date,
        "a_overall_elo": r.l_overall_elo,
        "a_surf_elo": r.l_surf_elo,
        "a_serve_elo": r.l_serve_elo,
        "a_return_elo": r.l_return_elo,
        "a_n_matches": r.l_n_matches,
        "b_overall_elo": r.w_overall_elo,
        "b_surf_elo": r.w_surf_elo,
        "b_serve_elo": r.w_serve_elo,
        "b_return_elo": r.w_return_elo,
        "b_n_matches": r.w_n_matches,
        "elo_diff": -r.elo_diff,
        "p_elo": 1 - r.p_elo_winner,
        "serve_return_matchup": 1 - r.serve_return_matchup,
        "surface_hard": r.surface_hard,
        "surface_clay": r.surface_clay,
        "surface_grass": r.surface_grass,
        "level_G": r.level_G,
        "level_M": r.level_M,
        "best_of_5": r.best_of_5,
        "a_is_prov": r.l_is_provisional,
        "b_is_prov": r.w_is_provisional,
        "y": 0,
    })

sym = pd.DataFrame(rows_sym)
log(f"  Symetryczny dataset: {sym.shape}")

FEATURE_COLS = [
    "a_overall_elo", "a_surf_elo", "a_serve_elo", "a_return_elo", "a_n_matches",
    "b_overall_elo", "b_surf_elo", "b_serve_elo", "b_return_elo", "b_n_matches",
    "elo_diff", "p_elo", "serve_return_matchup",
    "surface_hard", "surface_clay", "surface_grass",
    "level_G", "level_M", "best_of_5",
    "a_is_prov", "b_is_prov",
]

# ─────────────────────────────────────────────
# 4. WALK-FORWARD VALIDATION
# ─────────────────────────────────────────────
log("\n=== ETAP 4: Walk-Forward Cross-Validation ===")

SPLITS = [
    (1990, 2002, 2004),
    (1990, 2004, 2008),
    (1990, 2008, 2012),
    (1990, 2012, 2016),
    (1990, 2016, 2020),
]
# Holdout: 2021-2025

LGBM_PARAMS = {
    "n_estimators": 2000,
    "learning_rate": 0.02,
    "num_leaves": 63,
    "min_child_samples": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_lambda": 1.0,
    "objective": "binary",
    "metric": "binary_logloss",
    "verbosity": -1,
    "n_jobs": -1,
}

wf_results = []
all_val_preds = []

for train_start, val_start, val_end in SPLITS:
    mask_train = (sym["year"] >= train_start) & (sym["year"] < val_start)
    mask_val = (sym["year"] >= val_start) & (sym["year"] < val_end)

    X_train = sym.loc[mask_train, FEATURE_COLS].values
    y_train = sym.loc[mask_train, "y"].values
    X_val = sym.loc[mask_val, FEATURE_COLS].values
    y_val = sym.loc[mask_val, "y"].values

    if len(X_train) == 0 or len(X_val) == 0:
        continue

    t1 = time.time()
    model = lgb.LGBMClassifier(**LGBM_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )

    p_val = model.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, p_val)
    bs = brier_score_loss(y_val, p_val)
    ll = log_loss(y_val, p_val)
    acc = accuracy_score(y_val, p_val > 0.5)
    dur = time.time() - t1

    result = {
        "split": f"{train_start}-{val_start} → {val_start}-{val_end}",
        "n_train": len(X_train),
        "n_val": len(X_val),
        "auc": round(auc, 4),
        "brier": round(bs, 4),
        "log_loss": round(ll, 4),
        "accuracy": round(acc, 4),
        "best_iter": model.best_iteration_,
        "duration_s": round(dur, 1),
    }
    wf_results.append(result)
    log(f"  {result['split']}: AUC={auc:.4f} Acc={acc:.4f} BS={bs:.4f} [{dur:.1f}s]", result)

    all_val_preds.append({"y_true": y_val, "y_pred": p_val})

# Podsumowanie WF
mean_auc = np.mean([r["auc"] for r in wf_results])
mean_acc = np.mean([r["accuracy"] for r in wf_results])
mean_bs = np.mean([r["brier"] for r in wf_results])
log(f"\n  WALK-FORWARD ŚREDNIE: AUC={mean_auc:.4f} Acc={mean_acc:.4f} BS={mean_bs:.4f}",
    {"mean_auc": mean_auc, "mean_acc": mean_acc, "mean_bs": mean_bs})

# ─────────────────────────────────────────────
# 5. FINAL MODEL — train na 1990-2020
# ─────────────────────────────────────────────
log("\n=== ETAP 5: Trenowanie finalnego modelu (1990-2020) ===")

mask_final_train = (sym["year"] >= 1990) & (sym["year"] < 2021)
mask_holdout = (sym["year"] >= 2021)

X_final = sym.loc[mask_final_train, FEATURE_COLS].values
y_final = sym.loc[mask_final_train, "y"].values
X_hold = sym.loc[mask_holdout, FEATURE_COLS].values
y_hold = sym.loc[mask_holdout, "y"].values

log(f"  Train: {len(X_final):,} | Holdout 2021-2025: {len(X_hold):,}")

t1 = time.time()
LGBM_FINAL = {**LGBM_PARAMS, "n_estimators": 3000, "learning_rate": 0.015}
final_model = lgb.LGBMClassifier(**LGBM_FINAL)
final_model.fit(
    X_final, y_final,
    eval_set=[(X_hold, y_hold)],
    callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(period=100)],
)
dur_final = time.time() - t1

p_hold = final_model.predict_proba(X_hold)[:, 1]
hold_auc = roc_auc_score(y_hold, p_hold)
hold_acc = accuracy_score(y_hold, p_hold > 0.5)
hold_bs = brier_score_loss(y_hold, p_hold)
hold_ll = log_loss(y_hold, p_hold)

log(f"  HOLDOUT 2021-2025: AUC={hold_auc:.4f} Acc={hold_acc:.4f} BS={hold_bs:.4f} [{dur_final:.1f}s]",
    {"hold_auc": hold_auc, "hold_acc": hold_acc, "hold_bs": hold_bs})

# ─────────────────────────────────────────────
# 6. FEATURE IMPORTANCE
# ─────────────────────────────────────────────
log("\n=== ETAP 6: Feature Importance ===")
importance = pd.DataFrame({
    "feature": FEATURE_COLS,
    "importance": final_model.feature_importances_,
}).sort_values("importance", ascending=False)

for _, row in importance.iterrows():
    log(f"  {row.feature}: {row.importance}")

# ─────────────────────────────────────────────
# 7. META-LEARNER (Logistic Regression stacking)
# ─────────────────────────────────────────────
log("\n=== ETAP 7: Meta-learner (Elo + LGBM stacking) ===")

# OOF predictions dla stacking
from sklearn.model_selection import TimeSeriesSplit

mask_stack = (sym["year"] >= 1990) & (sym["year"] < 2021)
X_stack = sym.loc[mask_stack, FEATURE_COLS].values
y_stack = sym.loc[mask_stack, "y"].values
p_elo_stack = sym.loc[mask_stack, "p_elo"].values

# 5-fold temporal CV dla OOF
n = len(X_stack)
tscv = TimeSeriesSplit(n_splits=5)
oof_lgbm = np.zeros(n)
oof_elo = p_elo_stack.copy()

for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_stack)):
    m = lgb.LGBMClassifier(**{**LGBM_PARAMS, "n_estimators": 500})
    m.fit(X_stack[tr_idx], y_stack[tr_idx], callbacks=[lgb.log_evaluation(period=-1)])
    oof_lgbm[val_idx] = m.predict_proba(X_stack[val_idx])[:, 1]
    log(f"  OOF fold {fold+1}/5 done")

# Meta features: [lgbm_oof, elo_oof]
X_meta = np.column_stack([oof_lgbm, oof_elo])
meta_lr = LogisticRegression(C=10.0, max_iter=1000)
meta_lr.fit(X_meta, y_stack)
meta_coefs = dict(zip(["lgbm_weight", "elo_weight"], meta_lr.coef_[0]))
log(f"  Meta-learner coefs: LGBM={meta_coefs['lgbm_weight']:.3f} Elo={meta_coefs['elo_weight']:.3f}", meta_coefs)

# Holdout z meta-learner
p_hold_lgbm = final_model.predict_proba(X_hold)[:, 1]
p_hold_elo = sym.loc[mask_holdout, "p_elo"].values
X_hold_meta = np.column_stack([p_hold_lgbm, p_hold_elo])
p_hold_ensemble = meta_lr.predict_proba(X_hold_meta)[:, 1]

ensemble_auc = roc_auc_score(y_hold, p_hold_ensemble)
ensemble_acc = accuracy_score(y_hold, p_hold_ensemble > 0.5)
ensemble_bs = brier_score_loss(y_hold, p_hold_ensemble)

log(f"\n  ENSEMBLE HOLDOUT: AUC={ensemble_auc:.4f} Acc={ensemble_acc:.4f} BS={ensemble_bs:.4f}",
    {"ensemble_auc": ensemble_auc, "ensemble_acc": ensemble_acc, "ensemble_bs": ensemble_bs})

# ─────────────────────────────────────────────
# 8. ZAPISZ MODELE
# ─────────────────────────────────────────────
log("\n=== ETAP 8: Zapis modeli ===")

ts = datetime.now().strftime("%Y%m%d_%H%M")
paths = {
    "lgbm": MODELS_PATH / f"lgbm_final_{ts}.joblib",
    "meta_lr": MODELS_PATH / f"meta_lr_{ts}.joblib",
    "feature_cols": MODELS_PATH / f"feature_cols_{ts}.json",
    "metrics": MODELS_PATH / f"metrics_{ts}.json",
}

joblib.dump(final_model, paths["lgbm"])
joblib.dump(meta_lr, paths["meta_lr"])

with open(paths["feature_cols"], "w") as f:
    json.dump(FEATURE_COLS, f, indent=2)

metrics = {
    "trained_at": ts,
    "n_train": len(X_final),
    "n_holdout": len(X_hold),
    "walk_forward": wf_results,
    "mean_wf_auc": round(mean_auc, 4),
    "mean_wf_accuracy": round(mean_acc, 4),
    "holdout_lgbm_auc": round(hold_auc, 4),
    "holdout_lgbm_accuracy": round(hold_acc, 4),
    "holdout_lgbm_brier": round(hold_bs, 4),
    "holdout_ensemble_auc": round(ensemble_auc, 4),
    "holdout_ensemble_accuracy": round(ensemble_acc, 4),
    "holdout_ensemble_brier": round(ensemble_bs, 4),
    "meta_coefs": meta_coefs,
    "feature_importance": importance.to_dict(orient="records"),
}

with open(paths["metrics"], "w") as f:
    json.dump(metrics, f, indent=2, default=str)

for name, path in paths.items():
    if Path(path).exists():
        size = Path(path).stat().st_size / 1024
        log(f"  ✅ {name}: {path} ({size:.0f} KB)")

# ─────────────────────────────────────────────
# 9. FINALNE PODSUMOWANIE
# ─────────────────────────────────────────────
total_time = time.time() - t0
log(f"\n{'='*60}")
log(f"TRENING ZAKOŃCZONY — {total_time/60:.1f} minut")
log(f"{'='*60}")
log(f"\n📊 WYNIKI FINALNE:")
log(f"  Walk-Forward AUC (śr.):     {mean_auc:.4f}")
log(f"  Walk-Forward Accuracy (śr.): {mean_acc:.4f}")
log(f"  Holdout LGBM AUC:            {hold_auc:.4f}")
log(f"  Holdout LGBM Accuracy:       {hold_acc:.4f}")
log(f"  Holdout ENSEMBLE AUC:        {ensemble_auc:.4f}")
log(f"  Holdout ENSEMBLE Accuracy:   {ensemble_acc:.4f}")
log(f"  Brier Score (ensemble):      {ensemble_bs:.4f}")
log(f"\n🏆 Benchmark: random=0.500, rank_model=0.620, target=0.650+")

print("\n✅ DONE — modele zapisane w /home/ubuntu/betatp/models/")
print(json.dumps({k: v for k, v in metrics.items() if k != "feature_importance"}, indent=2, default=str))
