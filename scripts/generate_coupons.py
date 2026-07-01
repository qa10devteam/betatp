"""
Generator kuponów STS — Wimbledon 2026 Day 3 (1 lipca)
Champion stack: v70_is_straight, v31_fatigue_5sets, v54_ou39.5_full,
                v23_ou36.5, v80_hcp_9, v39_cross_over33
"""
import joblib, numpy as np, pandas as pd, json, warnings, sys, psycopg2
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings('ignore')
BASE = Path('/home/ubuntu/betatp')
sys.path.insert(0, str(BASE))

# ── POŁĄCZENIE z PG ──────────────────────────────────────────────────────
conn = psycopg2.connect(host='localhost', dbname='betatp', user='postgres', password='betatp2026')

# ── DZISIEJSZE MECZE ATP Wimbledon 2R (1.07.2026) ─────────────────────
# (name_a, name_b, elo_a, elo_b, rank_a, rank_b, age_a, age_b, odds_a_b365, odds_b_b365)
# Wimbledon 2R = BO3, surface=Grass, is_grand_slam=1, is_bo5=0, round_num=2
MATCHES = [
    ("Sinner J.",        "Borges N.",         2380, 1880,  1,  53, 23, 26, 1.10, 7.00),
    ("Tsitsipas S.",     "Djokovic N.",        2100, 2290, 11,   7, 26, 39, 3.10, 1.38),
    ("Auger-Al. F.",     "Prizmic D.",         2120, 1780,  3,  87, 24, 20, 1.18, 5.00),
    ("Medvedev D.",      "Merida D.",          2160, 1620,  8, 220, 28, 22, 1.07, 9.50),
    ("Hurkacz H.",       "Ofner S.",           2060, 1820, 22,  42, 27, 26, 1.35, 3.00),
    ("Nakashima B.",     "Struff J.",          1960, 1880, 28,  44, 23, 34, 1.55, 2.45),
    ("Paul T.",          "Kwon S.",            2020, 1760, 21,  98, 27, 28, 1.15, 5.50),
    ("Fonseca J.",       "De Jong J.",         1980, 1760, 24,  95, 19, 24, 1.20, 4.50),
    ("Rinderknech A.",   "Damm M. Jr",         1900, 1740, 25, 101, 28, 23, 1.40, 2.80),
    ("Dav.Fokina A.",    "Marozsan F.",        1980, 1820, 22,  55, 26, 25, 1.42, 2.75),
    ("Jodar R.",         "Carreno Busta P.",   1940, 1890, 23,  35, 24, 33, 1.55, 2.40),
]

# ── POBIERZ ROLLING STATS Z BAZY (ostatnie 20 meczów każdego gracza) ────
def get_player_stats(cur, name_pattern, last_n=30, surface='Grass'):
    """Pobiera rolling serve/return stats dla gracza."""
    last = name_pattern.split()[-1].rstrip('.')
    q = """
        SELECT m.w_ace, m.l_ace, m.w_df, m.l_df,
               m.w_svpt, m.l_svpt,
               m.w_1stin, m.w_1stwon, m.w_2ndwon,
               m.l_1stin, m.l_1stwon, m.l_2ndwon,
               m.w_bpsaved, m.w_bpfaced, m.l_bpsaved, m.l_bpfaced,
               te.surface, m.score, m.best_of, m.winner_id, m.loser_id,
               p_w.full_name as winner_name, p_l.full_name as loser_name
        FROM matches m
        JOIN tournament_editions te ON m.edition_id = te.edition_id
        JOIN players p_w ON m.winner_id = p_w.player_id
        JOIN players p_l ON m.loser_id = p_l.player_id
        WHERE (p_w.full_name ILIKE %s OR p_l.full_name ILIKE %s)
          AND m.match_date >= '2023-01-01'
        ORDER BY m.match_date DESC
        LIMIT 40
    """
    cur.execute(q, (f'%{last}%', f'%{last}%'))
    rows = cur.fetchall()
    cols = ['ace_w','ace_l','df_w','df_l','svpt_w','svpt_l',
            '1stIn_w','1stWon_w','2ndWon_w','1stIn_l','1stWon_l','2ndWon_l',
            'bpSaved_w','bpFaced_w','bpSaved_l','bpFaced_l',
            'surface','score','best_of','w_id','l_id','winner_name','loser_name']
    return pd.DataFrame(rows, columns=cols)

