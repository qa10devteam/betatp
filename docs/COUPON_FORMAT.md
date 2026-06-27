# Format Kuponu Dziennego — betatp.io

Każdego ranka (ok. 07:00 CET) subskrybenci Pro otrzymują **dzienny kupon ATP** wygenerowany przez model LightGBM v14. Kupon zawiera najlepsze value bety dnia wraz z systemem 2/3.

---

## Pola kuponu

| Pole          | Typ       | Opis                                                       |
|---------------|-----------|------------------------------------------------------------|
| `date`        | string    | Data kuponu w formacie ISO (`YYYY-MM-DD`)                  |
| `model_version` | int     | Wersja modelu (np. 14)                                     |
| `edge_threshold` | float  | Minimalny edge wymagany do włączenia zakładu (np. 0.15)    |
| `top_singles` | array     | Lista do 3 singlów z najwyższym EV                         |
| `system_2_3`  | object    | System 2 z 3 — wszystkie kombinacje 2-pick z kuponu        |
| `total_ev`    | float     | Suma oczekiwanej wartości wszystkich singlów                |
| `generated_at`| string    | Timestamp generowania kuponu                               |

### Pola pojedynczego singlesa (`top_singles[i]`)

| Pole            | Typ    | Opis                                                         |
|-----------------|--------|--------------------------------------------------------------|
| `pick_id`       | string | Unikalny identyfikator picku (np. `p1`)                      |
| `player`        | string | Gracz do postawienia                                         |
| `opponent`      | string | Rywal                                                        |
| `tournament`    | string | Nazwa turnieju                                               |
| `surface`       | string | Nawierzchnia: `hard`, `clay`, `grass`                        |
| `round`         | string | Runda turnieju (np. `QF`, `SF`, `R32`)                       |
| `odds`          | float  | Kurs bookmakerski (dziesiętny)                               |
| `edge`          | float  | Przewaga modelu nad rynkiem: `model_prob - implied_prob`     |
| `ev`            | float  | Oczekiwana wartość na jednostkę: `odds * model_prob - 1`     |
| `kelly_fraction`| float  | Rekomendowana frakcja Kelly (ułamkowe Kelly ×0.25)           |
| `model_prob`    | float  | Prawdopodobieństwo wygranej wg modelu                        |
| `market_prob`   | float  | Implikowane prawdopodobieństwo rynkowe (po devig)            |
| `bookmaker`     | string | Najlepszy bukmacher dla tego kursu                           |
| `reasoning`     | string | Krótkie uzasadnienie picku po polsku                         |

### Pola systemu (`system_2_3`)

| Pole            | Typ    | Opis                                               |
|-----------------|--------|----------------------------------------------------|
| `type`          | string | Zawsze `"2/3"` — wygrana gdy 2 z 3 trafień         |
| `picks`         | array  | Lista pick_id włączonych do systemu                |
| `combinations`  | array  | Wszystkie kombinacje 2-pick z kursem łącznym       |
| `system_ev`     | float  | Oczekiwana wartość systemu (Monte Carlo, 10k iteracji) |

---

## Przykładowy kupon JSON (dane demo v14 — Wimbledon 2026)

