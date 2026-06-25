"""
betatp.io — LightGBM v2
Właściwe A/B labelowanie: random assignment (nie symetria lustrzana)
Features: Elo 6-variant + rank + age + hand + surface + level + round + indoor
Holdout: 2024-2025-2026 (aktualne!)
"""
import sys, os, time, json, warnings, random
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss, accuracy_score
from sklearn.calibration import calibration_curve
import joblib

TML_PATH = Path("/home/ubuntu/TML-Database")
MODELS_PATH = Path("/home/ubuntu/betatp/models")
MODELS_PATH.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── 1. WCZYTAJ DANE ────────────────────────────────────────────────────────
log("=== v2 | ETAP 1: Wczytywanie 1990-2026 ===")
dfs = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 1990: continue
    df = pd.read_csv(f, low_memory=False)
    df["year"] = yr
    dfs.append(df)

raw = pd.concat(dfs, ignore_index=True)
raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
raw = raw.dropna(subset=["tourney_date", "winner_id", "loser_id"])
raw = raw.sort_values("tourney_date").reset_index(drop=True)

surf_map = {"Hard":"Hard","Clay":"Clay","Grass":"Grass","Carpet":"Hard","Indoor Hard":"Hard","Acrylic":"Hard"}
raw["surface"] = raw["surface"].map(surf_map).fillna("Hard")

level_map = {"G":"G","M":"M","A":"500","D":"250","F":"F","C":"250","S":"500","250":"250","500":"500"}
raw["tourney_level"] = raw["tourney_level"].map(level_map).fillna("250")

round_map = {
    "F":7,"SF":6,"QF":5,"R16":4,"R32":3,"R64":2,"R128":1,
    "RR":4,"BR":5,"ER":1,"Q1":1,"Q2":2,"Q3":3
}
raw["round_num"] = raw["round"].map(round_map).fillna(3).astype(int)

for c in ["winner_rank","loser_rank","winner_rank_points","loser_rank_points",
          "winner_age","loser_age","winner_ht","loser_ht"]:
    raw[c] = pd.to_numeric(raw.get(c, pd.Series(dtype=float)), errors="coerce")

log(f"  Wczytano {len(raw):,} meczów | zakres: {raw.tourney_date.min().date()} → {raw.tourney_date.max().date()}")

# ─── 2. ELO ─────────────────────────────────────────────────────────────────
log("=== v2 | ETAP 2: Elo 6-variant ===")
from engine.elo import EloEngine
elo = EloEngine()
t0 = time.time()

for c in ["w_svpt","w_1stWon","w_2ndWon","l_svpt","l_1stWon","l_2ndWon"]:
    raw[c] = pd.to_numeric(raw.get(c, pd.Series(dtype=float)), errors="coerce")

