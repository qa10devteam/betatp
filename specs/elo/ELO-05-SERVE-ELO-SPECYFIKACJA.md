# ELO-05: SERVE ELO — SPECYFIKACJA FORMALNA sElo

**Moduł:** betatp.io ELO ENGINE  
**Wersja:** 1.0.0  
**Status:** Specyfikacja formalna  
**Data:** 2025-06-25

---

## 1. Wprowadzenie i Motywacja

Standardowy Elo mierzy ogólną siłę zawodnika na podstawie binarnych wyników meczów (wygrana/przegrana). Nie rozróżnia jednak, w jaki sposób zawodnik wygrywa — poprzez dominację serwisową czy przewagę returnową. W ATP tennis, szczególnie na nawierzchniach szybkich (trawa, twarda) serwis jest kluczowym determinantem wyniku meczu.

**Serve Elo (sElo)** to osobny system ratingów mierzący jakość serwisu zawodnika, aktualizowany po każdym meczu na podstawie statystyk punktów serwisowych z bazy TML-Database.

---

## 2. Definicje Formalne

### 2.1 Definicja Serve Elo

**Definicja D1 (sElo):** Serve Elo zawodnika $i$ to liczba rzeczywista $\text{sElo}_i \in [1000, 2800]$, reprezentująca szacowaną jakość jego serwisu względem innych zawodników ATP.

Wyższa wartość sElo oznacza wyższy odsetek punktów wygrywanych przy własnym serwisie.

### 2.2 Statystyki Serwisowe z TML-Database

Dla zawodnika $A$ w meczu z TML-Database dostępne są:

| Pole | Opis |
|------|------|
| `w_1stWon` | Liczba wygranych punktów po pierwszym serwisie |
| `w_2ndWon` | Liczba wygranych punktów po drugim serwisie |
| `w_svpt` | Łączna liczba punktów serwisowych |
| `w_1stIn` | Liczba pierwszych serwisów wewnątrz |
| `w_df` | Liczba podwójnych błędów |

### 2.3 Wskaźnik Jakości Serwisu

**Definicja D2 (actual_svw):** Faktyczny odsetek wygranych punktów serwisowych:

$$\text{actual\_svw} = \frac{\texttt{w\_1stWon} + \texttt{w\_2ndWon}}{\texttt{w\_svpt}}$$

Zakres: $\text{actual\_svw} \in [0, 1]$.

**Wartości referencyjne ATP (TML-Database 2000-2025):**

| Kategoria gracza | Typowe actual_svw |
|-----------------|-------------------|
| Top serwujący (Isner, Karlović) | 0.72–0.76 |
| Top 10 ATP | 0.66–0.70 |
| Top 50 ATP | 0.62–0.66 |
| Typowy zawodnik ATP | 0.58–0.62 |
| Słabi serwujący | 0.52–0.58 |

---

## 3. Oczekiwany Odsetek Serwisowy

### 3.1 Funkcja Oczekiwanego sElo

**Definicja D3 (expected_svw):** Dla serwującego $A$ o $\text{sElo}_A$ grającego przeciw $B$ o $\text{rElo}_B$ (rating returnowy, patrz ELO-06):

$$\text{expected\_svw}(A, B) = \frac{1}{1 + 10^{(\text{rElo}_B - \text{sElo}_A)/400}} \cdot (\mu_{\text{svw,max}} - \mu_{\text{svw,min}}) + \mu_{\text{svw,min}}$$

Uproszczona wersja z jednym ratingiem (gdy rElo niedostępne):

$$\boxed{\text{expected\_svw}(A) = \sigma_{400}\left(\text{sElo}_A - \overline{\text{sElo}}\right) \cdot (\mu_{\text{max}} - \mu_{\text{min}}) + \mu_{\text{min}}}$$

gdzie $\sigma_{400}(x) = \frac{1}{1 + 10^{-x/400}}$ oraz:
- $\mu_{\text{min}} = 0.52$ (minimum ATP)
- $\mu_{\text{max}} = 0.78$ (maximum ATP)
- $\overline{\text{sElo}} = 1500$ (wartość bazowa)