```json
{
  "date": "2026-06-27",
  "model_version": 14,
  "edge_threshold": 0.15,
  "generated_at": "2026-06-27T07:02:14Z",
  "top_singles": [
    {
      "pick_id": "p1",
      "player": "Taylor Fritz",
      "opponent": "Carlos Alcaraz",
      "tournament": "Wimbledon",
      "surface": "grass",
      "round": "QF",
      "odds": 3.20,
      "edge": 0.172,
      "ev": 0.216,
      "kelly_fraction": 0.054,
      "model_prob": 0.380,
      "market_prob": 0.312,
      "bookmaker": "bet365",
      "reasoning": "Fritz wykazuje wyjątkową skuteczność serwisową na trawie (67% punktów za serwis), Alcaraz wchodzi po 3-setowej batalii w 1/8 finału — wyraźna przewaga świeżości. Model widzi 38% szans vs 31.2% rynkowych."
    },
    {
      "pick_id": "p2",
      "player": "Novak Djokovic",
      "opponent": "Lorenzo Musetti",
      "tournament": "Wimbledon",
      "surface": "grass",
      "round": "QF",
      "odds": 1.65,
      "edge": 0.158,
      "ev": 0.143,
      "kelly_fraction": 0.095,
      "model_prob": 0.723,
      "market_prob": 0.606,
      "bookmaker": "Pinnacle",
      "reasoning": "Djokovic na Wimbledonie to historyczne 85.7% wygranych QF. Musetti nie wygrał żadnego meczu z top-10 na trawie w 2026. ELO różnica 287 punktów."
    },
    {
      "pick_id": "p3",
      "player": "Carlos Alcaraz",
      "opponent": "Daniil Medvedev",
      "tournament": "Wimbledon",
      "surface": "grass",
      "round": "SF",
      "odds": 1.80,
      "edge": 0.161,
      "ev": 0.188,
      "kelly_fraction": 0.089,
      "model_prob": 0.658,
      "market_prob": 0.556,
      "bookmaker": "Unibet",
      "reasoning": "Alcaraz mistrz Wimbledonu 2024 — model szacuje 65.8% szans. Medvedev historycznie słaby na trawie (win rate 48% na ATP500+). Różnica ELO grass-specific: +312 dla Alcaraza."
    }
  ],
  "system_2_3": {
    "type": "2/3",
    "picks": ["p1", "p2", "p3"],
    "system_ev": 0.234,
    "combinations": [
      {
        "picks": ["p1", "p2"],
        "players": ["Taylor Fritz", "Novak Djokovic"],
        "combined_odds": 5.28,
        "combined_prob": 0.275,
        "combination_ev": 0.453
      },
      {
        "picks": ["p1", "p3"],
        "players": ["Taylor Fritz", "Carlos Alcaraz"],
        "combined_odds": 5.76,
        "combined_prob": 0.250,
        "combination_ev": 0.440
      },
      {
        "picks": ["p2", "p3"],
        "players": ["Novak Djokovic", "Carlos Alcaraz"],
        "combined_odds": 2.97,
        "combined_prob": 0.476,
        "combination_ev": 0.414
      }
    ]
  },
  "total_ev": 0.547,
  "meta": {
    "bets_analyzed_today": 23,
    "bets_above_threshold": 3,
    "avg_edge": 0.164,
    "model_roi_last_30d": 0.421
  }
}
```

---

## Objaśnienia kluczowych pojęć

### Edge (przewaga)
`edge = model_prob - market_prob`

Jeśli model ocenia szansę wygranej Fritza na 38%, a kurs 3.20 implikuje ~31.2% — edge wynosi **+6.8 pp**. Gramy tylko gdy edge ≥ 15%.

### EV (Expected Value)
`ev = odds × model_prob - 1`

Przykład: `3.20 × 0.38 - 1 = +0.216` → na każdą postawioną jednostkę oczekujemy zysku **+21.6 groszy**.

### Kelly Fraction (frakcja Kelly)
`kelly = (odds × model_prob - 1) / (odds - 1)`

Stosujemy **ułamkowe Kelly × 0.25** dla zarządzania ryzykiem. Przykład: full Kelly = 21.4%, rekomendujemy **5.4% bankrolla**.

### System 2/3
Stawiasz na **3 kupony parlay 2-pick**. Wygrywasz jeśli trafisz co najmniej 2 z 3 zakładów. Redukuje wariancję przy zachowaniu wysokiego EV.

---

## Zarządzanie bankrollem

| Typ zakładu   | Rekomendowana stawka        |
|---------------|-----------------------------|
| Single (pro)  | Kelly × 0.25 × bankroll     |
| Single (ostrożny) | 1-2% bankrolla stały    |
| System 2/3    | 0.5% bankrolla per kombinacja |

> **Uwaga:** Kupon ma charakter informacyjny. Hazard wiąże się z ryzykiem utraty środków. Graj odpowiedzialnie.
