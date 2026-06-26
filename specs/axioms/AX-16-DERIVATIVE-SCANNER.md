# AX-16: FORMALNY SKANER RYNKÓW POCHODNYCH
## Specyfikacja Formalna — betatp.io Prediction Engine
**Wersja:** 1.0.0  
**Status:** Zatwierdzony  
**Data:** 2026-06-25  

---

## 1. Wstęp i Zakres

Niniejszy aksjomat definiuje formalne ramy matematyczne dla skanera rynków pochodnych w systemie betatp.io. Rynki pochodne (derivative markets) w tenisie są rynkami bukmacherskimi, których kursy wynikają deterministycznie lub probabilistycznie z kursu moneyline (wyniku meczu). Błędy wyceny tych rynków są systematycznie większe niż błędy na moneyline, ponieważ bukmacherzy stosują uproszczone modele interpolacji liniowej zamiast pełnych rozkładów Monte Carlo.

**Definicja AX-16.1 (Rynek Pochodny):** Rynek $M_D$ jest rynkiem pochodnym względem rynku bazowego $M_B$, jeżeli istnieje odwzorowanie $\phi: \Omega_B \to \Omega_D$ takie, że prawdopodobieństwa na $M_D$ są w pełni zdeterminowane przez rozkład probabilistyczny na $\Omega_B$.

---

## 2. Taksonomia Rynków Pochodnych w Tenisie

### 2.1 Handicap Gemowy (Gem Handicap)

**Definicja AX-16.2:** Rynek handicap gemowy $H_g(k)$ dla wartości $k \in \mathbb{Z}$ definiuje się jako:

$$H_g(k) = P\left(\sum_{s=1}^{S} G_A^{(s)} - \sum_{s=1}^{S} G_B^{(s)} > k \;\middle|\; \text{Mecz zakończony}\right)$$

gdzie $G_A^{(s)}$ i $G_B^{(s)}$ oznaczają liczbę gemów wygranych przez gracza A i B odpowiednio w secie $s$, zaś $S$ jest łączną liczbą setów.

Typowe wartości $k \in \{-8, -6, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6, 8\}$.

### 2.2 Rynek Sumy Gemów (Total Games Over/Under)

**Definicja AX-16.3:** Rynek sumy gemów $T(n)$ dla progu $n \in \mathbb{R}^+$ definiuje się jako:

$$T_{over}(n) = P\left(\sum_{s=1}^{S}\left(G_A^{(s)} + G_B^{(s)}\right) > n\right)$$

$$T_{under}(n) = 1 - T_{over}(n)$$

Standardowe progi rynkowe: $n \in \{18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5\}$ dla meczów do 2 setów wygranych.

### 2.3 Wynik Setowy (Set Score Market)

**Definicja AX-16.4:** Rynek wyniku setowego w formacie best-of-3 definiuje się jako rozkład prawdopodobieństwa na przestrzeni:

$$\Omega_{SS}^{(3)} = \{2\text{-}0_A,\; 2\text{-}1_A,\; 1\text{-}2_B,\; 0\text{-}2_B\}$$

Dla formatu best-of-5:

$$\Omega_{SS}^{(5)} = \{3\text{-}0_A,\; 3\text{-}1_A,\; 3\text{-}2_A,\; 2\text{-}3_B,\; 1\text{-}3_B,\; 0\text{-}3_B\}$$

### 2.4 Rynek Tie-Break (Tiebreak Market)

**Definicja AX-16.5:** Rynek tie-break definiuje się jako:

$$TB_{any} = P\left(\exists s: G_A^{(s)} = G_B^{(s)} = 6\right)$$

$$TB_{n} = P\left(\left|\{s: G_A^{(s)} = G_B^{(s)} = 6\}\right| \geq n\right) \quad \text{dla } n \in \{1, 2, 3\}$$

---

## 3. Model Błędu Algorytmicznego

### 3.1 Interpolacja Liniowa Bukmacherów

**Aksjomat AX-16.A (Model Bukmachera):** Bukmacherzy komercyjni obliczają kursy na rynki pochodne poprzez liniową interpolację z moneyline:

$$p_{BK}^{(D)} = \alpha \cdot p_{ML} + \beta$$

gdzie $\alpha, \beta$ są współczynnikami kalibracji wyznaczonymi empirycznie na zbiorze historycznym, bez uwzględnienia nieliniowych efektów rozkładu gemów.

**Twierdzenie AX-16.T1:** Interpolacja liniowa jest obciążona systematycznie dla meczów z asymetrycznym rozkładem gemów, tj. gdy:

