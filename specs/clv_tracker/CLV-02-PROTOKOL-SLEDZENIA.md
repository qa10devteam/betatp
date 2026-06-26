# CLV-02: Protokół Śledzenia Closing Line Value

**Moduł:** betatp.io CLV TRACKER  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Zatwierdzone  

---

## 1. Cel i Zakres

Niniejszy dokument definiuje formalny **protokół śledzenia CLV** — kompletną specyfikację operacyjną procesu rejestracji zakładów, pobierania kursów zamknięcia, obliczania CLV oraz przechowywania i wizualizacji danych w systemie betatp.io. Protokół ten zapewnia powtarzalność, integralność danych oraz statystyczną rzetelność pomiaru wydajności modelu.

---

## 2. Schema Danych — Rekord Zakładu

### Definicja 2.1 — Krotka Zakładu

Każdy zakład reprezentowany jest jako krotka:

$$\mathcal{B} = (\text{match\_id},\ \text{player\_backed},\ \text{stake},\ o_{\text{open}},\ t_{\text{open}},\ o_{\text{close}},\ t_{\text{close}},\ r,\ \text{pnl})$$

gdzie:

| Pole | Typ | Opis | Ograniczenia |
|---|---|---|---|
| `match_id` | UUID / VARCHAR(36) | Unikalny identyfikator meczu ATP | NOT NULL, PRIMARY KEY ref |
| `player_backed` | VARCHAR(100) | Imię i nazwisko obstawionego gracza | NOT NULL |
| `stake` | NUMERIC(10,2) | Stawka zakładu w jednostkach walutowych | > 0 |
| `opening_odds` ($o_{\text{open}}$) | NUMERIC(6,3) | Kurs dziesiętny w chwili zawarcia zakładu | > 1.0 |
| `opening_timestamp` ($t_{\text{open}}$) | TIMESTAMPTZ | Czas zawarcia zakładu (UTC) | NOT NULL |
| `closing_odds_pinnacle` ($o_{\text{close}}$) | NUMERIC(6,3) | Kurs zamknięcia Pinnacle Sports | > 1.0, nullable do czasu meczu |
| `closing_timestamp` ($t_{\text{close}}$) | TIMESTAMPTZ | Czas pobrania kursu zamknięcia (UTC) | $t_{\text{close}} \geq t_{\text{open}}$ |
| `actual_result` | BOOLEAN | TRUE = zakład wygrany, FALSE = przegrany | nullable do czasu meczu |
| `pnl` | NUMERIC(10,2) | Zysk/strata w jednostkach walutowych | nullable |

### Definicja 2.2 — Schemat PostgreSQL

```sql
CREATE TABLE bets (
    id               BIGSERIAL PRIMARY KEY,
    match_id         VARCHAR(36)     NOT NULL REFERENCES matches(id),
    player_backed    VARCHAR(100)    NOT NULL,
    stake            NUMERIC(10,2)   NOT NULL CHECK (stake > 0),
    opening_odds     NUMERIC(6,3)    NOT NULL CHECK (opening_odds > 1.0),
    opening_timestamp TIMESTAMPTZ   NOT NULL,
    closing_odds_pinnacle NUMERIC(6,3) CHECK (closing_odds_pinnacle > 1.0),
    closing_timestamp TIMESTAMPTZ,
    actual_result    BOOLEAN,
    pnl              NUMERIC(10,2),
    clv              NUMERIC(8,5)    GENERATED ALWAYS AS (
                         CASE WHEN closing_odds_pinnacle IS NOT NULL
                              THEN opening_odds / closing_odds_pinnacle - 1.0
                              ELSE NULL END
                     ) STORED,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_timestamps CHECK (closing_timestamp IS NULL OR closing_timestamp >= opening_timestamp)
);

CREATE INDEX idx_bets_match_id ON bets(match_id);
CREATE INDEX idx_bets_opening_timestamp ON bets(opening_timestamp);
CREATE INDEX idx_bets_clv ON bets(clv) WHERE clv IS NOT NULL;
```

---

## 3. Pipeline Obliczania CLV

### Definicja 3.1 — Sekwencja Przetwarzania

Pipeline CLV składa się z czterech kroków formalnych:

$$\mathcal{P}: \mathcal{B}_{\text{partial}} \to \mathcal{B}_{\text{complete}} \to \mathcal{B}_{\text{computed}} \to \mathcal{B}_{\text{stored}}$$

**Krok 1 — Rejestracja zakładu:**

W chwili $t_0$ gracz zawiera zakład po kursie $o_{\text{open}}$. System rejestruje rekord częściowy:

$$\mathcal{B}_{\text{partial}} = (\text{match\_id},\ \text{player\_backed},\ \text{stake},\ o_{\text{open}},\ t_0,\ \text{NULL},\ \text{NULL},\ \text{NULL},\ \text{NULL})$$

**Krok 2 — Pobranie kursu zamknięcia:**

W chwili $t_1 = \text{match\_start} - \varepsilon$ (gdzie $\varepsilon < 60$ sekund) system odpytuje Pinnacle Sports API:

```
GET https://api.pinnacle.com/v1/odds?sportId=33&matchId={match_id}&lineType=closing
```

Zwrócona wartość $o_{\text{close}}$ zapisywana jest do rekordu wraz z $t_1$.

**Krok 3 — Obliczenie CLV:**

$$CLV_i = \frac{o_{\text{open},i}}{o_{\text{close},i}} - 1$$

Kolumna `clv` jest wyliczana automatycznie (GENERATED ALWAYS) po uzupełnieniu `closing_odds_pinnacle`.

**Krok 4 — Uzupełnienie wyniku i P&L:**

Po zakończeniu meczu:

$$\text{pnl}_i = \begin{cases} \text{stake}_i \cdot (o_{\text{open},i} - 1) & \text{jeśli wygrany} \\ -\text{stake}_i & \text{jeśli przegrany} \end{cases}$$

---

## 4. Metryki Kroczące CLV

### Definicja 4.1 — Okna Czasowe

Niech $\mathcal{S}_w$ oznacza zbiór zakładów z ostatnich $w$ dni z niepustą wartością CLV:

$$\mathcal{S}_w = \{i : t_{\text{open},i} \geq \text{NOW}() - w\text{ days} \wedge CLV_i \neq \text{NULL}\}$$

**Metryki kroczące:**

$$\overline{CLV}_{7} = \frac{1}{|\mathcal{S}_7|} \sum_{i \in \mathcal{S}_7} CLV_i$$

$$\overline{CLV}_{30} = \frac{1}{|\mathcal{S}_{30}|} \sum_{i \in \mathcal{S}_{30}} CLV_i$$

$$\overline{CLV}_{90} = \frac{1}{|\mathcal{S}_{90}|} \sum_{i \in \mathcal{S}_{90}} CLV_i$$

$$\overline{CLV}_{\text{all}} = \frac{1}{N_{\text{total}}} \sum_{i=1}^{N_{\text{total}}} CLV_i$$

### Implementacja SQL Metryk Kroczących

```sql
-- Metryka 30-dniowa CLV
SELECT
    AVG(clv)                     AS clv_30d_mean,
    STDDEV(clv)                  AS clv_30d_std,
    COUNT(*)                     AS n_bets,
    MIN(opening_timestamp)       AS period_start,
    MAX(opening_timestamp)       AS period_end
FROM bets
WHERE opening_timestamp >= NOW() - INTERVAL '30 days'
  AND clv IS NOT NULL;
```

---

## 5. Test Statystyczny — t-test na Serii CLV

### Definicja 5.1 — Test t dla Średniej CLV

Dla serii CLV $\{CLV_1, \ldots, CLV_N\}$ testujemy:

$$H_0: \mu_{CLV} = 0 \quad \text{(brak przewagi)}$$
$$H_1: \mu_{CLV} > 0 \quad \text{(dodatnia przewaga)}$$

Statystyka testowa (jednostronny t-test):

$$t = \frac{\overline{CLV}}{s_{CLV} / \sqrt{N}}$$

gdzie:
- $\overline{CLV} = \frac{1}{N}\sum_{i=1}^N CLV_i$
- $s_{CLV} = \sqrt{\frac{1}{N-1}\sum_{i=1}^N (CLV_i - \overline{CLV})^2}$

**Reguła decyzyjna:** Odrzucamy $H_0$ na poziomie $\alpha = 0.05$ (jednostronnie), gdy:

