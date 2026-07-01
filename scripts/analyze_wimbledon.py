import pandas as pd, numpy as np, joblib
from pathlib import Path

model     = joblib.load(sorted(Path('models').glob('lgbm_v14_*.joblib'))[-1])
feat_cols = joblib.load(sorted(Path('models').glob('feat_cols_v14_*.joblib'))[-1])
df = pd.read_parquet('data/matches_with_odds.parquet')
df['year'] = pd.to_datetime(df['tourney_date']).dt.year

def est_sts_odds(p, margin=0.08):
    if p <= 0.01 or p >= 0.99: return 99.0
    return round((1/p) * (1 - margin), 2)

# Dane historyczne na trawie per gracz + model v14
# p30h/p31h/p32h = historyczny rozkład setów gdy gracz wygrywa na trawie
picks = {
    'Mensik':    dict(p_model=0.854, pin=1.38, p30h=0.500, p31h=0.333, p32h=0.000, elo=1557,
                     note='13M grass WR=0.46 (mały sample). #15 vs Samuel ~200. Forma ok.'),
    'Lehecka':   dict(p_model=0.860, pin=1.27, p30h=0.333, p31h=0.083, p32h=0.083, elo=1691,
                     note='19M grass WR=0.63. Forma rosnaca rank_trend=-8. Elo #2 w picks.'),
    'Tiafoe':    dict(p_model=0.863, pin=1.23, p30h=0.500, p31h=0.167, p32h=0.042, elo=1618,
                     note='43M grass WR=0.56. Sprawdzony serwisant, lubi trawę.'),
    'Khachanov': dict(p_model=0.796, pin=1.30, p30h=0.400, p31h=0.167, p32h=0.200, elo=1622,
                     note='48M grass WR=0.63 ale AŻ 16.7% meczów idzie do 5 setów!'),
    'Nakashima': dict(p_model=0.832, pin=1.23, p30h=0.389, p31h=0.222, p32h=0.000, elo=1658,
                     note='33M grass WR=0.55. Vs wildcard Pinnington Jones. Elo=1658.'),
    'Zverev':    dict(p_model=0.906, pin=1.10, p30h=0.403, p31h=0.028, p32h=0.056, elo=1724,
                     note='123M grass WR=0.59. Hist 3:0=40% (model mówi 77%!) - rozbieznosc!'),
    'Djokovic':  dict(p_model=0.952, pin=1.05, p30h=0.524, p31h=0.258, p32h=0.081, elo=1770,
                     note='143M grass WR=0.87. GOAT na trawie. Elo=1770 #1.'),
    'Hijikata':  dict(p_model=0.528, pin=1.34, p30h=0.714, p31h=0.000, p32h=0.000, elo=1530,
                     note='17M grass: gdy WYGRYWA to az 71% w 3:0! Agresywny serwisant.'),
}

print('='*75)
print('WIMBLEDON 2026 — ANALIZA VALUE — MODEL v14 AUC=0.903 — BEST OF 5')
print('='*75)

best_bets = []

for player, d in picks.items():
    p_model = d['p_model']
    pin     = d['pin']
    p_pin   = 1/pin
    p30h, p31h, p32h = d['p30h'], d['p31h'], d['p32h']
    elo     = d['elo']
    note    = d['note']

    # Rozkład setów: normalizuj historię do P(win) modelu
    hist_win_sum = p30h + p31h + p32h
    if hist_win_sum > 0.01:
        p30 = (p30h / hist_win_sum) * p_model
        p31 = (p31h / hist_win_sum) * p_model
        p32 = (p32h / hist_win_sum) * p_model
    else:
        p30 = p_model * 0.55
        p31 = p_model * 0.30
        p32 = p_model * 0.15

    p_loss = 1 - p_model

    # Rynki BO5
    rynki = [
        # (nazwa, P(zdarzenia), kurs_fair_szacunek, typ)
        ('1/2 Zwycięzca',               p_model,       pin,                          'main'),
        ('HCP set -1.5  (wygrywa 3:0/3:1)',  p30+p31,  est_sts_odds(p30+p31),        'hcp'),
        ('HCP set -2.5  (tylko 3:0)',   p30,            est_sts_odds(p30),            'hcp'),
        ('U4.5 setów    (mecz ≤4 setów)',p30+p31,       est_sts_odds(p30+p31),        'ou'),
        ('O4.5 setów    (5 setów)',      p32+p_loss,     est_sts_odds(p32+p_loss),     'ou'),
        ('Rywal weźmie 1 seta (+1.5)',   p31+p32+p_loss, est_sts_odds(p31+p32+p_loss),'hcp'),
    ]

    print(f'\n{"="*75}')
    print(f'  {player:12s} | PIN={pin:.2f} | MODEL={p_model:.3f} | ELO={elo} | EDGE={p_model-p_pin:+.3f}')
    print(f'  {note}')
    print(f'  P(3:0)={p30:.3f}  P(3:1)={p31:.3f}  P(3:2)={p32:.3f}  P(przegrana)={p_loss:.3f}')
    print(f'  {"Rynek":<38} {"P":>6}  {"~kurs":>6}  {"edge":>7}  {"ocena"}')
    print(f'  {"-"*70}')

    for nazwa, prob, kurs, typ in rynki:
        fair_p = 1/kurs if kurs < 90 else 0
        edge   = prob - fair_p
        if prob > 0.70:
            ocena = '🔥 VALUE' if edge > 0.06 else ('✅ ok' if edge > 0.02 else '⬜ slim')
        elif prob > 0.45:
            ocena = '🔥 VALUE' if edge > 0.06 else ('✅ ok' if edge > 0.02 else '⬜ slim')
        else:
            ocena = '⬜ low_p'

        print(f'  {nazwa:<38} {prob:>6.3f}  {kurs:>6.2f}  {edge:>+7.3f}  {ocena}')

        if edge > 0.04 and prob > 0.35:
            best_bets.append({
                'player': player, 'rynek': nazwa, 'prob': prob,
                'kurs': kurs, 'edge': edge, 'elo': elo, 'p_model': p_model,
                'pin': pin
            })

