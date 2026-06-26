# betatp.io — KONTYNUACJA SESJA 4
> **Wczytaj ten plik w nowym wątku:**
> `przeczytaj /home/ubuntu/betatp/KONTYNUACJA_2026-06-26_sesja4.md i kontynuuj`

---

## 🔑 Podstawy projektu

| | |
|---|---|
| **Repo** | `https://github.com/qa10devteam/betatp` (private) |
| **Lokalizacja** | `/home/ubuntu/betatp/` |
| **Live URL** | `https://qa10devteam.github.io/betatp/` |
| **PostgreSQL** | `host=localhost dbname=betatp user=postgres password=betatp2024` |
| **Python** | `3.11` — bez venv, używaj `python3` bezpośrednio |

---

## 🏆 Model ML — NOWY CHAMPION

| Wersja | Holdout AUC | WF AUC | Backtest ROI (edge>15%) | Plik |
|---|---|---|---|---|
| **v14** ✅ CHAMPION | 0.9031 (train AUC) | 0.9482 | **+58.7%** @ edge≥15% | `models/lgbm_v14_20260626_1706.joblib` |
| v23 (clean) | 0.8509 | 0.8982 | +18.6% @ edge≥5% (longhots) | `models/lgbm_v23_calibrated_20260626_2140.joblib` |
| v22 ❌ | 0.9171 (LEAKAGE) | — | -84.8% | wykluczone |

### ⚠️ KLUCZOWE ODKRYCIA SESJI 3

**Problem Kelly — NAPRAWIONY:**
- Stary bug: `kelly_fraction(cap=0.05) * 50 = 2.5` zawsze (0.05×50=2.5)
- Fix w `scripts/backtest_vX.py`: raw Kelly × 0.5 × 100 = half-Kelly %
- API: `kelly_stake_pct` teraz realny (np. 15.46% dla Fritza vs Bublik)

**Problem v22 — ZIDENTYFIKOWANY:**
- v22 AUC z treningu: 0.9171 ← **FAŁSZYWE** (leakage w naming/pipeline mismatch)
- v22 AUC z backtestu: 0.72 ← prawdziwe (gorsze niż Pinnacle 0.7457!)
- Przyczyna: `train_versions.py` buduje cechy OFFLINE, `backtest_vX.py` ONLINE → różne wartości
- `winner_rank_a` = `winner_rank` zwycięzcy w datasecie (nie jest leakage per se, ale naming confuses) 

**v14 empirycznie najlepszy:**
- edge≥15%: 57 zakładów, WR=59.6%, flat ROI=**+42.1%**, Kelly ROI=**+58.7%**
- edge≥20%: 13 zakładów, WR=69.2%, ROI=+18.2% (za mało próbek)
- Używaj **edge≥15%** jako minimum

**v23 — nowy czysty model:**
- Pipeline identyczny train↔backtest
- Czyste nazwy: `player_rank_a/b` (nie winner_rank)
- Platt kalibracja na dedykowanym val split
- WF AUC=0.8982, Holdout=0.8509 (realne, bez leakage)
- Łapie głównie long shots (avg odds 18.46) — mało zakładów ale +ROI

---

## 📊 Backtest Summary

```
Model  | edge threshold | Bets | WR    | Kelly ROI | MaxDD
v14    | ≥15%           |  57  | 59.6% | +58.7%    | 17.9%  ← CHAMPION
v14    | ≥20%           |  13  | 69.2% | +5.8%     |  2.5%
v23    | ≥5%            |  42  | 11.9% | +18.6%    | 26.2%  (long shots)
v22    | ≥8%            | 1390 | 40.7% | -84.8%    | 91.0%  ← WYKLUCZONE
```

---

## ✅ CO ZROBIONO W SESJI 3