$$t > t_{0.05, N-1} \approx 1.645 \quad \text{(dla dużych } N\text{)}$$

Równoważnie, gdy $p\text{-value} < 0.05$.

### Przykład Obliczeniowy

Dla $N = 441$, $\overline{CLV} = 0.02$, $s_{CLV} = 0.05$:

$$t = \frac{0.02}{0.05 / \sqrt{441}} = \frac{0.02}{0.05 / 21} = \frac{0.02}{0.00238} \approx 8.40$$

$t = 8.40 \gg 1.645$, więc odrzucamy $H_0$ z bardzo wysoką pewnością ($p \approx 0$).

---

## 6. Definicja Wizualizacji Dashboardu

### Wykres 6.1 — Skumulowane CLV w Czasie

$$CLV_{\text{cum}}(t) = \frac{1}{N(t)} \sum_{i: t_i \leq t} CLV_i$$

Wykres liniowy z osią X = czas, osią Y = średnie CLV, wstążką ufności $\pm 1.96 \cdot s_{CLV}/\sqrt{N(t)}$.

### Wykres 6.2 — Rozkład CLV

Histogram $\{CLV_i\}$ z naniesionym rozkładem normalnym $\mathcal{N}(\overline{CLV}, s_{CLV}^2)$ — pozwala wizualnie ocenić normalność próby.

### Wykres 6.3 — Heatmapa CLV według Turniejów

Macierz: wiersze = turnieje ATP (Grand Slam, Masters, ATP 500, ATP 250, Challenger), kolumny = miesiące. Kolor komórki = średnie CLV (zielony = dodatni, czerwony = ujemny).

### Wykres 6.4 — Rolling CLV z Alertem

Kroczące 30-dniowe CLV z progiem alertu = 0%. Gdy $\overline{CLV}_{30} < 0\%$, wykres sygnalizuje kolor czerwony i wyzwala powiadomienie o konieczności rekalibracji modelu.

| Wizualizacja | Typ | Odświeżanie | Priorytet |
|---|---|---|---|
| Skumulowane CLV | Wykres liniowy | Po każdym meczu | Wysoki |
| Histogram CLV | Histogram + krzywa norm. | Dzienny | Średni |
| Heatmapa turnieje | Heatmapa | Tygodniowe | Średni |
| Rolling 7/30/90d CLV | Wykres wieloliniowy | Po każdym meczu | Wysoki |
| t-statystyka i p-value | Karta numeryczna | Po każdym meczu | Wysoki |

---

## 7. Procedury Kontroli Jakości Danych

### Reguła QC-1: Kompletność

$$\text{Completeness} = \frac{|\{i : CLV_i \neq \text{NULL}\}|}{N_{\text{total}}} \geq 0.95$$

Cel: 95% rekordów zakładów powinno mieć uzupełniony kurs zamknięcia w ciągu 24h od początku meczu.

### Reguła QC-2: Integralność Kursów

$$\forall i: o_{\text{close},i} \in [1.01,\ 50.0]$$

Kursy poza tym zakresem flagowane jako anomalie wymagające manualnej weryfikacji.

### Reguła QC-3: Spójność Czasowa

$$\forall i: t_{\text{close},i} \leq t_{\text{match\_start},i}$$

Kurs zamknięcia musi być pobrany przed rozpoczęciem meczu — po starcie meczu kurs jest nieważny jako benchmark.

---

## 8. Podsumowanie Wymagań Protokołu

| Wymaganie | Specyfikacja |
|---|---|
| Pola rekordu zakładu | 9 pól zgodnie z Definicją 2.1 |
| Baza danych | PostgreSQL, tabela `bets` ze wyliczaną kolumną `clv` |
| Źródło kursu zamknięcia | Pinnacle Sports API (SportId=33 tenis) |
| Czas pobrania zamknięcia | $\leq$ 60s przed startem meczu |
| Metryki kroczące | 7d, 30d, 90d, all-time |
| Test statystyczny | t-test jednostronny, $\alpha = 0.05$ |
| Kompletność danych | ≥ 95% rekordów z CLV |

---

*Dokument opracowany na potrzeby modułu CLV TRACKER systemu betatp.io. Wersja 1.0.0.*
