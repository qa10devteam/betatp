"""
betatp.io — LightGBM v3
v2 + form features:
  - EWMA win-rate (α=0.1, per player+surface)
  - H2H wins/total (last 5 lat)
  - Fatigue: mecze w ostatnich 14/28 dniach
  - Win-streak (current)
  - Serve%/Return% rolling (last 20 meczów)
Holdout: 2024-2026 (aktualne!)
"""
import sys, time, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score
import joblib

TML_PATH = Path("/home/ubuntu/TML-Database")
MODELS_PATH = Path("/home/ubuntu/betatp/models")
MODELS_PATH.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── 1. WCZYTAJ ──────────────────────────────────────────────────────────────
log("=== v3 | ETAP 1: Wczytywanie ===")
dfs = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 1990: continue
    df = pd.read_csv(f, low_memory=False)
    df["year"] = yr
    dfs.append(df)

raw = pd.concat(dfs, ignore_index=True)
raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
raw = raw.dropna(subset=["tourney_date","winner_id","loser_id"])
raw = raw.sort_values("tourney_date").reset_index(drop=True)

surf_map = {"Hard":"Hard","Clay":"Clay","Grass":"Grass","Carpet":"Hard","Indoor Hard":"Hard","Acrylic":"Hard"}
raw["surface"] = raw["surface"].map(surf_map).fillna("Hard")
level_map = {"G":"G","M":"M","A":"500","D":"250","F":"F","C":"250","S":"500","250":"250","500":"500"}
raw["tourney_level"] = raw["tourney_level"].map(level_map).fillna("250")
round_map = {"F":7,"SF":6,"QF":5,"R16":4,"R32":3,"R64":2,"R128":1,"RR":4,"BR":5,"ER":1,"Q1":1,"Q2":2,"Q3":3}
raw["round_num"] = raw["round"].map(round_map).fillna(3).astype(int)

for c in ["winner_rank","loser_rank","winner_rank_points","loser_rank_points",
          "winner_age","loser_age","winner_ht","loser_ht",
          "w_svpt","w_1stIn","w_1stWon","w_2ndWon","w_SvGms",
          "l_svpt","l_1stIn","l_1stWon","l_2ndWon","l_SvGms"]:
    raw[c] = pd.to_numeric(raw.get(c, pd.Series(dtype=float)), errors="coerce")

log(f"  {len(raw):,} meczów | {raw.tourney_date.min().date()} → {raw.tourney_date.max().date()}")

# ─── 2. ELO + FORM STATE ─────────────────────────────────────────────────────
log("=== v3 | ETAP 2: Elo + Form features (chronologicznie) ===")
from engine.elo import EloEngine
elo = EloEngine()
t0 = time.time()

ALPHA = 0.10        # EWMA decay
H2H_WINDOW_DAYS = 5*365  # 5 lat
FATIGUE_SHORT = 14  # dni
FATIGUE_LONG  = 28  # dni
STREAK_MAX = 20     # cap streak

# Stan per gracz
ewma_win  = defaultdict(lambda: 0.5)      # ogólny
ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))  # per surface
h2h       = defaultdict(lambda: deque(maxlen=30))  # (date, w_is_A)
match_dates = defaultdict(list)            # ostatnie daty meczów
streak    = defaultdict(int)               # + = seria wygranych, - = seria przegranych
srv_ewma  = defaultdict(lambda: 0.60)     # serve% ewma
ret_ewma  = defaultdict(lambda: 0.35)     # return% ewma

def get_form(pid, pdate, surf):
    # Fatigue
    fat14 = sum(1 for d in match_dates[pid] if (pdate-d).days <= FATIGUE_SHORT)
    fat28 = sum(1 for d in match_dates[pid] if (pdate-d).days <= FATIGUE_LONG)
    return {
        "ewma_win": ewma_win[pid],
        "ewma_surf": ewma_surf[pid][surf],
        "fat14": fat14,
        "fat28": fat28,
        "streak": min(max(streak[pid], -STREAK_MAX), STREAK_MAX),
        "srv_pct": srv_ewma[pid],
        "ret_pct": ret_ewma[pid],
    }

