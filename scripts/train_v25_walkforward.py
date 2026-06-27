"""
betatp v25 — Walk-Forward LightGBM z serve/return stats + Elo + odds
=================================================================
Strategia:
  1. Dane 2005-2026 z TML-Database (wszystkie z serve stats)
  2. Serve/return EWMA features (20-match window)
  3. Elo surface-specific + overall
  4. Walk-forward: train on [Y-4,Y-1], test on Y (rok po roku 2020-2026)
  5. Kelly betting: edge vs Pinnacle closing odds
  6. NO weather features (unreliable, overfitting)
  7. Calibration: isotonic per fold

Benchmark: Pinnacle AUC=0.7457 (v14 holdout)
Target: AUC > 0.74, profitable Kelly on holdout 2024-2026
"""

import sys, warnings, time, json
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
from sklearn.isotonic import IsotonicRegression
import lightgbm as lgb

warnings.filterwarnings('ignore')
sys.path.insert(0, str(Path(__file__).parent.parent))

TML_DIR = Path("/home/ubuntu/TML-Database")
ODDS_PATH = Path("/home/ubuntu/betatp/data/matches_with_odds.parquet")
OUT_DIR = Path("/home/ubuntu/betatp/models")
OUT_DIR.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─────────────────────────────────────────────
# STEP 1: Load all TML data with serve stats
# ─────────────────────────────────────────────
def load_tml(min_year=2005):
    """Load TML csvs + merge with odds parquet. Returns df with serve stats AND odds."""
    frames = []
    for f in sorted(TML_DIR.glob("*.csv")):
        yr = f.stem
        if not yr.isdigit() or int(yr) < min_year:
            continue
        df = pd.read_csv(f, low_memory=False)
        df['year'] = int(yr)
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    log(f"  TML Raw: {len(all_df):,} matches ({min_year}-2026)")
    
    # Keep rows with serve stats
    all_df = all_df.dropna(subset=['w_svpt', 'l_svpt'])
    all_df = all_df[all_df['w_svpt'] > 0]
    log(f"  With serve stats: {len(all_df):,}")
    
    # Load odds parquet
    if ODDS_PATH.exists():
        odds_df = pd.read_parquet(ODDS_PATH)
        # Mark rows with Pinnacle odds
        has_pin = odds_df['pin_prob_w'].notna() & odds_df['PSW'].notna()
        odds_sub = odds_df[has_pin][['year', 'winner_name', 'loser_name', 'round',
                                      'pin_prob_w', 'PSW', 'PSL', 
                                      'b365_prob_w', 'max_prob_w', 'avg_prob_w',
                                      'odds_consensus_w']].copy()
        odds_sub.columns = ['year', 'winner_name', 'loser_name', 'round',
                           'pin_prob_w', 'psw', 'psl',
                           'b365_prob_w', 'max_prob_w', 'avg_prob_w', 'consensus_w']
        
        # Merge on year + winner_name + loser_name
        all_df['winner_name_clean'] = all_df['winner_name'].astype(str).str.strip()
        all_df['loser_name_clean'] = all_df['loser_name'].astype(str).str.strip()
        odds_sub['winner_name'] = odds_sub['winner_name'].astype(str).str.strip()
        odds_sub['loser_name'] = odds_sub['loser_name'].astype(str).str.strip()
        
        merged = all_df.merge(
            odds_sub, 
            left_on=['year', 'winner_name_clean', 'loser_name_clean'],
            right_on=['year', 'winner_name', 'loser_name'],
            how='left', suffixes=('', '_odds')
        )
        n_odds = merged['pin_prob_w'].notna().sum()
        log(f"  Merged with odds: {n_odds:,} have Pinnacle odds")
        return merged
    else:
        log(f"  ⚠️ No odds parquet found, proceeding without odds features")
        return all_df

