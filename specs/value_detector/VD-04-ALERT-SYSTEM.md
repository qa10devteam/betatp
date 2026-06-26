# VD-04: System Alertów Wartościowych — Formalna Specyfikacja

**Moduł:** Value Detector  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Obowiązujący  

---

## 1. Wprowadzenie

System alertów wartościowych (Value Alert System, VAS) jest komponentem odpowiedzialnym za automatyczne wykrywanie i dystrybucję informacji o zakładach wartościowych (ang. *value bets*) w czasie rzeczywistym. Niniejszy dokument formalizuje warunki wyzwalania alertów, schemat danych ładunku alertu (payload), kanały powiadomień oraz mechanizmy ograniczania częstotliwości (rate limiting). System musi zapewniać niskie opóźnienie ($< 500$ ms od wykrycia do dostarczenia) oraz odporność na awarie.

---

## 2. Formalny Model Alertu

### Definicja 2.1 (Alert)
Alert to krotka:

$$\mathcal{A} = (\text{id},\ t,\ E,\ \text{EV},\ \text{priority},\ \text{odds},\ \text{payload})$$

gdzie:
- $\text{id} \in \mathbb{N}$ — unikalny identyfikator alertu (UUID v4)
- $t \in \mathbb{R}_{\geq 0}$ — czas wygenerowania (timestamp UNIX)
- $E$ — zdarzenie zakładu (mecz, typ zakładu, zawodnik)
- $\text{EV} \in \mathbb{R}$ — wartość oczekiwana zakładu
- $\text{priority} \in \{\text{MEDIUM, HIGH, CRITICAL}\}$ — poziom priorytetu
- $\text{odds}$ — dane kursowe w momencie alertu
- $\text{payload}$ — kompletny schemat JSON (sekcja 5)

---

## 3. Warunki Wyzwalania Alertu

### Definicja 3.1 (Warunki wyzwalania)
System generuje alert gdy spełniony jest **co najmniej jeden** z poniższych warunków:

**Warunek W1 — EV pre-match:**

$$\text{EV}_{\text{pre}} \geq 0.02$$

Definicja: $\text{EV} = p_{\text{model}} \cdot d_{\text{Shin}} - 1$, gdzie $d_{\text{Shin}}$ — kurs po de-viggingu metodą Shina.

**Warunek W2 — EV in-play:**

$$\text{EV}_{\text{live}} \geq 0.05$$

Wyższy próg uzasadniony szybką zmiennością kursów live i wyższym ryzykiem modelu w trakcie meczu.

**Warunek W3 — Rozbieżność z rynkiem pochodnym:**

$$|p_{\text{model}} - p_{\text{derivative}}| > 0.05$$

gdzie $p_{\text{derivative}}$ — prawdopodobieństwo implikowane z rynku pochodnego (set betting, game handicap). Warunek sygnalizuje potencjalną nieefektywność rynku.

### Definicja 3.2 (Rynek pochodny)
Rynek pochodny to zakład na wynik cząstkowy meczu:
- Set betting: wynik setami (np. 2:0, 2:1, 1:2)
- Game handicap: różnica gemów
- First set winner, next game winner

Prawdopodobieństwo $p_{\text{derivative}}$ wyznaczamy z kursów na rynek pochodny metodą odwrotną (inverse mapping):

$$p_{\text{derivative}}(A) = \sum_{\omega: A \text{ wygrywa}} P^{\text{Shin}}(\omega)$$

---

## 4. Poziomy Priorytetu

### Definicja 4.1 (Klasyfikacja priorytetów)

| Poziom | Symbol | Warunek EV | Opis |
|--------|--------|-----------|------|
| CRITICAL | 🔴 | $\text{EV} \geq 0.08$ | Wyjątkowa okazja, działaj natychmiast |
| HIGH | 🟠 | $0.05 \leq \text{EV} < 0.08$ | Silna okazja, rekomendowane działanie |
| MEDIUM | 🟡 | $0.02 \leq \text{EV} < 0.05$ | Standardowa okazja, zweryfikuj ręcznie |

