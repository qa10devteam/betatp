# ADV-08: Specyfikacja Potoku Danych ETL — TML-Database do Silnika Elo

**Moduł:** `data_pipeline`  
**Wersja:** 2.3.0  
**Status:** Zatwierdzony  
**Data:** 2025-06-25  
**Autor:** betatp.io — Zespół Inżynierii Danych

---

## 1. Cel i Zakres

Dokument definiuje kompletną specyfikację potoku ETL (Extract, Transform, Load) przetwarzającego surowe dane tenisowe z bazy TML-Database (Jeff Sackmann) do systemu obliczania ratingu Elo betatp.io. Specyfikacja obejmuje wszystkie etapy: ingestion CSV, kontrolę jakości danych, standaryzację nazw graczy, obliczenie cech statystycznych, sekwencyjne obliczenie Elo i zapis do PostgreSQL.

---

## 2. Źródło Danych: TML-Database

### 2.1 Struktura Źródłowa

**Lokalizacja:** `/home/ubuntu/TML-Database/*.csv`

**Format plików:** Jeden plik CSV per rok sezonu ATP, np.:
- `atp_matches_2024.csv` — mecze 2024
- `atp_matches_2023.csv` — mecze 2023
- ...
- `atp_matches_1968.csv` — mecze 1968 (dane historyczne Open Era)

**Kluczowa właściwość — `player_id` jako Primary Key:**

**Aksjomat 2.1:** TML-Database używa stałego, spójnego `player_id` (integer) jako identyfikatora gracza across wszystkich plików i lat. Ten sam gracz ma ten sam `player_id` w pliku 2010 i 2024. betatp używa `player_id` jako primary key we wszystkich operacjach.

**Przykładowe kolumny CSV:**

```
tourney_id, tourney_name, surface, draw_size, tourney_level, tourney_date,
match_num, winner_id, winner_seed, winner_entry, winner_name, winner_hand,
winner_ht, winner_ioc, winner_age, loser_id, loser_seed, loser_entry,
loser_name, loser_hand, loser_ht, loser_ioc, loser_age, score, best_of,
round, minutes, w_ace, w_df, w_svpt, w_1stIn, w_1stWon, w_2ndWon,
w_SvGms, w_bpSaved, w_bpFaced, l_ace, l_df, l_svpt, l_1stIn, l_1stWon,
l_2ndWon, l_SvGms, l_bpSaved, l_bpFaced
```

---

## 3. Architektura Potoku ETL

### 3.1 Diagram Przepływu

```
/home/ubuntu/TML-Database/*.csv
         │
         ▼ [Krok 1: Ingestion]
    Raw DataFrame
         │
         ▼ [Krok 2: Quality Checks]
    Cleaned DataFrame
         │
         ▼ [Krok 3: Standaryzacja]
    Normalized DataFrame (player_id primary key)
         │
         ▼ [Krok 4: Feature Computation]
    Feature-Enriched DataFrame
         │
         ▼ [Krok 5: Elo Computation]
    Elo-Rated DataFrame (chronological)
         │
         ▼ [Krok 6: PostgreSQL Load]
    Tabele: matches, players, elo_history, features
```

---

## 4. Krok 1: Ingestion CSV

### 4.1 Specyfikacja Ingestion

```python
# Pseudokod ingestion
def ingest_all_csvs(base_path: str = "/home/ubuntu/TML-Database") -> pd.DataFrame:
    """
    Wczytuje wszystkie pliki atp_matches_*.csv i łączy w jeden DataFrame.
    Zachowuje chronologię przez sortowanie po tourney_date + match_num.
    """
    dfs = []
    for year in range(1968, CURRENT_YEAR + 1):
        path = f"{base_path}/atp_matches_{year}.csv"
        if os.path.exists(path):
            df = pd.read_csv(path, dtype={'winner_id': int, 'loser_id': int})
            df['year'] = year
            dfs.append(df)
    
    combined = pd.concat(dfs, ignore_index=True)
    combined['tourney_date'] = pd.to_datetime(combined['tourney_date'], format='%Y%m%d')
    combined = combined.sort_values(['tourney_date', 'match_num']).reset_index(drop=True)
    return combined
```

**Wymaganie:** Kolumny `winner_id` i `loser_id` są wczytywane jako `int` (nie `float`) aby zapobiec NaN-coercion.

---

## 5. Krok 2: Kontrola Jakości Danych

### 5.1 Formalne Reguły Jakości

**Definicja 5.1 (Reguły Jakości Danych):** Każdy rekord meczu musi przejść następujące walidacje:

#### 5.1.1 Reguły Obowiązkowe (Hard Rules — odrzucenie rekordu)

| Reguła | Warunek | Akcja przy naruszeniu |
|---|---|---|
| R01 | `winner_id IS NOT NULL AND loser_id IS NOT NULL` | Odrzuć rekord |
| R02 | `winner_id != loser_id` | Odrzuć (niemożliwy mecz) |
| R03 | `tourney_date IS NOT NULL` | Odrzuć rekord |
| R04 | `score IS NOT NULL AND score != 'W/O'` | Odrzuć (walkower) |
| R05 | `best_of IN (3, 5)` | Odrzuć (nieznany format) |

