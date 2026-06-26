"""
ml/model_loader.py — Singleton loader dla LightGBM modelu + Elo state.

Ładuje:
 - Najlepszy model z versions_results.json (AUC < 0.99 = brak leakage)
 - feat_cols
 - Elo engine z pełną historią (TML-Database)
 - MatchState (forma, H2H, fatigue)

Użycie:
  from ml.model_loader import get_model_context
  ctx = get_model_context()
  ctx.predict(player_a_id, player_b_id, surface, odds_a, odds_b)
"""
import json, warnings, time, threading
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore")

MODELS_PATH  = Path(__file__).parent.parent / "models"
TML_PATH     = Path("/home/ubuntu/TML-Database")
ODDS_PATH    = Path(__file__).parent.parent / "data" / "matches_with_odds.parquet"
RESULTS_JSON = MODELS_PATH / "versions_results.json"

ALPHA = 0.10
TML_ROUND = {'R128':'R1','R64':'R1','R32':'R2','R16':'R3',
             'QF':'QF','SF':'SF','F':'F','RR':'RR','BR':'BR'}


# ─── Singleton ────────────────────────────────────────────────────────────────
_ctx = None
_lock = threading.Lock()


def get_model_context():
    """Zwraca załadowany ModelContext (singleton). Lazy-load przy pierwszym wywołaniu."""
    global _ctx
    if _ctx is None:
        with _lock:
            if _ctx is None:
                _ctx = ModelContext()
                _ctx.load()
    return _ctx


def reload_model_context():
    """Force reload — wywołaj po retreningu."""
    global _ctx
    with _lock:
        _ctx = ModelContext()
        _ctx.load()
    return _ctx