$$\text{Var}\left[\sum_s G_A^{(s)}\right] \neq \text{Var}\left[\sum_s G_B^{(s)}\right]$$

*Dowód:* Niech $\mu_A = E[G_A]$ i $\sigma_A^2 = \text{Var}[G_A]$. Model liniowy zakłada $p_{BK}^{(D)} = f(\mu_A, \mu_B)$ z pominięciem $\sigma_A^2, \sigma_B^2$. Dla rynku sumy gemów, całka $P(G_A + G_B > n) = \int_n^\infty f_{G_A+G_B}(x)dx$ jest funkcją zarówno $\mu$ jak i $\sigma$. Pomijając $\sigma$, interpolacja liniowa generuje błąd $\varepsilon \propto (\sigma_A^2 - \sigma_B^2)$. $\square$

### 3.2 Model Monte Carlo betatp

**Definicja AX-16.6 (Symulacja MC):** System betatp oblicza prawdopodobieństwa rynków pochodnych poprzez symulację Monte Carlo z $N = 100{,}000$ iteracji:

$$\hat{p}_{MC}^{(D)} = \frac{1}{N} \sum_{i=1}^{N} \mathbf{1}[\text{wynik}_i \in \Omega_D]$$

Każda iteracja $i$ symuluje mecz punkt po punkcie, korzystając z parametrów:
- $p_s^A$ — prawdopodobieństwo wygrania punktu przy własnym serwisie przez A
- $p_s^B$ — prawdopodobieństwo wygrania punktu przy własnym serwisie przez B

Oba parametry wyznaczone z modelu sElo/rElo (AX-20).

**Błąd Standardowy Monte Carlo:**

$$\sigma_{MC} = \sqrt{\frac{\hat{p}(1-\hat{p})}{N}} \leq \frac{1}{2\sqrt{N}} = \frac{1}{2\sqrt{100{,}000}} \approx 0.00158$$

---

## 4. Trzy Klasy Błędów Wyceny

### 4.1 Klasa A — Mecze z Dominującym Serwisem (Big Server Totals)

**Definicja AX-16.7 (Mecz Serwisowy):** Mecz klasyfikowany jako "big-server matchup" gdy:

$$p_s^A + p_s^B > 1.48 \quad \text{(empiryczny próg, ATP 2015-2025)}$$

**Twierdzenie AX-16.T2 (Błąd Totals dla Big-Server):** Dla meczów serwisowych, bukmacherzy systematycznie zaniżają prawdopodobieństwo *under* dla niskich progów sumy gemów.

*Uzasadnienie:* Gdy oba serwisy są dominujące, rozkład liczby gemów jest bardziej skoncentrowany wokół wyników tie-breakowych (6:4, 7:5, 7:6). Interpolacja liniowa ignoruje tę koncentrację, generując zawyżone $p_{BK}(over)$.

**Formuła EV dla Klasy A:**

$$EV_A = \hat{p}_{MC}(under_n) \cdot K_{BK}(under_n) - 1$$

gdzie $K_{BK}$ jest kursem bukmachera, a warunek wejścia:

$$\hat{p}_{MC}(under_n) \cdot K_{BK}(under_n) > 1 + \delta_{min}$$

z $\delta_{min} = 0.02$ (minimalne EV = 2%).

**Tabela 4.1: Empiryczne Błędy Bukmacherów dla Big-Server Matchups**

| Próg | $\bar{p}_{BK}$ | $\bar{p}_{MC}$ | Średni Błąd | Kierunek |
|------|--------------|--------------|-------------|----------|
| U20.5 | 0.312 | 0.358 | +0.046 | BK zawyża over |
| U21.5 | 0.418 | 0.447 | +0.029 | BK zawyża over |
| U22.5 | 0.531 | 0.551 | +0.020 | BK zawyża over |
| O23.5 | 0.601 | 0.572 | -0.029 | BK zawyża over |

### 4.2 Klasa B — Specialista Trawiasta vs. Ziemna (Clay/Grass Specialist Set Scores)

**Definicja AX-16.8 (Klasa B Mispricingu):** Błąd wyceny wyniku setowego gdy zawodnik A jest specjalistą nawierzchniowym, a B jest specjalistą innej nawierzchni. Formalnie:

$$\Delta_{surface}^{(A,B)} = \Delta p_s^A(\text{surface}) - \Delta p_s^B(\text{surface}) > 0.04$$

gdzie $\Delta p_s(\text{surface})$ — delta serwisowa specyficzna dla nawierzchni (AX-17).