pre = []
for i, row in enumerate(raw.itertuples(index=False)):
    wid, lid = str(row.winner_id), str(row.loser_id)
    surf, level = str(row.surface), str(row.tourney_level)

    we = elo.get_or_create(wid)
    le = elo.get_or_create(lid)
    w_srf = elo.get_blended_surface_elo(wid, surf)
    l_srf = elo.get_blended_surface_elo(lid, surf)
    p_w = elo.win_probability(w_srf, l_srf)

    # Rank features (log-transform, handle NaN)
    w_rank = row.winner_rank if not pd.isna(row.winner_rank) else 500.0
    l_rank = row.loser_rank  if not pd.isna(row.loser_rank)  else 500.0
    w_rp   = row.winner_rank_points if not pd.isna(row.winner_rank_points) else 0.0
    l_rp   = row.loser_rank_points  if not pd.isna(row.loser_rank_points)  else 0.0
    w_age  = row.winner_age if not pd.isna(row.winner_age) else 25.0
    l_age  = row.loser_age  if not pd.isna(row.loser_age)  else 25.0
    w_ht   = row.winner_ht  if not pd.isna(row.winner_ht)  else 185.0
    l_ht   = row.loser_ht   if not pd.isna(row.loser_ht)   else 185.0
    w_hand = 1 if str(getattr(row,"winner_hand","R")) == "L" else 0
    l_hand = 1 if str(getattr(row,"loser_hand","R")) == "L" else 0
    indoor = 1 if str(getattr(row,"indoor","O")) == "I" else 0
    round_n = getattr(row, "round_num", 3)

    pre.append({
        "tourney_date": row.tourney_date, "year": row.year,
        "surface": surf, "tourney_level": level,
        "winner_id": wid, "loser_id": lid,
        # winner pre-match
        "w_elo": we.overall, "w_srf_elo": w_srf,
        "w_srv_elo": we.serve, "w_ret_elo": we.return_elo,
        "w_n": we.n_matches, "w_prov": int(we.is_provisional),
        "w_rank": w_rank, "w_rp": w_rp, "w_age": w_age,
        "w_ht": w_ht, "w_hand": w_hand,
        # loser pre-match
        "l_elo": le.overall, "l_srf_elo": l_srf,
        "l_srv_elo": le.serve, "l_ret_elo": le.return_elo,
        "l_n": le.n_matches, "l_prov": int(le.is_provisional),
        "l_rank": l_rank, "l_rp": l_rp, "l_age": l_age,
        "l_ht": l_ht, "l_hand": l_hand,
        # derived
        "elo_diff": w_srf - l_srf, "p_elo": p_w,
        "srv_ret_matchup": elo.win_probability(we.serve, le.return_elo),
        "rank_diff": np.log1p(l_rank) - np.log1p(w_rank),
        "rp_diff": np.log1p(w_rp) - np.log1p(l_rp),
        "age_diff": w_age - l_age,
        "ht_diff": w_ht - l_ht,
        # context
        "surf_hard": int(surf=="Hard"), "surf_clay": int(surf=="Clay"),
        "surf_grass": int(surf=="Grass"),
        "level_G": int(level=="G"), "level_M": int(level=="M"),
        "best_of_5": int(getattr(row,"best_of",3)==5),
        "indoor": indoor, "round_num": round_n,
    })

    mdate = row.tourney_date.date()
    def _i(v): return int(v) if v and not (isinstance(v, float) and np.isnan(v)) else None
    elo.update_match(
        winner_id=wid, loser_id=lid,
        surface=surf, tourney_level=level, match_date=mdate,
        w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon),
    )
    if (i+1) % 25000 == 0:
        log(f"  [{i+1:,}/{len(raw):,}] {time.time()-t0:.0f}s")

log(f"  Elo gotowe w {time.time()-t0:.1f}s — {len(elo.ratings)} graczy")
df = pd.DataFrame(pre)

# ─── 3. RANDOM A/B DATASET (v2 key fix) ─────────────────────────────────────
log("=== v2 | ETAP 3: Random A/B dataset (bez symetrii) ===")
rng = np.random.default_rng(42)
flip = rng.integers(0, 2, size=len(df)).astype(bool)

FEAT_W = ["w_elo","w_srf_elo","w_srv_elo","w_ret_elo","w_n","w_prov",
          "w_rank","w_rp","w_age","w_ht","w_hand"]
FEAT_L = ["l_elo","l_srf_elo","l_srv_elo","l_ret_elo","l_n","l_prov",
          "l_rank","l_rp","l_age","l_ht","l_hand"]
FEAT_COMMON = ["surf_hard","surf_clay","surf_grass","level_G","level_M",
               "best_of_5","indoor","round_num"]

