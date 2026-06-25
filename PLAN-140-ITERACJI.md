# betatp.io — Plan MVP 140 Iteracji
> Platforma predykcji tenisowej ATP z generowaniem kuponów dla subskrybentów

**Cel produktu:** Subskrybenci (B2C) otrzymują gotowe kupony — singlowe i systemowe — wygenerowane przez silnik matematyczny oparty na 22 aksjomatach + ML ensemble. Kupon = konkretne zakłady z selekcją, stawkami (Kelly), EV i uzasadnieniem.

**Stack:** Python 3.11, FastAPI, PostgreSQL, Redis, LightGBM, NumPy, pandas, SQLAlchemy, Celery

---

## FAZA 1 — CORE ENGINE (iter 1–35)
### Fundament matematyczny: Elo, Monte Carlo, Data Pipeline

**Iter 1–5: Projekt i setup**
- `pyproject.toml` — deps: fastapi, uvicorn, sqlalchemy, psycopg2, numpy, pandas, lightgbm, scikit-learn, celery, redis, pytest
- `engine/__init__.py`, `engine/constants.py` — K-faktory, surface delty, floor/ceiling
- `.env.example`, `docker-compose.yml` — PostgreSQL + Redis
- `tests/conftest.py` — fixtures
- Commit: `chore: project setup`

**Iter 6–10: Data Pipeline — TML-Database ingestion**
- `data/loader.py` — wczytaj wszystkie CSV z `/home/ubuntu/TML-Database/`
- `data/schema.py` — SQLAlchemy models: Match, Player, EloHistory
- `data/quality.py` — walidacja: serve_win_pct ∈ [0.3, 0.95], ace_pct ∈ [0, 0.30]
- `scripts/ingest.py` — CLI: python scripts/ingest.py --source /home/ubuntu/TML-Database/
- `tests/test_loader.py`
- Commit: `feat: TML-Database ingestion pipeline`

**Iter 11–18: Elo Engine**
- `engine/elo.py` — klasa `EloEngine`:
  - `update(winner, loser, surface, tourney_level)` → K-factor lookup
  - `P(Ra, Rb)` = 1/(1+10^((Rb-Ra)/400))
  - decay(player, days_inactive) → exp decay T½=365
  - surface_blend(n_surface, R_surface, R_overall) → alpha=1-exp(-n/30)
  - sElo update z actual_svw = (w_1stWon+w_2ndWon)/w_svpt
  - rElo update z actual_rpw
- `engine/elo_runner.py` — compute_all_elos(matches_df) chronologicznie
- `tests/test_elo.py` — 15 testów jednostkowych
- Commit: `feat: Elo engine 6-variant (overall/surface/serve/return)`

**Iter 19–25: Monte Carlo Engine**
- `engine/monte_carlo.py` — klasa `MonteCarloEngine`:
  - `simulate_match(p_serve_A, p_serve_B, best_of=3, n=100_000)` → dict
  - NumPy vectorized — cały batch naraz
  - Outputs: p_win_A, p_set_scores, p_tiebreak, E[games], E[duration_min]
  - LUT precomputation dla live (<1ms lookup)
- `tests/test_monte_carlo.py` — zbieżność CLT, SE < 0.002
- Commit: `feat: Monte Carlo engine N=100k vectorized NumPy`

**Iter 26–30: Feature Engineering**
- `engine/features.py` — klasa `FeatureBuilder`:
  - EWMA α=0.15 dla serve/return stats
  - 10 Elo features (diff, momentum, peak, uncertainty)
  - 18 serve/return ratios z TML-Database
  - FatigueScore(sets_7d, rest_hours, travel_km, tz_crossings)
  - H2H Bayesian posterior Beta(3+wins, 3+losses)
  - age_performance_diff z career arc LOESS
- `tests/test_features.py`
- Commit: `feat: feature engineering 54 features`

**Iter 31–35: Pre-match probability pipeline**
- `engine/predictor.py` — `PreMatchPredictor`:
  - Wczytaj Elo → compute features → zwróć p_win_A
  - Metoda: enhanced Elo (primary) + feature vector (secondary)
  - surface_elo blending
- `scripts/compute_elos.py` — offline: oblicz wszystkie Elo z historii
- `tests/test_predictor.py`
- Commit: `feat: pre-match predictor pipeline`

---

## FAZA 2 — VALUE DETECTOR + ML (iter 36–70)

**Iter 36–42: Value Detector**
- `value/devig.py` — 4 metody:
  - `proportional(odds_A, odds_B)` 
  - `additive(odds_A, odds_B)`
  - `power_shin(odds_A, odds_B)` — bisection solver
  - `multiplicative(odds_A, odds_B)`