### Definicja 4.2 (Priorytet złożony)
Dla warunków W2 i W3 jednoczesnych, priorytet jest podwyższany o jeden poziom:

$$\text{priority\_final} = \min(\text{CRITICAL},\ \text{priority}(W_i) + 1)$$

### Tabela 4.1 — Macierz priorytetów

| EV pre | EV live | Rozbieżność | Priorytet |
|--------|---------|-------------|-----------|
| 2–5% | — | — | MEDIUM |
| 5–8% | — | — | HIGH |
| ≥8% | — | — | CRITICAL |
| — | 5–8% | — | HIGH |
| — | ≥8% | — | CRITICAL |
| 2–5% | — | >5pp | HIGH (podwyższony) |
| — | 5–8% | >5pp | CRITICAL (podwyższony) |

---

## 5. Schemat Ładunku Alertu (Payload Schema)

### Specyfikacja 5.1 (JSON Schema — Alert Payload)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://betatp.io/schemas/alert/v1.0.0",
  "title": "ValueAlert",
  "type": "object",
  "required": [
    "alert_id", "timestamp", "priority", "match", "bet",
    "model", "market", "kelly", "expires_at"
  ],
  "properties": {
    "alert_id": {
      "type": "string",
      "format": "uuid",
      "description": "UUID v4 — unikalny identyfikator alertu"
    },
    "timestamp": {
      "type": "number",
      "description": "Unix timestamp UTC (sekundy z ułamkami)"
    },
    "priority": {
      "type": "string",
      "enum": ["MEDIUM", "HIGH", "CRITICAL"]
    },
    "match": {
      "type": "object",
      "required": ["match_id", "player_a", "player_b", "tournament",
                   "surface", "round", "start_time", "is_live"],
      "properties": {
        "match_id":    {"type": "string"},
        "player_a":    {"type": "string"},
        "player_b":    {"type": "string"},
        "tournament":  {"type": "string"},
        "surface":     {"type": "string", "enum": ["hard", "clay", "grass", "indoor"]},
        "round":       {"type": "string"},
        "start_time":  {"type": "number"},
        "is_live":     {"type": "boolean"},
        "score":       {"type": "string", "description": "np. '6-3, 3-2'"}
      }
    },
    "bet": {
      "type": "object",
      "required": ["bet_type", "selection", "bookmaker",
                   "decimal_odds", "ev", "trigger_condition"],
      "properties": {
        "bet_type":    {"type": "string", "enum": ["match_winner", "set_betting",
                        "game_handicap", "first_set_winner", "total_games"]},
        "selection":   {"type": "string", "description": "np. 'player_a_wins'"},
        "bookmaker":   {"type": "string"},
        "decimal_odds":{"type": "number", "minimum": 1.01},
        "ev":          {"type": "number", "description": "EV w ułamku (0.03 = 3%)"},
        "ev_percent":  {"type": "number", "description": "EV w procentach"},
        "trigger_condition": {
          "type": "string",
          "enum": ["W1_pre_match", "W2_in_play", "W3_derivative"]
        }
      }
    },
    "model": {
      "type": "object",
      "required": ["p_win_A", "p_win_B", "n_simulations",
                   "std_error", "model_version"],
      "properties": {
        "p_win_A":       {"type": "number", "minimum": 0, "maximum": 1},
        "p_win_B":       {"type": "number", "minimum": 0, "maximum": 1},
        "n_simulations": {"type": "integer", "minimum": 10000},
        "std_error":     {"type": "number"},
        "model_version": {"type": "string"},
        "p_serve_A":     {"type": "number"},
        "p_serve_B":     {"type": "number"},
        "confidence_95": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
      }
    },
    "market": {
      "type": "object",
      "properties": {
        "implied_prob_A":  {"type": "number"},
        "implied_prob_B":  {"type": "number"},
        "overround":       {"type": "number"},
        "devig_method":    {"type": "string", "enum": ["shin", "proportional", "additive"]},
        "true_prob_A":     {"type": "number"},
        "true_prob_B":     {"type": "number"},
        "edge":            {"type": "number"}
      }
    },
    "kelly": {
      "type": "object",
      "required": ["full_kelly", "half_kelly", "recommended_fraction",
                   "recommended_stake_pct"],
      "properties": {
        "full_kelly":             {"type": "number"},
        "half_kelly":             {"type": "number"},
        "recommended_fraction":   {"type": "number"},
        "recommended_stake_pct":  {"type": "number",
                                   "description": "% bankrollu (Half Kelly)"},
        "max_stake_abs":          {"type": "number",
                                   "description": "Absolutny limit stawki [PLN/EUR]"}
      }
    },
    "expires_at": {
      "type": "number",
      "description": "Unix timestamp ważności alertu — pre-match: start_time; live: now + 60s"
    }
  }
}
```

---

## 6. Kanały Powiadomień

### Definicja 6.1 (Kanały dystrybucji)
System BetaTP obsługuje trzy kanały powiadomień:

#### Kanał C1 — WebSocket Push

**Protokół:** WebSocket (RFC 6455) z JWT autoryzacją  
**Endpoint:** `wss://api.betatp.io/v1/alerts/stream`  
**Latencja docelowa:** $< 200$ ms od wykrycia  
**Format:** JSON (schemat z sekcji 5)  