def safe_div(a, b, default=0.0):
    return float(a)/float(b) if b and b > 0 else default

def calc_serve_stats(df, player_name):
    """Oblicza rolling statystyki serwisowe dla gracza."""
    last = player_name.split()[-1].rstrip('.').lower()
    stats = defaultdict(list)
    for _, r in df.iterrows():
        wn = str(r.get('winner_name','')).lower()
        ln = str(r.get('loser_name','')).lower()
        is_winner = last in wn
        is_loser  = last in ln
        if not (is_winner or is_loser):
            continue
        if is_winner:
            svpt = r['svpt_w'] or 0; ace = r['ace_w'] or 0; df_ = r['df_w'] or 0
            fstIn = r['1stIn_w'] or 0; fstWon = r['1stWon_w'] or 0; sndWon = r['2ndWon_w'] or 0
            bpS = r['bpSaved_w'] or 0; bpF = r['bpFaced_w'] or 0
        else:
            svpt = r['svpt_l'] or 0; ace = r['ace_l'] or 0; df_ = r['df_l'] or 0
            fstIn = r['1stIn_l'] or 0; fstWon = r['1stWon_l'] or 0; sndWon = r['2ndWon_l'] or 0
            bpS = r['bpSaved_l'] or 0; bpF = r['bpFaced_l'] or 0
        if svpt < 20: continue
        stats['ace'].append(safe_div(ace, svpt))
        stats['df'].append(safe_div(df_, svpt))
        stats['fstWon'].append(safe_div(fstWon, fstIn) if fstIn > 0 else 0.65)
        stats['sndWon'].append(safe_div(sndWon, svpt - fstIn) if (svpt-fstIn) > 0 else 0.50)
        stats['hold'].append(1 - safe_div(bpF - bpS, max(bpF,1)))
        stats['svpt_per_game'].append(svpt / max(1, svpt/6))  # szacunek
        stats['surface'].append(str(r.get('surface','')))

    if not stats['ace']:
        # Default ATP grass averages
        return {
            'ace_rate': 0.072, 'df_rate': 0.028,
            '1stWon_pct': 0.72, '2ndWon_pct': 0.54,
            'hold_pct': 0.82, 'svpt_per_game': 6.8, 'tb_rate': 0.19,
            'avg_game_len': 4.2, 'ace_per_set': 5.2,
            'serve_dom': 0.72 + 0.54 - 1,
            'form': 0.55, 'streak': 1, 'surf_form': 0.55,
        }

    # Grass-specific
    grass_ace  = [a for a, s in zip(stats['ace'], stats['surface']) if 'rass' in s]
    ace_rate   = np.mean(grass_ace) if grass_ace else np.mean(stats['ace'])
    df_rate    = np.mean(stats['df'][-10:])
    fstWon     = np.mean(stats['fstWon'][-10:])
    sndWon     = np.mean(stats['sndWon'][-10:])
    hold       = np.mean(stats['hold'][-10:])
    svpt_pg    = np.mean(stats['svpt_per_game'][-10:])
    ace_per_set= ace_rate * svpt_pg
    return {
        'ace_rate': ace_rate, 'df_rate': df_rate,
        '1stWon_pct': fstWon, '2ndWon_pct': sndWon,
        'hold_pct': hold, 'svpt_per_game': svpt_pg,
        'tb_rate': 0.19, 'avg_game_len': 4.2,
        'ace_per_set': ace_per_set,
        'serve_dom': fstWon * 0.60 + sndWon * 0.40,
        'form': min(0.9, max(0.3, np.mean([1 if v > 0.5 else 0
                                            for v in stats['hold'][-6:]]))),
        'streak': min(5, sum(1 for v in reversed(stats['hold'][-5:]) if v > 0.5)),
        'surf_form': min(0.9, max(0.3,
            np.mean([1 if v > 0.5 else 0
                     for v, s in zip(stats['hold'][-10:], stats['surface'][-10:])
                     if 'rass' in s] or [0.55])),
        ),
    }