def get_h2h(aid, bid, pdate):
    cutoff = pdate - timedelta(days=H2H_WINDOW_DAYS)
    # szukaj w obu kierunkach
    key = tuple(sorted([aid, bid]))
    wins_a = sum(1 for d,w in h2h[key] if d >= cutoff and w == aid)
    wins_b = sum(1 for d,w in h2h[key] if d >= cutoff and w == bid)
    total  = wins_a + wins_b
    return wins_a / total if total > 0 else 0.5, total

def update_form(wid, lid, surf, wdate,
                w_svpt=None, w_1stWon=None, w_2ndWon=None, w_SvGms=None,
                l_svpt=None, l_1stWon=None, l_2ndWon=None, l_SvGms=None):
    # EWMA
    ewma_win[wid] = ALPHA * 1 + (1-ALPHA) * ewma_win[wid]
    ewma_win[lid] = ALPHA * 0 + (1-ALPHA) * ewma_win[lid]
    ewma_surf[wid][surf] = ALPHA * 1 + (1-ALPHA) * ewma_surf[wid][surf]
    ewma_surf[lid][surf] = ALPHA * 0 + (1-ALPHA) * ewma_surf[lid][surf]
    # Streak
    streak[wid] = streak[wid]+1 if streak[wid] >= 0 else 1
    streak[lid] = streak[lid]-1 if streak[lid] <= 0 else -1
    # H2H
    key = tuple(sorted([wid, lid]))
    h2h[key].append((wdate, wid))
    # Match dates (ostatnie 28 dni)
    match_dates[wid].append(wdate)
    match_dates[lid].append(wdate)
    match_dates[wid] = [d for d in match_dates[wid] if (wdate-d).days <= FATIGUE_LONG+1]
    match_dates[lid] = [d for d in match_dates[lid] if (wdate-d).days <= FATIGUE_LONG+1]
    # Serve/Return %
    if w_svpt and w_svpt > 0 and w_1stWon and w_2ndWon:
        srv_pct_w = (w_1stWon + w_2ndWon) / w_svpt
        srv_ewma[wid] = ALPHA * srv_pct_w + (1-ALPHA) * srv_ewma[wid]
    if l_svpt and l_svpt > 0 and l_1stWon and l_2ndWon:
        srv_pct_l = (l_1stWon + l_2ndWon) / l_svpt
        srv_ewma[lid] = ALPHA * srv_pct_l + (1-ALPHA) * srv_ewma[lid]
    # Return% = 1 - opponent serve%
    if l_svpt and l_svpt > 0 and l_1stWon and l_2ndWon:
        ret_ewma[wid] = ALPHA * (1 - (l_1stWon+l_2ndWon)/l_svpt) + (1-ALPHA) * ret_ewma[wid]
    if w_svpt and w_svpt > 0 and w_1stWon and w_2ndWon:
        ret_ewma[lid] = ALPHA * (1 - (w_1stWon+w_2ndWon)/w_svpt) + (1-ALPHA) * ret_ewma[lid]

