"""
betatp.io — LightGBM v4 FINAL (VALUE BETTING MODEL)
=====================================================
Fundamentalna zmiana vs v1/v2/v3:
  - usunięto elo_diff, rank_diff, rp_diff — market (Pinnacle) to już wie
  - pin_prob_w jako BASELINE feature (rynek)
  - model uczy się RESIDUALU: co rynek systematycznie pomija?
  - dodatkowe features: fatigue, H2H trend, forma EWMA, change surface/indoor

Architektura:
  - Feature X = [pin_prob_w, form_delta, context_alpha]
  - Target y = kto wygrał (A/B random)
  - Oczekiwany AUC ≈ 0.70-0.74 (realny = rynkowy + marginalny edge)
  - Kalibracja: model_prob vs pin_prob → market_edge

Walk-Forward: 2004→2026 (mecze z Pinnacle)
Holdout: 2024-2026
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

TML_PATH    = Path("/home/ubuntu/TML-Database")
ODDS_PATH   = Path("/home/ubuntu/betatp/data/matches_with_odds.parquet")
MODELS_PATH = Path("/home/ubuntu/betatp/models")
MODELS_PATH.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── 1. WCZYTAJ ODDS ─────────────────────────────────────────────────────────
log("=== v4 | ETAP 1: Wczytywanie odds ===")
odds_df = pd.read_parquet(ODDS_PATH)
has_pin = odds_df['pin_prob_w'].notna()
log(f"  Łącznie: {len(odds_df):,} | z Pinnacle: {has_pin.sum():,}")

# ─── 2. ELO + FORM STATE ─────────────────────────────────────────────────────
log("=== v4 | ETAP 2: Elo + Form state (1990→2026) ===")
dfs = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 1990: continue
    df = pd.read_csv(f, low_memory=False); df["year"] = yr; dfs.append(df)

raw = pd.concat(dfs, ignore_index=True)
raw["tourney_date"] = pd.to_datetime(raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
raw = raw.dropna(subset=["tourney_date","winner_id","loser_id"])
raw = raw.sort_values("tourney_date").reset_index(drop=True)

surf_map = {"Hard":"Hard","Clay":"Clay","Grass":"Grass","Carpet":"Hard","Indoor Hard":"Hard","Acrylic":"Hard"}
raw["surface"] = raw["surface"].map(surf_map).fillna("Hard")
level_map = {"G":"G","M":"M","A":"500","D":"250","F":"F","C":"250","S":"500","250":"250","500":"500"}
raw["tourney_level"] = raw["tourney_level"].map(level_map).fillna("250")
for c in ["winner_rank","loser_rank","winner_rank_points","loser_rank_points",
          "winner_age","loser_age","w_svpt","w_1stWon","w_2ndWon","l_svpt","l_1stWon","l_2ndWon"]:
    raw[c] = pd.to_numeric(raw.get(c, pd.Series(dtype=float)), errors="coerce")

log(f"  TML: {len(raw):,} meczów")

from engine.elo import EloEngine
elo = EloEngine()
t0 = time.time()

ALPHA = 0.10
# Form state
ewma_win  = defaultdict(lambda: 0.5)
ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))
h2h       = defaultdict(lambda: deque(maxlen=30))
match_dates = defaultdict(list)
streak    = defaultdict(int)
srv_ewma  = defaultdict(lambda: 0.60)
ret_ewma  = defaultdict(lambda: 0.35)
last_surface = {}   # ostatnia nawierzchnia gracza

def get_form(pid, pdate, surf):
    fat14 = sum(1 for d in match_dates[pid] if (pdate-d).days <= 14)
    fat28 = sum(1 for d in match_dates[pid] if (pdate-d).days <= 28)
    last_surf = last_surface.get(pid, surf)
    surf_change = int(last_surf != surf)
    return {
        "ewma": ewma_win[pid],
        "ewma_surf": ewma_surf[pid][surf],
        "fat14": fat14, "fat28": fat28,
        "streak": min(max(streak[pid], -20), 20),
        "srv_pct": srv_ewma[pid],
        "ret_pct": ret_ewma[pid],
        "surf_change": surf_change,     # zmiana nawierzchni vs poprzedni turniej
    }

def get_h2h(aid, bid, pdate):
    key = tuple(sorted([aid, bid]))
    cutoff = pdate - timedelta(days=3*365)  # ostatnie 3 lata
    recs = [(d, w) for d, w in h2h[key] if d >= cutoff]
    wins_a = sum(1 for d, w in recs if w == aid)
    total  = len(recs)
    return (wins_a / total if total > 0 else 0.5), total

def get_elo_form(pid, surf):
    """Elo surface efficiency — ile % powyżej/poniżej overall"""
    we = elo.get_or_create(pid)
    srf = elo.get_blended_surface_elo(pid, surf)
    return srf - we.overall   # pozytywny = specialista na tej nawierzchni

def update_state(wid, lid, surf, wdate, w_svpt=None, w_1stWon=None, w_2ndWon=None,
                 l_svpt=None, l_1stWon=None, l_2ndWon=None):
    ewma_win[wid] = ALPHA*1 + (1-ALPHA)*ewma_win[wid]
    ewma_win[lid] = ALPHA*0 + (1-ALPHA)*ewma_win[lid]
    ewma_surf[wid][surf] = ALPHA*1 + (1-ALPHA)*ewma_surf[wid][surf]
    ewma_surf[lid][surf] = ALPHA*0 + (1-ALPHA)*ewma_surf[lid][surf]
    streak[wid] = streak[wid]+1 if streak[wid] >= 0 else 1
    streak[lid] = streak[lid]-1 if streak[lid] <= 0 else -1
    key = tuple(sorted([wid, lid]))
    h2h[key].append((wdate, wid))
    for pid in [wid, lid]:
        match_dates[pid].append(wdate)
        match_dates[pid] = [d for d in match_dates[pid] if (wdate-d).days <= 29]
    last_surface[wid] = surf
    last_surface[lid] = surf
    if w_svpt and w_svpt > 0 and w_1stWon and w_2ndWon:
        srv_ewma[wid] = ALPHA*(w_1stWon+w_2ndWon)/w_svpt + (1-ALPHA)*srv_ewma[wid]
        ret_ewma[lid] = ALPHA*(1-(w_1stWon+w_2ndWon)/w_svpt) + (1-ALPHA)*ret_ewma[lid]
    if l_svpt and l_svpt > 0 and l_1stWon and l_2ndWon:
        srv_ewma[lid] = ALPHA*(l_1stWon+l_2ndWon)/l_svpt + (1-ALPHA)*srv_ewma[lid]
        ret_ewma[wid] = ALPHA*(1-(l_1stWon+l_2ndWon)/l_svpt) + (1-ALPHA)*ret_ewma[wid]

# Indeks odds
def last_tml(s):
    parts = str(s).strip().split(' ')
    return parts[-1].lower().replace('-','').replace("'","")
TML_ROUND = {'R128':'R1','R64':'R1','R32':'R2','R16':'R3','QF':'QF','SF':'SF','F':'F','RR':'RR','BR':'BR'}
def norm_rnd(r): return TML_ROUND.get(str(r).strip().upper(), str(r).strip().upper())

log("  Buduję indeks odds...")
odds_idx = {}
for _, row in odds_df[has_pin].iterrows():
    key = (row['year'], row['wl'], row['ll'], row['rnd'])
    odds_idx[key] = {
        'pin_prob_w': float(row['pin_prob_w']),
        'max_prob_w': float(row['max_prob_w']) if pd.notna(row.get('max_prob_w')) else np.nan,
        'avg_prob_w': float(row['avg_prob_w']) if pd.notna(row.get('avg_prob_w')) else np.nan,
        'PSW': float(row['PSW']) if pd.notna(row.get('PSW')) else np.nan,
        'PSL': float(row['PSL']) if pd.notna(row.get('PSL')) else np.nan,
        'odds_consensus_w': float(row['odds_consensus_w']) if pd.notna(row.get('odds_consensus_w')) else np.nan,
        'b365_log_odds': float(row['b365_log_odds']) if pd.notna(row.get('b365_log_odds')) else np.nan,
        'pin_log_odds': float(row['pin_log_odds']) if pd.notna(row.get('pin_log_odds')) else np.nan,
    }
log(f"  Indeks odds: {len(odds_idx):,}")

# ─── 3. CHRONOLOGICZNY PRZEBIEG ──────────────────────────────────────────────
log("=== v4 | ETAP 3: Pre-match features (chronologicznie) ===")
rows_with_odds = []

for i, row in enumerate(raw.itertuples(index=False)):
    wid, lid = str(row.winner_id), str(row.loser_id)
    surf  = str(row.surface)
    level = str(row.tourney_level)
    yr    = row.year
    mdate = row.tourney_date.date()
    rnd   = norm_rnd(getattr(row, 'round', 'R1'))

    # Elo pre-match (potrzebne do surface specialization, ale NIE jako feature bezpośredni)
    we  = elo.get_or_create(wid)
    le  = elo.get_or_create(lid)

    # Form pre-match
    wf = get_form(wid, mdate, surf)
    lf = get_form(lid, mdate, surf)
    h2h_pw, h2h_n = get_h2h(wid, lid, mdate)

    # Surface specialization (czy gracz jest lepszy na tej nawierzchni niż ogólnie)
    w_surf_spec = get_elo_form(wid, surf)
    l_surf_spec = get_elo_form(lid, surf)

    # Wiek
    def _f(v): return float(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else np.nan
    w_age = _f(row.winner_age) or 25.
    l_age = _f(row.loser_age) or 25.
    w_hand = 1 if str(getattr(row,"winner_hand","R")) == "L" else 0
    l_hand = 1 if str(getattr(row,"loser_hand","R")) == "L" else 0
    indoor = 1 if str(getattr(row,"indoor","O")) == "I" else 0
    round_n = {'R1':1,'R2':2,'R3':3,'R4':4,'QF':5,'SF':6,'F':7,'RR':4,'BR':5}.get(rnd, 3)

    feat_dict = {
        "year": yr,
        "winner_id": wid, "loser_id": lid,
        # ── FORM winner (pre-match) ──
        "w_ewma": wf["ewma"],
        "w_ewma_surf": wf["ewma_surf"],
        "w_fat14": wf["fat14"],
        "w_fat28": wf["fat28"],
        "w_streak": wf["streak"],
        "w_srv_pct": wf["srv_pct"],
        "w_ret_pct": wf["ret_pct"],
        "w_surf_change": wf["surf_change"],
        "w_surf_spec": w_surf_spec,       # surface specialist edge
        "w_age": w_age,
        "w_hand": w_hand,
        # ── FORM loser (pre-match) ──
        "l_ewma": lf["ewma"],
        "l_ewma_surf": lf["ewma_surf"],
        "l_fat14": lf["fat14"],
        "l_fat28": lf["fat28"],
        "l_streak": lf["streak"],
        "l_srv_pct": lf["srv_pct"],
        "l_ret_pct": lf["ret_pct"],
        "l_surf_change": lf["surf_change"],
        "l_surf_spec": l_surf_spec,
        "l_age": l_age,
        "l_hand": l_hand,
        # ── DELTA features ──
        "ewma_diff": wf["ewma"] - lf["ewma"],
        "ewma_surf_diff": wf["ewma_surf"] - lf["ewma_surf"],
        "streak_diff": wf["streak"] - lf["streak"],
        "fat14_diff": wf["fat14"] - lf["fat14"],
        "srv_pct_diff": wf["srv_pct"] - lf["srv_pct"],
        "surf_spec_diff": w_surf_spec - l_surf_spec,   # kto bardziej pasuje do tej nawierzchni
        "age_diff": w_age - l_age,
        "h2h_pw": h2h_pw,
        "h2h_n": h2h_n,
        # ── KONTEKST ──
        "surf_hard": int(surf=="Hard"), "surf_clay": int(surf=="Clay"), "surf_grass": int(surf=="Grass"),
        "level_G": int(level=="G"), "level_M": int(level=="M"),
        "best_of_5": int(getattr(row,"best_of",3)==5),
        "indoor": indoor, "round_num": round_n,
    }

    # Szukaj kursów
    wl_w = last_tml(str(getattr(row,'winner_name', wid)))
    wl_l = last_tml(str(getattr(row,'loser_name', lid)))
    odds_key = (yr, wl_w, wl_l, rnd)
    odds_match = odds_idx.get(odds_key)

    if odds_match:
        feat_dict.update(odds_match)
        rows_with_odds.append(feat_dict)

    # Update state
    def _i(v): return int(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else None
    elo.update_match(wid, lid, surf, level, mdate,
        w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))
    update_state(wid, lid, surf, mdate,
        w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))

    if (i+1) % 25000 == 0:
        log(f"  [{i+1:,}/{len(raw):,}] | z odds: {len(rows_with_odds):,} | {time.time()-t0:.0f}s")

log(f"  Gotowe | z odds: {len(rows_with_odds):,} | {time.time()-t0:.1f}s")

# ─── 4. RANDOM A/B ───────────────────────────────────────────────────────────
log("=== v4 | ETAP 4: Random A/B ===")
df_odds = pd.DataFrame(rows_with_odds)
log(f"  Dataset: {df_odds.shape}")

rng = np.random.default_rng(42)
flip = rng.integers(0, 2, size=len(df_odds)).astype(bool)

W_COLS = ["w_ewma","w_ewma_surf","w_fat14","w_fat28","w_streak",
          "w_srv_pct","w_ret_pct","w_surf_change","w_surf_spec","w_age","w_hand"]
L_COLS = ["l_ewma","l_ewma_surf","l_fat14","l_fat28","l_streak",
          "l_srv_pct","l_ret_pct","l_surf_change","l_surf_spec","l_age","l_hand"]

DIFF_COLS = ["ewma_diff","ewma_surf_diff","streak_diff","fat14_diff",
             "srv_pct_diff","surf_spec_diff","age_diff"]
CTX_COLS  = ["surf_hard","surf_clay","surf_grass","level_G","level_M",
             "best_of_5","indoor","round_num"]

# Kolumny odds — symetryczne odwrócenie
PROB_COLS = ["pin_prob_w","max_prob_w","avg_prob_w","b365_log_odds","pin_log_odds"]

ab_rows = []
for r, f in zip(df_odds.itertuples(index=False), flip):
    def g(col): return getattr(r, col, np.nan)

    if f:  # A=winner
        a = {col.replace("w_","a_"): g(col) for col in W_COLS}
        b = {col.replace("l_","b_"): g(col) for col in L_COLS}
        diffs = {k: g(k) for k in DIFF_COLS}
        h2h_a = g("h2h_pw")
        probs = {k: g(k) for k in PROB_COLS}
        consensus = g("odds_consensus_w")
        y = 1
    else:  # A=loser
        a = {wcol.replace("w_","a_"): g(lcol) for wcol, lcol in zip(W_COLS, L_COLS)}
        b = {lcol.replace("l_","b_"): g(wcol) for lcol, wcol in zip(L_COLS, W_COLS)}
        diffs = {k: -g(k) if not np.isnan(g(k)) else np.nan for k in DIFF_COLS}
        h2h_a = 1.0 - g("h2h_pw") if not np.isnan(g("h2h_pw")) else np.nan
        probs = {}
        for k in PROB_COLS:
            v = g(k)
            if "log_odds" in k:
                probs[k] = -v if not np.isnan(v) else np.nan   # log-odds odwrócony
            else:
                probs[k] = 1.0 - v if not np.isnan(v) else np.nan
        consensus = g("odds_consensus_w")  # symetryczny
        y = 0

    ctx = {k: g(k) for k in CTX_COLS}
    ab_rows.append({
        "year": g("year"),
        **a, **b, **diffs,
        "h2h_a": h2h_a, "h2h_n": g("h2h_n"),
        **probs, "odds_consensus_w": consensus,
        **ctx, "y": y,
    })

ds = pd.DataFrame(ab_rows)
log(f"  A/B dataset: {ds.shape} | balance: {ds.y.mean():.3f}")
log(f"  pin_prob_w coverage: {ds['pin_prob_w'].notna().mean():.1%}")

FEAT_COLS = [c for c in ds.columns if c not in ("year", "y")]

# Quick sanity: top corr features
corrs = ds[FEAT_COLS + ['y']].corr()['y'].drop('y').abs().sort_values(ascending=False)
log(f"\n  Top 10 corr z y:\n{corrs.head(10).to_string()}")

# ─── 5. WALK-FORWARD ─────────────────────────────────────────────────────────
log("\n=== v4 | ETAP 5: Walk-Forward ===")
SPLITS = [
    (2004, 2012, 2015),
    (2004, 2015, 2018),
    (2004, 2018, 2021),
    (2004, 2021, 2023),
    (2004, 2023, 2024),
]
LGBM_P = {
    "n_estimators": 2000, "learning_rate": 0.02, "num_leaves": 31,
    "min_child_samples": 30, "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_lambda": 3.0, "objective": "binary", "metric": "auc",
    "verbosity": -1, "n_jobs": -1,
}

wf_results = []
for tr_start, val_start, val_end in SPLITS:
    Xtr = ds.loc[(ds.year >= tr_start) & (ds.year < val_start), FEAT_COLS]
    ytr = ds.loc[(ds.year >= tr_start) & (ds.year < val_start), "y"]
    Xv  = ds.loc[(ds.year >= val_start) & (ds.year < val_end), FEAT_COLS]
    yv  = ds.loc[(ds.year >= val_start) & (ds.year < val_end), "y"]
    if len(Xtr) < 200 or len(Xv) < 50: continue
    t1 = time.time()
    m = lgb.LGBMClassifier(**LGBM_P)
    m.fit(Xtr, ytr, eval_set=[(Xv, yv)],
          callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(-1)])
    p = m.predict_proba(Xv)[:, 1]
    res = {
        "split": f"{tr_start}-{val_start}→{val_end}",
        "n_tr": len(Xtr), "n_val": len(Xv),
        "auc": round(roc_auc_score(yv, p), 4),
        "acc": round(accuracy_score(yv, p > 0.5), 4),
        "bs":  round(brier_score_loss(yv, p), 4),
        "best_iter": m.best_iteration_,
        "dur": round(time.time()-t1, 1),
    }
    wf_results.append(res)
    log(f"  {res['split']}: AUC={res['auc']} Acc={res['acc']} BS={res['bs']} iters={res['best_iter']} [{res['dur']}s]")

mean_auc = np.mean([r["auc"] for r in wf_results]) if wf_results else 0
mean_acc = np.mean([r["acc"] for r in wf_results]) if wf_results else 0
mean_bs  = np.mean([r["bs"] for r in wf_results]) if wf_results else 0
log(f"\n  WF ŚREDNIE: AUC={mean_auc:.4f} Acc={mean_acc:.4f} BS={mean_bs:.4f}")

# ─── 6. FINAL MODEL ──────────────────────────────────────────────────────────
log("=== v4 | ETAP 6: Final (train≤2023, holdout 2024-2026) ===")
Xfin = ds.loc[ds.year <= 2023, FEAT_COLS]
yfin = ds.loc[ds.year <= 2023, "y"]
Xho  = ds.loc[ds.year >= 2024, FEAT_COLS]
yho  = ds.loc[ds.year >= 2024, "y"]
log(f"  Train: {len(Xfin):,} | Holdout: {len(Xho):,}")

LGBM_FIN = {**LGBM_P, "n_estimators": 5000, "learning_rate": 0.01}
t1 = time.time()
final = lgb.LGBMClassifier(**LGBM_FIN)
final.fit(Xfin, yfin, eval_set=[(Xho, yho)],
          callbacks=[lgb.early_stopping(200, verbose=False), lgb.log_evaluation(100)])
pho = final.predict_proba(Xho)[:, 1]
ho_auc = roc_auc_score(yho, pho)
ho_acc = accuracy_score(yho, pho > 0.5)
ho_bs  = brier_score_loss(yho, pho)
log(f"  HOLDOUT: AUC={ho_auc:.4f} Acc={ho_acc:.4f} BS={ho_bs:.4f} iters={final.best_iteration_} [{time.time()-t1:.1f}s]")

# ─── 7. KALIBRACJA vs PINNACLE ───────────────────────────────────────────────
log("\n=== v4 | ETAP 7: Model vs Pinnacle ===")
pin_ho = Xho["pin_prob_w"].values
valid  = ~np.isnan(pin_ho)

if valid.sum() > 50:
    pin_auc = roc_auc_score(yho[valid], pin_ho[valid])
    pin_bs  = brier_score_loss(yho[valid], pin_ho[valid])
    mod_auc = roc_auc_score(yho[valid], pho[valid])
    mod_bs  = brier_score_loss(yho[valid], pho[valid])
    log(f"  Pinnacle:   AUC={pin_auc:.4f}  BS={pin_bs:.4f}")
    log(f"  Nasz model: AUC={mod_auc:.4f}  BS={mod_bs:.4f}")
    log(f"  Delta:      AUC={mod_auc-pin_auc:+.4f}  BS={mod_bs-pin_bs:+.4f}")

    market_edge = pho[valid] - pin_ho[valid]
    log(f"\n  market_edge: μ={market_edge.mean():.4f}  σ={market_edge.std():.4f}")
    log(f"  Rozkład edge: <-10%={( market_edge<-0.10).mean():.1%}  "
        f"-10-0%={((-0.10<=market_edge)&(market_edge<0)).mean():.1%}  "
        f"0-10%={((0<=market_edge)&(market_edge<0.10)).mean():.1%}  "
        f">10%={(market_edge>=0.10).mean():.1%}")

    log("\n  Value betting simulation (edge thresholds):")
    for thresh in [0.02, 0.05, 0.08, 0.10, 0.15]:
        mask = market_edge > thresh
        n = mask.sum()
        if n > 5:
            wins  = yho.values[valid][mask]
            odds  = pin_ho[valid][mask]
            # ROI = avg(win * (1/pin_prob) - 1)  przy zakładaniu 1 jednostki
            roi = (wins / odds - (1 - wins)).mean()
            acc_t = wins.mean()
            log(f"  edge>{thresh:.0%}: n={n:4d} | win_rate={acc_t:.3f} | ROI/zakład={roi:+.4f}")
    
    # Najlepsze edge bins
    log("\n  Analiza edgów według bin:")
    df_ho = pd.DataFrame({
        "pin_prob": pin_ho[valid],
        "model_prob": pho[valid],
        "edge": market_edge,
        "y": yho.values[valid],
    })
    df_ho["edge_bin"] = pd.cut(df_ho["edge"], bins=[-1,-0.10,-0.05,0,0.05,0.10,1], 
                                labels=["<-10%","-10-5%","-5-0%","0-5%","5-10%",">10%"])
    stats = df_ho.groupby("edge_bin", observed=True).agg(
        n=("y","count"), win_rate=("y","mean"),
        avg_pin=("pin_prob","mean"), avg_model=("model_prob","mean"),
    )
    log(f"\n{stats.to_string()}")

# ─── 8. FEATURE IMPORTANCE ───────────────────────────────────────────────────
log("\n=== v4 | Feature Importance TOP-20 ===")
imp = sorted(zip(FEAT_COLS, final.feature_importances_), key=lambda x: -x[1])
for feat, fi in imp[:20]:
    log(f"  {feat}: {fi}")

# ─── 9. ZAPIS ─────────────────────────────────────────────────────────────────
log("\n=== v4 | ETAP 9: Zapis ===")
now = datetime.now().strftime("%Y%m%d_%H%M")
joblib.dump(final, MODELS_PATH / f"lgbm_v4_{now}.joblib")
joblib.dump(FEAT_COLS, MODELS_PATH / f"feat_cols_v4_{now}.joblib")
joblib.dump({
    "elo_ratings": elo.ratings,
    "ewma_win": dict(ewma_win),
    "ewma_surf": {k: dict(v) for k, v in ewma_surf.items()},
    "streak": dict(streak),
    "srv_ewma": dict(srv_ewma),
    "ret_ewma": dict(ret_ewma),
    "last_surface": last_surface,
}, MODELS_PATH / f"inference_state_v4_{now}.joblib")

metrics = {
    "version": "v4",
    "trained_at": now,
    "train_period": "2004-2023 (z Pinnacle)",
    "holdout_period": "2024-2026",
    "n_train": len(Xfin), "n_holdout": len(Xho), "n_features": len(FEAT_COLS),
    "features_used": FEAT_COLS,
    "walk_forward": wf_results,
    "mean_wf_auc": round(mean_auc, 4), "mean_wf_acc": round(mean_acc, 4),
    "holdout_auc": round(ho_auc, 4), "holdout_acc": round(ho_acc, 4), "holdout_bs": round(ho_bs, 4),
    "feature_importance": [{"feat": f, "imp": int(i)} for f, i in imp],
}
with open(MODELS_PATH / f"metrics_v4_{now}.json", "w") as f:
    json.dump(metrics, f, indent=2)

log("\n" + "="*60)
log(f"v4 DONE | AUC={ho_auc:.4f} | BS={ho_bs:.4f} | iters={final.best_iteration_} | feats={len(FEAT_COLS)}")
log("="*60)
print(json.dumps({k:v for k,v in metrics.items() if k not in ("feature_importance","features_used","walk_forward")}, indent=2))
