# betatp.io — Status kontynuacji (2026-06-26, sesja 2)

## Repo GitHub
https://github.com/qa10devteam/betatp (private, org: qa10devteam)
Lokalizacja: `/home/ubuntu/betatp/`
PostgreSQL: host=localhost dbname=betatp user=postgres password=betatp2024

---

## Stan treningu (w TOKU przy zamknięciu wątku)

### Proces: `proc_6ae7e2418908`
```bash
cd /home/ubuntu/betatp && PYTHONPATH=. python scripts/train_versions.py --versions 9,10,11,12,13,14,15,16,17,18,19,20,21,22 2>&1 | tee models/train_clean_v9-v22.log
```
**Status przy zamknięciu wątku:** trening v11 w toku (AUC=0.8797 WF 2014→2017)
**Log:** `models/train_clean_v9-v22.log`

Jeśli proces nie żyje → uruchom ponownie polecenie powyżej.

---

## Historia bugów i napraw

### Bug #1 — Główny leakage odds (NAPRAWIONY commit 9601e5d)
`fix_base_pairs()`: b365/max/avg/odds_consensus były shared `(col,col)` → model zawsze widział P(winner wins).
Fix: dodane `_l` kolumny (1-prob, -log_odds).

### Bug #2 — v6 pw_heat_wr (SUSPECT, nie naprawiony)
AUC=0.9866 po fix #1. `pw_heat_wr_w/l` koreluje z rankingiem. V6 jest de facto pomijalny.

### Bug #3 — Shared delta features (NAPRAWIONY w tej sesji)
Następujące features były używane jako `(col, col)` w make_ab_dataset():
- `h2h_wins_delta_3` — delta z perspektywy winnera (zawsze winner-oriented)
- `h2h_surf_winrate` — win rate z perspektywy winnera
- `rank_traj_diff` — rank_traj_w - rank_traj_l (zawsze winner-oriented)
- `draw_diff_delta` — draw_diff_w - draw_diff_l (usunięty z par)

**Fix:** W `build_h2h()` dodano `_w` i `_l` kolumny. Wszystkie pary zamienione na asymetryczne:
- `(h2h_wins_delta_3_w, h2h_wins_delta_3_l)`
- `(h2h_surf_winrate_w, h2h_surf_winrate_l)`
- `(rank_traj_w, rank_traj_l)`

Łącznie 22 poprawki w `scripts/train_versions.py`.

### Bug #4 — v9 AUC=0.9975 (NOWY, do zbadania!)
Po naprawie #3, v9 nadal ma AUC=0.9975 w holdout.
TOP-5 features: winner_rank_a, winner_age_a, winner_age_b, winner_rank_b, **h2h_surf_winrate_a**
`h2h_surf_winrate_a` dominuje — mimo rename na _w/_l, efektywnie encode'uje wynik.
**Prawdopodobna przyczyna:** `h2h_surf_winrate` obliczana jest z perspektywy `winner_id` danego meczu — więc `_w = winrate gracza który WYGRAŁ ten mecz`. Po AB flip `_a` = winrate zawsze gracza który wygrał = leakage.
**Fix do zaimplementowania:** build_h2h() musi zwracać DWIE kolumny — jedną dla gracza A, drugą dla gracza B (identyfikowane przez ID, nie winner/loser):
  ```python
  # Zamiast h2h_surf_winrate_w/l (obie z perspektywy winnera)
  # Trzeba: dla każdego meczu obliczyć winrate gracza_A i gracza_B niezależnie od wyniku
  ```

---

## Wyniki (czyste — po fix #1, przed fix #3)

| Wersja | AUC holdout | BS | Opis |
|--------|------------|-----|------|
| v5  | 0.8030 | 0.1818 | +Weather ERA5 |
| v7  | 0.8041 | 0.1814 | +Surface×weather cross |
| v8  | 0.8060 | 0.1807 | +Fatigue |
| v12 | **0.8707** ✅ | 0.1453 | Combo H2H+fatigue+weather ← BEST CLEAN (stare featy) |

## Wyniki (po fix #3 — trening w toku):
Sprawdź: `cat models/versions_results.json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'{v[\"version\"]:4s}  AUC={v.get(\"holdout_auc\",0):.4f}  {v.get(\"hypothesis\",\"\")}') for v in sorted(d, key=lambda x: x.get('holdout_auc',0), reverse=True)]"`

---

## Co zrobić dalej

### Priorytet 1: Sprawdź czy trening skończył
```bash
tail -30 /home/ubuntu/betatp/models/train_clean_v9-v22.log
```
Jeśli nie — uruchom ponownie (patrz wyżej).