rows = []
for i, (r, f) in enumerate(zip(df.itertuples(index=False), flip)):
    if f:  # A=winner
        a = {k.replace("w_","a_"): getattr(r, k) for k in [x for x in dir(r) if x.startswith("w_")]}
        b = {k.replace("l_","b_"): getattr(r, k) for k in [x for x in dir(r) if x.startswith("l_")]}
        elo_d = r.elo_diff
        p_e   = r.p_elo
        srm   = r.srv_ret_matchup
        rank_d = r.rank_diff
        rp_d   = r.rp_diff
        age_d  = r.age_diff
        ht_d   = r.ht_diff
        y = 1
    else:  # A=loser
        a = {k.replace("l_","a_"): getattr(r, k) for k in [x for x in dir(r) if x.startswith("l_")]}
        b = {k.replace("w_","b_"): getattr(r, k) for k in [x for x in dir(r) if x.startswith("w_")]}
        elo_d  = -r.elo_diff
        p_e    = 1 - r.p_elo
        srm    = 1 - r.srv_ret_matchup
        rank_d = -r.rank_diff
        rp_d   = -r.rp_diff
        age_d  = -r.age_diff
        ht_d   = -r.ht_diff
        y = 0

    row_dict = {
        "year": r.year,
        "a_elo": a.get("a_elo",0), "a_srf_elo": a.get("a_srf_elo",0),
        "a_srv_elo": a.get("a_srv_elo",0), "a_ret_elo": a.get("a_ret_elo",0),
        "a_n": a.get("a_n",0), "a_prov": a.get("a_prov",0),
        "a_rank": a.get("a_rank",500), "a_rp": a.get("a_rp",0),
        "a_age": a.get("a_age",25), "a_ht": a.get("a_ht",185), "a_hand": a.get("a_hand",0),
        "b_elo": b.get("b_elo",0), "b_srf_elo": b.get("b_srf_elo",0),
        "b_srv_elo": b.get("b_srv_elo",0), "b_ret_elo": b.get("b_ret_elo",0),
        "b_n": b.get("b_n",0), "b_prov": b.get("b_prov",0),
        "b_rank": b.get("b_rank",500), "b_rp": b.get("b_rp",0),
        "b_age": b.get("b_age",25), "b_ht": b.get("b_ht",185), "b_hand": b.get("b_hand",0),
        "elo_diff": elo_d, "p_elo": p_e, "srv_ret_matchup": srm,
        "rank_diff": rank_d, "rp_diff": rp_d, "age_diff": age_d, "ht_diff": ht_d,
        "surf_hard": r.surf_hard, "surf_clay": r.surf_clay, "surf_grass": r.surf_grass,
        "level_G": r.level_G, "level_M": r.level_M, "best_of_5": r.best_of_5,
        "indoor": r.indoor, "round_num": r.round_num,
        "y": y,
    }
    rows.append(row_dict)

ds = pd.DataFrame(rows)
log(f"  Dataset: {ds.shape} | y-balance: {ds.y.mean():.3f} (target=0.500)")

FEAT_COLS = [c for c in ds.columns if c not in ("year","y")]

# ─── 4. WALK-FORWARD ─────────────────────────────────────────────────────────
log("=== v2 | ETAP 4: Walk-Forward (holdout=2024+) ===")

SPLITS = [
    (1990, 2008, 2012),
    (1990, 2012, 2016),
    (1990, 2016, 2020),
    (1990, 2020, 2022),
    (1990, 2022, 2024),
]

LGBM_P = {
    "n_estimators": 2000, "learning_rate": 0.03,
    "num_leaves": 63, "min_child_samples": 50,
    "subsample": 0.8, "colsample_bytree": 0.7,
    "reg_lambda": 2.0, "objective": "binary",
    "metric": "auc", "verbosity": -1, "n_jobs": -1,
}

wf = []
for tr_start, val_start, val_end in SPLITS:
    Xtr = ds.loc[(ds.year>=tr_start)&(ds.year<val_start), FEAT_COLS]
    ytr = ds.loc[(ds.year>=tr_start)&(ds.year<val_start), "y"]
    Xv  = ds.loc[(ds.year>=val_start)&(ds.year<val_end),  FEAT_COLS]
    yv  = ds.loc[(ds.year>=val_start)&(ds.year<val_end),  "y"]
    if len(Xtr)==0 or len(Xv)==0: continue
    t1 = time.time()
    m = lgb.LGBMClassifier(**LGBM_P)
    m.fit(Xtr, ytr,
          eval_set=[(Xv, yv)],
          callbacks=[lgb.early_stopping(50,verbose=False), lgb.log_evaluation(-1)])
    p = m.predict_proba(Xv)[:,1]
    res = {
        "split": f"{tr_start}-{val_start}→{val_end}",
        "n_tr": len(Xtr), "n_val": len(Xv),
        "auc": round(roc_auc_score(yv,p),4),
        "acc": round(accuracy_score(yv,p>0.5),4),
        "bs":  round(brier_score_loss(yv,p),4),
        "dur": round(time.time()-t1,1),
    }
    wf.append(res)
    log(f"  {res['split']}: AUC={res['auc']} Acc={res['acc']} BS={res['bs']} [{res['dur']}s]")

