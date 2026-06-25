"""
betatp.io — Backtest realistyczny v4
=====================================
- Używa rzeczywistych kursów PSW (nie de-vig) jako payout
- Kelly criterion: f = (p*b - q) / b  gdzie b = PSW-1
- Bankroll simulation z drawdown tracking
- Porównanie strategii: Kelly full / half-Kelly / flat 1u / Pinnacle baseline
"""
import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, brier_score_loss

MODELS_PATH = Path("/home/ubuntu/betatp/models")
TML_PATH    = Path("/home/ubuntu/TML-Database")
ODDS_PATH   = Path("/home/ubuntu/betatp/data/matches_with_odds.parquet")
OUT_PATH    = Path("/home/ubuntu/betatp/data")

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── 1. WCZYTAJ MODEL v4 ─────────────────────────────────────────────────────
log("=== BACKTEST v4 | ETAP 1: Ładowanie modelu ===")
model_file = sorted(MODELS_PATH.glob("lgbm_v4_*.joblib"))[-1]
feat_file  = sorted(MODELS_PATH.glob("feat_cols_v4_*.joblib"))[-1]
state_file = sorted(MODELS_PATH.glob("inference_state_v4_*.joblib"))[-1]
model      = joblib.load(model_file)
feat_cols  = joblib.load(feat_file)
log(f"  Model: {model_file.name} | features: {len(feat_cols)}")

# ─── 2. ODTWÓRZ DATASET (chronologicznie) ─────────────────────────────────────
log("=== BACKTEST v4 | ETAP 2: Odtwarzanie datasetu holdout ===")

odds_df = pd.read_parquet(ODDS_PATH)
has_pin = odds_df['pin_prob_w'].notna() & odds_df['PSW'].notna() & odds_df['PSL'].notna()
log(f"  Odds z Pinnacle+PSW: {has_pin.sum():,}")

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

from engine.elo import EloEngine
elo = EloEngine()

import time
from datetime import timedelta
ALPHA = 0.10
ewma_win  = defaultdict(lambda: 0.5)
ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))
h2h       = defaultdict(lambda: deque(maxlen=30))
match_dates = defaultdict(list)
streak    = defaultdict(int)
srv_ewma  = defaultdict(lambda: 0.60)
ret_ewma  = defaultdict(lambda: 0.35)
last_surface = {}

def get_form(pid, pdate, surf):
    fat14 = sum(1 for d in match_dates[pid] if (pdate-d).days <= 14)
    fat28 = sum(1 for d in match_dates[pid] if (pdate-d).days <= 28)
    last_surf = last_surface.get(pid, surf)
    return {
        "ewma": ewma_win[pid], "ewma_surf": ewma_surf[pid][surf],
        "fat14": fat14, "fat28": fat28, "streak": min(max(streak[pid],-20),20),
        "srv_pct": srv_ewma[pid], "ret_pct": ret_ewma[pid],
        "surf_change": int(last_surf != surf),
    }

def get_h2h(aid, bid, pdate):
    key = tuple(sorted([aid, bid]))
    cutoff = pdate - timedelta(days=3*365)
    recs = [(d,w) for d,w in h2h[key] if d >= cutoff]
    wins_a = sum(1 for d,w in recs if w == aid)
    return (wins_a/len(recs) if recs else 0.5), len(recs)

def get_surf_spec(pid, surf):
    we  = elo.get_or_create(pid)
    srf = elo.get_blended_surface_elo(pid, surf)
    return srf - we.overall

