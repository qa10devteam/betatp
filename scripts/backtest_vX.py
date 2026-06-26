"""
betatp.io — Backtest generyczny vX
=====================================
Działa na DOWOLNEJ wersji modelu (v4, v9, v12, v22 ...).
Automatycznie wykrywa feat_cols i buduje właściwy dataset.

Użycie:
  PYTHONPATH=. python scripts/backtest_vX.py --version 12
  PYTHONPATH=. python scripts/backtest_vX.py --version 12 --edge 0.08
  PYTHONPATH=. python scripts/backtest_vX.py --best   # wybierz najlepszy z versions_results.json

Strategia referencyjna: Pinnacle AUC=0.746 (holdout 2024-2026)
"""
import sys, json, argparse, warnings, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
from sklearn.metrics import roc_auc_score, brier_score_loss

# ─── Ścieżki ──────────────────────────────────────────────────────────────────
MODELS_PATH = Path("/home/ubuntu/betatp/models")
TML_PATH    = Path("/home/ubuntu/TML-Database")
ODDS_PATH   = Path("/home/ubuntu/betatp/data/matches_with_odds.parquet")
OUT_PATH    = Path("/home/ubuntu/betatp/data")
RESULTS_JSON = MODELS_PATH / "versions_results.json"

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)


# ─── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--version", type=int, help="Numer wersji modelu (np. 12)")
    p.add_argument("--best", action="store_true", help="Użyj najlepszego modelu z versions_results.json")
    p.add_argument("--edge", type=float, default=0.08, help="Min edge dla zakładów (default 0.08)")
    p.add_argument("--holdout_start", type=int, default=2024, help="Rok startu holdout (default 2024)")
    return p.parse_args()


# ─── Wybór modelu ─────────────────────────────────────────────────────────────
def pick_model(args) -> dict:
    """Zwraca dict: {version, model_file, feat_file, state_file, auc}"""
    if args.best:
        if not RESULTS_JSON.exists():
            raise FileNotFoundError(f"Brak {RESULTS_JSON} — uruchom trening najpierw.")
        with open(RESULTS_JSON) as f:
            results = json.load(f)
        # Filtruj czyte modele (AUC < 0.99 to nie-leakage)
        clean = [r for r in results if r.get("holdout_auc", 0) < 0.99]
        if not clean:
            clean = results
        best = max(clean, key=lambda r: r.get("holdout_auc", 0))
        version = int(best["version"].replace("v", ""))
        auc = best.get("holdout_auc", 0)
        log(f"  Auto-selected best model: v{version}  AUC={auc:.4f}")
    elif args.version is not None:
        version = args.version
        auc = None
    else:
        raise ValueError("Podaj --version N lub --best")

    vstr = f"v{version}"
    model_files = sorted(MODELS_PATH.glob(f"lgbm_{vstr}_*.joblib"))
    feat_files  = sorted(MODELS_PATH.glob(f"feat_cols_{vstr}_*.joblib"))
    state_files = sorted(MODELS_PATH.glob(f"inference_state_{vstr}_*.joblib"))

    if not model_files:
        raise FileNotFoundError(f"Brak modelu lgbm_{vstr}_*.joblib w {MODELS_PATH}")

    result = {
        "version": version,
        "model_file": model_files[-1],
        "auc": auc,
    }

    if feat_files:
        result["feat_file"] = feat_files[-1]
    if state_files:
        result["state_file"] = state_files[-1]

    return result


# ─── Ładowanie danych ─────────────────────────────────────────────────────────
def load_raw():
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
    return raw


def load_odds():
    odds_df = pd.read_parquet(ODDS_PATH)
    has_pin = odds_df['pin_prob_w'].notna() & odds_df['PSW'].notna() & odds_df['PSL'].notna()
    log(f"  Odds z Pinnacle+PSW: {has_pin.sum():,}")
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
    return odds_idx


# ─── State management (chronologiczne) ───────────────────────────────────────
ALPHA = 0.10
TML_ROUND = {'R128':'R1','R64':'R1','R32':'R2','R16':'R3','QF':'QF','SF':'SF','F':'F','RR':'RR','BR':'BR'}