pre = []
for i, row in enumerate(raw.itertuples(index=False)):
    wid, lid = str(row.winner_id), str(row.loser_id)
    surf, level = str(row.surface), str(row.tourney_level)
    mdate = row.tourney_date.date()

    # Elo pre-match
    we = elo.get_or_create(wid)
    le = elo.get_or_create(lid)
    w_srf = elo.get_blended_surface_elo(wid, surf)
    l_srf = elo.get_blended_surface_elo(lid, surf)
    p_w = elo.win_probability(w_srf, l_srf)

    # Form pre-match
    wf = get_form(wid, mdate, surf)
    lf = get_form(lid, mdate, surf)
    h2h_pw, h2h_n = get_h2h(wid, lid, mdate)

    # Static features
    def _f(v, default): return float(v) if not pd.isna(v) else default
    w_rank = _f(row.winner_rank, 500.); l_rank = _f(row.loser_rank, 500.)
    w_rp   = _f(row.winner_rank_points, 0.); l_rp = _f(row.loser_rank_points, 0.)
    w_age  = _f(row.winner_age, 25.); l_age = _f(row.loser_age, 25.)
    w_ht   = _f(row.winner_ht, 185.); l_ht  = _f(row.loser_ht, 185.)
    w_hand = 1 if str(getattr(row,"winner_hand","R")) == "L" else 0
    l_hand = 1 if str(getattr(row,"loser_hand","R")) == "L" else 0
    indoor = 1 if str(getattr(row,"indoor","O")) == "I" else 0
    round_n = getattr(row,"round_num",3)

    pre.append({
        "tourney_date": row.tourney_date, "year": row.year,
        # Winner
        "w_elo":we.overall,"w_srf_elo":w_srf,"w_srv_elo":we.serve,"w_ret_elo":we.return_elo,
        "w_n":we.n_matches,"w_prov":int(we.is_provisional),
        "w_rank":w_rank,"w_rp":w_rp,"w_age":w_age,"w_ht":w_ht,"w_hand":w_hand,
        "w_ewma":wf["ewma_win"],"w_ewma_surf":wf["ewma_surf"],
        "w_fat14":wf["fat14"],"w_fat28":wf["fat28"],"w_streak":wf["streak"],
        "w_srv_pct":wf["srv_pct"],"w_ret_pct":wf["ret_pct"],
        # Loser
        "l_elo":le.overall,"l_srf_elo":l_srf,"l_srv_elo":le.serve,"l_ret_elo":le.return_elo,
        "l_n":le.n_matches,"l_prov":int(le.is_provisional),
        "l_rank":l_rank,"l_rp":l_rp,"l_age":l_age,"l_ht":l_ht,"l_hand":l_hand,
        "l_ewma":lf["ewma_win"],"l_ewma_surf":lf["ewma_surf"],
        "l_fat14":lf["fat14"],"l_fat28":lf["fat28"],"l_streak":lf["streak"],
        "l_srv_pct":lf["srv_pct"],"l_ret_pct":lf["ret_pct"],
        # Derived
        "elo_diff":w_srf-l_srf,"p_elo":p_w,
        "srv_ret_matchup":elo.win_probability(we.serve,le.return_elo),
        "rank_diff":np.log1p(l_rank)-np.log1p(w_rank),
        "rp_diff":np.log1p(w_rp)-np.log1p(l_rp),
        "age_diff":w_age-l_age,"ht_diff":w_ht-l_ht,
        "ewma_diff":wf["ewma_win"]-lf["ewma_win"],
        "ewma_surf_diff":wf["ewma_surf"]-lf["ewma_surf"],
        "streak_diff":wf["streak"]-lf["streak"],
        "fat14_diff":wf["fat14"]-lf["fat14"],
        "srv_pct_diff":wf["srv_pct"]-lf["srv_pct"],
        "h2h_pw":h2h_pw,"h2h_n":h2h_n,
        # Context
        "surf_hard":int(surf=="Hard"),"surf_clay":int(surf=="Clay"),"surf_grass":int(surf=="Grass"),
        "level_G":int(level=="G"),"level_M":int(level=="M"),
        "best_of_5":int(getattr(row,"best_of",3)==5),
        "indoor":indoor,"round_num":round_n,
    })

    # Update state
    def _i(v): return int(v) if v and not (isinstance(v,float) and np.isnan(v)) else None
    elo.update_match(wid,lid,surf,level,mdate,
        w_svpt=_i(row.w_svpt),w_1stWon=_i(row.w_1stWon),w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt),l_1stWon=_i(row.l_1stWon),l_2ndWon=_i(row.l_2ndWon))
    w_SvGms = _f(getattr(row,"w_SvGms",None), None) if hasattr(row,"w_SvGms") else None
    update_form(wid,lid,surf,mdate,
        w_svpt=_i(row.w_svpt),w_1stWon=_i(row.w_1stWon),w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt),l_1stWon=_i(row.l_1stWon),l_2ndWon=_i(row.l_2ndWon))

    if (i+1) % 25000 == 0:
        log(f"  [{i+1:,}/{len(raw):,}] {time.time()-t0:.0f}s")

log(f"  State gotowe w {time.time()-t0:.1f}s")
df = pd.DataFrame(pre)

