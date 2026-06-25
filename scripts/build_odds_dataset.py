"""
betatp.io — build_odds_dataset.py
Scala TML-Database (Elo+form features) z tennis-data.co.uk (kursy bukmacherskie)
Output: /home/ubuntu/betatp/data/matches_with_odds.parquet
        /home/ubuntu/betatp/data/matches_with_odds_stats.json

Matching: winner_last + loser_last + round_norm
Coverage: 2004-2026 (Pinnacle), 2002-2026 (Bet365), 2010-2026 (Max/Avg)
"""
import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/betatp")

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

TML_PATH   = Path("/home/ubuntu/TML-Database")
ODDS_PATH  = Path("/home/ubuntu/tennis-odds/csv")
OUT_PATH   = Path("/home/ubuntu/betatp/data")
OUT_PATH.mkdir(exist_ok=True)

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"[{ts()}] {msg}", flush=True)

# ─── NORMALIZERS ─────────────────────────────────────────────────────────────
def last_td(s):
    """'De Minaur A.' → 'deminaur',  'Djokovic N.' → 'djokovic'"""
    s = str(s).strip()
    parts = s.split(' ')
    # Ostatni token = inicjał ('A.'), reszta = nazwisko
    last = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
    return last.lower().replace(' ', '').replace('-', '').replace("'", "")

def last_tml(s):
    """'Novak Djokovic' → 'djokovic',  'Alex De Minaur' → 'deminaur'"""
    parts = str(s).strip().split(' ')
    return parts[-1].lower().replace('-', '').replace("'", "")

# Round mapping tennis-data → unified
TD_ROUND = {
    '1st round': 'R1', '2nd round': 'R2', '3rd round': 'R3', '4th round': 'R4',
    'quarterfinals': 'QF', 'semifinals': 'SF', 'the final': 'F',
    'round robin': 'RR', 'bronze medal': 'BR',
}
# Round mapping TML → unified (collapse R128/R64→R1, R32→R2, R16→R3)
TML_ROUND = {
    'R128': 'R1', 'R64': 'R1', 'R32': 'R2', 'R16': 'R3',
    'QF': 'QF', 'SF': 'SF', 'F': 'F', 'RR': 'RR', 'BR': 'BR',
}

def norm_round_td(r):
    return TD_ROUND.get(str(r).lower().strip(), str(r).lower().strip())

def norm_round_tml(r):
    return TML_ROUND.get(str(r).strip().upper(), str(r).strip().upper())

# ─── 1. WCZYTAJ TML (1990–2026) ──────────────────────────────────────────────
log("=== ETAP 1: Wczytywanie TML-Database ===")
tml_dfs = []
for f in sorted(TML_PATH.glob("[0-9]*.csv")):
    yr = int(f.stem)
    if yr < 2000: continue          # odds zaczynają się od 2001
    df = pd.read_csv(f, low_memory=False)
    df['year'] = yr
    tml_dfs.append(df)

tml = pd.concat(tml_dfs, ignore_index=True)
tml['tourney_date'] = pd.to_datetime(tml['tourney_date'].astype(str), format="%Y%m%d", errors="coerce")
tml = tml.dropna(subset=['tourney_date', 'winner_id', 'loser_id'])
tml = tml.sort_values('tourney_date').reset_index(drop=True)

tml['wl']  = tml['winner_name'].apply(last_tml)
tml['ll']  = tml['loser_name'].apply(last_tml)
tml['rnd'] = tml['round'].apply(norm_round_tml)

log(f"  TML: {len(tml):,} meczów | {tml.year.min()}–{tml.year.max()}")

# ─── 2. WCZYTAJ ODDS (tennis-data) ───────────────────────────────────────────
log("=== ETAP 2: Wczytywanie tennis-data odds ===")
odds_dfs = []
ODDS_COLS = ['B365W', 'B365L', 'PSW', 'PSL', 'MaxW', 'MaxL', 'AvgW', 'AvgL', 'BFEW', 'BFEL']

for f in sorted(ODDS_PATH.glob("*.csv")):
    yr = int(f.stem)
    if yr < 2002: continue          # 2001 ma tylko starych bukmacherów bez B365/PS
    df = pd.read_csv(f, low_memory=False)
    df['odds_year'] = yr

    # Dodaj brakujące kolumny
    for c in ODDS_COLS:
        if c not in df.columns:
            df[c] = np.nan

    df['wl']  = df['Winner'].apply(last_td)
    df['ll']  = df['Loser'].apply(last_td)
    df['rnd'] = df['Round'].apply(norm_round_td)

    keep = ['odds_year', 'wl', 'll', 'rnd', 'Winner', 'Loser', 'Tournament'] + ODDS_COLS
    odds_dfs.append(df[keep])