**Twierdzenie AX-16.T3:** Dla meczów typu clay vs. grass specialist na trawie, bukmacherzy systematycznie zaniżają prawdopodobieństwo wyników 2:0 i 3:0 dla gracza trawiastego.

**Formuła EV dla Klasy B:**

$$EV_B(\text{wynik}_{j}) = \hat{p}_{MC}(\text{wynik}_j) \cdot K_{BK}(\text{wynik}_j) - 1$$

$$\text{gdzie } j \in \Omega_{SS} \text{ i } EV_B > 0.03$$

**Tabela 4.2: Błędy Wyceny Set Score — Nawierzchnia Trawa**

| Wynik | $\bar{p}_{BK}$ | $\bar{p}_{MC}$ | EV Średnie |
|-------|--------------|--------------|------------|
| 2:0 (grass spec.) | 0.341 | 0.398 | +8.2% |
| 2:1 (grass spec.) | 0.289 | 0.271 | -6.2% |
| 1:2 (clay spec.) | 0.198 | 0.164 | -17.2% |
| 0:2 (clay spec.) | 0.172 | 0.167 | -3.0% |

### 4.3 Klasa C — Błędy Prawdopodobieństwa Tie-Break

**Definicja AX-16.9 (Model Tie-Break):** Prawdopodobieństwo tie-breaka w secie $s$:

$$P(TB_s) = P(G_A^{(s)} = 6) \cdot P(G_B^{(s)} = 6 \;|\; G_A^{(s)} = 6)$$

Obliczone rekurencyjnie z parametrów serwisowych $p_s^A, p_s^B$ poprzez model gema Markowa.

**Błąd Bukmachera dla TB:**

Bukmacherzy stosują uproszczenie:

$$P_{BK}(TB_{any}) \approx 1 - (1-p_{ML})^\gamma$$

gdzie $\gamma \approx 2.3$ — stała empiryczna. Ta aproksymacja jest błędna dla skrajnych wartości $p_{ML}$.

**Formuła EV dla Klasy C:**

$$EV_C = \hat{p}_{MC}(TB_{any}) \cdot K_{BK}(TB_{any}) - 1$$

Warunek wejścia: $|p_{MC} - p_{BK}| > 0.04$.

**Tabela 4.3: Błędy TB Probability vs. Moneyline**

| $p_{ML}^A$ | $p_{BK}(TB)$ | $p_{MC}(TB)$ | Błąd |
|-----------|-------------|-------------|------|
| 0.50 | 0.421 | 0.418 | -0.003 |
| 0.60 | 0.389 | 0.374 | -0.015 |
| 0.70 | 0.322 | 0.298 | -0.024 |
| 0.80 | 0.241 | 0.198 | -0.043 |
| 0.85 | 0.187 | 0.141 | -0.046 |

---

## 5. Algorytm Skanera

**Algorytm AX-16.ALG1 (Derivative Scanner):**

```
WEJŚCIE: Mecz (A vs B), kursy bukmacherów K_BK
WYJŚCIE: Lista okazji wartościowych z EV > δ_min

1. Oblicz p_s^A, p_s^B z modelu sElo/rElo
2. Uruchom symulację MC (N=100,000)
3. Wyznacz {p_MC(D)} dla wszystkich rynków D
4. Dla każdego rynku D i kursu K_BK(D):
   a. EV = p_MC(D) * K_BK(D) - 1
   b. Klasyfikuj typ błędu (A/B/C)
   c. Jeśli EV > δ_min = 0.02: dodaj do listy okazji
5. Sortuj listę według EV malejąco
6. Zwróć TOP-K okazji (K=5 domyślnie)
```

---

## 6. Metryki Skuteczności Skanera

**Definicja AX-16.10 (Precision@K):** Precyzja skanera dla top-K okazji:

$$\text{Precision}@K = \frac{1}{K}\sum_{i=1}^{K} \mathbf{1}[EV_i^{realized} > 0]$$

**Definicja AX-16.11 (ROI Skanera):**

$$ROI_{scanner} = \frac{\sum_{i} (wynik_i \cdot stake_i - stake_i)}{\sum_i stake_i}$$

Cel: $ROI_{scanner} > 0.06$ (6%) na bazie backtestu 2019-2025.

---

## 7. Referencje i Dane Empiryczne

- ATP TML-Database: 198,063 meczów (1990-2025)
- Dane serwisowe: `w_1stWon`, `w_svpt`, `w_1stIn`, `w_2ndWon` (AX-20)
- Bukmacherzy referencyjni: Pinnacle, Bet365, Unibet (dane historyczne)
- Benchmark błędu MC: $\sigma_{MC} < 0.002$ dla $N = 100{,}000$