#### 5.1.2 Reguły Statystyk Serwisu (Soft Rules — flaga + zachowanie)

| Pole | Reguła | Zakres Dozwolony | Akcja przy naruszeniu |
|---|---|---|---|
| `serve_win_pct` | $\in [0.30, 0.95]$ | 30%–95% | Flaga: `quality_flag=1`, nie odrzucaj |
| `ace_pct` | $\in [0.00, 0.30]$ | 0%–30% | Flaga: `quality_flag=1` |
| `df_pct` | $\in [0.00, 0.15]$ | 0%–15% | Flaga: `quality_flag=1` |
| `first_serve_in_pct` | $\in [0.40, 0.90]$ | 40%–90% | Flaga: `quality_flag=1` |
| `bp_conversion_pct` | $\in [0.00, 0.80]$ | 0%–80% | Flaga: `quality_flag=1` |
| `minutes` | $\in [20, 400]$ | 20–400 minut | Flaga: `quality_flag=1` |

**Obliczanie pochodnych statystyk:**

$$\text{serve\_win\_pct} = \frac{w\_1stWon + w\_2ndWon}{w\_svpt}$$

$$\text{ace\_pct} = \frac{w\_ace}{w\_svpt}$$

$$\text{first\_serve\_in\_pct} = \frac{w\_1stIn}{w\_svpt}$$

**Definicja 5.2 (Statystyki niemożliwe):** Jeśli `serve_win_pct > 0.95`, to rekord sugeruje błąd w danych (wynik 0:6 0:6 przy 95% skuteczności serwisu jest niemożliwy). Taki rekord jest flagowany.

### 5.2 Raportowanie Jakości

```
Raport kontroli jakości (przykładowe dane dla roku 2024):
- Wczytano rekordów: 2,847
- Odrzucono (Hard Rules): 12 (0.4%)
  - R04 (walkower): 8
  - R01/R02 (brak ID): 4
- Flagowano (Soft Rules): 23 (0.8%)
  - serve_win_pct outlier: 11
  - minutes outlier: 9
  - ace_pct outlier: 3
- Rekordy do dalszego przetwarzania: 2,835 (99.6%)
```

---

## 6. Krok 3: Standaryzacja i Normalizacja Nazw Graczy

### 6.1 Polityka Identyfikatorów

**Aksjomat 6.1:** `player_id` z TML-Database jest **kanonicznym identyfikatorem gracza** w całym systemie betatp. Żaden inny klucz nie jest używany jako primary key.

**Dlaczego nie `player_name`?** Baza TML-Database historycznie zawiera różne zapisy tego samego gracza:
- `"Djokovic N."` vs `"N. Djokovic"` vs `"Novak Djokovic"`
- `"Del Potro J.M."` vs `"Juan Martin Del Potro"`
- Diakrytyki: `"Berdych T."` vs `"Tomáš Berdych"`

**Rozwiązanie:** Wszystkie operacje JOIN używają `player_id`, nigdy `player_name`.

### 6.2 Tabela Słownikowa Graczy

Podczas ingestion budujemy tabelę `players` z unikalnym mapowaniem:

```sql
-- Tabela players (budowana z danych TML-Database)
CREATE TABLE players (
    player_id     INTEGER PRIMARY KEY,  -- TML-Database player_id
    canonical_name VARCHAR(100) NOT NULL, -- Najnowsza wersja nazwy
    first_name    VARCHAR(50),
    last_name     VARCHAR(50),
    hand          CHAR(1),               -- R/L/U
    dob           DATE,
    ioc           CHAR(3),               -- Kod kraju IOC
    height_cm     INTEGER,
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);
```

---

## 7. Krok 4: Obliczanie Cech (Feature Computation)

### 7.1 Cechy Obliczane per Mecz

Dla każdego meczu obliczamy krocząco (rolling windows) statystyki gracza:

| Cecha | Formuła | Okno | Zastosowanie |
|---|---|---|---|
| `serve_win_pct_30d` | śr. ważona serve_win_pct | 30 dni | Feature ML |
| `return_win_pct_30d` | śr. ważona return_win_pct | 30 dni | Feature ML |
| `ace_pct_90d` | śr. ważona ace_pct | 90 dni | Feature ML |
| `win_rate_surface_1y` | (wygrane na nawierzchni) / (mecze na nawierzchni) | 365 dni | Feature ML |
| `fatigue_score` | $\sum_{t-14}^{t} 1/2^{(t-\tau)/7}$ | 14 dni | Feature ML |

### 7.2 Sekwencja Obliczeniowa

**Kluczowe wymaganie:** Cechy muszą być obliczane **tylko z danych przeszłych** (no data leakage):