# ─────────────────────────────────────────────
# STEP 2: Serve/Return EWMA Features
# ─────────────────────────────────────────────
class ServeEWMA:
    """Track serve/return stats per player with exponential moving average."""
    
    def __init__(self, span=20):
        self.alpha = 2 / (span + 1)
        self.stats = {}  # player_id -> {metric: ewma_value}
    
    def _default(self):
        return {
            'serve_pct': 0.60, '1st_in_pct': 0.62, '1st_won_pct': 0.72,
            '2nd_won_pct': 0.50, 'ace_rate': 0.06, 'df_rate': 0.03,
            'bp_save_pct': 0.62, 'ret_pts_won_pct': 0.37,
            'dominance': 0.0, 'n_matches': 0
        }
    
    def update(self, player_id, match_stats):
        """Update EWMA after match. match_stats: dict with raw serve numbers."""
        if player_id not in self.stats:
            self.stats[player_id] = self._default()
        
        s = self.stats[player_id]
        svpt = match_stats.get('svpt', 0)
        if svpt <= 0:
            return
        
        new = {
            'serve_pct': match_stats.get('1stWon', 0) / max(svpt, 1),
            '1st_in_pct': match_stats.get('1stIn', 0) / max(svpt, 1),
            '1st_won_pct': match_stats.get('1stWon', 0) / max(match_stats.get('1stIn', 1), 1),
            '2nd_won_pct': match_stats.get('2ndWon', 0) / max(svpt - match_stats.get('1stIn', 0), 1),
            'ace_rate': match_stats.get('ace', 0) / max(svpt, 1),
            'df_rate': match_stats.get('df', 0) / max(svpt, 1),
            'bp_save_pct': match_stats.get('bpSaved', 0) / max(match_stats.get('bpFaced', 1), 1),
            'dominance': (match_stats.get('1stWon', 0) + match_stats.get('2ndWon', 0)) / max(svpt, 1)
        }
        
        # Return points won (opponent's serve)
        opp_svpt = match_stats.get('opp_svpt', 0)
        opp_pts = match_stats.get('opp_1stWon', 0) + match_stats.get('opp_2ndWon', 0)
        if opp_svpt > 0:
            new['ret_pts_won_pct'] = 1 - opp_pts / opp_svpt
        
        alpha = self.alpha
        s['n_matches'] = s.get('n_matches', 0) + 1
        for k, v in new.items():
            if k in s:
                s[k] = alpha * v + (1 - alpha) * s[k]
        
    def get(self, player_id):
        return self.stats.get(player_id, self._default()).copy()


# ─────────────────────────────────────────────
# STEP 3: Elo Engine (surface-specific)
# ─────────────────────────────────────────────
class EloSystem:
    """Surface-weighted Elo with K-factor decay."""
    
    def __init__(self, k_base=32, surface_weight=0.7):
        self.ratings = {}  # (player_id, surface) -> elo
        self.overall = {}  # player_id -> elo
        self.k_base = k_base
        self.sw = surface_weight
    
    def _get(self, pid, surface=None):
        if surface:
            return self.ratings.get((pid, surface), 1500.0)
        return self.overall.get(pid, 1500.0)
    
    def update(self, winner_id, loser_id, surface):
        # Surface Elo
        elo_w = self._get(winner_id, surface)
        elo_l = self._get(loser_id, surface)
        exp_w = 1 / (1 + 10**((elo_l - elo_w)/400))
        k = self.k_base
        self.ratings[(winner_id, surface)] = elo_w + k * (1 - exp_w)
        self.ratings[(loser_id, surface)] = elo_l + k * (0 - (1 - exp_w))
        
        # Overall
        ov_w = self._get(winner_id)
        ov_l = self._get(loser_id)
        exp_ov = 1 / (1 + 10**((ov_l - ov_w)/400))
        self.overall[winner_id] = ov_w + k * 0.6 * (1 - exp_ov)
        self.overall[loser_id] = ov_l + k * 0.6 * (0 - (1 - exp_ov))
    
    def win_prob(self, player_a, player_b, surface):
        """Blended (surface + overall) win probability for A."""
        elo_a_s = self._get(player_a, surface)
        elo_b_s = self._get(player_b, surface)
        elo_a_o = self._get(player_a)
        elo_b_o = self._get(player_b)
        
        p_surf = 1 / (1 + 10**((elo_b_s - elo_a_s)/400))
        p_over = 1 / (1 + 10**((elo_b_o - elo_a_o)/400))
        return self.sw * p_surf + (1-self.sw) * p_over
    
    def elo_diff(self, player_a, player_b, surface):
        """Blended Elo diff (A - B)."""
        a = self.sw * self._get(player_a, surface) + (1-self.sw) * self._get(player_a)
        b = self.sw * self._get(player_b, surface) + (1-self.sw) * self._get(player_b)
        return a - b