# ─── 3. RANDOM A/B ───────────────────────────────────────────────────────────
log("=== v3 | ETAP 3: Random A/B ===")
rng = np.random.default_rng(42)
flip = rng.integers(0,2,size=len(df)).astype(bool)

W_FEATS = ["w_elo","w_srf_elo","w_srv_elo","w_ret_elo","w_n","w_prov",
           "w_rank","w_rp","w_age","w_ht","w_hand",
           "w_ewma","w_ewma_surf","w_fat14","w_fat28","w_streak","w_srv_pct","w_ret_pct"]
L_FEATS = [f.replace("w_","l_") for f in W_FEATS]
DIFF_FEATS = ["elo_diff","p_elo","srv_ret_matchup","rank_diff","rp_diff","age_diff","ht_diff",
              "ewma_diff","ewma_surf_diff","streak_diff","fat14_diff","srv_pct_diff"]
CTX_FEATS = ["surf_hard","surf_clay","surf_grass","level_G","level_M","best_of_5","indoor","round_num",
             "h2h_pw","h2h_n"]

rows = []
for r, f in zip(df.itertuples(index=False), flip):
    if f:
        a = {af: getattr(r, wf) for af, wf in zip([x.replace("w_","a_") for x in W_FEATS], W_FEATS)}
        b = {bf: getattr(r, lf) for bf, lf in zip([x.replace("l_","b_") for x in L_FEATS], L_FEATS)}
        diffs = {k: getattr(r,k) for k in DIFF_FEATS}
        y = 1
    else:
        a = {af: getattr(r, lf) for af, lf in zip([x.replace("w_","a_") for x in W_FEATS], L_FEATS)}
        b = {bf: getattr(r, wf) for bf, wf in zip([x.replace("l_","b_") for x in L_FEATS], W_FEATS)}
        # neguj diff-features
        diffs = {}
        for k in DIFF_FEATS:
            v = getattr(r,k)
            if k == "p_elo": diffs[k] = 1-v
            elif k == "h2h_pw": diffs[k] = 1-v
            else: diffs[k] = -v
        y = 0

    ctx = {k: getattr(r,k) for k in CTX_FEATS}
    if not f:
        ctx["h2h_pw"] = 1 - ctx["h2h_pw"]

    row_dict = {"year": r.year, **a, **b, **diffs, **ctx, "y": y}
    rows.append(row_dict)

ds = pd.DataFrame(rows)
log(f"  Dataset: {ds.shape} | balance: {ds.y.mean():.3f}")
FEAT_COLS = [c for c in ds.columns if c not in ("year","y")]

# ─── 4. WALK-FORWARD ─────────────────────────────────────────────────────────
log("=== v3 | ETAP 4: Walk-Forward ===")
SPLITS = [
    (1990,2008,2012),(1990,2012,2016),(1990,2016,2020),
    (1990,2020,2022),(1990,2022,2024),
]
LGBM_P = {
    "n_estimators":2000,"learning_rate":0.03,"num_leaves":63,
    "min_child_samples":50,"subsample":0.8,"colsample_bytree":0.7,
    "reg_lambda":2.0,"objective":"binary","metric":"auc","verbosity":-1,"n_jobs":-1,
}
wf = []
for tr_start,val_start,val_end in SPLITS:
    Xtr = ds.loc[(ds.year>=tr_start)&(ds.year<val_start),FEAT_COLS]
    ytr = ds.loc[(ds.year>=tr_start)&(ds.year<val_start),"y"]
    Xv  = ds.loc[(ds.year>=val_start)&(ds.year<val_end),FEAT_COLS]
    yv  = ds.loc[(ds.year>=val_start)&(ds.year<val_end),"y"]
    if len(Xtr)==0 or len(Xv)==0: continue
    t1=time.time()
    m=lgb.LGBMClassifier(**LGBM_P)
    m.fit(Xtr,ytr,eval_set=[(Xv,yv)],
          callbacks=[lgb.early_stopping(50,verbose=False),lgb.log_evaluation(-1)])
    p=m.predict_proba(Xv)[:,1]
    res={"split":f"{tr_start}-{val_start}→{val_end}",
         "n_tr":len(Xtr),"n_val":len(Xv),
         "auc":round(roc_auc_score(yv,p),4),
         "acc":round(accuracy_score(yv,p>0.5),4),
         "bs":round(brier_score_loss(yv,p),4),
         "dur":round(time.time()-t1,1)}
    wf.append(res)
    log(f"  {res['split']}: AUC={res['auc']} Acc={res['acc']} BS={res['bs']} [{res['dur']}s]")