odds = pd.concat(odds_dfs, ignore_index=True)
log(f"  Odds: {len(odds):,} meczów | {odds.odds_year.min()}–{odds.odds_year.max()}")
log(f"  PSW coverage: {odds['PSW'].notna().sum():,} | B365W: {odds['B365W'].notna().sum():,} | MaxW: {odds['MaxW'].notna().sum():,}")

# ─── 3. MERGE ────────────────────────────────────────────────────────────────
log("=== ETAP 3: Merge TML ↔ Odds (wl + ll + rnd + year) ===")

# Merge po year + wl + ll + rnd
tml['_yr'] = tml['year']
odds['_yr'] = odds['odds_year']

merged = tml.merge(
    odds[['_yr', 'wl', 'll', 'rnd', 'Tournament'] + ODDS_COLS],
    on=['_yr', 'wl', 'll', 'rnd'],
    how='left'
)

# Dedup: jeśli ta sama kombinacja (_yr, wl, ll, rnd) pojawia się kilka razy
# (ten sam gracz gra dwa razy w R1 jednego roku w różnych turniejach)
# zachowaj TYLKO mecze z != NaN PSW, bierz pierwszy match
merged = merged.sort_values('_yr')
n_before = len(merged)
merged = merged.drop_duplicates(subset=['year', 'wl', 'll', 'rnd', 'tourney_name'], keep='first')
log(f"  Przed dedup: {n_before:,} | Po dedup: {len(merged):,}")

# Ile meczów ma kursy?
has_odds = merged['PSW'].notna()
has_b365  = merged['B365W'].notna()
has_max   = merged['MaxW'].notna()
log(f"  Mecze z Pinnacle: {has_odds.sum():,} ({100*has_odds.mean():.1f}%)")
log(f"  Mecze z B365:     {has_b365.sum():,} ({100*has_b365.mean():.1f}%)")
log(f"  Mecze z Max/Avg:  {has_max.sum():,} ({100*has_max.mean():.1f}%)")

# ─── 4. OBLICZ IMPLIED PROBABILITIES ─────────────────────────────────────────
log("=== ETAP 4: Implied probabilities (de-vig Pinnacle) ===")

# De-vig: Pinnacle margin ~2-3%
# pin_prob = (1/PSW) / (1/PSW + 1/PSL)  — pure implied probability
def devig_pinnacle(row):
    psw, psl = row['PSW'], row['PSL']
    if pd.isna(psw) or pd.isna(psl) or psw <= 1 or psl <= 1:
        return np.nan, np.nan
    raw_w = 1.0 / psw
    raw_l = 1.0 / psl
    total = raw_w + raw_l
    return raw_w / total, raw_l / total

def devig_b365(row):
    try:
        b365w, b365l = float(row['B365W']), float(row['B365L'])
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(b365w) or np.isnan(b365l) or b365w <= 1 or b365l <= 1:
        return np.nan
    raw_w = 1.0 / b365w
    raw_l = 1.0 / b365l
    total = raw_w + raw_l
    return raw_w / total

# Pinnacle implied prob (winner)
pin_probs = merged[['PSW', 'PSL']].apply(devig_pinnacle, axis=1, result_type='expand')
merged['pin_prob_w'] = pin_probs[0]   # implied prob winner wins
merged['pin_prob_l'] = pin_probs[1]   # implied prob loser wins

# Bet365 implied prob
merged['b365_prob_w'] = merged[['B365W', 'B365L']].apply(devig_b365, axis=1)

# Max odds implied prob
def devig_max(row):
    try:
        mw, ml = float(row['MaxW']), float(row['MaxL'])
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(mw) or np.isnan(ml) or mw <= 1 or ml <= 1:
        return np.nan
    raw_w = 1.0 / mw
    raw_l = 1.0 / ml
    return raw_w / (raw_w + raw_l)

merged['max_prob_w'] = merged[['MaxW', 'MaxL']].apply(devig_max, axis=1)

# Avg odds
def devig_avg(row):
    try:
        aw, al = float(row['AvgW']), float(row['AvgL'])
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(aw) or np.isnan(al) or aw <= 1 or al <= 1:
        return np.nan
    raw_w = 1.0 / aw
    raw_l = 1.0 / al
    return raw_w / (raw_w + raw_l)

