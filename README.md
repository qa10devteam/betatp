# atpbet.io — AI Value Betting ATP 🎾

> **Automatyczny system value bettingu na tenis ATP** oparty na modelu LightGBM v14.  
> ROI: **+58.7%** | Edge: **≥15%** | Model: **LightGBM v14** | Dane: 2015–2026

---

## O projekcie

**atpbet.io** to platforma do inteligentnego wykrywania value betów w tenisie ATP. System łączy:

- **Model ML** — LightGBM v14 z 87 feature'ami (ELO, serwis, return, zmęczenie, H2H bayesowski)
- **Silnik Monte Carlo** — 10 000 symulacji meczu per predykcja
- **Dzienny kupon** — top 3 singlesy + system 2/3 z uzasadnieniami po polsku
- **Live engine** — recalkulacja prawdopodobieństwa w czasie rzeczywistym
- **CLV Tracker** — śledzenie Closing Line Value jako miary jakości predykcji

### Wyniki backtestów (2022–2026, edge ≥15%)

| Metryka          | Wartość      |
|------------------|-------------|
| Total bets       | 318         |
| ROI              | **+58.7%**  |
| Win rate         | 51.2%       |
| Avg odds         | 2.84        |
| Profit (units)   | 186.7       |
| Sharpe ratio     | 1.43        |
| Max drawdown     | 11.2%       |

---

## Struktura projektu

```
ATPBet/
├── api/                  # FastAPI — endpointy REST + WebSocket
│   ├── main.py
│   └── routes/           # coupons, value, stats, live
├── engine/               # Silnik predykcji
│   ├── coupon.py         # Generator dziennych kuponów
│   ├── coupon_system.py  # Systemy 2/3
│   ├── elo.py            # ELO rating (overall + per nawierzchnia)
│   └── monte_carlo.py    # Symulacje MC
├── ml/                   # Pipeline ML
│   ├── lgbm_model.py     # LightGBM training/inference
│   └── calibration.py    # Kalibracja prawdopodobieństwa
├── value/                # Value detection
│   ├── alerts.py         # System alertów
│   ├── devig.py          # Devigorowanie kursów
│   └── clv_tracker.py    # CLV monitoring
├── tasks/                # Celery async tasks
│   ├── celery_app.py
│   └── daily_pipeline.py
├── scripts/              # Skrypty CLI
│   ├── backtest_vX.py    # Backtest modelu
│   └── run_daily_pipeline.py
├── tests/                # Testy jednostkowe i integracyjne
├── docs/                 # Dokumentacja (API.md, COUPON_FORMAT.md)
├── Makefile              # Skróty deweloperskie
└── docker-compose.yml    # Infrastruktura lokalna
```

---

## Instalacja

### Wymagania

- Python 3.11+
- PostgreSQL 16 (lub Docker)
- Redis 7 (lub Docker)

### Szybki start

```bash
# 1. Klonuj repozytorium
git clone https://github.com/ATPBet/ATPBet.git
cd ATPBet

# 2. Zainstaluj zależności
pip install -r requirements.txt

# 3. Skopiuj i uzupełnij zmienne środowiskowe
cp .env.example .env

# 4. Uruchom infrastrukturę (PostgreSQL + Redis + Celery)
docker-compose up -d

# 5. Uruchom API
make serve
```

---

## Użycie

### Makefile — skróty

```bash
make serve      # Uruchom API: uvicorn api.main:app --reload --port 8000
make daily      # Wygeneruj dzienny kupon (edge >= 15%, max 3 picks)
make test       # Uruchom testy jednostkowe
make coverage   # Testy z raportem pokrycia
make backtest   # Backtest modelu v14 (edge >= 15%)
make lint       # Sprawdź składnię kluczowych modułów
make install    # Zainstaluj zależności pip
```

### Generowanie dziennego kuponu

```bash
# Przez make:
make daily

# Bezpośrednio:
python3 scripts/run_daily_pipeline.py --edge 0.15 --max-picks 3

# Backtest modelu v14:
make backtest
# lub:
python3 scripts/backtest_vX.py --version 14 --edge 0.15
```

---

## API — przegląd endpointów

Pełna dokumentacja: [docs/API.md](docs/API.md)