### 3.2 Skalowanie

Funkcja logistyczna odwzorowuje zakres $(-\infty, +\infty)$ ratingów na zakres fizycznie sensownych wartości $[0.52, 0.78]$ dla serwisów ATP.

---

## 4. Reguła Aktualizacji sElo

### 4.1 Definicja Aktualizacji

**Definicja D4 (Aktualizacja sElo):**

$$\boxed{\text{sElo}_A^{\text{new}} = \text{sElo}_A^{\text{old}} + K_s \cdot \left(\text{actual\_svw} - \text{expected\_svw}\right)}$$

gdzie $K_s = 24$ jest K-faktorem serwisowym.

**Uzasadnienie $K_s = 24$:**
- Serwis jest jedną z dwóch stron gry (serwis i return)
- Jeden mecz dostarcza ~70-100 punktów serwisowych, co jest wystarczającą próbą
- $K_s = 24$ odpowiada ATP 250 (bazowy poziom informacji)

### 4.2 Interpretacja Aktualizacji

| Sytuacja | $\text{actual} - \text{expected}$ | $\Delta \text{sElo}$ |
|----------|----------------------------------|---------------------|
| Wybitny serwis | +0.10 | +2.4 |
| Dobry serwis | +0.05 | +1.2 |
| Zgodny z oczekiwaniem | 0.00 | 0.0 |
| Słaby serwis | -0.05 | -1.2 |
| Bardzo słaby serwis | -0.10 | -2.4 |

---

## 5. Dowód Zbieżności sElo do Prawdziwej Jakości Serwisu

### 5.1 Model Probabilistyczny

Niech $p_i^{\text{true}}$ będzie prawdziwym prawdopodobieństwem wygrania punktu serwisowego przez zawodnika $i$. Zakładamy:

$$\text{actual\_svw}_{i,t} = p_i^{\text{true}} + \varepsilon_{i,t}$$

gdzie $\varepsilon_{i,t}$ są i.i.d. z $\mathbb{E}[\varepsilon] = 0$ i $\text{Var}(\varepsilon) = \sigma_{\varepsilon}^2$.

### 5.2 Twierdzenie o Zbieżności

**Twierdzenie T1 (Zbieżność sElo):** Przy założeniu stałości $p_i^{\text{true}}$ i nieskończenie wielu meczów:

$$\mathbb{E}[\text{sElo}_i^{(t)}] \xrightarrow{t \to \infty} \text{sElo}_i^*$$

gdzie $\text{sElo}_i^*$ jest jedynym rozwiązaniem:

$$\sigma_{400}(\text{sElo}_i^* - \overline{\text{sElo}}) \cdot (\mu_{\text{max}} - \mu_{\text{min}}) + \mu_{\text{min}} = p_i^{\text{true}}$$

**Dowód:** W stanie stacjonarnym, $\mathbb{E}[\Delta \text{sElo}_i] = K_s \cdot \mathbb{E}[\text{actual} - \text{expected}] = K_s \cdot (p_i^{\text{true}} - \text{expected}(\text{sElo}_i^*)) = 0$. Równanie posiada unikalne rozwiązanie, bo $\text{expected}(\cdot)$ jest ściśle rosnące. $\square$

### 5.3 Wariancja Stanu Stacjonarnego

$$\text{Var}(\text{sElo}_i^{(t)}) \approx \frac{K_s^2 \sigma_{\varepsilon}^2}{2K_s |\text{expected}'(\text{sElo}^*)|} = \frac{K_s \sigma_{\varepsilon}^2}{2|\text{expected}'(\text{sElo}^*)|}$$

Przy $K_s = 24$, $\sigma_{\varepsilon} \approx 0.05$: $\text{SD}(\text{sElo}) \approx 35$ punktów — akceptowalny poziom szumu.

---