- `value/ev_calculator.py`:
  - `expected_value(p_model, decimal_odds)` = p*odds - 1
  - `kelly_fraction(p, odds, fraction=0.5)` = Half Kelly
  - `lay_kelly(p, lay_odds, fraction=0.5)`
- `tests/test_value.py` — 20 testów
- Commit: `feat: value detector — de-vig + EV + Kelly`

**Iter 43–50: ML Ensemble**
- `ml/dataset.py` — `DatasetBuilder(train_years, val_years)`:
  - Walk-forward splits (no leakage)
  - Feature matrix X, labels y, temporal guard
- `ml/lgbm_model.py` — `LightGBMPredictor`:
  - params: n_estimators=1000, lr=0.05, num_leaves=63
  - train(X_train, y_train, X_val, y_val)
  - predict_proba(X)
  - calibrate(X_cal, y_cal) — isotonic regression
- `ml/xgb_model.py` — `XGBoostPredictor` (params z spec)
- `ml/ensemble.py` — `EnsemblePredictor`:
  - weights: {lgbm: 0.35, xgb: 0.25, lr: 0.10, elo: 0.30}
  - cold_start_rule: n_matches<10 → elo weight=0.90
  - predict(match_features)
- `tests/test_ml.py`
- Commit: `feat: ML ensemble LightGBM+XGBoost+LogReg+Elo`

**Iter 51–55: ML Training Script**
- `scripts/train_models.py` — pipeline trenujący wszystkie modele:
  - walk-forward validation (1990-2018 train, 2019-2025 test)
  - zapis modeli do `models/`
  - raport: accuracy, Brier Score, Log Loss
- `scripts/evaluate.py` — metryki na holdout
- Commit: `feat: training + evaluation pipeline`

**Iter 56–60: Derivative Scanner**
- `value/derivative_scanner.py` — klasa `DerivativeScanner`:
  - `scan_total_games(match, bk_line, bk_odds)` — MC vs linear
  - `scan_tiebreak(match, bk_p_tb, bk_odds)` — P(TB) exact
  - `scan_set_betting(match, bk_set_odds)` — EV per set score
  - Threshold: EV > 0.04 → yield alert
- `tests/test_derivative_scanner.py`
- Commit: `feat: derivative markets scanner (totals/TB/set betting)`

**Iter 61–65: Alert System**
- `value/alerts.py` — `AlertEngine`:
  - priority: CRITICAL(EV>8%), HIGH(5-8%), MEDIUM(2-5%)
  - payload schema (JSON)
  - deduplika (Redis TTL 15min)
- `value/notifier.py` — interfejsy: WebSocket push, Telegram, email
- Commit: `feat: alert engine CRITICAL/HIGH/MEDIUM`

**Iter 66–70: CLV Tracker**
- `value/clv_tracker.py` — `CLVTracker`:
  - `record_bet(match_id, player, stake, opening_odds)`
  - `record_closing(match_id, pinnacle_closing_odds)`
  - `compute_clv(bet_id)` = opening/closing - 1
  - rolling 7/30/90d CLV
  - t-test significance (H0: CLV=0)
- `tests/test_clv.py`
- Commit: `feat: CLV tracker with statistical tests`

---

## FAZA 3 — COUPON GENERATOR (iter 71–95)
### Serce produktu — to co dostaje subskrybent

**Iter 71–78: Coupon Engine — Single**
- `engine/coupon.py` — klasa `CouponGenerator`:
  - `generate_singles(matches, min_ev=0.02, min_odds=1.30, max_odds=5.00)`:
    - dla każdego meczu: oblicz p_model → devig bk_odds → EV
    - filtruj EV > min_ev
    - sortuj po EV desc
    - wylicz Half Kelly stake
    - zwróć listę `BetSelection` z uzasadnieniem
  - `BetSelection` dataclass:
    - match_id, player, surface, tourney
    - p_model, bk_odds, devigged_p, ev_pct
    - kelly_stake_pct, recommended_stake_units
    - confidence: HIGH/MEDIUM/LOW
    - reasoning: f-string z kluczowymi statystykami
- `tests/test_coupon_singles.py`
- Commit: `feat: coupon generator — singles`

**Iter 79–86: Coupon Engine — System Bets**
- `engine/coupon_system.py` — `SystemBetBuilder`:
  - `build_system(selections, system_type)`:
    - system_type: "2/3", "2/4", "3/4", "3/5", "TRIXIE", "PATENT", "YANKEE"
    - generuje wszystkie kombinacje
    - oblicza combined_odds = prod(odds_i)
    - oblicza system_ev = E[zwrot_systemu] - 1
    - wylicza optymalny podział bankrolla
  - `combined_probability(p_list)` — zakładając niezależność: prod(p_i)
  - `system_expected_return(p_list, odds_list, system_type)` — dokładne obliczenie
  - Uwaga: tylko selekcje z EV > 1.5% wchodzą do systemu
