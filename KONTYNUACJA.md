# betatp.io — Status kontynuacji (2026-06-26)

## Repo GitHub
https://github.com/qa10devteam/betatp (private, org: qa10devteam)
Ostatni commit: `732fe88` — fix leakage odds_consensus/log_odds + v20 runner

## Lokalizacja
`/home/ubuntu/betatp/`
PostgreSQL: host=localhost dbname=betatp user=postgres password=betatp2024

---

## Stan treningu (przerwany ręcznie przy v17)

### Czyste wyniki (train_all_final.log — po naprawie leakage)
Trening uruchomiony: `proc_ea6eea8f667d` — ZABITY przy v17
Plik logu: `models/train_all_final.log`

| Wersja | AUC holdout | BS | Opis |
|--------|------------|-----|------|
| v5  | 0.8030 | 0.1818 | +Weather ERA5 |
| v6  | **0.9866** ⚠️ | 0.0328 | +pw_heat/rain/wind_wr — SUSPECT (do zbadania) |
| v7  | 0.8041 | 0.1814 | +Surface×weather cross |
| v8  | 0.8060 | 0.1807 | +Fatigue |
| v9  | ~0.874 | ~0.143 | +H2H (z poprzedniego runu) |
| v10 | ~0.860 | ~0.150 | +Rank trajectory |
| v11 | ~0.860 | ~0.150 | +Serve/return |
| v12 | **0.8707** ✅ | 0.1453 | Combo H2H+fatigue+weather |
| v13 | (przerwane przy start) | — | draw_difficulty |
| v14–v22 | (nie uruchomione) | — | — |

**Wersje do dokończenia:** 13, 14, 15, 16, 17, 18, 19, 20, 21, 22

---

## Krytyczne bugi — NAPRAWIONE

### 1. Leakage w fix_base_pairs() ← GŁÓWNY BUG
Plik: `scripts/train_versions.py`, funkcja `fix_base_pairs()`

**Problem:** b365_prob_w, max_prob_w, avg_prob_w były jako `(col, col)` shared →
model dostawał P(winner wins) zawsze niezależnie od A/B flip → AUC=0.999 fake.

**Fix (commit 9601e5d):**
- `b365_prob_l = 1 - b365_prob_w`
- `max_prob_l = 1 - max_prob_w`
- `odds_consensus_l = 1 / odds_consensus_w` (bo to ratio MaxW/PSW, nie prob)
- `pin_log_odds_l = -pin_log_odds` (log-odds flipped)

### 2. v6 — pw_heat_wr nadal podejrzane
AUC=0.9866 po naprawie leakage. Suspect: `pw_heat_wr_w/l` (win rate gracza
w gorących warunkach) koreluje zbyt mocno z rankingiem → efektywnie leakuje
doświadczenie gracza. Do zbadania: usunąć `pw_heat_wr_a/b`, zostawić tylko
`pw_heat_edge`. V6 jest wtedy prawie identyczne z v5.

### 3. v13 — draw_difficulty leakage (poprzedni run: AUC=0.952)
`build_draw_difficulty` iteruje po meczach i dodaje wcześniej pokonanych
graczy. Prawdopodobnie OK (pre-match), ale wymaga weryfikacji podobnie jak v6.

### 4. Inne naprawione bugi
- v19 XGBoost: `early_stopping_rounds` przeniesiony do konstruktora
- v22: `cv='prefit'` → `cv=5` (sklearn 1.9 API change)
- v18 stacking: `data.reindex(columns=feats)` zamiast `data[avail]`
- v20 runner: obsługa `(meta, surf_dict, fc)` tuple
- v21/v22: `rank_ratio` przed AB flip → `rank_inv_w`/`rank_inv_l` para

---

## Backtest v4 (stare modele — z leakage, nieaktualne)
Plik: `models/backtest_v4_final.log`
- AUC model=0.884 (z leakage), Pinnacle=0.746
- Flat ROI edge≥10%: +47.2% (838 bets, WR=75.5%)
- **UWAGA: wyniki z leakage — po wytrenowaniu czystych modeli uruchomić backtest ponownie**

---

## Co zrobić dalej

### Priorytet 1: Dokończyć trening
```bash
cd /home/ubuntu/betatp
PYTHONPATH=. python scripts/train_versions.py --versions 13,14,15,16,17,18,19,20,21,22 2>&1 | tee models/train_v13-v22_final.log
```

### Priorytet 2: Zbadać v6 (pw_heat_wr leakage)
```bash
# Sprawdź czy usunięcie pw_heat_wr_a/b naprawia AUC
# W run_v6() zmienić pairs: usunąć ('pw_heat_wr_w','pw_heat_wr_l') etc.
# Zostawić tylko pw_heat_edge jako shared feature
```

### Priorytet 3: Uruchomić czysty backtest
```bash
PYTHONPATH=. python scripts/backtest_v4.py
# Lub po wytrenowaniu v22: napisać backtest_v22.py
```

### Priorytet 4: Porównanie modeli
Po zakończeniu treningu:
```bash
cat models/versions_results.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for v in sorted(d, key=lambda x: x.get('holdout_auc',0), reverse=True):
    print(f'{v[\"version\"]}: AUC={v.get(\"holdout_auc\",0):.4f}  {v.get(\"hypothesis\",\"\")}')
"
```

---

## Pliki kluczowe
```
scripts/train_versions.py   — główny framework treningu v4-v22
scripts/backtest_v4.py      — backtest Kelly + flat bet
scripts/build_odds_dataset.py — import odds z tennis-data.co.uk
data/matches_with_odds.parquet — 78,022 meczów z kursami
data/weather_features.parquet  — ERA5 weather per turniej
models/versions_results.json   — wyniki wszystkich wersji
models/train_all_final.log     — log ostatniego treningu
```

## Modele (wytrenowane, czyste):
```
models/lgbm_v5_20260626_*.joblib   AUC=0.803
models/lgbm_v7_20260626_*.joblib   AUC=0.804
models/lgbm_v8_20260626_*.joblib   AUC=0.806
models/lgbm_v12_20260626_1211.joblib  AUC=0.871 ← BEST CLEAN
```

---

## Architektura systemu
```
Enhanced Elo Engine → LightGBM v4-v22 (walk-forward CV)
    → Monte Carlo → Value Detection (edge vs Pinnacle)
    → Kelly criterion sizing → B2C coupons (betatp.io)
```

Holdout period: 2024-2026 (6,150 meczów, Pinnacle AUC=0.746)
Train period: 2004-2023 (71,872 meczów)
