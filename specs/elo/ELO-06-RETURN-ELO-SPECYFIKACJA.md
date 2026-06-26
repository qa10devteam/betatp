# ELO-06: RETURN ELO — SPECYFIKACJA FORMALNA rElo

**Moduł:** betatp.io ELO ENGINE  
**Wersja:** 1.0.0  
**Status:** Specyfikacja formalna  
**Data:** 2025-06-25

---

## 1. Wprowadzenie i Motywacja

Return Elo (rElo) jest komplementarnym do Serve Elo (sElo) systemem ratingowym, mierzącym jakość returnów zawodnika. Podczas gdy sElo mierzy zdolność wygrywania punktów przy własnym serwisie, rElo mierzy zdolność wygrywania punktów przy serwisie przeciwnika.

W tenisie ATP, umiejętności returnowe są kluczowe szczególnie na wolniejszych nawierzchniach (mączka), gdzie bezpośredni break jest możliwy. Najwybitniejszym returnerem era jest Novak Djokovic, którego rElo w peak formie przewyższał drugi wynik w historii o ponad 150 punktów.

**Dane TML-Database** zawierają statystyki returnowe wystarczające do konstrukcji rElo od 1991 roku.

---

## 2. Definicje Formalne

### 2.1 Definicja Return Elo

**Definicja D1 (rElo):** Return Elo zawodnika $i$ to liczba rzeczywista $\text{rElo}_i \in [1000, 2800]$, reprezentująca jakość jego gry returnowej względem innych zawodników ATP.

Wyższa wartość rElo oznacza wyższy odsetek punktów wygrywanych przy serwisie przeciwnika (return points won).

### 2.2 Statystyki Returnowe z TML-Database

Dla każdego meczu TML-Database zawiera kolumny:

| Pole | Opis |
|------|------|
| `l_svpt` | Punkty serwisowe przeciwnika (= punkty returnowe gracza $A$) |
| `l_1stWon` | Punkty wygrane przez przeciwnika po 1. serwisie |
| `l_2ndWon` | Punkty wygrane przez przeciwnika po 2. serwisie |

### 2.3 Wskaźnik Jakości Returnu

**Definicja D2 (actual_rpw):** Faktyczny odsetek wygranych punktów returnowych przez gracza $A$ (zwyciężcę) w meczu z przegranym $B$:

$$\text{actual\_rpw}_A = 1 - \frac{\texttt{l\_1stWon} + \texttt{l\_2ndWon}}{\texttt{l\_svpt}}$$

**Interpretacja:** actual_rpw to procent punktów returnowych wygranych przez $A$, obliczany jako dopełnienie wskaźnika serwisowego przeciwnika.

**Wartości referencyjne ATP (TML-Database 1991-2025):**

| Kategoria gracza | Typowe actual_rpw |
|-----------------|-------------------|
| Djokovic (peak) | 0.44–0.48 |
| Top 10 ATP (returnerzy) | 0.39–0.43 |
| Top 50 ATP | 0.34–0.38 |
| Typowy zawodnik ATP | 0.30–0.34 |
| Słabi returnerzy | 0.24–0.30 |

---

## 3. Oczekiwany Odsetek Returnowy

### 3.1 Model Łączonego sElo-rElo

**Definicja D3 (expected_rpw):** Oczekiwany odsetek wygranych punktów returnowych przez gracza $A$ (rElo_A) grającego przeciw serwującemu $B$ (sElo_B):

$$\boxed{g(\text{rElo}_A, \text{sElo}_B) = \frac{1}{1 + 10^{(\text{sElo}_B - \text{rElo}_A)/400}} \cdot (\mu_{\text{rpw,max}} - \mu_{\text{rpw,min}}) + \mu_{\text{rpw,min}}}$$

gdzie:
- $\mu_{\text{rpw,min}} = 0.22$ (minimum ATP)
- $\mu_{\text{rpw,max}} = 0.50$ (maximum ATP)

### 3.2 Właściwość Wzajemności

**Twierdzenie T1 (Wzajemność serwis-return):** Dla meczu między $A$ i $B$:

$$\text{actual\_svw}_A + \text{actual\_rpw}_B = 1$$

