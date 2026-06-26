# AX-22: ARCHITEKTURA PLATFORMY betatp.io — SPECYFIKACJA FORMALNA
## Specyfikacja Formalna — betatp.io Prediction Engine
**Wersja:** 1.0.0  
**Status:** Zatwierdzony  
**Data:** 2026-06-25  

---

## 1. Wstęp i Zakres

Niniejszy aksjomat definiuje formalną architekturę systemu betatp.io jako całości — od warstwy danych przez silnik predykcji, warstwę API, aż po interfejs użytkownika. Specyfikacja określa SLA (Service Level Agreements), przepływy danych, protokoły komunikacji i interfejsy B2B.

---

## 2. Architektura 4-Warstwowa

**Aksjomat AX-22.1 (Architektura Warstwowa):** System betatp.io jest podzielony na 4 logiczne warstwy:

```
┌─────────────────────────────────────────────────────────┐
│  WARSTWA 4: Frontend (Next.js)                           │
│  Dashboard · Alerty · Wykresy · B2B Widget              │
├─────────────────────────────────────────────────────────┤
│  WARSTWA 3: API Layer (FastAPI)                          │
│  REST API · WebSocket · Auth · Rate Limiting             │
├─────────────────────────────────────────────────────────┤
│  WARSTWA 2: Prediction Engine (Python)                   │
│  21 Aksjomatów · Elo · ML · Monte Carlo                  │
├─────────────────────────────────────────────────────────┤
│  WARSTWA 1: Data Layer (PostgreSQL + Redis)              │
│  TML-Database · Real-time Odds · Cache                   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Warstwa 1 — Data Layer

### 3.1 PostgreSQL — Składnica Danych

**Definicja AX-22.1 (Schemat Bazy Danych):** Baza PostgreSQL 15+ z następującymi głównymi tabelami:

| Tabela | Opis | Klucz | Rozmiar est. |
|--------|------|-------|-------------|
| `matches` | Historyczne mecze ATP/Challenger | `match_id` | 250K wierszy |
| `players` | Profile zawodników | `player_id` | 18K wierszy |
| `elo_ratings` | Ratingi Elo (czasowe) | `(player_id, date)` | 4M wierszy |
| `serve_elo` | sElo/rElo ratings | `(player_id, surface, date)` | 2M wierszy |
| `odds` | Kursy bukmacherów | `(match_id, book_id)` | 800K wierszy |
| `predictions` | Predykcje systemu | `(match_id, model_version)` | 250K wierszy |
| `bets_log` | Log zakładów (B2B) | `bet_id` | 50K wierszy |

**Indeksy Wymagane:**

```sql
CREATE INDEX idx_matches_date ON matches(tourney_date);
CREATE INDEX idx_matches_surface ON matches(surface);
CREATE INDEX idx_elo_player_date ON elo_ratings(player_id, date);
CREATE INDEX idx_serve_elo_composite ON serve_elo(player_id, surface, date);
```

### 3.2 Redis — Cache Czasu Rzeczywistego

**Definicja AX-22.2 (Strategia Cache Redis):**

| Klucz Redis | Dane | TTL |
|-------------|------|-----|
| `elo:{player_id}` | Aktualny Elo zawodnika | 1h |
| `selo:{player_id}:{surface}` | sElo/rElo | 1h |
| `pred:{match_id}` | Predykcja meczu | 30min |
| `odds:{match_id}:{book}` | Kursy live | 60s |
| `features:{match_id}` | Wektor cech | 15min |
| `session:{user_id}` | Sesja użytkownika | 24h |

**SLA Redis:** Latencja zapisu/odczytu < 2ms (p99).

---

## 4. Warstwa 2 — Prediction Engine

### 4.1 Moduły Silnika

**Definicja AX-22.3 (Moduły Silnika Predykcji):**

```
prediction_engine/
├── core/
│   ├── elo_engine.py          # AX-03: Enhanced Elo
│   ├── serve_return_elo.py    # AX-20: sElo/rElo
│   ├── surface_model.py       # AX-17: Surface adjustments
│   ├── h2h_bayesian.py        # AX-18: H2H Bayesian
│   └── monte_carlo.py         # AX-04: MC simulation
├── ml/
│   ├── lgbm_model.py          # LightGBM
│   ├── xgboost_model.py       # XGBoost
│   ├── logistic_model.py      # Logistic Regression
│   └── ensemble_stacker.py    # AX-19: Ensemble
├── markets/
│   ├── derivative_scanner.py  # AX-16: Derivative markets
│   ├── value_detector.py      # EV calculation
│   └── kelly_sizer.py         # AX-21: Kelly sizing
└── data/
    ├── feature_engineer.py    # Feature extraction
    └── tml_ingestion.py       # TML-Database ingestion