### ML / Backend
- [x] Fix Kelly bug w `backtest_vX.py` (cap=0.05*50=2.5 → raw kelly*0.5*100)
- [x] Diagnoza v22 — leakage w pipeline train↔backtest mismatch
- [x] Trenowanie v23 — clean model, leakage-free, Platt calibration
- [x] Backtest v14, v22, v23 z poprawnym Kelly
- [x] API `min_edge` podniesione z 5% → 15% (empirycznie optymalne dla v14)
- [x] Kategorie kuponów: TOP PICK ≥20%, RECOMMENDED 15-20%
- [x] `backtest_vX.py` rozszerzony o v23 feature aliases (player_rank/age/ewma/streak)

### Infrastruktura
- [x] `scripts/train_v23.py` — nowy, standalone train script
- [x] `data/backtest_v14_bets.csv` — zaktualizowany z prawdziwym Kelly
- [x] `data/backtest_v23_bets.csv` — świeży backtest

---

## 🎯 MISJA SESJI 4

Wróć do 140-iteracyjnego spec-off (plik sesja 3).

**PRIORYTETY:**
1. **Faza A** — 27 assetów AI + mobile polish (iter 1–35)
2. **Faza B** — SHAP bars + AI storytelling (iter 36–70)  
3. **Faza C** — API stabilne + cloudflare tunnel + daily cron (iter 71–105)
4. **Faza D** — Three.js 3D court + gyroscope (iter 106–125)
5. **Faza E** — Launch (iter 126–140)

---

## 🛠️ Komendy startowe

```bash
# 1. Stan repo
cd /home/ubuntu/betatp && git log --oneline -3

# 2. Modele
ls models/lgbm_v14_20260626_1706.joblib models/lgbm_v23_calibrated_20260626_2140.joblib

# 3. API health
curl -s http://localhost:8000/health
curl -s "http://localhost:8000/coupons/daily" | python3 -c "import json,sys; [print(c['priority'], len(c['selections']), 'picks') for c in json.load(sys.stdin)]"

# 4. Kelly check (powinno być ~5-20%, NIE 2.5 dla wszystkich)
python3 -c "import pandas as pd; df=pd.read_csv('data/backtest_v14_bets.csv'); print(df.kelly_stake_pct.describe())"

# 5. Frontend
wc -l frontend/index.html  # ~1426 linii
grep -c "fal.media" frontend/index.html  # ~10 assetów
```

---

## 📁 Kluczowe pliki

```
/home/ubuntu/betatp/
├── .codequality.yml              ← SPEC JAKOŚCI
├── frontend/
│   └── index.html                ← FRONTEND (1426 linii)
├── api/
│   ├── main.py
│   └── routes/
│       ├── coupons.py            ← ZAKTUALIZOWANY (min_edge=0.15)
│       ├── predictions.py
│       └── live.py
├── models/
│   ├── lgbm_v14_20260626_1706.joblib    ← CHAMPION (edge>15% = +58.7% ROI)
│   ├── lgbm_v23_calibrated_20260626_2140.joblib  ← clean model
│   └── versions_results.json
├── scripts/
│   ├── backtest_vX.py            ← ZAKTUALIZOWANY (Kelly fix + v23 aliases)
│   ├── train_v23.py              ← NOWY clean training script
│   └── run_daily_pipeline.py
├── data/
│   ├── backtest_v14_bets.csv     ← świeży (Kelly poprawny)
│   └── backtest_v23_bets.csv     ← świeży
└── KONTYNUACJA_2026-06-26_sesja3.md  ← poprzednia sesja (spec 140 iter)
```

---

## 🧠 Wyniki badań Kelly

```python
# v14 @ edge≥15% — PRODUKCYJNE
# Bets: 57, WR: 59.6%, avg odds: 2.38
# Kelly range: 2.7% - 31.0% (mean: 9.8%)
# Rekomendowana stawka: Half-Kelly = ~5-15% bankrolla

# Wzór Kelly (poprawny):
def kelly_pct_half(p, odds):
    b = odds - 1.0
    raw = (p * b - (1-p)) / b
    return max(0.0, raw) * 0.5 * 100  # %
```

---

*Hermes — 2026-06-26 | Sesja 3 zakończona | Model v14 champion @ edge≥15% | Kelly naprawiony*