mean_auc = np.mean([r["auc"] for r in wf])
mean_acc = np.mean([r["acc"] for r in wf])
log(f"\n  WF ŚREDNIE: AUC={mean_auc:.4f} Acc={mean_acc:.4f}")

# ─── 5. FINAL MODEL — train 1990-2023, holdout 2024-2026 ─────────────────────
log("=== v2 | ETAP 5: Final model (train≤2023, holdout 2024-2026) ===")
Xfin = ds.loc[ds.year<=2023, FEAT_COLS]
yfin = ds.loc[ds.year<=2023, "y"]
Xho  = ds.loc[ds.year>=2024, FEAT_COLS]
yho  = ds.loc[ds.year>=2024, "y"]
log(f"  Train: {len(Xfin):,} | Holdout 2024-2026: {len(Xho):,}")

LGBM_FIN = {**LGBM_P, "n_estimators":3000, "learning_rate":0.02}
t1 = time.time()
final = lgb.LGBMClassifier(**LGBM_FIN)
final.fit(Xfin, yfin,
          eval_set=[(Xho, yho)],
          callbacks=[lgb.early_stopping(100,verbose=False), lgb.log_evaluation(200)])
pho = final.predict_proba(Xho)[:,1]
ho_auc = roc_auc_score(yho, pho)
ho_acc = accuracy_score(yho, pho>0.5)
ho_bs  = brier_score_loss(yho, pho)
log(f"  HOLDOUT 2024-2026: AUC={ho_auc:.4f} Acc={ho_acc:.4f} BS={ho_bs:.4f} [{time.time()-t1:.1f}s]")

# ─── 6. FEATURE IMPORTANCE ───────────────────────────────────────────────────
imp = sorted(zip(FEAT_COLS, final.feature_importances_), key=lambda x: -x[1])
log("\n=== v2 | Feature Importance TOP-10 ===")
for feat, fi in imp[:10]:
    log(f"  {feat}: {fi}")

# ─── 7. ZAPIS ────────────────────────────────────────────────────────────────
now = datetime.now().strftime("%Y%m%d_%H%M")
joblib.dump(final, MODELS_PATH / f"lgbm_v2_{now}.joblib")
joblib.dump(FEAT_COLS, MODELS_PATH / f"feat_cols_v2_{now}.joblib")

metrics = {
    "version": "v2",
    "trained_at": now,
    "train_period": "1990-2023",
    "holdout_period": "2024-2026",
    "n_train": len(Xfin),
    "n_holdout": len(Xho),
    "walk_forward": wf,
    "mean_wf_auc": round(mean_auc,4),
    "mean_wf_acc": round(mean_acc,4),
    "holdout_auc": round(ho_auc,4),
    "holdout_acc": round(ho_acc,4),
    "holdout_bs":  round(ho_bs,4),
    "feature_importance": [{"feat":f,"imp":int(i)} for f,i in imp],
}
with open(MODELS_PATH / f"metrics_v2_{now}.json","w") as f:
    json.dump(metrics, f, indent=2)

log("\n" + "="*60)
log(f"v2 DONE | AUC_holdout={ho_auc:.4f} | Acc={ho_acc:.4f} | BS={ho_bs:.4f}")
log("="*60)
print(json.dumps({k:v for k,v in metrics.items() if k!="feature_importance"}, indent=2))
