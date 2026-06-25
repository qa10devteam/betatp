# ADV-02: Schemat Wyjść Monte Carlo — Formalna Specyfikacja

**Moduł:** `montecarlo_engine`  
**Wersja:** 2.1.0  
**Status:** Zatwierdzony  
**Data:** 2025-06-25  
**Autor:** betatp.io — Zespół API

---

## 1. Cel i Zakres

Dokument definiuje kompletny schemat wyjść silnika Monte Carlo betatp.io. Każde pole jest specyfikowane z typem danych, dozwolonym zakresem wartości, semantyczną interpretacją i warunkami brzegowymi. Specyfikacja obejmuje endpoint REST API oraz przykładową odpowiedź dla meczu Djokovic vs Alcaraz, Australian Open 2024 (format BO5).

---

## 2. Definicje Formalne

### 2.1 Aksjomat Podstawowy Symulacji

**Definicja 2.1 (Symulacja Monte Carlo meczu):** Niech $\Omega$ będzie przestrzenią zdarzeń meczu tenisowego. Symulacja MC generuje $N$ niezależnych losowań $\omega_1, \ldots, \omega_N \sim P(\cdot | \theta)$, gdzie $\theta$ to wektor parametrów wejściowych. Każde $\omega_k$ to kompletna trajektoria meczu: sekwencja punktów, gemów i setów.

**Definicja 2.2 (Estymator MC):** Dla zdarzenia $A \subseteq \Omega$:

$$\hat{P}(A) = \frac{1}{N}\sum_{k=1}^{N} \mathbf{1}[A \in \omega_k]$$

**Twierdzenie 2.1 (Zbieżność):** Na mocy Prawa Wielkich Liczb: $\hat{P}(A) \xrightarrow{a.s.} P(A)$ dla $N \to \infty$.

**Błąd standardowy estymatora:** $\text{SE}(\hat{P}) = \sqrt{\hat{P}(1-\hat{P})/N}$.

Dla $N = 100\,000$ i $\hat{P} = 0.5$: $\text{SE} = 0.00158$ (przedział 95%: $\pm 0.0031$).

---

## 3. Specyfikacja Pól Wyjściowych

### 3.1 Prawdopodobieństwa Wygranej

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `p_winner_A` | `float` | $[0, 1]$ | Prawdopodobieństwo wygranej gracza A w meczu |
| `p_winner_B` | `float` | $[0, 1]$ | Prawdopodobieństwo wygranej gracza B w meczu |

**Niezmiennik:** $p\_winner\_A + p\_winner\_B = 1.0$ (dokładnie, bez błędu numerycznego).

**Implementacja:** `p_winner_B = 1.0 - p_winner_A` (nie obliczane niezależnie).

### 3.2 Rozkład Wyników Setów

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `p_set_scores` | `dict[str, float]` | klucz: string, wartość: $[0,1]$ | Rozkład prawdopodobieństwa wszystkich możliwych wyników meczu |

**Dozwolone klucze dla BO3:**

```
"2:0", "2:1", "0:2", "1:2"
```

**Dozwolone klucze dla BO5:**

```
"3:0", "3:1", "3:2", "0:3", "1:3", "2:3"
```

**Niezmiennik:** $\sum_{\text{score}} p\_set\_scores[\text{score}] = 1.0$

### 3.3 Prawdopodobieństwa Tie-Breaków

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `p_tiebreak_set1` | `float` | $[0, 1]$ | P(tie-break w secie 1) |
| `p_tiebreak_set2` | `float` | $[0, 1]$ | P(tie-break w secie 2) |
| `p_tiebreak_set3` | `float` | $[0, 1]$ | P(tie-break w secie 3) |
| `p_tiebreak_set4` | `float` | $[0, 1]$ | P(tie-break w secie 4) \| mecz dochodzi do seta 4 |
| `p_tiebreak_set5` | `float` | $[0, 1]$ | P(tie-break w secie 5) \| mecz dochodzi do seta 5 |