def update_state(wid, lid, surf, wdate, w_svpt=None, w_1stWon=None, w_2ndWon=None,
                 l_svpt=None, l_1stWon=None, l_2ndWon=None):
    ewma_win[wid] = ALPHA*1+(1-ALPHA)*ewma_win[wid]
    ewma_win[lid] = ALPHA*0+(1-ALPHA)*ewma_win[lid]
    ewma_surf[wid][surf] = ALPHA*1+(1-ALPHA)*ewma_surf[wid][surf]
    ewma_surf[lid][surf] = ALPHA*0+(1-ALPHA)*ewma_surf[lid][surf]
    streak[wid] = streak[wid]+1 if streak[wid]>=0 else 1
    streak[lid] = streak[lid]-1 if streak[lid]<=0 else -1
    key = tuple(sorted([wid,lid]))
    h2h[key].append((wdate,wid))
    for pid in [wid,lid]:
        match_dates[pid].append(wdate)
        match_dates[pid] = [d for d in match_dates[pid] if (wdate-d).days<=29]
    last_surface[wid] = surf; last_surface[lid] = surf
    if w_svpt and w_svpt>0 and w_1stWon and w_2ndWon:
        srv_ewma[wid] = ALPHA*(w_1stWon+w_2ndWon)/w_svpt+(1-ALPHA)*srv_ewma[wid]
        ret_ewma[lid] = ALPHA*(1-(w_1stWon+w_2ndWon)/w_svpt)+(1-ALPHA)*ret_ewma[lid]
    if l_svpt and l_svpt>0 and l_1stWon and l_2ndWon:
        srv_ewma[lid] = ALPHA*(l_1stWon+l_2ndWon)/l_svpt+(1-ALPHA)*srv_ewma[lid]
        ret_ewma[wid] = ALPHA*(1-(l_1stWon+l_2ndWon)/l_svpt)+(1-ALPHA)*ret_ewma[wid]

def last_tml(s):
    return str(s).strip().split(' ')[-1].lower().replace('-','').replace("'","")
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
        'PSW': float(row['PSW']), 'PSL': float(row['PSL']),
        'odds_consensus_w': float(row['odds_consensus_w']) if pd.notna(row.get('odds_consensus_w')) else np.nan,
    }

# ─── 3. PRE-MATCH FEATURES (chronologicznie) ──────────────────────────────────
log("=== BACKTEST v4 | ETAP 3: Pre-match features ===")
W_COLS = ["w_ewma","w_ewma_surf","w_fat14","w_fat28","w_streak",
          "w_srv_pct","w_ret_pct","w_surf_change","w_surf_spec","w_age","w_hand"]
L_COLS = ["l_ewma","l_ewma_surf","l_fat14","l_fat28","l_streak",
          "l_srv_pct","l_ret_pct","l_surf_change","l_surf_spec","l_age","l_hand"]
DIFF_COLS = ["ewma_diff","ewma_surf_diff","streak_diff","fat14_diff",
             "srv_pct_diff","surf_spec_diff","age_diff"]
CTX_COLS  = ["surf_hard","surf_clay","surf_grass","level_G","level_M",
             "best_of_5","indoor","round_num"]
PROB_COLS = ["pin_prob_w","max_prob_w","avg_prob_w"]

# Chronologiczne — zachowuje Elo/form stan bez look-ahead
holdout_records = []  # tylko mecze 2024+