- `tests/test_coupon_system.py`
- Commit: `feat: system bets builder (2/3, TRIXIE, PATENT, YANKEE, etc.)`

**Iter 87–91: Coupon Ranker + Uzasadnienie**
- `engine/coupon_ranker.py`:
  - `rank_coupons(singles, systems)` → sorted by expected_value
  - `generate_reasoning(selection)` → czytelny tekst PL:
    - "Elo serwisowe Jannik Sinner (+180 vs ATP avg) dominuje na nawierzchni twardej"
    - "Model daje 68.4% vs rynek 62.1% → EV +10.3%"
    - "Ostatnie 5 meczów: 4-1, forma wzrostowa (EWMA α=0.15)"
- `engine/daily_coupon.py` — `DailyCouponBuilder`:
  - scanuje wszystkie mecze dnia
  - grupuje: TOP SINGLE, SYSTEM 2/3, SYSTEM 3/4
  - max 3 singla + 1 system na dzień
- `tests/test_coupon_ranker.py`
- Commit: `feat: coupon ranker + reasoning generator (PL)`

**Iter 92–95: Backtest**
- `backtest/engine.py` — `BacktestEngine`:
  - `run(start_year, end_year, strategy)`:
    - walk-forward: train 1990-Y, test Y
    - symulacja kuponów dzień po dniu
    - realistic constraints: Half Kelly, max 3% bankroll per selection
    - account limit simulation
  - Metryki: ROI, Sharpe, Max Drawdown, Win Rate, Avg CLV
  - Equity curve CSV
- `scripts/run_backtest.py`
- `tests/test_backtest.py`
- Commit: `feat: backtesting engine walk-forward 2019-2025`

---

## FAZA 4 — API + SUBSKRYPCJE (iter 96–120)

**Iter 96–103: Database Models**
- `data/models.py` — SQLAlchemy:
  - `Match` — id, date, player_a, player_b, surface, tourney_level, score, winner
  - `Player` — id, name, country, dob
  - `EloHistory` — player_id, date, overall/hard/clay/grass/serve/return elo
  - `Coupon` — id, date, type(single/system), selections_json, ev, status
  - `Subscription` — user_id, tier(FREE/PRO/ELITE), expires_at
  - `Bet` — user_id, coupon_id, stake, opening_odds, closing_odds, clv, pnl
  - `Alert` — match_id, type, ev, priority, sent_at
- `data/migrations/` — Alembic init
- Commit: `feat: database schema SQLAlchemy + Alembic migrations`

**Iter 104–112: FastAPI endpoints**
- `api/main.py` — FastAPI app, CORS, lifespan
- `api/routes/predictions.py`:
  - `GET /api/v1/matches/today` — lista meczów z p_win
  - `GET /api/v1/match/{id}/prediction` — pełna predykcja + MC outputs
  - `GET /api/v1/match/{id}/simulate` — POST z custom p_serve
- `api/routes/coupons.py`:
  - `GET /api/v1/coupons/today` — dzisiejsze kupony (wymaga auth)
  - `GET /api/v1/coupons/singles` — najlepsze single
  - `GET /api/v1/coupons/systems` — systemy 2/3, 3/4
  - `GET /api/v1/coupons/{id}` — szczegóły kuponu z reasoning
- `api/routes/value.py`:
  - `POST /api/v1/value/check` — podaj kurs → dostań EV
  - `GET /api/v1/alerts` — aktywne alerty (SSE stream)
- `api/routes/stats.py`:
  - `GET /api/v1/stats/elo/{player_id}` — historia Elo
  - `GET /api/v1/stats/clv` — CLV tracking dashboard
- `api/auth.py` — JWT Bearer + subscription tier check
- Commit: `feat: FastAPI REST API — predictions, coupons, value`

**Iter 113–117: WebSocket live**
- `api/routes/live.py`:
  - `WS /api/v1/live/{match_id}` — live in-play probabilities
  - Na każdy punkt: state update → LUT lookup → emit P(win)
  - Broadcast: p_win_A, current_state, ev_live
- `engine/live_engine.py` — integracja state machine + LUT
- Commit: `feat: WebSocket live in-play engine`

**Iter 118–120: Subscription tiers**
- FREE: coupons preview (bez stake), 3 predykcji/dzień
- PRO: pełne kupony, systemy, alerty MEDIUM+HIGH
- ELITE: kupony + live WebSocket + CRITICAL alerty + CLV tracker
- `api/middleware/subscription.py` — tier guard
- Commit: `feat: subscription tiers FREE/PRO/ELITE`