print(f'\n{"="*75}')
print('TOP VALUE BETS — sorted by edge × prob (EV szacunkowe):')
print('='*75)
best_bets_sorted = sorted(best_bets, key=lambda x: -(x['edge'] * x['prob']))
for b in best_bets_sorted:
    ev_5zl = 5 * b['kurs'] * b['prob'] - 5
    print(f"  🎯 {b['player']:12s}  {b['rynek']:38s}  P={b['prob']:.3f}  ~{b['kurs']:.2f}  edge={b['edge']:+.3f}  EV(5zł)={ev_5zl:+.2f}")

print()
# Kupony optymalne
print('='*75)
print('OPTYMALNE KUPONY (15 zł / 3×5 zł) — best of 5 corrected:')
print('='*75)

# Selekcja: bierzemy top bety z różnych meczów
top = [b for b in best_bets_sorted if b['edge'] > 0.04]

# K1: Najwyższy łączny kurs z sensownym P
k1 = [b for b in top if b['p_model'] >= 0.83][:4]
k1_odds = np.prod([b['kurs'] for b in k1])
k1_prob  = np.prod([b['prob'] for b in k1])
print(f'\nKUPON 1 (wysoki kurs): kurs={k1_odds:.2f}x  P={k1_prob:.3f}  wygrana={5*k1_odds:.2f} zł')
for b in k1:
    print(f'  • {b["player"]:12s}  {b["rynek"]:<38}  ~{b["kurs"]:.2f}  P={b["prob"]:.3f}')

# K2: Mix mainstream + alter rynki
k2_candidates = sorted(top, key=lambda x: -x['edge'])
seen_players = set()
k2 = []
for b in k2_candidates:
    if b['player'] not in seen_players and len(k2) < 4:
        k2.append(b)
        seen_players.add(b['player'])
k2_odds = np.prod([b['kurs'] for b in k2])
k2_prob  = np.prod([b['prob'] for b in k2])
print(f'\nKUPON 2 (najwyższy edge): kurs={k2_odds:.2f}x  P={k2_prob:.3f}  wygrana={5*k2_odds:.2f} zł')
for b in k2:
    print(f'  • {b["player"]:12s}  {b["rynek"]:<38}  ~{b["kurs"]:.2f}  P={b["prob"]:.3f}')

# K3: Bezpieczniejszy — wysokie P
k3_candidates = sorted(top, key=lambda x: -x['prob'])
seen_players = set()
k3 = []
for b in k3_candidates:
    if b['player'] not in seen_players and len(k3) < 4:
        k3.append(b)
        seen_players.add(b['player'])
k3_odds = np.prod([b['kurs'] for b in k3])
k3_prob  = np.prod([b['prob'] for b in k3])
print(f'\nKUPON 3 (najwyższe P): kurs={k3_odds:.2f}x  P={k3_prob:.3f}  wygrana={5*k3_odds:.2f} zł')
for b in k3:
    print(f'  • {b["player"]:12s}  {b["rynek"]:<38}  ~{b["kurs"]:.2f}  P={b["prob"]:.3f}')