**Uwaga:** Dla AO 2024 obowiązuje final-set tiebreak (10 punktów) dla seta 5. Pole `p_tiebreak_set5` dla AO = P(final-set tiebreak), nie standardowy 7-pkt tiebreak.

**Uwaga BO3:** Pola `p_tiebreak_set4` i `p_tiebreak_set5` = `null` dla meczów BO3.

### 3.4 Oczekiwane Statystyki Meczu

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `expected_games` | `float` | $[12, 50]$ | Oczekiwana liczba gemów w meczu |
| `expected_duration_minutes` | `float` | $[40, 360]$ | Oczekiwany czas trwania w minutach |

**Model czasu trwania:**

$$T = \alpha \cdot G + \beta \cdot TB + \gamma$$

gdzie $G$ = liczba gemów, $TB$ = liczba tie-breaków, i:
- $\alpha = 2.1$ min/gem (na nawierzchni twardej)
- $\beta = 5.5$ min/tie-break
- $\gamma = 8$ min (przerwy między setami)

Parametry $(\alpha, \beta, \gamma)$ są kalibrowane na danych ATP 2018–2024.

### 3.5 Prawdopodobieństwa Struktury Meczu

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `p_match_goes_3sets` | `float` | $[0, 1]$ | P(mecz rozegrany w 3 setach), tylko BO3 |
| `p_match_goes_5sets` | `float` | $[0, 1]$ | P(mecz rozegrany w 5 setach), tylko BO5 |
| `p_A_wins_first_set` | `float` | $[0, 1]$ | P(gracz A wygra pierwszy set) |

**Relacja dla BO5:**

$$p\_match\_goes\_5sets = p\_set\_scores["3:2"] + p\_set\_scores["2:3"]$$

### 3.6 Przedziały Ufności i Metadane

| Pole | Typ | Zakres | Interpretacja |
|---|---|---|---|
| `confidence_interval_95` | `tuple[float, float]` | $[0,1] \times [0,1]$ | 95% CI dla `p_winner_A` |
| `n_simulations` | `int` | $[1000, 1000000]$ | Liczba przeprowadzonych symulacji |
| `computation_time_ms` | `float` | $[1, 10000]$ | Czas obliczeń w milisekundach |

**Obliczenie CI 95%:**

$$\text{CI}_{95} = \left[\hat{p} - 1.96\sqrt{\frac{\hat{p}(1-\hat{p})}{N}},\ \hat{p} + 1.96\sqrt{\frac{\hat{p}(1-\hat{p})}{N}}\right]$$

---

## 4. Definicja Endpointu API

### 4.1 Endpoint

```
POST /api/v1/simulate
Content-Type: application/json
Authorization: Bearer {API_KEY}
```

### 4.2 Schemat Żądania (Request Schema)

```json
{
  "player_a": {
    "name": "string",           // Wymagane: pełna nazwa gracza
    "player_id": "integer",     // Wymagane: ID z TML-Database
    "elo_rating": "float",      // Opcjonalne: nadpisuje obliczony Elo
    "surface_elo": {            // Opcjonalne: Elo per nawierzchnia
      "hard": "float",
      "clay": "float",
      "grass": "float"
    }
  },
  "player_b": { /* analogicznie */ },
  "match_config": {
    "format": "BO3" | "BO5",    // Wymagane
    "surface": "hard" | "clay" | "grass" | "carpet",  // Wymagane
    "tournament": "string",      // Opcjonalne: nazwa turnieju
    "round": "string",           // Opcjonalne: R128|R64|R32|R16|QF|SF|F
    "indoor": "boolean",         // Default: false
    "altitude_m": "integer"      // Default: 0 (m n.p.m.)
  },
  "simulation_config": {
    "n_simulations": "integer",  // Default: 100000, min: 1000, max: 1000000
    "seed": "integer | null",    // Opcjonalne: seed dla powtarzalności
    "include_tiebreak_probs": "boolean",  // Default: true
    "include_game_by_game": "boolean"     // Default: false (drogi obliczeniowo)
  }
}
```

### 4.3 Schemat Odpowiedzi (Response Schema)