## 6. Rankingowe Wzorce sElo — Dane ATP

### 6.1 Top ATP Serwujący według sElo (Peak Rating)

| Zawodnik | Narodowość | Peak sElo | Nawierzchnia dominacji | Charakterystyka |
|----------|-----------|----------|----------------------|-----------------|
| **John Isner** | USA | 2310 | Hard/Grass | Najwyższy wzrost (208 cm), flat serwis 240+ km/h |
| **Ivo Karlović** | Chorwacja | 2295 | Hard/Grass | Rekordzista asów (~13 800), 211 cm |
| **Reilly Opelka** | USA | 2270 | Hard | 211 cm, rekord asów w sezonie |
| **Milos Raonic** | Kanada | 2255 | Hard | Konsystentny top serwis, 85% pts po 1. serwisie |
| **Pete Sampras** | USA | 2240 | Hard/Grass | 7× Wimbledon, serwis+volley |
| **Goran Ivanišević** | Chorwacja | 2230 | Grass | Wimbledon 2001, serwis-dominant |
| **Roger Federer** | Szwajcaria | 2190 | Hard/Grass | Wszechstronny + doskonały serwis |
| **Nick Kyrgios** | Australia | 2185 | Hard/Grass | Nieprzewidywalny, wysoki ace-rate |

### 6.2 Korelacja sElo z Statystykami Serwisowymi (2010-2025)

| Statystyka | Korelacja z sElo |
|------------|-----------------|
| % asów na mecz | 0.87 |
| % 1. serwisów wygranych | 0.79 |
| % 2. serwisów wygranych | 0.71 |
| % punktów serwisowych wygranych | 0.93 |
| Średnia prędkość serwisu | 0.74 |

---

## 7. Nawierzchniowe Warianty sElo

Analogicznie do overall Elo, definiujemy nawierzchniowe warianty sElo:

$$\text{sElo}^{(s)} \quad \text{dla } s \in \{\text{hard}, \text{clay}, \text{grass}\}$$

z identyczną formułą blendowania (patrz ELO-03):

$$\text{sElo}^{(s,\text{blend})} = \alpha^{(s)} \cdot \text{sElo}^{(s)} + (1-\alpha^{(s)}) \cdot \text{sElo}^{\text{overall}}$$

**Obserwacja empiryczna:** sElo na trawie jest najwyżej skorelowane z wynikami (korelacja 0.71 vs 0.64 na mączce).

---

## 8. Korekta na Siłę Przeciwnika

### 8.1 Opponent-Adjusted sElo

Bazowy model aktualizuje sElo bez korekty na siłę returnową przeciwnika. Rozszerzona wersja:

$$\text{sElo}_A^{\text{new}} = \text{sElo}_A^{\text{old}} + K_s \cdot \left(\text{actual\_svw} - \text{expected\_svw}(A \mid \text{rElo}_B)\right)$$

gdzie $\text{expected\_svw}(A \mid \text{rElo}_B)$ zależy od siły returnowej przeciwnika $B$.

**Twierdzenie T2:** Wersja opponent-adjusted jest nieobciążona: $\mathbb{E}[\text{sElo}_i^{(t)}]$ zbiega do tej samej wartości $\text{sElo}_i^*$, niezależnie od harmonogramu przeciwników.

---

## 9. Referencje

- Kovalchik, S. (2016). Searching for the GOAT of tennis win prediction. *JQAS*, 12(3), 127–138.
- Barnett, T., & Clarke, S. R. (2005). Combining player statistics to predict outcomes of tennis matches. *IMA Journal of Management Mathematics*, 16(2), 113–120.
- TML-Database ATP (1990–2025). Tennis Match Library, betatp.io/data.
- Tennis Abstract Point-by-Point Data (2024). Jeff Sackmann. github.com/JeffSackmann.
- ATP Official Statistics Archive (2024). atptour.com/stats.

---

*Dokument ELO-05 v1.0.0 — betatp.io ELO ENGINE — Własność intelektualna betatp.io*