```python
# Przykład obliczenia cechy bez data leakage
def compute_rolling_feature(df: pd.DataFrame, player_id: int, feature_col: str, 
                             days: int, as_of_date: pd.Timestamp) -> float:
    """
    Oblicza krocząco cechę gracza z danych PRZED as_of_date.
    """
    mask = (
        ((df['winner_id'] == player_id) | (df['loser_id'] == player_id)) &
        (df['tourney_date'] < as_of_date) &
        (df['tourney_date'] >= as_of_date - pd.Timedelta(days=days))
    )
    return df[mask][feature_col].mean()
```

---

## 8. Krok 5: Sekwencyjne Obliczenie Elo

### 8.1 Specyfikacja Obliczeń Elo

**Wymaganie kluczowe:** Elo obliczany jest **w porządku chronologicznym**, mecz po meczu. Inicjalizacja:

```python
elo_ratings = defaultdict(lambda: 1500.0)  # Domyślny rating dla nowego gracza
```

**Aktualizacja per mecz:**

$$r_W' = r_W + K \cdot (1 - E_W), \qquad r_L' = r_L + K \cdot (0 - E_L)$$

$$E_W = \frac{1}{1 + 10^{(r_L - r_W)/400}}, \qquad K = 32$$

### 8.2 Historia Elo (elo_history)

Każda aktualizacja Elo jest zapisywana do tabeli `elo_history`:

```sql
CREATE TABLE elo_history (
    id              BIGSERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    match_id        BIGINT NOT NULL REFERENCES matches(id),
    rating_before   FLOAT NOT NULL,
    rating_after    FLOAT NOT NULL,
    rating_date     DATE NOT NULL,
    surface         VARCHAR(10),
    elo_type        VARCHAR(20) NOT NULL,  -- 'overall'|'hard'|'clay'|'grass'
    created_at      TIMESTAMP DEFAULT NOW(),
    INDEX idx_elo_player_date (player_id, rating_date),
    INDEX idx_elo_type (elo_type, rating_date)
);
```

---

## 9. Krok 6: Schemat PostgreSQL

### 9.1 Tabela `matches`

```sql
CREATE TABLE matches (
    id              BIGSERIAL PRIMARY KEY,
    tourney_id      VARCHAR(20),
    tourney_name    VARCHAR(100),
    surface         VARCHAR(10),
    tourney_level   CHAR(1),           -- G/M/A/C/D/F
    tourney_date    DATE NOT NULL,
    round           VARCHAR(5),
    best_of         SMALLINT,
    winner_id       INTEGER NOT NULL REFERENCES players(player_id),
    loser_id        INTEGER NOT NULL REFERENCES players(player_id),
    score           VARCHAR(50),
    minutes         SMALLINT,
    quality_flag    SMALLINT DEFAULT 0, -- 0=OK, 1=flagged
    source_year     SMALLINT,
    created_at      TIMESTAMP DEFAULT NOW(),
    INDEX idx_match_date (tourney_date),
    INDEX idx_match_winner (winner_id),
    INDEX idx_match_loser (loser_id)
);
```

### 9.2 Tabela `features`

```sql
CREATE TABLE features (
    id                      BIGSERIAL PRIMARY KEY,
    match_id                BIGINT NOT NULL REFERENCES matches(id),
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    role                    CHAR(1) NOT NULL,   -- 'W' lub 'L'
    -- Statystyki per mecz
    serve_win_pct           FLOAT,
    return_win_pct          FLOAT,
    ace_pct                 FLOAT,
    df_pct                  FLOAT,
    first_serve_in_pct      FLOAT,
    bp_conversion_pct       FLOAT,
    -- Cechy krocząco obliczone
    serve_win_pct_30d       FLOAT,
    return_win_pct_30d      FLOAT,
    win_rate_surface_1y     FLOAT,
    fatigue_score           FLOAT,
    elo_before_match        FLOAT,
    elo_surface_before      FLOAT,
    age_at_match            FLOAT,
    career_arc_factor       FLOAT,
    created_at              TIMESTAMP DEFAULT NOW(),
    INDEX idx_features_match (match_id),
    INDEX idx_features_player (player_id)
);
```

---

## 10. Specyfikacja Wydajnościowa

| Etap | Czas przetwarzania (pełna historia 1968–2025) | Czas inkrementalny (1 rok) |
|---|---|---|
| Ingestion CSV | ~45 s | ~2 s |
| Quality Checks | ~12 s | <1 s |
| Feature Computation | ~8 min | ~15 s |
| Elo Computation | ~3 min | ~8 s |
| PostgreSQL Load | ~6 min | ~20 s |
| **Łącznie** | **~18 min** | **~47 s** |

*Sprzęt referencyjny: AWS t3.xlarge, PostgreSQL 15, SSD storage.*

---

## Referencje

1. Sackmann, J. (2014–2025). *TML-Database: ATP Tennis Match Data*. GitHub: https://github.com/JeffSackmann/tennis_atp  
2. PostgreSQL Documentation 15: https://www.postgresql.org/docs/15/  
3. pandas Documentation: https://pandas.pydata.org/docs/  
4. Kimball, R., Ross, M. (2013). *The Data Warehouse Toolkit* (3rd ed.). Wiley.  
5. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media.