t0 = time.time()
for i, row in enumerate(raw.itertuples(index=False)):
    wid, lid = str(row.winner_id), str(row.loser_id)
    surf  = str(row.surface)
    level = str(row.tourney_level)
    yr    = row.year
    mdate = row.tourney_date.date()
    rnd   = norm_rnd(getattr(row, 'round', 'R1'))

    wf = get_form(wid, mdate, surf)
    lf = get_form(lid, mdate, surf)
    h2h_pw, h2h_n = get_h2h(wid, lid, mdate)
    w_surf_spec = get_surf_spec(wid, surf)
    l_surf_spec = get_surf_spec(lid, surf)

    def _f(v): return float(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else np.nan
    w_age = _f(row.winner_age) or 25.
    l_age = _f(row.loser_age) or 25.
    indoor = 1 if str(getattr(row,"indoor","O"))=="I" else 0
    round_n = {'R1':1,'R2':2,'R3':3,'R4':4,'QF':5,'SF':6,'F':7,'RR':4,'BR':5}.get(rnd,3)

    # Szukaj kursów
    wl_w = last_tml(str(getattr(row,'winner_name', wid)))
    wl_l = last_tml(str(getattr(row,'loser_name', lid)))
    odds_match = odds_idx.get((yr, wl_w, wl_l, rnd))

    if yr >= 2024 and odds_match:
        # Buduj feature vector (A=winner zawsze — potem porównamy z modelem)
        feat = {
            "a_ewma": wf["ewma"], "a_ewma_surf": wf["ewma_surf"],
            "a_fat14": wf["fat14"], "a_fat28": wf["fat28"], "a_streak": wf["streak"],
            "a_srv_pct": wf["srv_pct"], "a_ret_pct": wf["ret_pct"],
            "a_surf_change": wf["surf_change"], "a_surf_spec": w_surf_spec,
            "a_age": w_age, "a_hand": 1 if str(getattr(row,"winner_hand","R"))=="L" else 0,
            "b_ewma": lf["ewma"], "b_ewma_surf": lf["ewma_surf"],
            "b_fat14": lf["fat14"], "b_fat28": lf["fat28"], "b_streak": lf["streak"],
            "b_srv_pct": lf["srv_pct"], "b_ret_pct": lf["ret_pct"],
            "b_surf_change": lf["surf_change"], "b_surf_spec": l_surf_spec,
            "b_age": l_age, "b_hand": 1 if str(getattr(row,"loser_hand","R"))=="L" else 0,
            "ewma_diff": wf["ewma"]-lf["ewma"],
            "ewma_surf_diff": wf["ewma_surf"]-lf["ewma_surf"],
            "streak_diff": wf["streak"]-lf["streak"],
            "fat14_diff": wf["fat14"]-lf["fat14"],
            "srv_pct_diff": wf["srv_pct"]-lf["srv_pct"],
            "surf_spec_diff": w_surf_spec-l_surf_spec,
            "age_diff": w_age-l_age,
            "h2h_a": h2h_pw, "h2h_n": h2h_n,
            **odds_match,
            "surf_hard": int(surf=="Hard"), "surf_clay": int(surf=="Clay"),
            "surf_grass": int(surf=="Grass"), "level_G": int(level=="G"),
            "level_M": int(level=="M"),
            "best_of_5": int(getattr(row,"best_of",3)==5),
            "indoor": indoor, "round_num": round_n,
            # metadane
            "_date": mdate, "_year": yr, "_surface": surf,
            "_winner_id": wid, "_loser_id": lid,
            "_winner_name": str(getattr(row,"winner_name","?")),
            "_loser_name": str(getattr(row,"loser_name","?")),
            "_psw": odds_match["PSW"], "_psl": odds_match["PSL"],
        }
        holdout_records.append(feat)

    def _i(v): return int(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else None
    elo.update_match(wid, lid, surf, level, mdate,
        w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))
    update_state(wid, lid, surf, mdate,
        w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
        l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))

log(f"  Holdout records (2024-2026 z odds): {len(holdout_records):,} | {time.time()-t0:.1f}s")

# ─── 4. PREDYKCJE ─────────────────────────────────────────────────────────────
log("=== BACKTEST v4 | ETAP 4: Predykcje ===")
df_ho = pd.DataFrame(holdout_records)
meta_cols = [c for c in df_ho.columns if c.startswith("_")]
X_ho = df_ho[[c for c in feat_cols if c in df_ho.columns]].copy()
# wypełnij brakujące NaN
for c in feat_cols:
    if c not in X_ho.columns:
        X_ho[c] = np.nan

prob_winner = model.predict_proba(X_ho[feat_cols])[:,1]  # prob że A(=winner) wygra
df_ho["p_winner"] = prob_winner                 # model prob że wygrał faktyczny zwycięzca
df_ho["pin_p_winner"] = df_ho["pin_prob_w"]    # Pinnacle prob że wygrał faktyczny zwycięzca
df_ho["market_edge"] = prob_winner - df_ho["pin_prob_w"]  # edge modelu nad rynkiem