# ── WCZYTAJ CHAMPION MODELE ─────────────────────────────────────────────
print("Ładuję modele champion...")
model_files = {
    'straight': 'lgbm_v70_is_straight_20260701_0806.joblib',
    'fatigue5': 'lgbm_v31_fatigue_5sets_20260629_1957.joblib',
    'ou39':     'lgbm_v54_ou39.5_full_20260630_1705.joblib',
    'ou36':     'lgbm_v23_ou36.5_20260629_1938.joblib',
    'hcp9':     'lgbm_v80_hcp_9_20260701_1118.joblib',
    'ou33':     'lgbm_v39_cross_over33_20260629_2010.joblib',
}
loaded = {}
for key, fname in model_files.items():
    p = BASE / 'models' / fname
    if p.exists():
        loaded[key] = joblib.load(p)
        print(f"  ✅ {key}: {fname}")

# ── POBIERZ STATS Z BAZY ─────────────────────────────────────────────────
print("\nPobieram statystyki z bazy PostgreSQL...")
cur = conn.cursor()
player_cache = {}
for match in MATCHES:
    for name in [match[0], match[1]]:
        if name not in player_cache:
            df = get_player_stats(cur, name)
            player_cache[name] = calc_serve_stats(df, name)
            n = len(df)
            ace = player_cache[name]['ace_rate']
            hold = player_cache[name]['hold_pct']
            print(f"  {name:25s}: {n:3d} meczów | ace={ace:.3f} | hold={hold:.3f}")