### Priorytet 2: Napraw Bug #4 — h2h leakage
W `build_h2h()` zmienić podejście: zamiast `winner_id`-centric, liczyć winrate dla obu graczy niezależnie od wyniku:

```python
def build_h2h(df):
    df = df.sort_values("tourney_date").reset_index(drop=True)
    h2h = {}      # (sorted_pair) → [(date, winner_id, surface)]
    
    h2h_wr_w, h2h_wr_l = [], []    # winrate winnera / losera pre-match
    h2h_delta_w, h2h_delta_l = [], []  # last-3 H2H z perspektywy winnera/losera
    h2h_surf_wr_w, h2h_surf_wr_l = [], []  # surface winrate obu graczy
    
    for _, row in df.iterrows():
        wid = str(row.get("winner_id","")); lid = str(row.get("loser_id",""))
        surf = str(row.get("surface",""))
        key = tuple(sorted([wid, lid]))
        history = h2h.get(key, [])
        last3 = history[-3:]
        
        # Winrate z perspektywy każdego gracza (pre-match, before appending)
        wins_w = sum(1 for (_,w,_) in last3 if w == wid)
        wins_l = sum(1 for (_,w,_) in last3 if w == lid)
        h2h_delta_w.append(wins_w - (len(last3)-wins_w))
        h2h_delta_l.append(wins_l - (len(last3)-wins_l))
        
        surf_hist = [(d,w,s) for d,w,s in history if s == surf]
        sw = sum(1 for (_,w,_) in surf_hist if w == wid)
        sl = sum(1 for (_,w,_) in surf_hist if w == lid)
        tot = len(surf_hist)
        h2h_surf_wr_w.append(sw/(tot+1))
        h2h_surf_wr_l.append(sl/(tot+1))
        
        h2h.setdefault(key, []).append((row["tourney_date"], wid, surf))
    
    df["h2h_wins_delta_3_w"] = h2h_delta_w
    df["h2h_wins_delta_3_l"] = h2h_delta_l
    df["h2h_surf_winrate_w"] = h2h_surf_wr_w
    df["h2h_surf_winrate_l"] = h2h_surf_wr_l
    return df
```

Pary w wersjach pozostają bez zmian `(h2h_wins_delta_3_w, h2h_wins_delta_3_l)` — tylko logika obliczeń musi być symetryczna.

### Priorytet 3: Po naprawie h2h — re-trening v9-v22
```bash
cd /home/ubuntu/betatp
PYTHONPATH=. python scripts/train_versions.py --versions 9,10,11,12,13,14,15,16,17,18,19,20,21,22 2>&1 | tee models/train_h2h_fix.log
```

### Priorytet 4: Backtest na najlepszym modelu
Po otrzymaniu czystych wyników (~0.83-0.89 AUC):
```bash
# Sprawdź który model jest najlepszy:
cat models/versions_results.json | python3 -c "import json,sys; d=json.load(sys.stdin); v=sorted(d,key=lambda x:x.get('holdout_auc',0),reverse=True)[0]; print(v)"
# Uruchom backtest:
PYTHONPATH=. python scripts/backtest_v4.py
# lub napisz backtest_v22.py jeśli backtest_v4.py jest hardkodowany na v4
```

---

## Architektura systemu
```
Enhanced Elo Engine → LightGBM v4-v22 (walk-forward CV)
    → Monte Carlo → Value Detection (edge vs Pinnacle)
    → Kelly criterion sizing → B2C coupons (betatp.io)
```
Holdout: 2024-2026 (6,150 meczów, Pinnacle AUC=0.746)
Train: 2004-2023 (71,872 meczów)

## Pliki kluczowe
```
scripts/train_versions.py          — główny framework treningu v4-v22
scripts/backtest_v4.py             — backtest Kelly + flat bet (hardkodowany na v4)
data/matches_with_odds.parquet     — 78,022 meczów z kursami
data/weather_features.parquet      — ERA5 weather per turniej
models/versions_results.json       — wyniki wszystkich wersji
models/train_clean_v9-v22.log      — log bieżącego treningu (fix #3)
models/train_all_final.log         — log poprzedniego treningu (fix #1)
```

## Modele wytrenowane (czyste po fix #1, PRZED fix #3):
```
models/lgbm_v5_*   AUC=0.803
models/lgbm_v7_*   AUC=0.804
models/lgbm_v8_*   AUC=0.806
models/lgbm_v12_20260626_1211.joblib  AUC=0.871 ← best verified clean
```