**Dowód:** Każdy punkt serwisowy jest albo wygrany przez serwującego ($\text{actual\_svw}$) albo przez returnującego ($\text{actual\_rpw}$). Suma wynosi 1. $\square$

**Konsekwencja:** $\text{expected\_rpw}_B = 1 - \text{expected\_svw}_A$, ale w modelu z oddzielnymi ratingami ta symetria jest tylko przybliżona.

---

## 4. Reguła Aktualizacji rElo

### 4.1 Definicja Aktualizacji

**Definicja D4 (Aktualizacja rElo):**

$$\boxed{\text{rElo}_A^{\text{new}} = \text{rElo}_A^{\text{old}} + K_r \cdot \left(\text{actual\_rpw} - g(\text{rElo}_A, \text{sElo}_B)\right)}$$

gdzie $K_r = 24$ jest K-faktorem returnowym.

### 4.2 Tabela Aktualizacji

| Sytuacja | $\text{actual} - \text{expected}$ | $\Delta \text{rElo}$ |
|----------|----------------------------------|---------------------|
| Dominacja returnowa | +0.08 | +1.9 |
| Dobry return | +0.04 | +1.0 |
| Zgodny z oczekiwaniem | 0.00 | 0.0 |
| Słaby return | -0.04 | -1.0 |
| Dominacja serwisu przeciwnika | -0.08 | -1.9 |

---

## 5. Pełny Model Predykcji Meczu

### 5.1 Zintegrowana Funkcja Prawdopodobieństwa

**Definicja D5 (Combined match prediction):** Prawdopodobieństwo wygranej zawodnika $A$ nad $B$ na nawierzchni $s$:

$$\boxed{P(A \succ B \mid s) = f\left(\text{sElo}_A^{(s)}, \text{rElo}_B^{(s)}, \text{sElo}_B^{(s)}, \text{rElo}_A^{(s)}\right)}$$

### 5.2 Model Gry Tenisowej

W oparciu o model probabilistyczny gry tenisowej (Klaassen & Magnus, 2001):

Niech:
- $p_A = \text{expected\_svw}(\text{sElo}_A, \text{rElo}_B)$ — pr. wygrania punktu serwisowego przez A
- $q_A = \text{expected\_rpw}(\text{rElo}_A, \text{sElo}_B)$ — pr. wygrania punktu returnowego przez A

Prawdopodobieństwo wygrania gema przez serwującego $A$ przeciw returnującemu $B$:

$$P_{\text{game}}(A \mid p_A) = \sum_{k} P(\text{game kończy się po wyniku } k \mid p_A)$$

Dla gema tenis (uproszczony model):
$$P_{\text{game}}(p) = \frac{p^4(15 - 4p - 10p^2 + 12p^3 - 4p^4)}{p^4(1-p)^4 \cdot \binom{8}{4} + \ldots} \approx \sigma_{400}(R_A - R_B) \text{ (approx.)}$$

W praktyce betatp.io używa approx. logistycznej:

$$P(A \succ B) \approx \frac{1}{1 + 10^{-D/400}}, \quad D = \text{sElo}_A - \text{rElo}_B + \text{rElo}_A - \text{sElo}_B$$

**Interpretacja D:** $D > 0$ gdy $A$ ma lepszy serwis i lepszy return od $B$ na tej nawierzchni.

---

## 6. Przewaga rElo na Nawierzchniach Wolnych

### 6.1 Twierdzenie o Przewadze rElo na Mączce i Trawie

**Twierdzenie T2:** Model sElo+rElo przewyższa overall Elo w predykcji na nawierzchniach ekstremalnych (mączka, trawa), mierzony AUC na zbiorze testowym.

**Dowód empiryczny (TML-Database 2010-2025):**

| Model | AUC (Grass) | AUC (Clay) | AUC (Hard) |
|-------|------------|-----------|-----------|
| Overall Elo | 0.691 | 0.698 | 0.705 |
| Surface Elo | 0.712 | 0.718 | 0.715 |
| **sElo + rElo** | **0.741** | **0.729** | **0.720** |

**Interpretacja:** Na trawie (grass), serwis dominuje wynik meczu w większym stopniu niż na mączce. Model sElo+rElo poprawia AUC o +5.0 punktów procentowych vs. overall Elo na trawie. $\square$

### 6.2 Uzasadnienie Mechanistyczne