---

## FAZA 5 — SCHEDULER + POLISH (iter 121–140)

**Iter 121–126: Celery Tasks**
- `tasks/daily_pipeline.py`:
  - `task_update_elos` — daily Elo recalculation
  - `task_generate_coupons` — generate + store daily coupons
  - `task_scan_derivatives` — scan derivative markets
  - `task_send_alerts` — dispatch alerts to subscribers
- `tasks/celery_app.py` — Celery + Redis broker
- `docker-compose.yml` — add celery worker + beat
- Commit: `feat: Celery async tasks — daily pipeline`

**Iter 127–131: Telegram Bot**
- `tasks/telegram_notifier.py`:
  - kupon message formatter (Markdown)
  - `/kupon` — dzienny kupon
  - `/alerty` — aktywne alerty EV>5%
  - `/stats` — CLV stats subskrybenta
- Commit: `feat: Telegram bot notifications`

**Iter 132–136: Tests + CI**
- `tests/integration/` — end-to-end: API → engine → coupon
- `tests/test_backtest_regression.py` — ROI > 0% na holdout
- `.github/workflows/ci.yml` — pytest + coverage
- `Makefile` — make test, make backtest, make serve
- Commit: `test: integration tests + CI pipeline`

**Iter 137–140: Docs + README**
- `README.md` — projekt, setup, usage
- `docs/API.md` — endpoint reference
- `docs/COUPON_FORMAT.md` — format kuponu dla subskrybentów
- `docs/DEPLOYMENT.md` — Docker + env vars
- Final commit: `docs: README + API docs + deployment guide`

---

## Struktura plików (final)

```
betatp/
├── engine/
│   ├── elo.py              # 6-variant Elo (AX-03, AX-04, AX-20)
│   ├── elo_runner.py       # batch computation
│   ├── monte_carlo.py      # N=100k vectorized (AX-06, MC-01..04)
│   ├── features.py         # 54 features (FE-01..04, ADV-04,05)
│   ├── predictor.py        # pre-match pipeline
│   ├── live_engine.py      # LUT in-play (LE-01..04)
│   ├── coupon.py           # single coupon generator ⭐
│   ├── coupon_system.py    # system bets ⭐
│   ├── coupon_ranker.py    # ranker + PL reasoning ⭐
│   ├── daily_coupon.py     # daily TOP coupons ⭐
│   └── constants.py
├── ml/
│   ├── dataset.py          # walk-forward dataset builder
│   ├── lgbm_model.py       # LightGBM (ML-01)
│   ├── xgb_model.py        # XGBoost
│   ├── logistic_model.py   # Logistic Regression
│   ├── ensemble.py         # stacking + calibration (ML-02)
│   └── calibration.py      # isotonic regression
├── value/
│   ├── devig.py            # 4 de-vig methods (AX-08, VD-02)
│   ├── ev_calculator.py    # EV + Kelly (AX-09, VD-01,03)
│   ├── derivative_scanner.py # DS-01..03
│   ├── alerts.py           # alert engine
│   ├── notifier.py         # WebSocket/TG/email
│   └── clv_tracker.py      # CLV (CLV-01..06)
├── data/
│   ├── loader.py           # TML-Database CSV ingestion
│   ├── models.py           # SQLAlchemy ORM
│   ├── schema.py           # Pydantic schemas
│   ├── quality.py          # data validation
│   └── migrations/         # Alembic
├── api/
│   ├── main.py             # FastAPI app
│   ├── auth.py             # JWT + subscription
│   ├── middleware/
│   └── routes/
│       ├── predictions.py
│       ├── coupons.py      # ⭐ core B2C endpoint
│       ├── value.py
│       ├── live.py         # WebSocket
│       └── stats.py
├── backtest/
│   └── engine.py           # walk-forward backtest
├── tasks/
│   ├── celery_app.py
│   ├── daily_pipeline.py
│   └── telegram_notifier.py
├── tests/
├── scripts/
│   ├── ingest.py
│   ├── compute_elos.py
│   ├── train_models.py
│   └── run_backtest.py
├── models/                 # saved ML models
├── specs/                  # 68 spec docs
├── pyproject.toml
├── docker-compose.yml
└── README.md
```

## KPI Sukcesu MVP

| Metryka | Target |
|---|---|
| Accuracy (holdout 2019-2025) | ≥ 68% |
| Brier Score | ≤ 0.22 |
| Backtest ROI (Challenger) | ≥ 5% |
| Average CLV | ≥ 1.5% |
| API latency pre-match | < 200ms |
| Live in-play update | < 50ms |
| Daily coupons generated | 3-8 single + 1-2 system |
| Coupon EV average | ≥ 3% |