# ─── ModelContext ─────────────────────────────────────────────────────────────
class ModelContext:
    """
    Trzyma model + całą stronę chronologiczną (Elo, forma, H2H).
    Po załadowaniu state jest aktualny na ostatni mecz w TML-Database.
    """

    def __init__(self):
        self.model = None
        self.feat_cols = []
        self.version = None
        self.holdout_auc = None

        # State per-player
        self.elo_engine = None
        self.ewma_win  = defaultdict(lambda: 0.5)
        self.ewma_surf = defaultdict(lambda: defaultdict(lambda: 0.5))
        self.h2h_state = defaultdict(lambda: deque(maxlen=30))
        self.h2h_full  = defaultdict(list)
        self.match_dates = defaultdict(list)
        self.streak    = defaultdict(int)
        self.srv_ewma  = defaultdict(lambda: 0.60)
        self.ret_ewma  = defaultdict(lambda: 0.35)
        self.last_surface = {}
        self.rank_hist = defaultdict(list)
        self.last_rank = {}  # player_id → (rank, age)
        self.player_names = {}  # name_lower → player_id

        self.loaded_at = None
        self.n_matches = 0

    # ── Ładowanie ──────────────────────────────────────────────────────────────
    def load(self):
        t0 = time.time()
        self._load_model()
        self._build_state()
        self.loaded_at = date.today()
        elapsed = time.time() - t0
        print(f"[ModelContext] Loaded v{self.version} | {self.n_matches:,} matches | "
              f"AUC={self.holdout_auc} | {elapsed:.1f}s", flush=True)

    def _load_model(self):
        """Wybierz najlepszy czysty model z versions_results.json"""
        if RESULTS_JSON.exists():
            with open(RESULTS_JSON) as f:
                results = json.load(f)
            clean = [r for r in results if r.get("holdout_auc", 0) < 0.99]
            if not clean:
                clean = results
            best = max(clean, key=lambda r: r.get("holdout_auc", 0))
            self.version = int(best["version"].replace("v", ""))
            self.holdout_auc = best.get("holdout_auc")
        else:
            # Fallback: znajdź najnowszy model
            all_models = sorted(MODELS_PATH.glob("lgbm_v[0-9]*_*.joblib"))
            if not all_models:
                raise FileNotFoundError(f"Brak modeli w {MODELS_PATH}")
            latest = all_models[-1]
            vstr = latest.name.split("_")[1]  # lgbm_v12_... → v12
            self.version = int(vstr.replace("v", ""))

        vstr = f"v{self.version}"
        model_files = sorted(MODELS_PATH.glob(f"lgbm_{vstr}_*.joblib"))
        feat_files  = sorted(MODELS_PATH.glob(f"feat_cols_{vstr}_*.joblib"))

        if not model_files:
            raise FileNotFoundError(f"Brak lgbm_{vstr}_*.joblib")

        self.model = joblib.load(model_files[-1])
        print(f"[ModelContext] Loaded model: {model_files[-1].name}", flush=True)

        if feat_files:
            self.feat_cols = joblib.load(feat_files[-1])
        elif hasattr(self.model, "feature_name_"):
            self.feat_cols = list(self.model.feature_name_())
        elif hasattr(self.model, "feature_names_in_"):
            self.feat_cols = list(self.model.feature_names_in_)
        else:
            raise RuntimeError("Nie znaleziono feat_cols")

        print(f"[ModelContext] Features ({len(self.feat_cols)}): {self.feat_cols[:5]}...", flush=True)

    def _build_state(self):
        """Replay całej historii TML-Database chronologicznie."""
        from engine.elo import EloEngine
        self.elo_engine = EloEngine()

        surf_map = {"Hard":"Hard","Clay":"Clay","Grass":"Grass",
                    "Carpet":"Hard","Indoor Hard":"Hard","Acrylic":"Hard"}
        level_map = {"G":"G","M":"M","A":"500","D":"250","F":"F","C":"250",
                     "S":"500","250":"250","500":"500"}

        dfs = []
        for f in sorted(TML_PATH.glob("[0-9]*.csv")):
            yr = int(f.stem)
            if yr < 1990: continue
            df = pd.read_csv(f, low_memory=False); df["year"] = yr; dfs.append(df)
        raw = pd.concat(dfs, ignore_index=True)
        raw["tourney_date"] = pd.to_datetime(
            raw["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
        raw = raw.dropna(subset=["tourney_date","winner_id","loser_id"])
        raw = raw.sort_values("tourney_date").reset_index(drop=True)
        raw["surface"] = raw["surface"].map(surf_map).fillna("Hard")
        raw["tourney_level"] = raw["tourney_level"].map(level_map).fillna("250")

        for c in ["winner_rank","loser_rank","winner_age","loser_age",
                  "w_svpt","w_1stWon","w_2ndWon","l_svpt","l_1stWon","l_2ndWon"]:
            raw[c] = pd.to_numeric(raw.get(c, pd.Series(dtype=float)), errors="coerce")

        self.n_matches = len(raw)

        for row in raw.itertuples(index=False):
            wid = str(row.winner_id); lid = str(row.loser_id)
            surf  = str(row.surface)
            level = str(row.tourney_level)
            mdate = row.tourney_date.date()

            def _i(v):
                return int(v) if v is not None and not (
                    isinstance(v, float) and np.isnan(v)) else None
            def _f(v):
                return float(v) if v is not None and not (
                    isinstance(v, float) and np.isnan(v)) else None

            wrank = _f(row.winner_rank); lrank = _f(row.loser_rank)
            w_age = _f(row.winner_age) or 25.
            l_age = _f(row.loser_age) or 25.
            wname = str(getattr(row, "winner_name", wid)).lower().strip()
            lname = str(getattr(row, "loser_name", lid)).lower().strip()
            self.player_names[wname] = wid
            self.player_names[lname] = lid
            if wrank: self.last_rank[wid] = (wrank, w_age)
            if lrank: self.last_rank[lid] = (lrank, l_age)

            # Update Elo
            self.elo_engine.update_match(wid, lid, surf, level, mdate,
                w_svpt=_i(row.w_svpt), w_1stWon=_i(row.w_1stWon),
                w_2ndWon=_i(row.w_2ndWon), l_svpt=_i(row.l_svpt),
                l_1stWon=_i(row.l_1stWon), l_2ndWon=_i(row.l_2ndWon))

            # Update forma
            self.ewma_win[wid] = ALPHA*1+(1-ALPHA)*self.ewma_win[wid]
            self.ewma_win[lid] = ALPHA*0+(1-ALPHA)*self.ewma_win[lid]
            self.ewma_surf[wid][surf] = ALPHA*1+(1-ALPHA)*self.ewma_surf[wid][surf]
            self.ewma_surf[lid][surf] = ALPHA*0+(1-ALPHA)*self.ewma_surf[lid][surf]
            self.streak[wid] = self.streak[wid]+1 if self.streak[wid]>=0 else 1
            self.streak[lid] = self.streak[lid]-1 if self.streak[lid]<=0 else -1
            key = tuple(sorted([wid, lid]))
            self.h2h_state[key].append((mdate, wid))
            self.h2h_full.setdefault(key, []).append((mdate, wid, surf))
            for pid in [wid, lid]:
                self.match_dates[pid].append(mdate)
                self.match_dates[pid] = [d for d in self.match_dates[pid]
                                         if (mdate-d).days <= 29]
            self.last_surface[wid] = surf; self.last_surface[lid] = surf
            if wrank: self.rank_hist[wid].append((mdate, wrank))
            if lrank: self.rank_hist[lid].append((mdate, lrank))
            w_svpt = _i(row.w_svpt); w_1stWon = _i(row.w_1stWon); w_2ndWon = _i(row.w_2ndWon)
            l_svpt = _i(row.l_svpt); l_1stWon = _i(row.l_1stWon); l_2ndWon = _i(row.l_2ndWon)
            if w_svpt and w_svpt>0 and w_1stWon and w_2ndWon:
                self.srv_ewma[wid] = ALPHA*(w_1stWon+w_2ndWon)/w_svpt+(1-ALPHA)*self.srv_ewma[wid]
                self.ret_ewma[lid] = ALPHA*(1-(w_1stWon+w_2ndWon)/w_svpt)+(1-ALPHA)*self.ret_ewma[lid]
            if l_svpt and l_svpt>0 and l_1stWon and l_2ndWon:
                self.srv_ewma[lid] = ALPHA*(l_1stWon+l_2ndWon)/l_svpt+(1-ALPHA)*self.srv_ewma[lid]
                self.ret_ewma[wid] = ALPHA*(1-(l_1stWon+l_2ndWon)/l_svpt)+(1-ALPHA)*self.ret_ewma[wid]

    # ── Feature extraction dla live predict ───────────────────────────────────
    def get_player_features(self, pid: str, surf: str, today: date) -> dict:
        fat14 = sum(1 for d in self.match_dates[pid] if (today-d).days <= 14)
        fat28 = sum(1 for d in self.match_dates[pid] if (today-d).days <= 28)
        we = self.elo_engine.get_or_create(pid)
        surf_elo = self.elo_engine.get_blended_surface_elo(pid, surf)
        surf_spec = surf_elo - we.overall
        rank, age = self.last_rank.get(pid, (300, 25))
        rank_traj = self._get_rank_traj(pid, today)
        return {
            "ewma": self.ewma_win[pid],
            "ewma_surf": self.ewma_surf[pid][surf],
            "fat14": fat14, "fat28": fat28,
            "streak": min(max(self.streak[pid], -20), 20),
            "srv_pct": self.srv_ewma[pid],
            "ret_pct": self.ret_ewma[pid],
            "surf_change": int(self.last_surface.get(pid, surf) != surf),
            "surf_spec": surf_spec,
            "age": age, "rank": rank, "rank_traj": rank_traj,
            "elo_overall": we.overall,
            "elo_surface": surf_elo,
        }

    def _get_rank_traj(self, pid: str, today: date, window: int = 90) -> float:
        hist = [(d, r) for d, r in self.rank_hist[pid]
                if (today - d).days <= window]
        if len(hist) < 2:
            return 0.0
        return hist[0][1] - hist[-1][1]  # poprawa > 0

    def get_h2h_features(self, wid: str, lid: str, surf: str) -> dict:
        key = tuple(sorted([wid, lid]))
        history = self.h2h_full.get(key, [])
        last3 = history[-3:]
        wins_w = sum(1 for (_, w, _) in last3 if w == wid)
        wins_l = sum(1 for (_, w, _) in last3 if w == lid)
        delta_w = wins_w - (len(last3) - wins_w)
        delta_l = wins_l - (len(last3) - wins_l)
        surf_hist = [(d, w, s) for d, w, s in history if s == surf]
        sw = sum(1 for (_, w, _) in surf_hist if w == wid)
        sl = sum(1 for (_, w, _) in surf_hist if w == lid)
        tot = len(surf_hist)
        # Stary styl H2H (v4-v8)
        cutoff = date.today() - timedelta(days=3*365)
        recs = [(d, w) for d, w in self.h2h_state[key] if d >= cutoff]
        wins_a = sum(1 for d, w in recs if w == wid)
        h2h_pw = wins_a / len(recs) if recs else 0.5
        return {
            "h2h_pw": h2h_pw, "h2h_n": len(recs),
            "delta_w": delta_w, "delta_l": delta_l,
            "surf_wr_w": sw / (tot + 1), "surf_wr_l": sl / (tot + 1),
        }

    # ── Predykcja ─────────────────────────────────────────────────────────────
    def predict(self, player_a: str, player_b: str, surface: str,
                odds_a: float, odds_b: float,
                tourney_level: str = "250", today: date = None) -> dict:
        """
        Predykcja dla dowolnej pary graczy.
        player_a/b: name lub player_id (string)
        Zwraca: {p_a, p_b, ev_a, ev_b, edge_a, kelly_a, signal, ...}
        """
        if today is None:
            today = date.today()

        surf_norm = {"hard": "Hard", "clay": "Clay", "grass": "Grass"}.get(
            surface.lower(), surface.capitalize())

        # Resolve player IDs
        aid = self._resolve_player(player_a)
        bid = self._resolve_player(player_b)

        fa = self.get_player_features(aid, surf_norm, today)
        fb = self.get_player_features(bid, surf_norm, today)
        h2h = self.get_h2h_features(aid, bid, surf_norm)

        # De-vig Pinnacle (proportional)
        imp_a = 1.0 / odds_a; imp_b = 1.0 / odds_b
        total = imp_a + imp_b
        pin_a = imp_a / total

        feat = self._build_feat_vector(fa, fb, h2h, pin_a, odds_a, odds_b,
                                       surf_norm, tourney_level)

        # Predykcja
        X = pd.DataFrame([feat])
        for c in self.feat_cols:
            if c not in X.columns:
                X[c] = np.nan
        X = X[self.feat_cols]
        p_a = float(self.model.predict_proba(X)[0, 1])
        p_b = 1.0 - p_a

        # EV
        ev_a = round((p_a * odds_a - 1.0) * 100, 2)
        ev_b = round((p_b * odds_b - 1.0) * 100, 2)
        edge_a = round(p_a - pin_a, 4)

        # Kelly half
        def kelly(p, odds, frac=0.5):
            b = odds - 1.0
            if b <= 0: return 0.0
            f = (p * b - (1-p)) / b
            return round(max(0.0, min(f * frac, 0.05)), 4)

        signal = "NO_BET"
        if ev_a > 5.0 and ev_a > ev_b:
            signal = "BET_A"
        elif ev_b > 5.0 and ev_b > ev_a:
            signal = "BET_B"

        return {
            "player_a": player_a, "player_b": player_b,
            "surface": surf_norm,
            "p_a": round(p_a, 4), "p_b": round(p_b, 4),
            "pin_a": round(pin_a, 4),
            "ev_a": ev_a, "ev_b": ev_b,
            "edge_a": edge_a,
            "kelly_a": kelly(p_a, odds_a),
            "kelly_b": kelly(p_b, odds_b),
            "signal": signal,
            "model_version": f"v{self.version}",
            "model_auc": self.holdout_auc,
            "elo_a": round(fa["elo_overall"], 1),
            "elo_b": round(fb["elo_overall"], 1),
            "rank_a": int(fa["rank"]), "rank_b": int(fb["rank"]),
            "fatigue_a": fa["fat14"], "fatigue_b": fb["fat14"],
            "h2h_summary": f"H2H last-3: {(h2h['delta_w']+3)//2}-{(h2h['delta_l']+3)//2}",
        }

    def _resolve_player(self, name_or_id: str) -> str:
        """Próbuj rozwiązać nazwę gracza na player_id."""
        name_lower = name_or_id.lower().strip()
        # Exact match
        if name_lower in self.player_names:
            return self.player_names[name_lower]
        # Partial match (last name)
        for stored_name, pid in self.player_names.items():
            if name_lower in stored_name or stored_name.endswith(name_lower):
                return pid
        # Fallback: użyj jako ID
        return name_or_id

    def _build_feat_vector(self, fa, fb, h2h, pin_a, odds_a, odds_b,
                           surf, level) -> dict:
        """Buduje feature dict pasujący do feat_cols."""
        surf_norm = surf
        return {
            "a_ewma": fa["ewma"], "a_ewma_surf": fa["ewma_surf"],
            "a_fat14": fa["fat14"], "a_fat28": fa["fat28"],
            "a_streak": fa["streak"],
            "a_srv_pct": fa["srv_pct"], "a_ret_pct": fa["ret_pct"],
            "a_surf_change": fa["surf_change"], "a_surf_spec": fa["surf_spec"],
            "a_age": fa["age"], "a_hand": 0,
            "b_ewma": fb["ewma"], "b_ewma_surf": fb["ewma_surf"],
            "b_fat14": fb["fat14"], "b_fat28": fb["fat28"],
            "b_streak": fb["streak"],
            "b_srv_pct": fb["srv_pct"], "b_ret_pct": fb["ret_pct"],
            "b_surf_change": fb["surf_change"], "b_surf_spec": fb["surf_spec"],
            "b_age": fb["age"], "b_hand": 0,
            # Diffs
            "ewma_diff": fa["ewma"] - fb["ewma"],
            "ewma_surf_diff": fa["ewma_surf"] - fb["ewma_surf"],
            "streak_diff": fa["streak"] - fb["streak"],
            "fat14_diff": fa["fat14"] - fb["fat14"],
            "srv_pct_diff": fa["srv_pct"] - fb["srv_pct"],
            "surf_spec_diff": fa["surf_spec"] - fb["surf_spec"],
            "age_diff": fa["age"] - fb["age"],
            # H2H
            "h2h_a": h2h["h2h_pw"], "h2h_n": h2h["h2h_n"],
            "h2h_wins_delta_3_w": h2h["delta_w"],
            "h2h_wins_delta_3_l": h2h["delta_l"],
            "h2h_wins_delta_3_a": h2h["delta_w"],
            "h2h_wins_delta_3_b": h2h["delta_l"],
            "h2h_surf_winrate_w": h2h["surf_wr_w"],
            "h2h_surf_winrate_l": h2h["surf_wr_l"],
            "h2h_surf_winrate_a": h2h["surf_wr_w"],
            "h2h_surf_winrate_b": h2h["surf_wr_l"],
            # Ranking
            "winner_rank_a": fa["rank"], "winner_rank_b": fb["rank"],
            "winner_age_a": fa["age"], "winner_age_b": fb["age"],
            "rank_traj_w": fa["rank_traj"], "rank_traj_l": fb["rank_traj"],
            "rank_traj_diff": fa["rank_traj"] - fb["rank_traj"],
            # Odds
            "pin_prob_w": pin_a,
            "PSW": odds_a, "PSL": odds_b,
            "b365_prob_a": pin_a, "b365_prob_b": 1.0 - pin_a,
            "odds_consensus_w": pin_a,
            "max_prob_w": pin_a, "avg_prob_w": pin_a,
            # Context
            "surf_hard": int(surf_norm == "Hard"),
            "surf_clay": int(surf_norm == "Clay"),
            "surf_grass": int(surf_norm == "Grass"),
            "level_G": int(level == "G"), "level_M": int(level == "M"),
            "best_of_5": 0, "indoor": 0, "round_num": 3,
            "a_1st_in_pct_a": fa["srv_pct"],
            "a_1st_in_pct_b": fb["srv_pct"],
        }