# ── FEATURE BUILDER ──────────────────────────────────────────────────────
def build_features_full(match, sa, sb):
    """Buduje pełny 103-feature wektor."""
    (na, nb, elo_a, elo_b, rank_a, rank_b, age_a, age_b, odds_a, odds_b) = match

    # Kursy
    imp_a  = 1/odds_a; imp_b  = 1/odds_b
    vig    = imp_a + imp_b - 1
    pin_w  = imp_a / (imp_a + imp_b)
    pin_l  = 1 - pin_w
    b365_w = pin_w
    b365_l = pin_l
    pin_log = np.log(max(imp_a/imp_b, 1e-6))
    cons_w  = odds_b / max(odds_a, 0.01)
    mkt_w   = vig

    # Elo
    elo_prob_w = 1/(1+10**((elo_b-elo_a)/400))
    elo_prob_l = 1 - elo_prob_w
    surf_elo_w = elo_a + 40  # grass bias +40 dla serwujących
    surf_elo_l = elo_b + 20
    surf_elo_diff  = surf_elo_w - surf_elo_l
    surf_elo_prob_w= 1/(1+10**((surf_elo_l-surf_elo_w)/400))

    elo_pin_diff = elo_prob_w - pin_w

    # Rank
    rank_diff = rank_b - rank_a
    rank_ratio = rank_b / max(rank_a, 1)
    rank_w_log = np.log(max(rank_a, 1))
    rank_l_log = np.log(max(rank_b, 1))

    # Surface Wimbledon
    surface_enc    = 3  # Grass=3
    is_grass       = 1
    is_clay        = 0
    is_bo5         = 0  # 2R Wimbledon = BO3
    round_num      = 2
    tourney_level_enc = 4  # Grand Slam
    is_grand_slam  = 1
    is_masters     = 0
    round_x_level  = round_num * tourney_level_enc
    market_width   = abs(odds_a - odds_b)

    # Serve stats
    ace_w  = sa['ace_rate'];     ace_l  = sb['ace_rate']
    df_w   = sa['df_rate'];      df_l   = sb['df_rate']
    fst_w  = sa['1stWon_pct'];   fst_l  = sb['1stWon_pct']
    snd_w  = sa['2ndWon_pct'];   snd_l  = sb['2ndWon_pct']
    hold_w = sa['hold_pct'];     hold_l = sb['hold_pct']
    bp_w   = 1-hold_l;           bp_l   = 1-hold_w  # break rate = 1-opp_hold
    svpt_w = sa['svpt_per_game'];svpt_l = sb['svpt_per_game']
    tb_w   = sa['tb_rate'];      tb_l   = sb['tb_rate']
    gl_w   = sa['avg_game_len']; gl_l   = sb['avg_game_len']
    aps_w  = sa['ace_per_set'];  aps_l  = sb['ace_per_set']
    sdom_w = sa['serve_dom'];    sdom_l = sb['serve_dom']

    serve_diff   = sdom_w - sdom_l
    break_diff   = bp_w - bp_l
    hold_diff    = hold_w - hold_l
    combined_srv = hold_w + hold_l
    combined_brk = bp_w + bp_l
    combined_ace = ace_w + ace_l
    tb_comb      = (tb_w + tb_l)/2
    svpt_comb    = (svpt_w + svpt_l)/2

    # Momentum
    form_w  = sa['form'];        form_l  = sb['form']
    form_diff = form_w - form_l
    streak_w= sa['streak'];      streak_l= sb['streak']
    sfm_w   = sa['surf_form'];   sfm_l   = sb['surf_form']
    sfm_diff = sfm_w - sfm_l

    # Dodatkowe (brak historii TB/5set wr — defaults)
    tb_wr_w = 0.52; tb_wr_l = 0.50
    set5_wr_w= 0.55; set5_wr_l = 0.50
    clutch_diff = (tb_wr_w - tb_wr_l)

    # Rest (Wimbledon 2R — grają drugi mecz, ~2 dni odpoczynku)
    rest_w = 1; rest_l = 1; rest_diff = 0
    m7_w = 1; m7_l = 1; m14_w = 2; m14_l = 2
    fatigue_diff = 0

    # H2H (brak dokładnych danych — neutral)
    h2h_n = 3; h2h_bal = 0.5; h2h_surf = 0.5

    # In-tournament Elo (po 1R — taki sam jak elo)
    tour_n_w = 1; tour_n_l = 1; tour_n_diff = 0
    in_elo_w = elo_a; in_elo_l = elo_b; in_elo_diff = elo_a - elo_b

    # Interakcje
    elo_x_form        = elo_prob_w * form_w
    surf_elo_x_form   = surf_elo_prob_w * sfm_w
    serve_x_elo       = sdom_w * elo_prob_w
    clutch_x_round    = clutch_diff * round_num
    rank_x_form       = (1/max(rank_a,1)) * form_w
    age_x_surface     = age_a * is_grass
    pin_x_elo         = pin_w * elo_prob_w
    market_x_serve    = mkt_w * sdom_w
    h2h_x_form        = h2h_bal * form_w
    fatigue_x_round   = fatigue_diff * round_num
    bo5_x_clutch      = is_bo5 * clutch_diff
    gs_x_rank         = is_grand_slam * rank_w_log

    feat = {
        'pin_prob_w': pin_w, 'pin_log_odds': pin_log, 'b365_prob_w': b365_w,
        'odds_consensus_w': cons_w, 'rank_diff': rank_diff, 'rank_ratio': rank_ratio,
        'rank_w_log': rank_w_log, 'rank_l_log': rank_l_log,
        'age_diff': age_a-age_b, 'age_w': age_a, 'age_l': age_b,
        'surface_enc': surface_enc, 'is_grass': is_grass, 'is_clay': is_clay,
        'is_bo5': is_bo5, 'round_num': round_num,
        'tourney_level_enc': tourney_level_enc,
        'is_grand_slam': is_grand_slam, 'is_masters': is_masters,
        'round_x_level': round_x_level, 'market_width': market_width,
        'odds_implied_vig': vig,
        'elo_w': elo_a, 'elo_l': elo_b, 'elo_diff': elo_a-elo_b,
        'surf_elo_w': surf_elo_w, 'surf_elo_l': surf_elo_l,
        'surf_elo_diff': surf_elo_diff, 'elo_prob_w': elo_prob_w,
        'surf_elo_prob_w': surf_elo_prob_w, 'elo_pin_diff': elo_pin_diff,
        'ace_rate_w': ace_w, 'ace_rate_l': ace_l,
        'df_rate_w': df_w, 'df_rate_l': df_l,
        '1stWon_pct_w': fst_w, '1stWon_pct_l': fst_l,
        '2ndWon_pct_w': snd_w, '2ndWon_pct_l': snd_l,
        'hold_pct_w': hold_w, 'hold_pct_l': hold_l,
        'break_pct_w': bp_w, 'break_pct_l': bp_l,
        'svpt_per_game_w': svpt_w, 'svpt_per_game_l': svpt_l,
        'tb_rate_w': tb_w, 'tb_rate_l': tb_l,
        'avg_game_len_w': gl_w, 'avg_game_len_l': gl_l,
        'ace_per_set_w': aps_w, 'ace_per_set_l': aps_l,
        'serve_dom_w': sdom_w, 'serve_dom_l': sdom_l,
        'serve_diff': serve_diff, 'break_diff': break_diff, 'hold_diff': hold_diff,
        'combined_serve': combined_srv, 'combined_break': combined_brk,
        'combined_aces': combined_ace, 'tb_rate_combined': tb_comb,
        'svpt_per_game_combined': svpt_comb,
        'form_w': form_w, 'form_l': form_l, 'form_diff': form_diff,
        'streak_w': streak_w, 'streak_l': streak_l,
        'surf_form_w': sfm_w, 'surf_form_l': sfm_l, 'surf_form_diff': sfm_diff,
        'tb_wr_w': tb_wr_w, 'tb_wr_l': tb_wr_l,
        'set5_wr_w': set5_wr_w, 'set5_wr_l': set5_wr_l,
        'clutch_diff': clutch_diff,
        'rest_w': rest_w, 'rest_l': rest_l,
        'm7_w': m7_w, 'm7_l': m7_l, 'm14_w': m14_w, 'm14_l': m14_l,
        'rest_diff': rest_diff, 'fatigue_diff': fatigue_diff,
        'h2h_n': h2h_n, 'h2h_bal': h2h_bal, 'h2h_surf': h2h_surf,
        'tour_n_w': tour_n_w, 'tour_n_l': tour_n_l,
        'in_elo_w': in_elo_w, 'in_elo_l': in_elo_l, 'in_elo_diff': in_elo_diff,
        'tour_n_diff': tour_n_diff,
        'elo_x_form': elo_x_form, 'surf_elo_x_surf_form': surf_elo_x_form,
        'serve_x_elo': serve_x_elo, 'clutch_x_round': clutch_x_round,
        'rank_x_form': rank_x_form, 'age_x_surface': age_x_surface,
        'pin_x_elo': pin_x_elo, 'market_x_serve': market_x_serve,
        'h2h_x_form': h2h_x_form, 'fatigue_x_round': fatigue_x_round,
        'bo5_x_clutch': bo5_x_clutch, 'gs_x_rank': gs_x_rank,
    }
    return feat