# ─── 5. METRICS ───────────────────────────────────────────────────────────────
log("=== BACKTEST v4 | ETAP 5: Metryki ===")
# Zawsze y=1 bo rekord = faktyczny zwycięzca
y_true = np.ones(len(df_ho))
auc_model = roc_auc_score(y_true, prob_winner)  # Uwaga: y_true=1 zawsze → AUC na separacji prawdop
bs_model  = brier_score_loss(y_true, prob_winner)
auc_pin   = roc_auc_score(y_true, df_ho["pin_p_winner"])
bs_pin    = brier_score_loss(y_true, df_ho["pin_p_winner"])
log(f"  Uwaga: y=1 zawsze (rekord=winner) → metryki to kalibracja")
log(f"  Model  avg_prob={prob_winner.mean():.4f}  BS={bs_model:.4f}")
log(f"  Pinnacle avg_prob={df_ho['pin_p_winner'].mean():.4f}  BS={bs_pin:.4f}")

# ─── 6. KELLY BACKTEST ────────────────────────────────────────────────────────
log("\n=== BACKTEST v4 | ETAP 6: Kelly Criterion Simulation ===")

def kelly_fraction(p_model, odds_decimal, cap=0.25):
    """Fractional Kelly. b = odds-1, f = (pb-q)/b, capped at cap"""
    b = odds_decimal - 1.0
    if b <= 0 or p_model <= 0 or p_model >= 1:
        return 0.0
    q = 1.0 - p_model
    f = (p_model * b - q) / b
    return max(0.0, min(f, cap))  # no negative bets, cap at 25%

def simulate_strategy(df, strategy="half_kelly", edge_thresh=0.05, init_bankroll=1000.0):
    """
    strategy: 'full_kelly' | 'half_kelly' | 'quarter_kelly' | 'flat_1u' | 'flat_2pct'
    edge_thresh: minimalny edge modelu nad Pinnacle aby postawić zakład
    """
    bankroll = init_bankroll
    peak     = init_bankroll
    history  = [init_bankroll]
    bets     = 0
    wins     = 0
    profit   = 0.0
    max_dd   = 0.0
    df_sorted = df.sort_values("_date").reset_index(drop=True)

    for _, row in df_sorted.iterrows():
        edge = row["market_edge"]
        if edge < edge_thresh:
            history.append(bankroll)
            continue

        p_model = row["p_winner"]
        psw     = row["_psw"]  # kurs na faktycznego zwycięzcę

        # Oblicz stawkę
        if strategy == "full_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25)
        elif strategy == "half_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25) * 0.5
        elif strategy == "quarter_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25) * 0.25
        elif strategy == "flat_1u":
            f = 1.0 / bankroll  # zawsze 1 jednostka
        elif strategy == "flat_2pct":
            f = 0.02  # 2% bankrollu
        else:
            f = 0.0

        stake  = bankroll * f
        if stake < 0.01: 
            history.append(bankroll)
            continue

        # Wynik: zakład na zwycięzcę zawsze wygrywa (row = faktyczny winner)
        pnl = stake * (psw - 1)  # wygrana
        bankroll += pnl
        profit   += pnl
        bets     += 1
        wins     += 1

        # Drawdown (nigdy nie przegramy bo y=1 zawsze — to problem!)
        # Symulacja A/B random (50% rekordów to przegrana strona)
        peak = max(peak, bankroll)
        dd   = (peak - bankroll) / peak
        max_dd = max(max_dd, dd)
        history.append(bankroll)

    roi = (bankroll - init_bankroll) / init_bankroll
    return {
        "strategy": strategy,
        "edge_thresh": edge_thresh,
        "n_bets": bets,
        "win_rate": wins/bets if bets>0 else 0,
        "final_bankroll": round(bankroll, 2),
        "roi": round(roi, 4),
        "profit": round(profit, 2),
        "max_drawdown": round(max_dd, 4),
        "history": history,
    }

# WAŻNE: symulacja potrzebuje LOSOWEGO A/B żeby mierzyć rzeczywisty drawdown
# Budujemy symulację gdzie każdy zakład może wygrać lub przegrać
log("\n  Symulacja REALISTYCZNA (A/B random, z przegranymi):")
log("  (dla każdego meczu model decyduje: bet on A czy B, wg edge)")