```
// Przykładowy frame WebSocket
{
  "type": "ALERT",
  "data": { ...AlertPayload... }
}
```

**Mechanizm reconnect:** Wykładniczy backoff: $t_n = \min(2^n, 30)$ sekund, max 10 prób.

#### Kanał C2 — Telegram Bot

**Format wiadomości:**

```
🔴 CRITICAL ALERT — BetaTP
━━━━━━━━━━━━━━━━━━━━━
🎾 Djokovic vs Rublev
🏆 Australian Open, QF
📊 EV: +11.6% | Kurs: 1.25
🎯 Model: Djokovic 84.2%
💰 Half Kelly: 7.3% bankrollu
⏰ Wygasa: 15:30 UTC
━━━━━━━━━━━━━━━━━━━━━
🔗 betatp.io/alert/a7f3c2
```

**API:** Telegram Bot API v7.0  
**Rate limit:** Telegram: max 30 wiadomości/sekundę per bot  
**Formaty priorytetów:**
- CRITICAL: 🔴 + silent=false (dźwięk)
- HIGH: 🟠 + silent=false
- MEDIUM: 🟡 + silent=true (cisza)

#### Kanał C3 — Email Digest

**Format:** HTML email + plain text fallback  
**Harmonogram wysyłki:**
- CRITICAL: natychmiast (< 60s)
- HIGH: co 15 minut (batch)
- MEDIUM: codzienny digest (08:00 UTC)

**Provider:** SendGrid / AWS SES  
**Template:** Responsywny HTML (max 600px szerokości)

---

## 7. Rate Limiting

### Definicja 7.1 (Ograniczenie częstotliwości)
Dla każdego użytkownika $u$ i każdego kanału $c$:

$$\text{alerts\_sent}(u, c, [t - 3600, t]) \leq 10$$

Maksymalnie **10 alertów na godzinę** na użytkownika, na kanał.

### Algorytm 7.1 (Token Bucket)
Implementacja rate limiting metodą *token bucket*:

```python
class RateLimiter:
    """
    Token bucket dla alertów: 10 tokenów/godzina = 1 token/360s
    """
    def __init__(self, max_tokens=10, refill_rate=1/360):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  // tokenów/sekundę
    
    def can_send(self, user_id: str, channel: str) -> bool:
        key = f"{user_id}:{channel}"
        tokens = self.get_tokens(key)
        
        if tokens >= 1.0:
            self.consume_token(key)
            return True
        return False
    
    def get_tokens(self, key: str) -> float:
        now = time.time()
        last_check, stored_tokens = redis.hgetall(key)
        elapsed = now - last_check
        new_tokens = min(
            self.max_tokens,
            stored_tokens + elapsed * self.refill_rate
        )
        return new_tokens
```