```

### 4.2 Przepływ Predykcji

**Definicja AX-22.4 (Pipeline Predykcji):**

$$\text{Match Input} \to \text{Feature Extraction} \to \text{Elo Calculation} \to \text{ML Models} \to \text{Ensemble} \to \text{EV Detection} \to \text{Output}$$

Formalny opis Pipeline'u:

1. **Ingestion** ($t_0$): Wczytaj dane meczu $m$ z PostgreSQL
2. **Features** ($t_0 + 10\text{ms}$): Wygeneruj wektor $\mathbf{x}_m \in \mathbb{R}^{47}$
3. **Elo** ($t_0 + 15\text{ms}$): Oblicz $P_{Elo}$, $P_{sElo}$, $P_{H2H}$ (AX-03, AX-20, AX-18)
4. **ML** ($t_0 + 80\text{ms}$): Uruchom LightGBM, XGBoost, LR równolegle
5. **Ensemble** ($t_0 + 90\text{ms}$): Połącz modele (AX-19)
6. **MC** ($t_0 + 140\text{ms}$): Monte Carlo rynki pochodne (AX-16)
7. **EV** ($t_0 + 160\text{ms}$): Oblicz EV dla każdego rynku
8. **Output** ($t_0 + 180\text{ms}$): Zapisz do Redis + PostgreSQL

**SLA Predykcji:** Całkowita latencja $< 200\text{ms}$ (p95).

---

## 5. Warstwa 3 — API Layer (FastAPI)

### 5.1 Endpoints REST

**Tabela 5.1: REST API Endpoints**

| Endpoint | Metoda | Opis | Auth |
|----------|--------|------|------|
| `/api/v1/matches` | GET | Lista nadchodzących meczów | JWT |
| `/api/v1/matches/{id}` | GET | Szczegóły meczu + predykcja | JWT |
| `/api/v1/predictions/{id}` | GET | Predykcja dla meczu | JWT |
| `/api/v1/value` | GET | Lista okazji wartościowych | JWT |
| `/api/v1/players/{id}` | GET | Profil zawodnika + Elo | JWT |
| `/api/v1/players/{id}/elo` | GET | Historia Elo | JWT |
| `/api/v1/odds/{match_id}` | GET | Kursy dla meczu | JWT |
| `/api/v1/backtest/results` | GET | Wyniki backtestu | JWT+Admin |
| `/api/v1/b2b/feed` | GET | B2B data feed | API-Key |
| `/api/v1/b2b/webhook` | POST | Webhook registration | API-Key |

### 5.2 WebSocket Endpoints

**Definicja AX-22.5 (WebSocket Protocol):**

```
ws://api.betatp.io/v1/ws/live
```

Zdarzenia push:
- `match_update` — nowa predykcja meczu
- `odds_update` — zmiana kursów
- `value_alert` — nowa okazja wartościowa
- `live_score` — wynik na żywo

Payload format (JSON):

```json
{
  "event": "value_alert",
  "timestamp": "2025-06-25T14:23:11Z",
  "match_id": "atp_2025_wimbledon_r4_001",
  "market": "total_games_under_22.5",
  "ev": 0.047,
  "p_model": 0.512,
  "odds_best": 1.95,
  "book": "Pinnacle",
  "confidence": "HIGH"
}
```

**SLA Live Update:** Latencja od zdarzenia do push < 50ms (p99).

### 5.3 Uwierzytelnienie i Autoryzacja

**Definicja AX-22.6 (Schemat Auth):**

```
JWT (użytkownicy końcowi):
  - Algorithm: RS256
  - Expiry: 24h (access), 30d (refresh)
  - Claims: {user_id, tier, rate_limit, expires}

API Key (B2B):
  - Format: betatp_live_{32_char_hex}
  - Header: X-API-Key: {key}
  - Rotation: co 90 dni
  - Scope: {read_predictions, read_odds, webhook}
```

### 5.4 Rate Limiting

**Tabela 5.2: Rate Limits per Tier**

| Tier | Req/min | Req/day | WebSocket | Monte Carlo |
|------|---------|---------|-----------|-------------|
| Free | 10 | 500 | Brak | Brak |
| Basic | 60 | 5,000 | 1 conn | Brak |
| Pro | 300 | 50,000 | 5 conn | 100/day |
| B2B | 1,000 | 500,000 | 20 conn | Unlimited |

---

## 6. Warstwa 4 — Frontend (Next.js)

### 6.1 Architektura Frontend

**Definicja AX-22.7 (Stack Frontend):**

- Framework: Next.js 14 (App Router)
- UI: Tailwind CSS + shadcn/ui
- State: Zustand + React Query
- Charts: Recharts / D3.js
- Real-time: WebSocket hook

### 6.2 Główne Widoki

| Widok | Ścieżka | Opis |
|-------|---------|------|
| Dashboard | `/` | Przegląd okazji dnia |
| Mecze | `/matches` | Lista nadchodzących + predykcje |
| Wartość | `/value` | Tabela EV posortowana |
| Zawodnicy | `/players/{id}` | Profil + Elo history |
| Backtest | `/backtest` | Wyniki historyczne |
| Alerty | `/alerts` | Konfiguracja powiadomień |
| B2B Portal | `/b2b` | Klucze API, docs, usage |

---

## 7. Przepływ Danych End-to-End

**Definicja AX-22.8 (Pełny Przepływ Danych):**

```
TML-Database (GitHub/ATP)
    ↓ [Ingestion, cron: co 6h]