def norm_rnd(r):
    return TML_ROUND.get(str(r).strip().upper(), str(r).strip().upper())

def last_tml(s):
    return str(s).strip().split(' ')[-1].lower().replace('-','').replace("'","")

class MatchState:
    """Chronologiczny state tracker — forma, fatigue, H2H, serve/return"""
    def __init__(self):
        self.ewma_win  = defaultdict(lambda: 0.5)
        self.ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))
        self.h2h       = defaultdict(lambda: deque(maxlen=30))
        self.match_dates = defaultdict(list)
        self.streak    = defaultdict(int)
        self.srv_ewma  = defaultdict(lambda: 0.60)
        self.ret_ewma  = defaultdict(lambda: 0.35)
        self.last_surface = {}
        # Rank trajectory
        self.rank_hist = defaultdict(list)  # [(date, rank)]
        # H2H history (for train_versions.py style)
        self.h2h_full  = defaultdict(list)  # (p1,p2) → [(date, winner_id, surface)]

    def get_form(self, pid, pdate, surf):
        fat14 = sum(1 for d in self.match_dates[pid] if (pdate-d).days <= 14)
        fat28 = sum(1 for d in self.match_dates[pid] if (pdate-d).days <= 28)
        last_surf = self.last_surface.get(pid, surf)
        return {
            "ewma": self.ewma_win[pid],
            "ewma_surf": self.ewma_surf[pid][surf],
            "fat14": fat14, "fat28": fat28,
            "streak": min(max(self.streak[pid],-20),20),
            "srv_pct": self.srv_ewma[pid],
            "ret_pct": self.ret_ewma[pid],
            "surf_change": int(last_surf != surf),
        }

    def get_h2h(self, aid, bid, pdate):
        key = tuple(sorted([aid, bid]))
        cutoff = pdate - timedelta(days=3*365)
        recs = [(d,w) for d,w in self.h2h[key] if d >= cutoff]
        wins_a = sum(1 for d,w in recs if w == aid)
        return (wins_a/len(recs) if recs else 0.5), len(recs)

    def get_h2h_by_player(self, wid, lid, surf, pdate):
        """H2H symetryczne (fix bug #4) — z perspektywy każdego gracza osobno"""
        key = tuple(sorted([wid, lid]))
        history = self.h2h_full.get(key, [])
        last3 = history[-3:]
        wins_w = sum(1 for (_,w,_) in last3 if w == wid)
        wins_l = sum(1 for (_,w,_) in last3 if w == lid)
        delta_w = wins_w - (len(last3) - wins_w)
        delta_l = wins_l - (len(last3) - wins_l)
        surf_hist = [(d,w,s) for d,w,s in history if s == surf]
        sw = sum(1 for (_,w,_) in surf_hist if w == wid)
        sl = sum(1 for (_,w,_) in surf_hist if w == lid)
        tot = len(surf_hist)
        surf_wr_w = sw / (tot + 1)
        surf_wr_l = sl / (tot + 1)
        return delta_w, delta_l, surf_wr_w, surf_wr_l

    def get_rank_traj(self, pid, pdate, window=90):
        hist = [(d, r) for d, r in self.rank_hist[pid]
                if (pdate-d).days <= window]
        if len(hist) < 2:
            return 0.0
        first_rank = hist[0][1]; last_rank = hist[-1][1]
        return (first_rank - last_rank)  # pozytywny = poprawa (rank spada = lepiej)

    def update(self, wid, lid, surf, wdate, wrank=None, lrank=None,
               w_svpt=None, w_1stWon=None, w_2ndWon=None,
               l_svpt=None, l_1stWon=None, l_2ndWon=None):
        self.ewma_win[wid] = ALPHA*1+(1-ALPHA)*self.ewma_win[wid]
        self.ewma_win[lid] = ALPHA*0+(1-ALPHA)*self.ewma_win[lid]
        self.ewma_surf[wid][surf] = ALPHA*1+(1-ALPHA)*self.ewma_surf[wid][surf]
        self.ewma_surf[lid][surf] = ALPHA*0+(1-ALPHA)*self.ewma_surf[lid][surf]
        self.streak[wid] = self.streak[wid]+1 if self.streak[wid]>=0 else 1
        self.streak[lid] = self.streak[lid]-1 if self.streak[lid]<=0 else -1
        key = tuple(sorted([wid,lid]))
        self.h2h[key].append((wdate,wid))
        self.h2h_full.setdefault(key, []).append((wdate, wid, surf))
        for pid in [wid,lid]:
            self.match_dates[pid].append(wdate)
            self.match_dates[pid] = [d for d in self.match_dates[pid] if (wdate-d).days<=29]
        self.last_surface[wid] = surf; self.last_surface[lid] = surf
        if wrank: self.rank_hist[wid].append((wdate, wrank))
        if lrank: self.rank_hist[lid].append((wdate, lrank))
        if w_svpt and w_svpt>0 and w_1stWon and w_2ndWon:
            self.srv_ewma[wid] = ALPHA*(w_1stWon+w_2ndWon)/w_svpt+(1-ALPHA)*self.srv_ewma[wid]
            self.ret_ewma[lid] = ALPHA*(1-(w_1stWon+w_2ndWon)/w_svpt)+(1-ALPHA)*self.ret_ewma[lid]
        if l_svpt and l_svpt>0 and l_1stWon and l_2ndWon:
            self.srv_ewma[lid] = ALPHA*(l_1stWon+l_2ndWon)/l_svpt+(1-ALPHA)*self.srv_ewma[lid]
            self.ret_ewma[wid] = ALPHA*(1-(l_1stWon+l_2ndWon)/l_svpt)+(1-ALPHA)*self.ret_ewma[wid]