merged['avg_prob_w'] = merged[['AvgW', 'AvgL']].apply(devig_avg, axis=1)

# Upset potential: duże różnice między MaxW a PSW = sharp action
def odds_consensus(row):
    try:
        mw, psw = float(row['MaxW']), float(row['PSW'])
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(mw) or np.isnan(psw) or psw <= 1:
        return np.nan
    return mw / psw   # >1.05 = ktoś daje wyraźnie lepszy kurs

merged['odds_consensus_w'] = merged[['MaxW', 'PSW']].apply(odds_consensus, axis=1)

# Odds log-ratio (feature do ML)
merged['PSW_f']  = pd.to_numeric(merged['PSW'],  errors='coerce')
merged['PSL_f']  = pd.to_numeric(merged['PSL'],  errors='coerce')
merged['B365W_f'] = pd.to_numeric(merged['B365W'], errors='coerce')
merged['B365L_f'] = pd.to_numeric(merged['B365L'], errors='coerce')
merged['pin_log_odds']  = np.log(merged['PSW_f']  / merged['PSL_f'].replace(0, np.nan))
merged['b365_log_odds'] = np.log(merged['B365W_f'] / merged['B365L_f'].replace(0, np.nan))
merged.drop(columns=['PSW_f','PSL_f','B365W_f','B365L_f'], inplace=True)

log(f"  pin_prob_w coverage: {merged['pin_prob_w'].notna().sum():,}")
log(f"  max_prob_w coverage: {merged['max_prob_w'].notna().sum():,}")
log(f"  Sample implied probs:")
sample = merged[merged['pin_prob_w'].notna()][['winner_name','loser_name','PSW','PSL','pin_prob_w','max_prob_w']].head(5)
log(f"\n{sample.to_string(index=False)}")

# ─── 5. STATYSTYKI ───────────────────────────────────────────────────────────
log("\n=== ETAP 5: Statystyki coverage per rok ===")
per_year = merged.groupby('year').agg(
    total=('winner_id','count'),
    has_pin=('pin_prob_w', lambda x: x.notna().sum()),
    has_b365=('b365_prob_w', lambda x: x.notna().sum()),
    has_max=('max_prob_w', lambda x: x.notna().sum()),
).reset_index()
per_year['pin_pct'] = (per_year['has_pin'] / per_year['total'] * 100).round(1)
per_year['b365_pct'] = (per_year['has_b365'] / per_year['total'] * 100).round(1)
log(f"\n{per_year[per_year['year']>=2002].to_string(index=False)}")

# ─── 6. ZAPIS ────────────────────────────────────────────────────────────────
log("\n=== ETAP 6: Zapis ===")
# Konwertuj kolumny odds do float (mogą być stringami w starych .xls)
for c in ODDS_COLS:
    if c in merged.columns:
        merged[c] = pd.to_numeric(merged[c], errors='coerce')

out_parquet = OUT_PATH / "matches_with_odds.parquet"
merged.to_parquet(out_parquet, index=False)
log(f"  Parquet: {out_parquet} ({out_parquet.stat().st_size/1e6:.1f} MB)")

# CSV tylko z kursami (dla debugowania)
odds_only = merged[merged['pin_prob_w'].notna()].copy()
out_csv = OUT_PATH / "matches_with_odds_sample.csv"
odds_only.head(1000).to_csv(out_csv, index=False)

# Stats JSON
stats = {
    "built_at": datetime.now().isoformat(),
    "total_matches": len(merged),
    "matches_with_pinnacle": int(merged['pin_prob_w'].notna().sum()),
    "matches_with_b365": int(merged['b365_prob_w'].notna().sum()),
    "matches_with_max": int(merged['max_prob_w'].notna().sum()),
    "year_range": f"{int(merged.year.min())}–{int(merged.year.max())}",
    "per_year": per_year.to_dict(orient='records'),
}
with open(OUT_PATH / "matches_with_odds_stats.json", "w") as f:
    json.dump(stats, f, indent=2, default=str)
log(f"  Stats: {OUT_PATH / 'matches_with_odds_stats.json'}")

log("\n" + "="*60)
log(f"DONE | {len(merged):,} meczów | Pinnacle: {int(merged['pin_prob_w'].notna().sum()):,} | Max/Avg: {int(merged['max_prob_w'].notna().sum()):,}")
log("="*60)