PostgreSQL (matches, players)
    ↓ [Elo Computation, trigger: nowy mecz]
elo_ratings, serve_elo tables
    ↓ [Feature Engineering]
feature vectors (Redis cache, 15min TTL)
    ↓ [ML Prediction Pipeline, <200ms]
predictions table + Redis pred:{match_id}
    ↓ [Value Detection + EV]
value_alerts table
    ↓ [WebSocket Push, <50ms]
Frontend Dashboard + B2B Webhooks
    ↓ [User Actions]
bets_log table (opcjonalne śledzenie)
```

---

## 8. SLA — Service Level Agreements

**Aksjomat AX-22.2 (SLA Systemu):**

| Metryka | Cel | Pomiar |
|---------|-----|--------|
| API Uptime | ≥ 99.9% | Rolling 30 dni |
| Prediction Latency (p95) | < 200ms | Per request |
| Live Update Latency (p99) | < 50ms | Per WebSocket push |
| Database Query (p99) | < 50ms | Per query |
| Redis Read (p99) | < 2ms | Per operation |
| B2B Feed Delay | < 500ms | End-to-end |
| Scheduled Predictions | < 5min po opublikowaniu | ATP draw |

**Definicja AX-22.9 (Uptime Calculation):**

$$\text{Uptime} = \frac{T_{total} - T_{downtime}}{T_{total}} \times 100\%$$

Cel 99.9% = maksymalnie 8.76h downtime rocznie = 43.8 min/miesiąc.

---

## 9. Specyfikacja B2B API

### 9.1 Endpoints B2B

**Definicja AX-22.10 (B2B Endpoints):**

```
GET /api/v1/b2b/feed
Params: ?surface=&tournament=&min_ev=0.02&format=json
Response: [
  {
    "match_id": string,
    "player_a": string,
    "player_b": string,
    "tournament": string,
    "surface": string,
    "scheduled": ISO8601,
    "p_model": float,      // P(A beats B)
    "elo_a": int,
    "elo_b": int,
    "markets": [
      {
        "market": string,
        "p_betatp": float,
        "best_odds": float,
        "best_book": string,
        "ev": float
      }
    ]
  }
]

POST /api/v1/b2b/webhook
Body: {
  "url": string,
  "events": ["value_alert", "match_prediction"],
  "min_ev": float,
  "surfaces": ["hard", "clay", "grass"]
}
```

### 9.2 SLA B2B

| Metryka | Gwarantowane |
|---------|-------------|
| Webhook delivery | < 500ms od zdarzenia |
| Feed freshness | Aktualizacja co 5 min |
| Data completeness | > 98% meczów ATP |
| Historyczny dostęp | 2019-present |
| Uptime B2B endpoint | 99.95% |

---

## 10. Infrastruktura i Deployment

**Definicja AX-22.11 (Infrastruktura):**

| Komponent | Technologia | Spec (prod) |
|-----------|------------|-------------|
| API Server | FastAPI + Uvicorn | 4 vCPU, 16GB RAM |
| ML Worker | Python + Celery | 8 vCPU, 32GB RAM |
| Database | PostgreSQL 15 | 4 vCPU, 32GB RAM, SSD |
| Cache | Redis 7.0 | 2 vCPU, 8GB RAM |
| Frontend | Next.js (Vercel) | CDN, auto-scaling |
| Reverse Proxy | Nginx | 2 vCPU, 4GB RAM |
| Monitoring | Prometheus + Grafana | — |
| CI/CD | GitHub Actions | — |

**Aksjomat AX-22.3 (Izolacja Danych):** Dane użytkowników i dane predykcyjne są przechowywane w oddzielnych schematach PostgreSQL:

$$\text{schema: } \{analytics, users, b2b, audit\}$$

z Row-Level Security (RLS) na tabeli `users`.

---

## 11. Referencje i Standardy

- FastAPI: https://fastapi.tiangolo.com
- PostgreSQL 15 Documentation
- Redis 7.0 Commands Reference
- Next.js 14 App Router Documentation
- OAuth 2.0 / JWT RFC 7519
- WebSocket Protocol RFC 6455
- OpenAPI 3.0 Specification (pełna specyfikacja API: `/docs/openapi.json`)
- GDPR compliance: dane EU przechowywane na serwerach EU-West
