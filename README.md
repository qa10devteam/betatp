# betatp.io — ATP Tennis Prediction Engine

## Overview
Professional tennis prediction engine for ATP matches.
Generates B2C coupons with positive Expected Value.

## Architecture
- **22 Axioms** (AX-01..AX-22): Mathematical foundation
- **68 Spec docs**: Module-level specifications  
- **Elo Engine** (6 variants): Overall + Hard/Clay/Grass + Serve/Return
- **Monte Carlo** (N=100k, vectorized): Match simulation
- **ML Ensemble**: LGBM(0.35) + XGB(0.25) + LR(0.10) + Elo(0.30)
- **De-vig**: Power/Shin method (minimizes favourite-longshot bias)
- **Half Kelly**: Optimal staking (f* / 2)
- **CLV Tracking**: Pinnacle closing line as truth signal
- **Live Engine**: In-play probabilities < 50ms (LUT precomputed)

## Coupon Types
- **Single**: Top 5 matches by EV > 2%
- **System 2/3**: 3 selections, 3 doubles
- **Trixie**: 3 doubles + 1 treble
- **Yankee**: 6 doubles + 4 trebles + 1 fourfold

## Data Sources
- TML-Database: 198,063 ATP matches (1968-2026)
- Shot-by-Shot: tennis_MatchChartingProject

## Quick Start
```bash
# Install
pip install -e .

# Run integration test
PYTHONPATH=. python scripts/integration_test.py

# Run API
PYTHONPATH=. uvicorn api.main:app --reload

# Daily pipeline (dry run)
PYTHONPATH=. python scripts/run_daily_pipeline.py
```

## Project Status
- [x] 22 mathematical axioms (specs/axioms/)
- [x] 68 module specs (specs/elo/mc/value/features/ml/live/derivative/clv/backtest/)
- [x] Elo Engine (6-variant)
- [x] Monte Carlo (N=100k vectorized)
- [x] Feature Engineering (54 features)
- [x] De-vig + EV + Kelly
- [x] ML Ensemble (LGBM+XGB+LR+Elo stacking)
- [x] Coupon Generator (singles + systems + Polish reasoning)
- [x] CLV Tracker
- [x] Live Engine
- [x] Backtest Engine
- [x] FastAPI REST API
- [x] End-to-end integration test (5/5 pass)
- [ ] Backtest run (2019-2025) — iter 136-139
- [ ] Frontend (Next.js) — future
- [ ] Telegram bot — future
