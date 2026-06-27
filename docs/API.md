# betatp.io — API Reference

Wersja API: **v1**  
Base URL: `https://api.betatp.io`  
Autoryzacja: Bearer token w nagłówku `Authorization: Bearer <token>`

---

## Poziomy dostępu (tiers)

| Tier       | Opis                                   |
|------------|----------------------------------------|
| `public`   | Bez tokena — dane publiczne            |
| `free`     | Zarejestrowany użytkownik (darmowy)    |
| `pro`      | Subskrybent Pro — pełne kupony, stream |

---

## Endpointy

### GET /health

Sprawdza stan API.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | public           |
| Body     | brak             |

**Response 200:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-06-27T10:00:00Z"
}
```

---

### GET /api/v1/matches/today

Zwraca listę meczy ATP zaplanowanych na dziś z szansami bookmakerów.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | free             |
| Body     | brak             |

**Response 200:**
```json
{
  "date": "2026-06-27",
  "matches": [
    {
      "match_id": "atp-2026-06-27-fritz-alcaraz",
      "player1": "Taylor Fritz",
      "player2": "Carlos Alcaraz",
      "tournament": "Wimbledon",
      "surface": "grass",
      "round": "QF",
      "scheduled_time": "2026-06-27T13:00:00Z",
      "odds_b365": {"player1": 3.20, "player2": 1.35},
      "odds_pinnacle": {"player1": 3.10, "player2": 1.38}
    }
  ]
}
```

---

### GET /api/v1/coupons/today

Zwraca dzienny kupon value bets (top singlesy + system 2/3).

| Pole     | Wartość          |
|----------|------------------|
| Auth     | pro              |
| Body     | brak             |

**Response 200:** → patrz [COUPON_FORMAT.md](COUPON_FORMAT.md)

---

### GET /api/v1/coupons/singles

Zwraca tylko singlesy z dziennego kuponu.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | pro              |
| Body     | brak             |

**Response 200:**
```json
{
  "date": "2026-06-27",
  "singles": [
    {
      "pick_id": "p1",
      "player": "Taylor Fritz",
      "opponent": "Carlos Alcaraz",
      "odds": 3.20,
      "edge": 0.17,
      "kelly_fraction": 0.053,
      "model_prob": 0.38,
      "market_prob": 0.313,
      "reasoning": "Fritz przewaga serwo na trawie, Alcaraz forma po kontuzji"
    }
  ]
}
```

---

### GET /api/v1/coupons/systems

Zwraca systemy (akumulatory 2/3) z dziennego kuponu.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | pro              |
| Body     | brak             |

**Response 200:**
```json
{
  "date": "2026-06-27",
  "systems": [
    {
      "type": "2/3",
      "picks": ["p1", "p2", "p3"],
      "combined_odds": 7.84,
      "system_ev": 0.21,
      "combinations": [
        {"picks": ["p1", "p2"], "odds": 4.16},
        {"picks": ["p1", "p3"], "odds": 5.12},
        {"picks": ["p2", "p3"], "odds": 4.80}
      ]
    }
  ]
}
```

---

### GET /api/v1/coupons/{id}

Zwraca historyczny kupon po ID (data lub UUID).

| Pole      | Wartość           |
|-----------|-------------------|
| Auth      | pro               |
| Path param| `id` — np. `2026-06-27` lub UUID kuponu |
| Body      | brak              |

**Response 200:** pełny kupon jak `/coupons/today`

**Response 404:**
```json
{"detail": "Coupon not found"}
```

---

### POST /api/v1/value/check

Ręczna weryfikacja value bet dla podanego meczu i kursu.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | free             |
| Body     | JSON (patrz niżej)|

**Request body:**
```json
{
  "player1": "Taylor Fritz",
  "player2": "Carlos Alcaraz",
  "surface": "grass",
  "odds": 3.20,
  "bookmaker": "bet365"
}
```

**Response 200:**
```json
{
  "model_prob": 0.38,
  "market_prob": 0.313,
  "edge": 0.067,
  "ev": 0.214,
  "kelly_fraction": 0.053,
  "is_value": true,
  "confidence": "high"
}
```

---

### GET /api/v1/alerts

Zwraca listę aktywnych alertów value (ostatnie 24h).

| Pole     | Wartość          |
|----------|------------------|
| Auth     | pro              |
| Body     | brak             |

**Query params:**
| Param     | Typ    | Opis                          |
|-----------|--------|-------------------------------|
| `min_edge`| float  | Minimalny edge, domyślnie 0.10|
| `surface` | string | Filtr nawierzchni             |
| `limit`   | int    | Max wyników, domyślnie 20     |

**Response 200:**
```json
{
  "alerts": [
    {
      "alert_id": "a-001",
      "created_at": "2026-06-27T08:30:00Z",
      "match_id": "atp-2026-06-27-fritz-alcaraz",
      "player": "Taylor Fritz",
      "odds": 3.20,
      "edge": 0.17,
      "ev": 0.214,
      "bookmaker": "bet365",
      "expires_at": "2026-06-27T13:00:00Z"
    }
  ],
  "total": 1
}
```

---

### GET /api/v1/alerts/stream

SSE stream alertów value w czasie rzeczywistym.

| Pole     | Wartość            |
|----------|--------------------|
| Auth     | pro                |
| Protocol | Server-Sent Events |

**Event format:**
```
event: value_alert
data: {"alert_id": "a-002", "player": "Fritz", "odds": 3.25, "edge": 0.19, "timestamp": "2026-06-27T10:15:00Z"}
```

---

### GET /api/v1/stats/elo/{player}

Zwraca historię ELO gracza (ogółem + per nawierzchnia).

| Pole      | Wartość               |
|-----------|-----------------------|
| Auth      | free                  |
| Path param| `player` — nazwisko   |

**Response 200:**
```json
{
  "player": "Carlos Alcaraz",
  "elo_overall": 2387,
  "elo_by_surface": {
    "hard": 2401,
    "clay": 2445,
    "grass": 2312
  },
  "serve_elo": 2290,
  "return_elo": 2415,
  "last_updated": "2026-06-26"
}
```

---

### GET /api/v1/stats/clv

Zwraca statystyki CLV (Closing Line Value) modelu.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | free             |
| Body     | brak             |

**Query params:**
| Param    | Typ    | Opis                              |
|----------|--------|-----------------------------------|
| `days`   | int    | Okres w dniach, domyślnie 90      |
| `surface`| string | Filtr nawierzchni                 |

**Response 200:**
```json
{
  "period_days": 90,
  "clv_mean": 0.031,
  "clv_median": 0.028,
  "clv_positive_rate": 0.67,
  "bets_tracked": 142,
  "avg_edge_at_open": 0.172,
  "avg_edge_at_close": 0.141
}
```

---

### GET /api/v1/stats/backtest

Zwraca wyniki backtestów modelu v14.

| Pole     | Wartość          |
|----------|------------------|
| Auth     | free             |
| Body     | brak             |

**Query params:**
| Param     | Typ   | Opis                           |
|-----------|-------|--------------------------------|
| `version` | int   | Wersja modelu, domyślnie 14    |
| `edge`    | float | Min edge, domyślnie 0.15       |

**Response 200:**
```json
{
  "model_version": 14,
  "edge_threshold": 0.15,
  "total_bets": 318,
  "roi": 0.587,
  "profit_units": 186.7,
  "win_rate": 0.512,
  "avg_odds": 2.84,
  "sharpe_ratio": 1.43,
  "max_drawdown": 0.112,
  "period": "2022-01-01 — 2026-06-01"
}
```

---

### WS /api/v1/live/{match_id}

WebSocket z live-danymi meczu (prawdopodobieństwo, wynik).

| Pole      | Wartość                     |
|-----------|-----------------------------|
| Auth      | pro (token w query: `?token=`) |
| Protocol  | WebSocket                   |

**Subskrypcja:**
```
ws://api.betatp.io/api/v1/live/atp-2026-06-27-fritz-alcaraz?token=<bearer>
```

**Wiadomości (server → client):**
```json
{
  "event": "score_update",
  "match_id": "atp-2026-06-27-fritz-alcaraz",
  "score": {"set1": [3, 2], "set2": null},
  "server": "Fritz",
  "win_prob": {"Fritz": 0.54, "Alcaraz": 0.46},
  "live_odds_fair": {"Fritz": 1.85, "Alcaraz": 1.98},
  "timestamp": "2026-06-27T13:42:00Z"
}
```

---

## Kody błędów

| Kod | Opis                                    |
|-----|-----------------------------------------|
| 400 | Błędne parametry żądania                |
| 401 | Brak lub nieprawidłowy token            |
| 403 | Niewystarczający poziom subskrypcji     |
| 404 | Zasób nie istnieje                      |
| 429 | Przekroczony limit zapytań (rate limit) |
| 500 | Wewnętrzny błąd serwera                 |