```json
{
  "status": "success" | "error",
  "request_id": "string (UUID)",
  "timestamp": "string (ISO 8601)",
  "result": {
    "p_winner_A": "float",
    "p_winner_B": "float",
    "p_set_scores": "dict[string, float]",
    "p_tiebreak_set1": "float",
    "p_tiebreak_set2": "float",
    "p_tiebreak_set3": "float",
    "p_tiebreak_set4": "float | null",
    "p_tiebreak_set5": "float | null",
    "expected_games": "float",
    "expected_duration_minutes": "float",
    "p_match_goes_3sets": "float | null",
    "p_match_goes_5sets": "float | null",
    "p_A_wins_first_set": "float",
    "confidence_interval_95": "[float, float]",
    "n_simulations": "integer",
    "computation_time_ms": "float"
  },
  "model_metadata": {
    "model_version": "string",
    "elo_A_used": "float",
    "elo_B_used": "float",
    "surface_adjustment_applied": "boolean"
  }
}
```

---

## 5. Przykładowa Odpowiedź: Djokovic vs Alcaraz, AO 2024 (BO5)

**Kontekst:** Australian Open 2024, Półfinał, nawierzchnia twarda (hala), Melbourne.  
Elo Djokovic (hard): 2387, Elo Alcaraz (hard): 2241.

```json
{
  "status": "success",
  "request_id": "7f3a9c21-4b8e-4d12-a901-bc234def5678",
  "timestamp": "2024-01-26T14:32:00Z",
  "result": {
    "p_winner_A": 0.6821,
    "p_winner_B": 0.3179,
    "p_set_scores": {
      "3:0": 0.2134,
      "3:1": 0.2689,
      "3:2": 0.1998,
      "0:3": 0.0912,
      "1:3": 0.1193,
      "2:3": 0.1074
    },
    "p_tiebreak_set1": 0.1847,
    "p_tiebreak_set2": 0.1834,
    "p_tiebreak_set3": 0.1801,
    "p_tiebreak_set4": 0.1756,
    "p_tiebreak_set5": 0.1723,
    "expected_games": 38.7,
    "expected_duration_minutes": 184.3,
    "p_match_goes_3sets": null,
    "p_match_goes_5sets": 0.3072,
    "p_A_wins_first_set": 0.6612,
    "confidence_interval_95": [0.6759, 0.6883],
    "n_simulations": 100000,
    "computation_time_ms": 234.7
  },
  "model_metadata": {
    "model_version": "2.1.0",
    "elo_A_used": 2387.0,
    "elo_B_used": 2241.0,
    "surface_adjustment_applied": true
  }
}
```

**Weryfikacja niezmienników:**
- $0.2134 + 0.2689 + 0.1998 + 0.0912 + 0.1193 + 0.1074 = 1.0000$ ✓
- $p\_match\_goes\_5sets = 0.1998 + 0.1074 = 0.3072$ ✓
- $p\_winner\_A = 0.2134 + 0.2689 + 0.1998 = 0.6821$ ✓

---

## 6. Obsługa Błędów

| Kod HTTP | Kod błędu | Opis |
|---|---|---|
| 400 | `INVALID_FORMAT` | `format` nie jest BO3 ani BO5 |
| 400 | `INVALID_SURFACE` | Nieznana nawierzchnia |
| 400 | `N_SIM_OUT_OF_RANGE` | `n_simulations` < 1000 lub > 1000000 |
| 404 | `PLAYER_NOT_FOUND` | `player_id` nie istnieje w bazie |
| 429 | `RATE_LIMIT_EXCEEDED` | Przekroczono limit żądań (100/min) |
| 503 | `ENGINE_UNAVAILABLE` | Silnik MC niedostępny |

---

## Referencje

1. Barnett, T., Clarke, S.R. (2005). *Combining player statistics to predict outcomes of tennis matches*. IMA Journal of Management Mathematics, 16(2), 113–120.  
2. Newton, P.K., Aslam, K. (2009). *Monte Carlo Tennis*. SIAM Review, 51(3), 450–474.  
3. OpenAPI Specification 3.1.0 — https://spec.openapis.org/oas/v3.1.0