# Re-buduj z random A/B
rng = np.random.default_rng(2024)
sim_rows = []
for idx, rec in enumerate(holdout_records):
    flip = rng.integers(0, 2)
    feat = {k: v for k, v in rec.items() if not k.startswith("_")}

    if flip:  # A=winner (oryginał)
        p_model = prob_winner[idx]
        psw_bet = rec["_psw"]     # kurs na A (=winner)
        y_bet   = 1               # wygrana
        market_edge = p_model - rec["pin_prob_w"]
    else:      # A=loser (odwrócony)
        p_model = 1.0 - prob_winner[idx]
        psw_bet = rec["_psl"]     # kurs na A (=loser)
        y_bet   = 0               # przegrana
        market_edge = p_model - (1.0 - rec["pin_prob_w"])

    sim_rows.append({
        "date": rec["_date"],
        "p_model": p_model,
        "p_pin": rec["pin_prob_w"] if flip else 1.0-rec["pin_prob_w"],
        "psw_bet": psw_bet,
        "y_bet": y_bet,
        "market_edge": market_edge,
        "winner_name": rec["_winner_name"],
        "loser_name": rec["_loser_name"],
        "surface": rec["_surface"],
    })

df_sim = pd.DataFrame(sim_rows).sort_values("date").reset_index(drop=True)

def simulate_ab(df, strategy="half_kelly", edge_thresh=0.05, init=1000.0):
    bankroll = init
    peak     = init
    bets, wins = 0, 0
    profit = 0.0
    max_dd = 0.0
    history = [(None, init)]
    monthly_pnl = defaultdict(float)

    for _, row in df.iterrows():
        if row["market_edge"] < edge_thresh:
            continue

        p_model = row["p_model"]
        psw     = row["psw_bet"]
        y       = row["y_bet"]

        if strategy == "full_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25)
        elif strategy == "half_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25) * 0.5
        elif strategy == "quarter_kelly":
            f = kelly_fraction(p_model, psw, cap=0.25) * 0.25
        elif strategy == "flat_1u":
            f = min(1.0/bankroll, 0.05) if bankroll > 0 else 0
        elif strategy == "flat_2pct":
            f = 0.02
        else:
            f = 0.0

        stake = bankroll * f
        if stake < 0.10: continue

        if y == 1:
            pnl = stake * (psw - 1)
        else:
            pnl = -stake

        bankroll += pnl
        profit   += pnl
        bets     += 1
        if y == 1: wins += 1

        peak = max(peak, bankroll)
        dd   = (peak - bankroll) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        month = str(row["date"])[:7]
        monthly_pnl[month] += pnl
        history.append((row["date"], bankroll))

        if bankroll <= 0:
            log(f"    RUIN przy {bets} zakładach!")
            break

    roi = (bankroll - init) / init
    return {
        "strategy": strategy,
        "edge_thresh": edge_thresh,
        "n_bets": bets,
        "win_rate": round(wins/bets,4) if bets>0 else 0,
        "final_bankroll": round(bankroll, 2),
        "roi_pct": round(roi*100, 2),
        "profit": round(profit, 2),
        "max_drawdown_pct": round(max_dd*100, 2),
        "monthly_pnl": dict(sorted(monthly_pnl.items())),
        "history": [{"date": str(d), "br": round(b,2)} for d,b in history[-20:]],
    }

log(f"\n  Zbiór: {len(df_sim):,} rekordów | edge>5%: {(df_sim.market_edge>0.05).sum():,}")
log(f"  Win rate A/B baseline: {df_sim['y_bet'].mean():.3f} (oczekiwane ≈0.50)")

log("\n--- Porównanie strategii (edge>5%) ---")
strategies = ["full_kelly","half_kelly","quarter_kelly","flat_2pct"]
results = []
for strat in strategies:
    r = simulate_ab(df_sim, strategy=strat, edge_thresh=0.05)
    results.append(r)
    log(f"  {strat:16s}: bets={r['n_bets']:4d}  win={r['win_rate']:.3f}  "
        f"bankroll={r['final_bankroll']:8.2f}  ROI={r['roi_pct']:+.1f}%  "
        f"MaxDD={r['max_drawdown_pct']:.1f}%")