mean_auc=np.mean([r["auc"] for r in wf])
mean_acc=np.mean([r["acc"] for r in wf])
log(f"\n  WF ŚREDNIE: AUC={mean_auc:.4f} Acc={mean_acc:.4f}")

# ─── 5. FINAL MODEL ──────────────────────────────────────────────────────────
log("=== v3 | ETAP 5: Final (train≤2023, holdout 2024-2026) ===")
Xfin=ds.loc[ds.year<=2023,FEAT_COLS]; yfin=ds.loc[ds.year<=2023,"y"]
Xho=ds.loc[ds.year>=2024,FEAT_COLS];  yho=ds.loc[ds.year>=2024,"y"]
log(f"  Train: {len(Xfin):,} | Holdout 2024-2026: {len(Xho):,}")

LGBM_FIN={**LGBM_P,"n_estimators":3000,"learning_rate":0.02}
t1=time.time()
final=lgb.LGBMClassifier(**LGBM_FIN)
final.fit(Xfin,yfin,eval_set=[(Xho,yho)],
          callbacks=[lgb.early_stopping(100,verbose=False),lgb.log_evaluation(200)])
pho=final.predict_proba(Xho)[:,1]
ho_auc=roc_auc_score(yho,pho)
ho_acc=accuracy_score(yho,pho>0.5)
ho_bs=brier_score_loss(yho,pho)
log(f"  HOLDOUT 2024-2026: AUC={ho_auc:.4f} Acc={ho_acc:.4f} BS={ho_bs:.4f} [{time.time()-t1:.1f}s]")

# ─── 6. FEATURE IMPORTANCE ───────────────────────────────────────────────────
imp=sorted(zip(FEAT_COLS,final.feature_importances_),key=lambda x:-x[1])
log("\n=== v3 | Feature Importance TOP-15 ===")
for feat,fi in imp[:15]:
    log(f"  {feat}: {fi}")

# ─── 7. ZAPIS ────────────────────────────────────────────────────────────────
now=datetime.now().strftime("%Y%m%d_%H%M")
joblib.dump(final, MODELS_PATH/f"lgbm_v3_{now}.joblib")
joblib.dump(FEAT_COLS, MODELS_PATH/f"feat_cols_v3_{now}.joblib")

# Zapisz też state form (elo + ewma etc.) do inference
inference_state = {
    "elo_ratings": elo.ratings,
    "ewma_win": dict(ewma_win),
    "ewma_surf": {k: dict(v) for k,v in ewma_surf.items()},
    "streak": dict(streak),
    "srv_ewma": dict(srv_ewma),
    "ret_ewma": dict(ret_ewma),
}
joblib.dump(inference_state, MODELS_PATH/f"inference_state_v3_{now}.joblib")

metrics={
    "version":"v3",
    "trained_at":now,
    "train_period":"1990-2023",
    "holdout_period":"2024-2026",
    "n_train":len(Xfin),"n_holdout":len(Xho),
    "n_features":len(FEAT_COLS),
    "walk_forward":wf,
    "mean_wf_auc":round(mean_auc,4),"mean_wf_acc":round(mean_acc,4),
    "holdout_auc":round(ho_auc,4),"holdout_acc":round(ho_acc,4),"holdout_bs":round(ho_bs,4),
    "feature_importance":[{"feat":f,"imp":int(i)} for f,i in imp],
}
with open(MODELS_PATH/f"metrics_v3_{now}.json","w") as f:
    json.dump(metrics,f,indent=2)

log("\n"+"="*60)
log(f"v3 DONE | AUC={ho_auc:.4f} | Acc={ho_acc:.4f} | BS={ho_bs:.4f} | features={len(FEAT_COLS)}")
log("="*60)
print(json.dumps({k:v for k,v in metrics.items() if k!="feature_importance"},indent=2))