# ─── Budowanie feature vektora pasującego do feat_cols ────────────────────────
def build_features(feat_cols, wf, lf, wid, lid, w_age, l_age, w_hand, l_hand,
                   w_surf_spec, l_surf_spec, h2h_data, odds_match, surf, level,
                   indoor, round_n, flip, state, pdate, wrank, lrank):
    """
    Buduje feature vector dla dowolnej wersji — na podstawie feat_cols z modelu.
    Obsługuje: v4-style feats, rank feats (v10), serve/return (v11), H2H fix (v9+).
    """
    # Unpack h2h
    h2h_pw, h2h_n, h2h_delta_w, h2h_delta_l, h2h_surf_wr_w, h2h_surf_wr_l = h2h_data

    if flip:
        af, bf = wf, lf
        a_age, b_age = w_age, l_age
        a_hand, b_hand = w_hand, l_hand
        a_surf_spec, b_surf_spec = w_surf_spec, l_surf_spec
        psw_a, psw_b = odds_match["PSW"], odds_match["PSL"]
        pin_a = odds_match["pin_prob_w"]
        y_true = 1
        a_h2h_delta, b_h2h_delta = h2h_delta_w, h2h_delta_l
        a_h2h_surf_wr, b_h2h_surf_wr = h2h_surf_wr_w, h2h_surf_wr_l
        a_rank, b_rank = wrank or 300, lrank or 300
        a_rank_traj = state.get_rank_traj(wid, pdate)
        b_rank_traj = state.get_rank_traj(lid, pdate)
    else:
        af, bf = lf, wf
        a_age, b_age = l_age, w_age
        a_hand, b_hand = l_hand, w_hand
        a_surf_spec, b_surf_spec = l_surf_spec, w_surf_spec
        psw_a, psw_b = odds_match["PSL"], odds_match["PSW"]
        pin_a = 1.0 - odds_match["pin_prob_w"]
        y_true = 0
        a_h2h_delta, b_h2h_delta = h2h_delta_l, h2h_delta_w
        a_h2h_surf_wr, b_h2h_surf_wr = h2h_surf_wr_l, h2h_surf_wr_w
        a_rank, b_rank = lrank or 300, wrank or 300
        a_rank_traj = state.get_rank_traj(lid, pdate)
        b_rank_traj = state.get_rank_traj(wid, pdate)

    om_flipped = dict(odds_match)
    if not flip:
        om_flipped["pin_prob_w"] = 1.0 - odds_match["pin_prob_w"]
        om_flipped["PSW"] = odds_match["PSL"]
        om_flipped["PSL"] = odds_match["PSW"]

    base = {
        # Forma (v4+)
        "a_ewma": af["ewma"], "a_ewma_surf": af["ewma_surf"],
        "a_fat14": af["fat14"], "a_fat28": af["fat28"], "a_streak": af["streak"],
        "a_srv_pct": af["srv_pct"], "a_ret_pct": af["ret_pct"],
        "a_surf_change": af["surf_change"], "a_surf_spec": a_surf_spec,
        "a_age": a_age, "a_hand": a_hand,
        "b_ewma": bf["ewma"], "b_ewma_surf": bf["ewma_surf"],
        "b_fat14": bf["fat14"], "b_fat28": bf["fat28"], "b_streak": bf["streak"],
        "b_srv_pct": bf["srv_pct"], "b_ret_pct": bf["ret_pct"],
        "b_surf_change": bf["surf_change"], "b_surf_spec": b_surf_spec,
        "b_age": b_age, "b_hand": b_hand,
        # Diff (v4+)
        "ewma_diff": af["ewma"]-bf["ewma"],
        "ewma_surf_diff": af["ewma_surf"]-bf["ewma_surf"],
        "streak_diff": af["streak"]-bf["streak"],
        "fat14_diff": af["fat14"]-bf["fat14"],
        "srv_pct_diff": af["srv_pct"]-bf["srv_pct"],
        "surf_spec_diff": a_surf_spec-b_surf_spec,
        "age_diff": a_age-b_age,
        # H2H stary styl (v4-v8)
        "h2h_a": h2h_pw if flip else 1.0-h2h_pw,
        "h2h_n": h2h_n,
        # H2H nowy styl (v9+ fix #4)
        "h2h_wins_delta_3_w": a_h2h_delta, "h2h_wins_delta_3_l": b_h2h_delta,
        "h2h_wins_delta_3_a": a_h2h_delta, "h2h_wins_delta_3_b": b_h2h_delta,
        "h2h_surf_winrate_w": a_h2h_surf_wr, "h2h_surf_winrate_l": b_h2h_surf_wr,
        "h2h_surf_winrate_a": a_h2h_surf_wr, "h2h_surf_winrate_b": b_h2h_surf_wr,
        # v23 clean H2H names
        "h2h_delta_a": a_h2h_delta, "h2h_delta_b": b_h2h_delta,
        "h2h_surf_wr_a": a_h2h_surf_wr, "h2h_surf_wr_b": b_h2h_surf_wr,
        # v23 forma (EWMA + streak)
        "ewma_a": af["ewma"], "ewma_b": bf["ewma"],
        "ewma_surf_a": af["ewma_surf"], "ewma_surf_b": bf["ewma_surf"],
        "streak_a": af["streak"], "streak_b": bf["streak"],
        # Ranking (v10+) — DUPLIKATY z czystymi nazwami (v23+)
        "winner_rank_a": a_rank, "winner_rank_b": b_rank,
        "winner_age_a": a_age, "winner_age_b": b_age,
        "player_rank_a": a_rank, "player_rank_b": b_rank,   # v23 clean names
        "player_age_a": a_age, "player_age_b": b_age,       # v23 clean names
        "rank_inv_a": 1.0 / (a_rank + 1), "rank_inv_b": 1.0 / (b_rank + 1),  # v23
        "rank_traj_w": a_rank_traj, "rank_traj_l": b_rank_traj,
        "rank_traj_a": a_rank_traj, "rank_traj_b": b_rank_traj,  # v23 alias
        "rank_traj_diff": a_rank_traj - b_rank_traj,
        # Serve/return (v11+)
        "a_1st_in_pct_a": af["srv_pct"], "a_1st_in_pct_b": bf["srv_pct"],
        # Odds (v4+)
        **om_flipped,
        # Context
        "surf_hard": int(surf=="Hard"), "surf_clay": int(surf=="Clay"),
        "surf_grass": int(surf=="Grass"), "level_G": int(level=="G"),
        "level_M": int(level=="M"), "best_of_5": 0,
        "indoor": indoor, "round_num": round_n,
        # Odds devig
        "b365_prob_a": pin_a,  # fallback alias
        "b365_prob_b": 1.0 - pin_a,
    }

    # Metadata (nie w modelu)
    meta = {"_pin_a": pin_a, "_psw_a": psw_a, "_psw_b": psw_b, "_y_true": y_true}
    return base, meta