log("\n--- Edge threshold analiza (half-Kelly) ---")
edge_results = []
for thresh in [0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
    r = simulate_ab(df_sim, strategy="half_kelly", edge_thresh=thresh)
    edge_results.append(r)
    log(f"  edge>{thresh:.0%}: bets={r['n_bets']:4d}  win={r['win_rate']:.3f}  "
        f"ROI={r['roi_pct']:+.1f}%  MaxDD={r['max_drawdown_pct']:.1f}%  "
        f"final={r['final_bankroll']:.0f}")

# ─── 7. MONTHLY PnL (best strategy) ──────────────────────────────────────────
log("\n=== BACKTEST v4 | ETAP 7: Monthly PnL (half-Kelly, edge>8%) ===")
best = simulate_ab(df_sim, strategy="half_kelly", edge_thresh=0.08)
log(f"  Łącznie: bets={best['n_bets']} | ROI={best['roi_pct']:+.1f}% | MaxDD={best['max_drawdown_pct']:.1f}%")
log("\n  Miesiąc        PnL")
for month, pnl in best["monthly_pnl"].items():
    bar = "█"*int(abs(pnl)/5) if abs(pnl) < 500 else "█"*50
    sign = "+" if pnl >= 0 else ""
    log(f"  {month}:  {sign}{pnl:8.2f}  {bar}")

# ─── 8. PINNACLE BASELINE ─────────────────────────────────────────────────────
log("\n=== BACKTEST v4 | ETAP 8: Pinnacle baseline (always bet favourite) ===")
# Strategia referencyjna: zawsze bet na ulubieńca Pinnacle (pin_prob > 0.5)
fav_wins = (df_sim[df_sim["p_pin"] > 0.5]["y_bet"] == 1).mean()
log(f"  Favourite win rate (pin_prob>0.5): {fav_wins:.3f}")
# Kelly na Pinnacle prob (bez edge naszego modelu)
pin_sim = df_sim.copy()
pin_sim["market_edge"] = pin_sim["p_pin"] - 0.50  # bet gdy Pinnacle faworyt
pin_sim["p_model"] = pin_sim["p_pin"]
r_pin = simulate_ab(pin_sim, strategy="half_kelly", edge_thresh=0.0)
log(f"  Pinnacle half-Kelly (bet all): ROI={r_pin['roi_pct']:+.1f}%  MaxDD={r_pin['max_drawdown_pct']:.1f}%")

# ─── 9. ZAPIS ─────────────────────────────────────────────────────────────────
log("\n=== BACKTEST v4 | ETAP 9: Zapis ===")
out = {
    "backtest_date": datetime.now().isoformat(),
    "model": model_file.name,
    "holdout": "2024-2026",
    "n_matches": len(df_sim),
    "strategy_comparison": results,
    "edge_threshold_analysis": edge_results,
    "best_strategy": best,
    "pinnacle_baseline": r_pin,
}
with open(OUT_PATH / "backtest_v4.json", "w") as f:
    json.dump(out, f, indent=2, default=str)

# Zapisz też CSV z zakładami
df_bets = df_sim[df_sim["market_edge"] > 0.05].copy()
df_bets["kelly_stake_pct"] = df_bets.apply(
    lambda r: round(kelly_fraction(r["p_model"], r["psw_bet"])*50, 2), axis=1  # half-kelly %
)
df_bets.to_csv(OUT_PATH / "backtest_v4_bets.csv", index=False)

log(f"  Zapisano: backtest_v4.json, backtest_v4_bets.csv")
log("\n" + "="*60)
log(f"BACKTEST DONE | half-Kelly edge>8% | ROI={best['roi_pct']:+.1f}% | MaxDD={best['max_drawdown_pct']:.1f}%")
log("="*60)
