# 🎾 atpbet.io — ATP Tennis Betting Intelligence

> **ATP Intelligence. Real Edge.**
> 6-model LightGBM ensemble trained on 197,000 ATP matches (2000–2023)

[![Tests](https://img.shields.io/badge/tests-10%20passing-brightgreen)](tests/)
[![Models](https://img.shields.io/badge/models-6%20champion-lime)](models/)
[![AUC](https://img.shields.io/badge/best%20AUC-0.935-blue)](models/)

---

## What is atpbet?

**atpbet** is a quantitative ATP tennis betting intelligence platform.

Given a scheduled ATP match, atpbet predicts the probability of 6 specific betting markets:

| Market | Model | AUC | Description |
|--------|-------|-----|-------------|
| Straight Sets | v70_is_straight | **0.9354** | Match ends 2:0 or 3:0 |
| Full Distance 5 Sets | v80_is_5sets | 0.9195 | Match goes to 5th set |
| Over/Under 39.5 Games | v54_ou39 | 0.9276 | Total games exceed 39.5 |
| Over/Under 36.5 Games | v80_over_36 | 0.8925 | Total games exceed 36.5 |
| Game Handicap >9.5 | v80_hcp_9 | 0.8360 | Winner takes ≥10 more games |
| Over/Under 33.5 Games | v39_cross | 0.8326 | Total games exceed 33.5 |

### 2024 Backtest (out-of-sample)
- **57 bets** above 5% edge threshold
- **59.6% win rate**
- **+58.7% flat ROI**
- **17.9% max drawdown**

---

## Architecture

```
atpbet/
├── api/
│   ├── main.py              # FastAPI app (v1.0.0)
│   └── routes/
│       ├── predictions.py   # /api/v1/predictions/
│       └── coupons.py       # /api/v1/coupons/
├── config.py                # Centralised config, PG DSN, market metadata
├── engine/
│   ├── feature_builder.py   # 103-element feature vector from PostgreSQL
│   ├── prediction_service.py# Edge / EV / Kelly computation
│   └── value_detector.py    # Value bet detection + coupon builder
├── ml/
│   ├── champion_stack.py    # Registry for 6 champion LightGBM models
│   └── lgbm_model.py        # Model wrapper + calibration
├── models/                  # Saved .pkl models + metadata JSONs (v23–v80)
├── scripts/
│   ├── train_v23_v40.py     # Multi-target training framework
│   ├── train_v41_v80.py     # Extended training (1,553 lines)
│   └── generate_coupons.py  # Daily coupon generator
├── tasks/
│   └── daily_coupon_scheduler.py  # Cron + Telegram push
├── tests/
│   └── test_api.py          # 10 smoke tests (all passing)
└── frontend/
    └── index.html           # Production SPA (English, dark premium UI)
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16 with `betatp` database (197,495 ATP matches)

### Install
```bash
git clone https://github.com/qa10devteam/betatp.git
cd betatp
pip install -r requirements.txt
```

### Configure
```bash
cp .env.example .env
# Edit .env: set DATABASE_URL, TELEGRAM_BOT_TOKEN, etc.
```

### Run API
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: `http://localhost:8000/docs`

### Key endpoints
```
GET  /health                              # Health check
GET  /api/v1/coupons/today               # Today's value picks + 3 coupons
GET  /api/v1/predictions/markets         # 6 prediction market metadata
POST /api/v1/predictions/match           # Single match prediction
GET  /api/v1/predictions/model/info      # Champion stack info
GET  /api/v1/predictions/player?name=... # Player rolling stats
```

### Run tests
```bash
pytest tests/ -v
```

### Generate daily coupons
```bash
python3 tasks/daily_coupon_scheduler.py                   # run once
python3 tasks/daily_coupon_scheduler.py --schedule        # daily 07:30 UTC
python3 tasks/daily_coupon_scheduler.py --telegram        # push to Telegram
```

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL DSN | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token | Optional |
| `TELEGRAM_CHANNEL_ID` | Telegram channel ID | Optional |
| `SECRET_KEY` | JWT secret for auth | Yes (prod) |
| `EDGE_THRESHOLD` | Min edge for value bets | Default: 0.04 |

---

## Model Training

The champion stack was trained through 80 iterations:
- **v23–v40** (`scripts/train_v23_v40.py`): 970 lines, multi-target framework, 17 model variants
- **v41–v80** (`scripts/train_v41_v80.py`): 1,553 lines, 127 model variants
- **Champion stack**: 6 best models selected by AUC on 2024 holdout

Training data: ATP matches 2000–2023 (197,495 rows)
Holdout: 2024 (1,904 rows)

---

## Deploy

**Frontend (Vercel):** Push to `main` → auto-deploy via `vercel.json`

**API:** FastAPI on Ubuntu server, systemd or Docker

```bash
# API production start
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## License

Proprietary. All rights reserved — qa10devteam.