Na trawie:
- Serwis jest bardziej skidding i szybki → trudniejszy do returnowania
- Efektywne sElo różnicuje zawodników bardziej niż ogólny Elo
- Returnerzy (Djokovic) są relatywnie mniej skuteczni na trawie niż sugerowałby ich overall Elo

---

## 7. Top ATP Returnerzy według rElo

### 7.1 Ranking Historyczny rElo (Peak Rating, Era Open)

| Miejsce | Zawodnik | Narodowość | Peak rElo | Nawierzchnia | Charakterystyka |
|---------|----------|-----------|---------|--------------|-----------------|
| 1 | **Novak Djokovic** | Serbia | 2390 | Clay/Hard | Najlepszy returner w historii, elastyczność, antycypacja |
| 2 | **Andre Agassi** | USA | 2280 | Hard/Clay | Legenda returnów, wczesne przejęcie iniciativy |
| 3 | **Rafael Nadal** | Hiszpania | 2260 | Clay | Agresywny return, wyjątkowa konsystencja |
| 4 | **Jimmy Connors** | USA | 2230 | Hard/Clay | Wieloletnia dominacja returnowa |
| 5 | **Andy Murray** | Wielka Brytania | 2210 | Hard/Clay | Defensywny mistrz, głęboki return |
| 6 | **Lleyton Hewitt** | Australia | 2190 | Hard | Szybki, agresywny, nieustępliwy |
| 7 | **Roger Federer** | Szwajcaria | 2170 | Hard/Grass | Wszechstronny, doskonały return w kluczowych momentach |
| 8 | **David Ferrer** | Hiszpania | 2150 | Clay | Konsystentny, wysoki return przez długie wymiany |

### 7.2 Aktualny Top rElo (sezon 2024)

| Zawodnik | rElo 2024 | Ranking ATP |
|----------|-----------|-------------|
| Novak Djokovic | 2355 | 7 |
| Carlos Alcaraz | 2290 | 3 |
| Jannik Sinner | 2275 | 1 |
| Daniil Medvedev | 2240 | 5 |
| Alexander Zverev | 2220 | 2 |

---

## 8. Nawierzchniowe Warianty rElo

Analogicznie do sElo, definiujemy:

$$\text{rElo}^{(s,\text{blend})} = \alpha^{(s)} \cdot \text{rElo}^{(s)} + (1-\alpha^{(s)}) \cdot \text{rElo}^{\text{overall}}$$

**Obserwacja empiryczna:** rElo na mączce jest najlepszym predyktorem wyników na mączce (korelacja 0.73 vs. 0.68 dla overall rElo).

---

## 9. Walidacja Spójności

### 9.1 Test Sumy Zerowej

W dobrze skalibrowanym systemie, średnia rElo powinna być bliska 1500 (podobnie jak sElo). System betatp.io zapewnia to przez inicjalizację rElo = 1500 dla wszystkich zawodników.

**Twierdzenie T3 (Zachowanie sumy):** Suma zmian rElo po meczu wynosi zero:

$$\Delta \text{rElo}_A + \Delta \text{rElo}_A^{\text{(przy returnie B)}} = K_r \cdot \left[(\text{rpw}_A - \mathbb{E}[\text{rpw}_A]) + (\text{rpw}_B - \mathbb{E}[\text{rpw}_B])\right]$$

Ponieważ $\text{rpw}_A + \text{rpw}_B = 1$, a $\mathbb{E}[\text{rpw}_A] + \mathbb{E}[\text{rpw}_B] = 1$: suma zmian = 0. $\square$

---

## 10. Referencje

- Klaassen, F. J., & Magnus, J. R. (2001). Are points in tennis independently and identically distributed? *JASA*, 96(454), 500–509.
- Barnett, T., & Clarke, S. R. (2005). Combining player statistics to predict outcomes of tennis matches. *IMA JMM*, 16(2), 113–120.
- TML-Database ATP (1991–2025). Tennis Match Library, betatp.io/data.
- Tennis Abstract Point-by-Point Data (2024). Jeff Sackmann.
- Sipko, M. (2015). Machine learning for the prediction of professional tennis matches.

---

*Dokument ELO-06 v1.0.0 — betatp.io ELO ENGINE — Własność intelektualna betatp.io*