### Tabela 7.1 — Rate Limiting per priorytet i kanał

| Priorytet | WebSocket | Telegram | Email |
|-----------|-----------|----------|-------|
| CRITICAL | Bez limitu* | 10/h | Natychmiast |
| HIGH | 10/h | 10/h | 15 min batch |
| MEDIUM | 10/h | 10/h | Dziennik digest |

*CRITICAL: limit podniesiony do 20/h dla WebSocket.

### Specyfikacja 7.1 (Deduplikacja alertów)
Alert jest deduplikowany jeśli w ciągu 5 minut wysłano alert dla tego samego meczu i tego samego rynku:

$$\text{deduplicate} \iff \exists \mathcal{A}' : (\mathcal{A}'.E = \mathcal{A}.E) \land (t - \mathcal{A}'.t < 300)$$

---

## 8. Architektura Systemu Alertów

```
  ┌──────────────────┐
  │  Monte Carlo     │──→ p_model
  │  Engine          │
  └──────────────────┘
           │
           ▼
  ┌──────────────────┐     ┌──────────────────┐
  │  Value Detector  │←────│  Odds Scraper    │
  │  (EV Calculator) │     │  (Betfair/1xBet) │
  └──────────────────┘     └──────────────────┘
           │
           │ EV ≥ threshold?
           ▼
  ┌──────────────────┐
  │  Alert Router    │
  │  (Priority +     │
  │   Rate Limiter)  │
  └──────────────────┘
       │      │      │
       ▼      ▼      ▼
  [WS] [Telegram] [Email]
```

### Specyfikacja 8.1 (SLA — Service Level Agreement)

| Metryka | Wartość docelowa | Wartość krytyczna |
|---------|-----------------|-------------------|
| Latencja alert (CRITICAL) | < 200 ms | < 500 ms |
| Latencja alert (HIGH) | < 500 ms | < 2000 ms |
| Dostępność systemu | 99.5% | 99.0% |
| Utrata alertów (CRITICAL) | 0% | < 0.1% |
| Fałszywe alarmy | < 0.5% | < 2% |

---

## 9. Monitoring i Audyt

### Specyfikacja 9.1 (Logi audytowe)
Każdy alert jest logowany w systemie audytowym z polami:

```json
{
  "alert_id": "uuid",
  "generated_at": 1704067200.123,
  "delivered_at": {
    "websocket": 1704067200.234,
    "telegram": 1704067200.445,
    "email": null
  },
  "delivery_status": {
    "websocket": "delivered",
    "telegram": "delivered",
    "email": "queued"
  },
  "rate_limited": false,
  "deduplicated": false,
  "ev_at_delivery": 0.086,
  "odds_at_delivery": 1.25
}
```

### Specyfikacja 9.2 (Alerty ekspirowane)
Jeśli kurs zmienił się tak, że $\text{EV} < 0.01$ przed dostarczeniem alertu, alert jest anulowany z kodem `EXPIRED_BEFORE_DELIVERY`.

---

## 10. Literatura i Standardy

1. RFC 6455 (2011). *The WebSocket Protocol*. IETF.
2. Telegram Bot API (2024). *Telegram Bot API Documentation*. https://core.telegram.org/bots/api
3. SendGrid (2024). *Email API Documentation*. https://docs.sendgrid.com/
4. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media.
5. Fowler, M. (2002). *Patterns of Enterprise Application Architecture*. Addison-Wesley.
6. AWS (2024). *Amazon Simple Email Service Developer Guide*.
7. BetaTP Internal (2024). *System Architecture v2.1*. Dokument wewnętrzny.

---

*Dokument zatwierdzony przez zespół BetaTP Quantitative Research. Poprzedni: VD-03. Moduł Value Detector — dokumentacja kompletna.*