# ── PREDYKCJA ─────────────────────────────────────────────────────────────
print("\nGeneruję predykcje...")
predictions = []

for match in MATCHES:
    na, nb = match[0], match[1]
    sa = player_cache[na]
    sb = player_cache[nb]

    feats = build_features_full(match, sa, sb)
    X = pd.DataFrame([feats])

    result = {
        'match': f"{na} vs {nb}",
        'odds_a': match[8], 'odds_b': match[9],
        'pin_prob_a': feats['pin_prob_w'],
        'elo_prob_a': feats['elo_prob_w'],
    }

    for key, mdl in loaded.items():
        try:
            feat_names = mdl.feature_name_
            X_aligned = X.reindex(columns=feat_names, fill_value=0)
            prob = mdl.predict_proba(X_aligned)[0][1]
            result[f'p_{key}'] = round(prob, 4)
        except Exception as e:
            result[f'p_{key}'] = None

    predictions.append(result)

# ── WYŚWIETL PREDYKCJE ────────────────────────────────────────────────────
print("\n" + "═"*100)
print("PREDYKCJE WIMBLEDON 2026 — 1.07 (Day 3, 2R)")
print("P(straight)=straight sets (3:0/2:0)  P(5s)=5 setów  P(ou39)=O/U39.5  P(ou36)=O/U36.5  P(hcp9)=HCP>9.5  P(ou33)=O/U33.5")
print("═"*100)