# ─────────────────────────────────────────────
# STEP 4: Feature Construction
# ─────────────────────────────────────────────
def build_features_for_match(row, elo: EloSystem, serve_ewma: ServeEWMA, surface_map):
    """Build feature vector for a match (pre-match: before this match happens)."""
    w_id = row['winner_id']
    l_id = row['loser_id']
    surface = str(row.get('surface', 'Hard')).strip()
    rank_a = row.get('winner_rank', 200) or 200
    rank_b = row.get('loser_rank', 200) or 200
    age_a = row.get('winner_age') or 25
    age_b = row.get('loser_age') or 25
    return build_features_randomized(w_id, l_id, rank_a, rank_b, age_a, age_b, surface, row, elo, serve_ewma)


def build_features_randomized(a_id, b_id, rank_a, rank_b, age_a, age_b, surface, row, elo: EloSystem, serve_ewma: ServeEWMA):
    """Build feature vector given who is A and B (no winner/loser assumption)."""
    feats = {}
    
    # Elo features
    feats['elo_diff'] = elo.elo_diff(a_id, b_id, surface)
    feats['elo_prob_a'] = elo.win_prob(a_id, b_id, surface)
    feats['elo_a'] = elo._get(a_id, surface)
    feats['elo_b'] = elo._get(b_id, surface)
    
    # Serve/return features
    s_a = serve_ewma.get(a_id)
    s_b = serve_ewma.get(b_id)
    
    for metric in ['serve_pct', '1st_in_pct', '1st_won_pct', '2nd_won_pct', 
                   'ace_rate', 'df_rate', 'bp_save_pct', 'ret_pts_won_pct', 'dominance']:
        feats[f'{metric}_a'] = s_a[metric]
        feats[f'{metric}_b'] = s_b[metric]
        feats[f'{metric}_diff'] = s_a[metric] - s_b[metric]
    
    feats['n_matches_a'] = s_a['n_matches']
    feats['n_matches_b'] = s_b['n_matches']
    
    # Ranking features
    feats['rank_a'] = min(rank_a, 500)
    feats['rank_b'] = min(rank_b, 500)
    feats['rank_diff'] = rank_b - rank_a  # positive = A ranked higher
    feats['log_rank_ratio'] = np.log(rank_b/max(rank_a,1) + 1)
    
    # Age features  
    feats['age_a'] = age_a
    feats['age_b'] = age_b
    feats['age_diff'] = age_a - age_b
    feats['age_peak_a'] = abs(age_a - 26)
    feats['age_peak_b'] = abs(age_b - 26)
    
    # Surface encoding
    feats['is_hard'] = 1 if surface == 'Hard' else 0
    feats['is_clay'] = 1 if surface == 'Clay' else 0
    feats['is_grass'] = 1 if surface == 'Grass' else 0
    
    # Tourney level
    level = str(row.get('tourney_level', 'A')) if hasattr(row, 'get') else str(getattr(row, 'tourney_level', 'A'))
    feats['is_slam'] = 1 if level == 'G' else 0
    feats['is_masters'] = 1 if level == 'M' else 0
    
    # === ODDS FEATURES (pre-match, no leakage) ===
    # pin_prob_w is always from winner's perspective in raw data
    # We need to flip to A's perspective
    pin_prob_w = row.get('pin_prob_w') if hasattr(row, 'get') else getattr(row, 'pin_prob_w', None)
    w_id = row.get('winner_id') if hasattr(row, 'get') else getattr(row, 'winner_id', None)
    
    if pin_prob_w is not None and not (isinstance(pin_prob_w, float) and np.isnan(pin_prob_w)):
        # Determine if A is the winner or loser
        if a_id == w_id:
            pin_prob_a = pin_prob_w
        else:
            pin_prob_a = 1.0 - pin_prob_w
        
        feats['pin_prob_a'] = pin_prob_a
        feats['pin_prob_b'] = 1.0 - pin_prob_a
        feats['pin_log_odds_a'] = np.log(pin_prob_a / max(1 - pin_prob_a, 0.01))
        
        # Elo vs market disagreement — KEY feature
        feats['elo_vs_market'] = feats['elo_prob_a'] - pin_prob_a
        
        # B365 / max / consensus
        b365_w = row.get('b365_prob_w') if hasattr(row, 'get') else getattr(row, 'b365_prob_w', None)
        max_w = row.get('max_prob_w') if hasattr(row, 'get') else getattr(row, 'max_prob_w', None)
        cons_w = row.get('consensus_w') if hasattr(row, 'get') else getattr(row, 'consensus_w', None)
        
        if b365_w is not None and not (isinstance(b365_w, float) and np.isnan(b365_w)):
            b365_a = b365_w if a_id == w_id else 1.0 - b365_w
            feats['b365_prob_a'] = b365_a
            feats['pin_b365_diff'] = pin_prob_a - b365_a  # bookmaker disagreement
        else:
            feats['b365_prob_a'] = pin_prob_a
            feats['pin_b365_diff'] = 0.0
        
        if max_w is not None and not (isinstance(max_w, float) and np.isnan(max_w)):
            max_a = max_w if a_id == w_id else 1.0 - max_w
            feats['max_prob_a'] = max_a
        else:
            feats['max_prob_a'] = pin_prob_a
        
        if cons_w is not None and not (isinstance(cons_w, float) and np.isnan(cons_w)):
            cons_a = cons_w if a_id == w_id else 1.0 - cons_w
            feats['consensus_a'] = cons_a
        else:
            feats['consensus_a'] = pin_prob_a
            
        feats['has_odds'] = 1
    else:
        # No odds — fill with Elo-derived probabilities
        feats['pin_prob_a'] = feats['elo_prob_a']
        feats['pin_prob_b'] = 1 - feats['elo_prob_a']
        feats['pin_log_odds_a'] = np.log(feats['elo_prob_a'] / max(1 - feats['elo_prob_a'], 0.01))
        feats['elo_vs_market'] = 0.0
        feats['b365_prob_a'] = feats['elo_prob_a']
        feats['pin_b365_diff'] = 0.0
        feats['max_prob_a'] = feats['elo_prob_a']
        feats['consensus_a'] = feats['elo_prob_a']
        feats['has_odds'] = 0
    
    return feats


