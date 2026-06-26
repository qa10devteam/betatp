# betatp.io — ATP Tennis Prediction Engine

Professional sports prediction platform for ATP tennis. Subscribers receive match predictions with embedded value signals — single bets and system combinations against Pinnacle closing lines.

## Architecture

```
Enhanced Elo Engine
    ↓
LightGBM v4–v22 (walk-forward CV)
    ↓
Monte Carlo simulation
    ↓
Value Detection (market edge vs Pinnacle)
    ↓
Kelly criterion sizing → B2C coupons
```

## Model Performance (v4, holdout 2024–2026)

| Metric | Model | Pinnacle |
|--------|-------|----------|
| AUC | **0.884** | 0.746 |
| Brier Score | **0.140** | 0.204 |

**Flat bet ROI (2024-2026, 1,989 matches):**

| Edge threshold | Bets | Win Rate | Flat ROI |
|---|---|---|---|
| ≥5% | 988 | 74.5% | **+42.4%** |
| ≥10% | 838 | 75.5% | **+47.2%** |
| ≥15% | 689 | 77.6% | **+53.7%** |
| ≥20% | 535 | 79.4% | **+64.3%** |

Pinnacle half-Kelly baseline: **ROI = -0.4%** (market is efficient without edge).

## Features

- **78,022 matches** (ATP 2001–2026)
- **66,444 Pinnacle/Bet365/Max odds** (2013–2026, 79% match rate)
- **823 tournament-level ERA5 weather records** (temp/rain/wind/humidity)
- Enhanced Elo (overall + surface-specific + EWMA form)
- H2H features (last-3, surface-specific)
- Fatigue model (days rest, matches in 14d)
- Player×weather interaction (heat/rain/wind win rates)
- Ranking trajectory (90-day delta)
- Serve/return rolling stats (ace%, 1st won%, break%)
- Market consensus divergence (Pinnacle vs Max/Avg spread)

## Model Versions

| Version | Hypothesis | AUC (holdout) |
|---------|-----------|---------------|
| v4 | Pinnacle odds + form | 0.8995 |
| v5 | +Weather ERA5 | 0.8608 |
| v6 | +Player×weather interaction | TBD |
| v7 | +Surface×weather cross | 0.8621 |
| v8 | +Fatigue upgrade | 0.8621 |
| v9 | +H2H last-3 + surface H2H | 0.8705 |
| v10 | +Ranking trajectory | 0.8621 |
| v11 | +Serve/return rolling | 0.8611 |
| v12 | Combo: H2H+fatigue+weather | **0.9226** |
| v13 | +Draw difficulty | 0.9510* |
| v14 | +Age×surface + peak distance | 0.9469* |
| v15 | +Market consensus divergence | 0.8704 |
| v16 | Full feature set (49 feats) | **0.9224** |
| v17 | SHAP top-30 selection from v16 | TBD |
| v18 | Ensemble: LightGBM + LogReg meta | TBD |
| v19 | XGBoost vs LightGBM comparison | TBD |
| v20 | Surface-specific models (4×LightGBM) | TBD |
| v21 | Polynomial + ratio features | TBD |
| v22 | Champion: best arch + calibration | TBD |

*\* Requires leakage audit*

## Stack

- **ML:** LightGBM, scikit-learn, XGBoost, SHAP
- **Data:** PostgreSQL (197k matches), pandas, pyarrow
- **Weather:** Open-Meteo ERA5 reanalysis
- **Odds:** tennis-data.co.uk (Pinnacle, Bet365, Max/Avg)
- **API:** FastAPI
- **Infra:** Python 3.11, Ubuntu 22.04

## Setup

```bash
# 1. Clone
git clone https://github.com/qa10devteam/betatp.git
cd betatp

# 2. Install
pip install -r requirements.txt

# 3. Database
createdb betatp
psql betatp < db/schema.sql
python db/import.py

# 4. Train
python scripts/train_versions.py --versions 4

# 5. Backtest
python scripts/backtest_v4.py

# 6. API
uvicorn api.main:app --reload
```

## Data Sources

- **Matches:** [Jeff Sackmann TML Database](https://github.com/JeffSackmann/tennis_atp)
- **Odds:** [tennis-data.co.uk](http://tennis-data.co.uk)
- **Weather:** [Open-Meteo ERA5](https://open-meteo.com)

---

*betatp.io — built by [qa10.io](https://qa10.io)*