| Metoda | Ścieżka                        | Tier  | Opis                              |
|--------|-------------------------------|-------|-----------------------------------|
| GET    | /health                       | public| Status serwisu                    |
| GET    | /api/v1/matches/today         | free  | Mecze ATP na dziś z kursami       |
| GET    | /api/v1/coupons/today         | pro   | Dzienny kupon value (3 singlesy + system 2/3) |
| GET    | /api/v1/coupons/singles       | pro   | Tylko singlesy                    |
| GET    | /api/v1/coupons/systems       | pro   | Systemy akumulatorowe             |
| GET    | /api/v1/coupons/{id}          | pro   | Historyczny kupon po ID/dacie     |
| POST   | /api/v1/value/check           | free  | Sprawdź value dla podanego kursu  |
| GET    | /api/v1/alerts                | pro   | Aktywne alerty value (ostatnie 24h)|
| GET    | /api/v1/alerts/stream         | pro   | SSE stream alertów real-time      |
| GET    | /api/v1/stats/elo/{player}    | free  | Historia ELO gracza               |
| GET    | /api/v1/stats/clv             | free  | Statystyki CLV modelu             |
| GET    | /api/v1/stats/backtest        | free  | Wyniki backtestów                 |
| WS     | /api/v1/live/{match_id}       | pro   | Live WebSocket — wynik + prawdopodobieństwo |

---

## Konfiguracja (.env)

```env
# Baza danych
DATABASE_URL=postgresql://ATPBet:***@localhost:5432/ATPBet

# Redis (broker Celery + cache)
REDIS_URL=redis://localhost:***@localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:***@localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:***@localhost:6379/0

# API security
SECRET_KEY=twoj-tajny-klucz
API_KEY_PRO=klucz-pro-subskrybentow

# Telegram (alerty opcjonalne)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Deployment

### Backend API — Render.com

```yaml
# render.yaml (już skonfigurowany)
service:
  type: web
  runtime: python
  buildCommand: pip install -r requirements.txt
  startCommand: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

### Frontend — Vercel

```bash
# Wdróż frontend (static HTML + JS)
cd frontend
vercel --prod
```

### Lokalna infrastruktura (Docker Compose)

```bash
# Uruchom wszystkie serwisy:
docker-compose up -d

# Serwisy:
# - postgres    → localhost:5432
# - redis       → localhost:6379
# - api         → localhost:8000
# - celery-worker  → przetwarza zadania async
# - celery-beat    → scheduler (daily pipeline 07:00 CET)

# Zatrzymaj:
docker-compose down
```

---

## Testy

```bash
# Testy jednostkowe (verbose):
make test

# Z raportem pokrycia:
make coverage

# Lint (sprawdzenie składni):
make lint
```

### Pokrycie testów

- `tests/test_elo.py` — kalibracja i aktualizacja ELO
- `tests/test_coupon.py` — generator kuponów, filtrowanie edge
- `tests/test_value.py` — devig, EV, Kelly
- `tests/test_api.py` — endpoint responses
- `tests/test_backtest.py` — reprodukowalność wyników
- `tests/test_monte_carlo.py` — zbieżność symulacji MC

---

## Model ML — szczegóły techniczne

| Parametr          | Wartość                    |
|-------------------|---------------------------|
| Algorytm          | LightGBM (gradient boosting) |
| Wersja            | v14                        |
| Features          | 87 (ELO, serwis, return, fatigue, H2H, pogoda) |
| Walidacja         | Walk-forward (TimeSeriesSplit, 5 foldów) |
| Kalibracja        | Isotonic regression        |
| Edge threshold    | ≥ 15%                      |
| Dane treningowe   | 2015–2024 (ATP tour)       |
| Out-of-sample     | 2025–2026                  |

---

## Dokumentacja

- [docs/API.md](docs/API.md) — pełna referencja API REST/WS
- [docs/COUPON_FORMAT.md](docs/COUPON_FORMAT.md) — format kuponu dziennego, objaśnienia pól

---

## Licencja

Projekt prywatny — atpbet.io © 2026. Wszelkie prawa zastrzeżone.

> ⚠️ **Disclaimer:** Hazard wiąże się z ryzykiem utraty środków finansowych.  
> System ma charakter informacyjny i edukacyjny. Graj odpowiedzialnie.