print(f"{'Mecz':35s} | {'Kursy':11s} | {'Buk%A':>6} | {'Elo%A':>6} | {'P(str)':>7} | {'P(5s)':>6} | {'P(ou39)':>8} | {'P(ou36)':>8} | {'P(hcp9)':>8} | {'P(ou33)':>8}")
print("-"*100)

for p in predictions:
    def f(v): return f"{v*100:5.1f}%" if v is not None else "  n/a "
    print(f"{p['match']:35s} | {p['odds_a']:.2f}/{p['odds_b']:.2f} | "
          f"{f(p['pin_prob_a']):>6} | {f(p['elo_prob_a']):>6} | "
          f"{f(p.get('p_straight')):>7} | {f(p.get('p_fatigue5')):>6} | "
          f"{f(p.get('p_ou39')):>8} | {f(p.get('p_ou36')):>8} | "
          f"{f(p.get('p_hcp9')):>8} | {f(p.get('p_ou33')):>8}")

# ── VALUE BET DETECTION ───────────────────────────────────────────────────
print("\n" + "═"*100)
print("VALUE BETS — model_prob > implied_prob + 4%")
print("═"*100)

# Rynki dostępne w STS na Wimbledon (szacowane kursy)
# Kupon obejmuje: P(straight), O/U gemów, HCP
def gen_bets(predictions):
    bets = []
    for i, p in enumerate(predictions):
        na, nb = p['match'].split(' vs ')
        odds_a, odds_b = p['odds_a'], p['odds_b']
        pin_a = p['pin_prob_a']

        # O/U 39.5 gemów
        for model_key, threshold, market_label, side, sts_mult in [
            ('ou39', 0.5, 'UNDER 39.5 gemy', 'under', 1.85),
            ('ou36', 0.5, 'UNDER 36.5 gemy', 'under', 1.90),
            ('ou33', 0.5, 'UNDER 33.5 gemy', 'under', 1.95),
            ('ou39', 0.5, 'OVER 39.5 gemy', 'over', 1.85),
            ('ou36', 0.5, 'OVER 36.5 gemy', 'over', 1.90),
            ('straight', 0.5, 'STRAIGHT SETS', 'yes', 1.70),
            ('straight', 0.5, 'NIE STRAIGHT', 'no', 2.10),
            ('fatigue5', 0.5, '5 SETÓW', 'yes', 4.50),
            ('hcp9', 0.5, 'HCP >9.5 gemów', 'yes', 2.00),
        ]:
            raw = p.get(f'p_{model_key}')
            if raw is None: continue
            model_prob = raw if side in ('yes','over') else (1-raw)
            implied = 1/sts_mult
            edge = model_prob - implied
            ev   = model_prob * sts_mult - 1
            if edge > 0.04:  # min 4% edge
                bets.append({
                    'match': p['match'],
                    'market': market_label,
                    'sts_odds': sts_mult,
                    'model_prob': round(model_prob,4),
                    'implied_prob': round(implied,4),
                    'edge': round(edge,4),
                    'ev': round(ev,4),
                    'pin_prob_a': pin_a,
                })
    return sorted(bets, key=lambda x: -x['ev'])

all_bets = gen_bets(predictions)

if not all_bets:
    print("⚠️ Brak value betów przy progu 4% — sprawdź kursy STS")