# ─────────────────────────────────────────────
# STEP 5: Walk-Forward Training
# ─────────────────────────────────────────────
def walk_forward_train(df, test_years=range(2020, 2027), train_window=5):
    """
    Walk-forward: for each test_year, train on [year-window, year-1], test on year.
    Returns combined OOS predictions.
    """
    log(f"Walk-Forward: test years {list(test_years)}, window={train_window}")
    
    elo = EloSystem()
    serve_ewma = ServeEWMA(span=20)
    surface_map = {'Hard': 0, 'Clay': 1, 'Grass': 2, 'Carpet': 3}
    
    # Sort by date
    df = df.sort_values('tourney_date').reset_index(drop=True)
    
    # Phase 1: Build features for ALL matches (sequential, updating state)
    log("  Phase 1: Building features sequentially...")
    t0 = time.time()
    
    all_features = []
    all_labels = []
    all_years = []
    all_meta = []
    
    for idx, row in df.iterrows():
        if idx % 10000 == 0 and idx > 0:
            log(f"    {idx:,}/{len(df):,} processed")
        
        w_id = row['winner_id']
        l_id = row['loser_id']
        surface = str(row.get('surface', 'Hard')).strip()
        year = row['year']
        
        # Only build features if both players have history
        s_a = serve_ewma.get(w_id)
        s_b = serve_ewma.get(l_id)
        
        if s_a['n_matches'] >= 5 and s_b['n_matches'] >= 5:
            # RANDOMIZE who is "player A" to avoid leakage
            import random
            if random.random() < 0.5:
                # A = winner, B = loser → label = 1 (A wins)
                row_a_id, row_b_id = w_id, l_id
                rank_a = row.get('winner_rank', 200) or 200
                rank_b = row.get('loser_rank', 200) or 200
                age_a = row.get('winner_age') or 25
                age_b = row.get('loser_age') or 25
                label = 1
            else:
                # A = loser, B = winner → label = 0 (A loses)
                row_a_id, row_b_id = l_id, w_id
                rank_a = row.get('loser_rank', 200) or 200
                rank_b = row.get('winner_rank', 200) or 200
                age_a = row.get('loser_age') or 25
                age_b = row.get('winner_age') or 25
                label = 0
            
            feats = build_features_randomized(
                row_a_id, row_b_id, rank_a, rank_b, age_a, age_b,
                surface, row, elo, serve_ewma
            )
            
            # Store PSW odds for Kelly sim later
            psw_val = row.get('psw') if hasattr(row, 'get') else getattr(row, 'psw', None)
            psl_val = row.get('psl') if hasattr(row, 'get') else getattr(row, 'psl', None)
            if psw_val and psl_val and not (isinstance(psw_val, float) and np.isnan(psw_val)):
                # odds_a = odds for A to win
                odds_a = psw_val if row_a_id == w_id else psl_val
            else:
                odds_a = None
            
            all_features.append(feats)
            all_labels.append(label)
            all_years.append(year)
            all_meta.append({
                'winner': row.get('winner_name', ''),
                'loser': row.get('loser_name', ''),
                'surface': surface,
                'date': row.get('tourney_date', ''),
                'odds_a': odds_a,
            })
        
        # Update state AFTER feature extraction (no leakage)
        elo.update(w_id, l_id, surface)
        
        # Serve stats for winner
        serve_ewma.update(w_id, {
            'svpt': row.get('w_svpt', 0) or 0,
            '1stIn': row.get('w_1stIn', 0) or 0,
            '1stWon': row.get('w_1stWon', 0) or 0,
            '2ndWon': row.get('w_2ndWon', 0) or 0,
            'ace': row.get('w_ace', 0) or 0,
            'df': row.get('w_df', 0) or 0,
            'bpSaved': row.get('w_bpSaved', 0) or 0,
            'bpFaced': row.get('w_bpFaced', 0) or 0,
            'opp_svpt': row.get('l_svpt', 0) or 0,
            'opp_1stWon': row.get('l_1stWon', 0) or 0,
            'opp_2ndWon': row.get('l_2ndWon', 0) or 0,
        })
        # Serve stats for loser
        serve_ewma.update(l_id, {
            'svpt': row.get('l_svpt', 0) or 0,
            '1stIn': row.get('l_1stIn', 0) or 0,
            '1stWon': row.get('l_1stWon', 0) or 0,
            '2ndWon': row.get('l_2ndWon', 0) or 0,
            'ace': row.get('l_ace', 0) or 0,
            'df': row.get('l_df', 0) or 0,
            'bpSaved': row.get('l_bpSaved', 0) or 0,
            'bpFaced': row.get('l_bpFaced', 0) or 0,
            'opp_svpt': row.get('w_svpt', 0) or 0,
            'opp_1stWon': row.get('w_1stWon', 0) or 0,
            'opp_2ndWon': row.get('w_2ndWon', 0) or 0,
        })
    
    log(f"  Phase 1 done: {len(all_features):,} samples, {time.time()-t0:.1f}s")
    
    # Phase 2: Walk-forward fit/predict
    log("  Phase 2: Walk-forward training...")
    feat_df = pd.DataFrame(all_features)
    feat_cols = list(feat_df.columns)
    X = feat_df.values
    y = np.array(all_labels)
    years = np.array(all_years)
    
    oos_preds = []
    oos_labels = []
    oos_years = []
    oos_indices = []
    models = []
    calibrators = []
    
    for test_year in test_years:
        train_start = test_year - train_window
        train_mask = (years >= train_start) & (years < test_year)
        test_mask = years == test_year
        
        n_train = train_mask.sum()
        n_test = test_mask.sum()
        
        if n_train < 1000 or n_test < 100:
            log(f"    {test_year}: skip (train={n_train}, test={n_test})")
            continue
        
        X_train, y_train = X[train_mask], y[train_mask]
        X_test, y_test = X[test_mask], y[test_mask]
        
        # Split train into fit + calibration (last 20%)
        n_cal = int(len(X_train) * 0.2)
        X_fit, y_fit = X_train[:-n_cal], y_train[:-n_cal]
        X_cal, y_cal = X_train[-n_cal:], y_train[-n_cal:]
        
        # Train LightGBM
        model = lgb.LGBMClassifier(
            n_estimators=800,
            learning_rate=0.03,
            num_leaves=48,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,
            reg_lambda=1.0,
            max_depth=7,
            verbose=-1,
            n_jobs=-1,
            random_state=42
        )
        model.fit(
            X_fit, y_fit,
            eval_set=[(X_cal, y_cal)],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        
        # Calibrate
        cal_probs = model.predict_proba(X_cal)[:, 1]
        calibrator = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip')
        calibrator.fit(cal_probs, y_cal)
        
        # Predict test
        raw_probs = model.predict_proba(X_test)[:, 1]
        cal_probs_test = calibrator.predict(raw_probs)
        
        auc = roc_auc_score(y_test, cal_probs_test)
        bs = brier_score_loss(y_test, cal_probs_test)
        
        log(f"    {test_year}: train={n_train:,}, test={n_test:,}, AUC={auc:.4f}, BS={bs:.4f}")
        
        oos_preds.extend(cal_probs_test.tolist())
        oos_labels.extend(y_test.tolist())
        oos_years.extend([test_year] * n_test)
        oos_indices.extend(np.where(test_mask)[0].tolist())
        models.append(model)
        calibrators.append(calibrator)
    
    # Final model: train on everything up to 2025 (for live use)
    final_mask = years < 2026
    X_final = X[final_mask]
    y_final = y[final_mask]
    
    n_cal_f = int(len(X_final) * 0.15)
    final_model = lgb.LGBMClassifier(
        n_estimators=800, learning_rate=0.03, num_leaves=48,
        min_child_samples=30, subsample=0.8, colsample_bytree=0.7,
        reg_alpha=0.1, reg_lambda=1.0, max_depth=7, verbose=-1, n_jobs=-1, random_state=42
    )
    final_model.fit(
        X_final[:-n_cal_f], y_final[:-n_cal_f],
        eval_set=[(X_final[-n_cal_f:], y_final[-n_cal_f:])],
        callbacks=[lgb.early_stopping(50, verbose=False)]
    )
    final_cal = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip')
    final_cal_probs = final_model.predict_proba(X_final[-n_cal_f:])[:, 1]
    final_cal.fit(final_cal_probs, y_final[-n_cal_f:])
    
    return {
        'oos_preds': np.array(oos_preds),
        'oos_labels': np.array(oos_labels),
        'oos_years': np.array(oos_years),
        'oos_indices': oos_indices,
        'all_meta': all_meta,
        'feat_cols': feat_cols,
        'final_model': final_model,
        'final_calibrator': final_cal,
        'elo': elo,
        'serve_ewma': serve_ewma,
        'models': models,
        'calibrators': calibrators,
    }


# ─────────────────────────────────────────────
# STEP 6: Kelly Simulation
# ─────────────────────────────────────────────
def kelly_simulation(preds, labels, odds=None, edge_thresholds=[0.02, 0.05, 0.08, 0.10, 0.15]):
    """Simulate flat-bet and Kelly on OOS predictions.
    
    CORRECT approach: edge = p_model - p_market (where p_market = 1/odds devigged).
    We bet when our model disagrees with the market by >= threshold.
    """
    if odds is None:
        log("  ⚠️ No real odds, skipping Kelly sim")
        return
    
    # p_market from odds (approximate: 1/odds normalized by vig)
    p_market = 1.0 / odds
    
    log("\n--- KELLY SIMULATION (OOS) — edge = p_model - p_market ---")
    for thresh in edge_thresholds:
        # We bet on A winning when p_model > p_market + threshold
        mask = (preds - p_market) >= thresh
        n = mask.sum()
        if n == 0:
            log(f"  edge≥{thresh*100:.0f}%: n=0")
            continue
        p_sel = preds[mask]
        y_sel = labels[mask]
        o_sel = odds[mask]
        
        # Flat bet: 1 unit on each
        pnl = np.sum(y_sel * (o_sel - 1) - (1 - y_sel))
        wr = y_sel.mean()
        roi = pnl / n * 100
        
        # Half-Kelly
        kelly_fracs = np.clip((p_sel * o_sel - 1) / (o_sel - 1), 0, 0.05) * 0.5
        kelly_pnl = np.sum(kelly_fracs * (y_sel * (o_sel - 1) - (1 - y_sel)))
        kelly_roi = kelly_pnl / kelly_fracs.sum() * 100 if kelly_fracs.sum() > 0 else 0
        
        log(f"  edge≥{thresh*100:.0f}%: n={n:4d} WR={wr:.1%} flat_ROI={roi:+.1f}% kelly_ROI={kelly_roi:+.1f}%")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    log("=" * 60)
    log("BETATP v25 — Walk-Forward LightGBM + Serve/Return")
    log("=" * 60)
    
    # Load
    log("\n=== LOADING DATA ===")
    df = load_tml(min_year=2005)
    
    # Train walk-forward
    log("\n=== WALK-FORWARD TRAINING ===")
    results = walk_forward_train(df, test_years=range(2020, 2027), train_window=5)
    
    # OOS metrics
    preds = results['oos_preds']
    labels = results['oos_labels']
    years = results['oos_years']
    oos_indices = results['oos_indices']
    all_meta = results['all_meta']
    
    auc = roc_auc_score(labels, preds)
    bs = brier_score_loss(labels, preds)
    ll = log_loss(labels, preds)
    
    log(f"\n=== OOS AGGREGATE (2020-2026) ===")
    log(f"  N samples: {len(preds):,}")
    log(f"  AUC:       {auc:.4f}")
    log(f"  Brier:     {bs:.4f}")
    log(f"  LogLoss:   {ll:.4f}")
    log(f"  Baseline:  WR={labels.mean():.3f}")
    
    # Per-year breakdown
    log(f"\n  Per-year AUC:")
    for yr in sorted(set(years)):
        m = years == yr
        if m.sum() > 100:
            yr_auc = roc_auc_score(labels[m], preds[m])
            log(f"    {yr}: AUC={yr_auc:.4f} (n={m.sum():,})")
    
    # Kelly simulation with REAL PSW odds
    # PROPER: For each OOS sample, we have (p_model_a, label_a, odds_a)
    # We bet on A when p_model > p_market + threshold
    # This correctly measures: "when our model says A has edge, does A actually win more?"
    # Since random assignment, roughly half the bets will be on actual losers too.
    log(f"\n  Building proper Kelly sim...")
    
    kelly_bets = []
    for i, idx in enumerate(oos_indices):
        meta = all_meta[idx]
        odds_a = meta.get('odds_a')
        if odds_a is None:
            continue
        try:
            if np.isnan(odds_a):
                continue
        except:
            continue
        
        p_model_a = float(preds[i])
        label_a = int(labels[i])  # 1 if A won
        p_market_a = 1.0 / float(odds_a)
        edge_a = p_model_a - p_market_a
        
        kelly_bets.append({
            'p_model': p_model_a,
            'label': label_a,
            'odds': float(odds_a),
            'edge': edge_a,
            'p_market': p_market_a,
            'year': int(years[i])
        })
    
    log(f"  Total samples with odds: {len(kelly_bets)}")
    log(f"  Of which label=1 (A won): {sum(1 for b in kelly_bets if b['label']==1)}")
    log(f"  Of which label=0 (A lost): {sum(1 for b in kelly_bets if b['label']==0)}")
    
    if len(kelly_bets) > 50:
        bets_df = pd.DataFrame(kelly_bets)
        
        # Quick calibration check
        for q in [0.3, 0.5, 0.7, 0.9]:
            mask = (bets_df['p_model'] >= q-0.05) & (bets_df['p_model'] < q+0.05)
            if mask.sum() > 20:
                actual = bets_df.loc[mask, 'label'].mean()
                log(f"    Calibration: predicted ~{q:.0%} → actual {actual:.1%} (n={mask.sum()})")
        
        log("\n--- KELLY SIMULATION — bet when p_model > p_market + threshold ---")
        for thresh in [0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
            subset = bets_df[bets_df['edge'] >= thresh]
            n = len(subset)
            if n == 0:
                log(f"  edge≥{thresh*100:.0f}%: n=0")
                continue
            wr = subset['label'].mean()
            pnl = (subset['label'] * (subset['odds'] - 1) - (1 - subset['label'])).sum()
            roi = pnl / n * 100
            
            # Half-Kelly
            kf = np.clip((subset['p_model'] * subset['odds'] - 1) / (subset['odds'] - 1), 0, 0.05) * 0.5
            kpnl = (kf * (subset['label'] * (subset['odds'] - 1) - (1 - subset['label']))).sum()
            kroi = kpnl / kf.sum() * 100 if kf.sum() > 0 else 0
            
            log(f"  edge≥{thresh*100:.0f}%: n={n:4d} WR={wr:.1%} flat_ROI={roi:+.1f}% kelly_ROI={kroi:+.1f}% avg_odds={subset['odds'].mean():.2f}")
        
        # Per-year 2024+ (most relevant)
        log("\n  Per-year ROI (edge≥5%, 2024+):")
        for yr in [2024, 2025]:
            sub = bets_df[(bets_df['edge'] >= 0.05) & (bets_df['year'] == yr)]
            if len(sub) > 10:
                wr = sub['label'].mean()
                pnl = (sub['label'] * (sub['odds'] - 1) - (1 - sub['label'])).sum()
                roi = pnl / len(sub) * 100
                log(f"    {yr}: n={len(sub)} WR={wr:.1%} flat_ROI={roi:+.1f}%")
    
    # Feature importance
    log(f"\n=== TOP 15 FEATURES ===")
    fi = results['final_model'].feature_importances_
    feat_cols = results['feat_cols']
    fi_sorted = sorted(zip(feat_cols, fi), key=lambda x: -x[1])
    for i, (name, imp) in enumerate(fi_sorted[:15]):
        log(f"  {i+1:2d}. {name:30s} {imp:6.0f}")
    
    # Save
    ts_str = datetime.now().strftime("%Y%m%d_%H%M")
    model_path = OUT_DIR / f"lgbm_v25_{ts_str}.joblib"
    cal_path = OUT_DIR / f"calibrator_v25_{ts_str}.joblib"
    cols_path = OUT_DIR / f"feat_cols_v25_{ts_str}.joblib"
    elo_path = OUT_DIR / f"elo_v25_{ts_str}.joblib"
    serve_path = OUT_DIR / f"serve_ewma_v25_{ts_str}.joblib"
    
    joblib.dump(results['final_model'], model_path)
    joblib.dump(results['final_calibrator'], cal_path)
    joblib.dump(feat_cols, cols_path)
    joblib.dump(results['elo'], elo_path)
    joblib.dump(results['serve_ewma'], serve_path)
    
    log(f"\n=== SAVED ===")
    log(f"  Model:      {model_path}")
    log(f"  Calibrator: {cal_path}")
    log(f"  Feat cols:  {cols_path}")
    log(f"  Elo:        {elo_path}")
    log(f"  Serve EWMA: {serve_path}")
    
    # Summary
    log(f"\n{'='*60}")
    log(f"v25 RESULT: AUC={auc:.4f} (target: >0.74, Pinnacle=0.7457)")
    if auc > 0.7457:
        log(f"🏆 BEATS PINNACLE!")
    else:
        log(f"⚠️  Below Pinnacle — needs improvement")
    log(f"{'='*60}")