# ─── Kelly simulation ─────────────────────────────────────────────────────────
def kelly_fraction(p_model, odds_decimal, cap=0.05):
    b = odds_decimal - 1.0
    if b <= 0.01 or p_model <= 0 or p_model >= 1:
        return 0.0
    q = 1.0 - p_model
    f = (p_model * b - q) / b
    return max(0.0, min(f, cap))


def simulate_ab(df, strategy="half_kelly", edge_thresh=0.05, init=1000.0):
    bankroll = init; peak = init
    bets, wins = 0, 0
    profit = 0.0; max_dd = 0.0
    history = [(None, init)]
    monthly_pnl = defaultdict(float)

    for _, row in df.iterrows():
        if row["market_edge"] < edge_thresh:
            continue
        p_model = row["p_model"]; psw = row["psw_bet"]; y = row["y_bet"]

        if strategy == "full_kelly":
            f = kelly_fraction(p_model, psw, cap=0.05)
        elif strategy == "half_kelly":
            f = kelly_fraction(p_model, psw, cap=0.05) * 0.5
        elif strategy == "quarter_kelly":
            f = kelly_fraction(p_model, psw, cap=0.05) * 0.25
        elif strategy == "flat_2pct":
            f = 0.02
        else:
            f = 0.0

        stake = bankroll * f
        if stake < 0.10: continue

        pnl = stake * (psw - 1) if y == 1 else -stake
        bankroll += pnl; profit += pnl; bets += 1
        if y == 1: wins += 1
        peak = max(peak, bankroll)
        dd = (peak - bankroll) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        monthly_pnl[str(row["date"])[:7]] += pnl
        history.append((row["date"], bankroll))
        if bankroll <= 0:
            log(f"    RUIN przy {bets} zakładach!"); break

    roi = (bankroll - init) / init
    return {
        "strategy": strategy, "edge_thresh": edge_thresh,
        "n_bets": bets, "win_rate": round(wins/bets,4) if bets>0 else 0,
        "final_bankroll": round(bankroll, 2), "roi_pct": round(roi*100, 2),
        "profit": round(profit, 2), "max_drawdown_pct": round(max_dd*100, 2),
        "monthly_pnl": dict(sorted(monthly_pnl.items())),
        "history": [{"date": str(d), "br": round(b,2)} for d,b in history[-20:]],
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    log("=" * 60)
    log(f"BACKTEST vX — generyczny | edge>{args.edge:.0%}")
    log("=" * 60)

    # 1. Model
    log("=== ETAP 1: Ładowanie modelu ===")
    info = pick_model(args)
    model = joblib.load(info["model_file"])
    log(f"  Model: {info['model_file'].name}")

    # Wykryj feat_cols
    if "feat_file" in info:
        feat_cols = joblib.load(info["feat_file"])
        log(f"  feat_cols z pliku: {len(feat_cols)} features")
    elif hasattr(model, "feature_name_"):
        feat_cols = list(model.feature_name_())
        log(f"  feat_cols z modelu: {len(feat_cols)} features")
    elif hasattr(model, "feature_names_in_"):
        feat_cols = list(model.feature_names_in_)
        log(f"  feat_cols z modelu: {len(feat_cols)} features")
    else:
        raise RuntimeError("Nie znaleziono feat_cols — sprawdź czy feat_cols_vX_*.joblib istnieje")

    log(f"  Features: {feat_cols[:8]}{'...' if len(feat_cols)>8 else ''}")

    # 2. Dane
    log("=== ETAP 2: Wczytywanie danych ===")
    raw = load_raw()
    log(f"  Raw: {len(raw):,} meczów")
    odds_idx = load_odds()

    # Elo engine
    from engine.elo import EloEngine
    elo = EloEngine()
    state = MatchState()
    backtest_rng = np.random.default_rng(2024)

    # 3. Chronologiczne features
    log(f"=== ETAP 3: Pre-match features (holdout>={args.holdout_start}) ===")
    holdout_records = []
    t0 = time.time()
    ROUND_MAP = {'R1':1,'R2':2,'R3':3,'R4':4,'QF':5,'SF':6,'F':7,'RR':4,'BR':5}

    for i, row in enumerate(raw.itertuples(index=False)):
        wid, lid = str(row.winner_id), str(row.loser_id)
        surf  = str(row.surface)
        level = str(row.tourney_level)
        yr    = row.year
        mdate = row.tourney_date.date()
        rnd   = norm_rnd(getattr(row, 'round', 'R1'))

        def _f(v): return float(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else np.nan
        def _i(v): return int(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else None

        wf = state.get_form(wid, mdate, surf)
        lf = state.get_form(lid, mdate, surf)
        h2h_pw, h2h_n = state.get_h2h(wid, lid, mdate)
        h2h_delta_w, h2h_delta_l, h2h_surf_wr_w, h2h_surf_wr_l = state.get_h2h_by_player(wid, lid, surf, mdate)

        from engine.elo import EloEngine
        we = elo.get_or_create(wid)
        le = elo.get_or_create(lid)
        w_surf_spec = elo.get_blended_surface_elo(wid, surf) - we.overall
        l_surf_spec = elo.get_blended_surface_elo(lid, surf) - le.overall

        w_age   = _f(row.winner_age) or 25.
        l_age   = _f(row.loser_age) or 25.
        wrank   = _f(row.winner_rank)
        lrank   = _f(row.loser_rank)
        indoor  = 1 if str(getattr(row,"indoor","O"))=="I" else 0
        round_n = ROUND_MAP.get(rnd, 3)
        w_hand  = 1 if str(getattr(row,"winner_hand","R"))=="L" else 0
        l_hand  = 1 if str(getattr(row,"loser_hand","R"))=="L" else 0

        wl_w = last_tml(str(getattr(row,'winner_name', wid)))
        wl_l = last_tml(str(getattr(row,'loser_name', lid)))
        odds_match = odds_idx.get((yr, wl_w, wl_l, rnd))

        if yr >= args.holdout_start and odds_match:
            flip = bool(backtest_rng.integers(0, 2))
            h2h_data = (h2h_pw, h2h_n, h2h_delta_w, h2h_delta_l, h2h_surf_wr_w, h2h_surf_wr_l)
            feat, meta = build_features(
                feat_cols, wf, lf, wid, lid, w_age, l_age, w_hand, l_hand,
                w_surf_spec, l_surf_spec, h2h_data, odds_match, surf, level,
                indoor, round_n, flip, state, mdate,
                wrank if not np.isnan(wrank) else None,
                lrank if not np.isnan(lrank) else None,
            )
            record = {**feat, **meta,
                "_date": mdate, "_year": yr, "_surface": surf,
                "_winner_id": wid, "_loser_id": lid,
                "_winner_name": str(getattr(row,"winner_name","?")),
                "_loser_name":  str(getattr(row,"loser_name","?")),
            }
            holdout_records.append(record)

        # Update state
        elo.update_match(wid, lid, surf, level, mdate,
            w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
            l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))
        state.update(wid, lid, surf, mdate,
            wrank=wrank if wrank and not np.isnan(wrank) else None,
            lrank=lrank if lrank and not np.isnan(lrank) else None,
            w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon), w_2ndWon=_i(row.w_2ndWon),
            l_svpt=_i(row.l_svpt), l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))

    log(f"  Holdout records ({args.holdout_start}+): {len(holdout_records):,} | {time.time()-t0:.1f}s")

    # 4. Predykcje
    log("=== ETAP 4: Predykcje ===")
    df_ho = pd.DataFrame(holdout_records)
    X_ho = df_ho[[c for c in feat_cols if c in df_ho.columns]].copy()
    for c in feat_cols:
        if c not in X_ho.columns:
            X_ho[c] = np.nan
    X_ho = X_ho[feat_cols]

    p_a = model.predict_proba(X_ho)[:,1]
    df_ho["p_a"] = p_a
    df_ho["y_true"] = df_ho["_y_true"].astype(int)
    df_ho["market_edge"] = p_a - df_ho["_pin_a"]

    # 5. Metryki
    log("=== ETAP 5: Metryki ===")
    y_true_arr = df_ho["y_true"].values
    auc_model = roc_auc_score(y_true_arr, p_a)
    bs_model  = brier_score_loss(y_true_arr, p_a)
    auc_pin   = roc_auc_score(y_true_arr, df_ho["_pin_a"])
    bs_pin    = brier_score_loss(y_true_arr, df_ho["_pin_a"])
    win_rate_a = y_true_arr.mean()
    log(f"  Win rate A (powinno być ≈0.50): {win_rate_a:.3f}")
    log(f"  Model    AUC={auc_model:.4f}  BS={bs_model:.4f}")
    log(f"  Pinnacle AUC={auc_pin:.4f}   BS={bs_pin:.4f}")
    log(f"  Edge nad Pinnacle: Δ AUC = {auc_model-auc_pin:+.4f}")

    # 6. Symulacja
    log("=== ETAP 6: Kelly Simulation ===")
    df_sim = pd.DataFrame({
        "date": df_ho["_date"],
        "p_model": df_ho["p_a"],
        "p_pin": df_ho["_pin_a"],
        "psw_bet": df_ho["_psw_a"],
        "y_bet": df_ho["y_true"],
        "market_edge": df_ho["market_edge"],
        "winner_name": df_ho["_winner_name"],
        "loser_name": df_ho["_loser_name"],
        "surface": df_ho["_surface"],
    }).sort_values("date").reset_index(drop=True)

    log(f"  Zbiór: {len(df_sim):,} | edge>5%: {(df_sim.market_edge>0.05).sum():,} | edge>8%: {(df_sim.market_edge>0.08).sum():,}")
    log(f"  Win rate A/B baseline: {df_sim['y_bet'].mean():.3f}")

    # Flat bet analysis
    log("\n--- FLAT BET ANALYSIS (1 unit per bet, no compound) ---")
    for thresh in [0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
        subset = df_sim[df_sim["market_edge"] >= thresh].copy()
        if len(subset) == 0: continue
        n_bets = len(subset); wins = (subset["y_bet"]==1).sum(); wr = wins/n_bets
        pnl = subset.apply(lambda r: (r["psw_bet"]-1) if r["y_bet"]==1 else -1.0, axis=1)
        total_pnl = pnl.sum(); roi_flat = total_pnl / n_bets * 100
        running = 0; peak_r = 0; max_dd = 0
        for p2 in pnl.values:
            running += p2; peak_r = max(peak_r, running)
            max_dd = max(max_dd, peak_r - running)
        avg_odds_w = subset[subset["y_bet"]==1]["psw_bet"].mean() if wins > 0 else 0
        log(f"  edge≥{thresh:.0%}: bets={n_bets:4d}  W/L={wins}/{n_bets-wins}  "
            f"WR={wr:.1%}  flat_ROI={roi_flat:+.1f}%  "
            f"PnL={total_pnl:+.1f}u  MaxDD={max_dd:.1f}u  "
            f"avg_odds_W={avg_odds_w:.2f}")

    # Compound strategies
    log(f"\n--- COMPOUND STRATEGIES (edge>{args.edge:.0%}, Kelly caps 5%) ---")
    strategies = ["full_kelly","half_kelly","quarter_kelly","flat_2pct"]
    results = []
    for strat in strategies:
        r = simulate_ab(df_sim, strategy=strat, edge_thresh=args.edge)
        results.append(r)
        log(f"  {strat:16s}: bets={r['n_bets']:4d}  win={r['win_rate']:.3f}  "
            f"bankroll={r['final_bankroll']:10.2f}  ROI={r['roi_pct']:+.1f}%  MaxDD={r['max_drawdown_pct']:.1f}%")

    # Best: half_kelly
    log(f"\n--- EDGE THRESHOLD (half-Kelly) ---")
    edge_results = []
    for thresh in [0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
        r = simulate_ab(df_sim, strategy="half_kelly", edge_thresh=thresh)
        edge_results.append(r)
        log(f"  edge>{thresh:.0%}: bets={r['n_bets']:4d}  win={r['win_rate']:.3f}  "
            f"ROI={r['roi_pct']:+.1f}%  MaxDD={r['max_drawdown_pct']:.1f}%  final={r['final_bankroll']:.0f}")

    # Monthly PnL
    log(f"\n--- MONTHLY PnL (half-Kelly, edge>{args.edge:.0%}) ---")
    best = simulate_ab(df_sim, strategy="half_kelly", edge_thresh=args.edge)
    log(f"  Łącznie: bets={best['n_bets']} | ROI={best['roi_pct']:+.1f}% | MaxDD={best['max_drawdown_pct']:.1f}%")
    for month, pnl in best["monthly_pnl"].items():
        bar = "█"*int(abs(pnl)/10)
        sign = "+" if pnl >= 0 else ""
        log(f"  {month}:  {sign}{pnl:8.2f}  {bar}")

    # Pinnacle baseline
    log("\n--- PINNACLE BASELINE ---")
    fav_wins = (df_sim[df_sim["p_pin"] > 0.5]["y_bet"] == 1).mean()
    log(f"  Favourite win rate (pin>0.5): {fav_wins:.3f}")
    pin_sim = df_sim.copy()
    pin_sim["market_edge"] = pin_sim["p_pin"] - 0.50
    pin_sim["p_model"] = pin_sim["p_pin"]
    r_pin = simulate_ab(pin_sim, strategy="half_kelly", edge_thresh=0.0)
    log(f"  Pinnacle half-Kelly: ROI={r_pin['roi_pct']:+.1f}%  MaxDD={r_pin['max_drawdown_pct']:.1f}%")

    # 7. Zapis
    log("=== ETAP 7: Zapis ===")
    version_str = f"v{info['version']}"
    out = {
        "backtest_date": datetime.now().isoformat(),
        "model": str(info["model_file"].name),
        "version": version_str,
        "holdout": f"{args.holdout_start}-2026",
        "n_matches": len(df_sim),
        "model_auc": round(auc_model, 4),
        "pinnacle_auc": round(auc_pin, 4),
        "auc_delta": round(auc_model - auc_pin, 4),
        "strategy_comparison": results,
        "edge_threshold_analysis": edge_results,
        "best_strategy": best,
        "pinnacle_baseline": r_pin,
    }
    json_out = OUT_PATH / f"backtest_{version_str}.json"
    csv_out  = OUT_PATH / f"backtest_{version_str}_bets.csv"
    with open(json_out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    df_bets = df_sim[df_sim["market_edge"] > 0.05].copy()
    # FIXED: kelly_fraction(cap=0.05)*50 zawsze = 2.5 (0.05*50).
    # Poprawnie: raw Kelly fraction (bez cap) * 100 = % bankrolla.
    # Wyświetlamy HALF-Kelly (bezpieczny standard).
    def kelly_pct_half(p, odds):
        b = odds - 1.0
        if b <= 0 or p <= 0 or p >= 1:
            return 0.0
        q = 1.0 - p
        raw = (p * b - q) / b
        return max(0.0, raw) * 0.5 * 100  # half-Kelly jako % bankrolla

    df_bets["kelly_stake_pct"] = df_bets.apply(
        lambda r: round(kelly_pct_half(r["p_model"], r["psw_bet"]), 2), axis=1
    )
    df_bets.to_csv(csv_out, index=False)
    log(f"  Zapisano: {json_out.name}, {csv_out.name}")

    log("\n" + "="*60)
    log(f"BACKTEST DONE | model={version_str} | AUC={auc_model:.4f} (Pinnacle={auc_pin:.4f})")
    log(f"  half-Kelly edge>{args.edge:.0%}: ROI={best['roi_pct']:+.1f}%  MaxDD={best['max_drawdown_pct']:.1f}%")
    log("="*60)


if __name__ == "__main__":
    main()