else:
    print(f"\n  {'Mecz':35s} | {'Rynek':22s} | {'Kurs':>5} | {'Model%':>7} | {'Buk%':>6} | {'Edge':>6} | {'EV':>6}")
    print("  " + "-"*100)
    for v in all_bets[:15]:
        print(f"  {v['match']:35s} | {v['market']:22s} | {v['sts_odds']:5.2f} | "
              f"{v['model_prob']*100:6.1f}% | {v['implied_prob']*100:5.1f}% | "
              f"{v['edge']*100:+5.1f}% | {v['ev']*100:+5.1f}%")

# ── BUDOWA 3 KUPONÓW ──────────────────────────────────────────────────────
print("\n" + "═"*100)
print("╔══════════════════════════════════════════════════════════════════════╗")
print("║           KUPONY STS — WIMBLEDON 2026 — 1 LIPCA                    ║")
print("║                   15 zł = 3 × 5 zł                                  ║")
print("╚══════════════════════════════════════════════════════════════════════╝")

if len(all_bets) >= 2:
    # KUPON 1: najwyższy EV single lub 2-fold
    k1 = sorted(all_bets, key=lambda x: -x['ev'])[:2]
    k1_odds = round(np.prod([b['sts_odds'] for b in k1]), 2)
    k1_win  = round(5 * k1_odds, 2)
    print("\n📋 KUPON 1 — MAX VALUE AKO 2-fold (5 zł)")
    for b in k1:
        print(f"   ✅ {b['match']}")
        print(f"      {b['market']} @ {b['sts_odds']:.2f}  "
              f"[model: {b['model_prob']*100:.1f}% | edge: {b['edge']*100:+.1f}% | EV: {b['ev']*100:+.1f}%]")
    print(f"   🎯 Kurs łączny: {k1_odds:.2f}  |  Wygrana: {k1_win:.2f} zł")

    # KUPON 2: najstabilniejszy rynek × 3 mecze
    straight_bets = [b for b in all_bets if 'STRAIGHT' in b['market'] or 'UNDER' in b['market']]
    k2 = straight_bets[:3] if len(straight_bets) >= 3 else all_bets[:3]
    k2_odds = round(np.prod([b['sts_odds'] for b in k2]), 2)
    k2_win  = round(5 * k2_odds, 2)
    print("\n📋 KUPON 2 — STRUKTURALNY AKO 3-fold (5 zł)")
    for b in k2:
        print(f"   ✅ {b['match']}")
        print(f"      {b['market']} @ {b['sts_odds']:.2f}  "
              f"[model: {b['model_prob']*100:.1f}% | edge: {b['edge']*100:+.1f}%]")
    print(f"   🎯 Kurs łączny: {k2_odds:.2f}  |  Wygrana: {k2_win:.2f} zł")

    # KUPON 3: diversified — mix rynków
    used = set()
    k3 = []
    for b in sorted(all_bets, key=lambda x: -x['ev']):
        key = b['match'] + b['market']
        if key not in used and len(k3) < 3:
            k3.append(b)
            used.add(key)
    k3_odds = round(np.prod([b['sts_odds'] for b in k3]), 2)
    k3_win  = round(5 * k3_odds, 2)
    print("\n📋 KUPON 3 — DIVERSIFIED AKO 3-fold (5 zł)")
    for b in k3:
        print(f"   ✅ {b['match']}")
        print(f"      {b['market']} @ {b['sts_odds']:.2f}  "
              f"[model: {b['model_prob']*100:.1f}% | edge: {b['edge']*100:+.1f}%]")
    print(f"   🎯 Kurs łączny: {k3_odds:.2f}  |  Wygrana: {k3_win:.2f} zł")

    print(f"\n   💰 Łączna potencjalna wygrana: {k1_win + k2_win + k3_win:.2f} zł")
else:
    print("\n⚠️ Za mało value betów — podaj aktualne kursy STS żeby dopasować próg")

cur.close()
conn.close()
print("\n✅ Done.")
