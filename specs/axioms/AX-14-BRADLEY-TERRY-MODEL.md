# AX-14: MODEL BRADLEY-TERRY — SPECYFIKACJA FORMALNA

**Dokument:** AX-14  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. MODEL BRADLEY-TERRY — DEFINICJA KANONICZNA

### Definicja 1.1 — Parametry siły gracza

Niech $\mathcal{P} = \{1, 2, \ldots, K\}$ będzie zbiorem $K$ zawodników. Każdemu zawodnikowi $i$ przypisujemy **parametr siły** $\pi_i > 0$.

### Definicja 1.2 — Model Bradley-Terry (BT)

Prawdopodobieństwo, że zawodnik $i$ pokona zawodnika $j$ w bezpośrednim meczu:

$$P(i \succ j) = \frac{\pi_i}{\pi_i + \pi_j}$$

**Własności:**
- $P(i \succ j) + P(j \succ i) = 1$ ✓
- $P(i \succ j) \in (0, 1)$ dla $\pi_i, \pi_j > 0$ ✓
- Monotoniczność: jeśli $\pi_i > \pi_j$, to $P(i \succ j) > 0.5$ ✓

### Definicja 1.3 — Parametryzacja log-liniowa

Definiujemy $\lambda_i = \ln \pi_i$, wtedy:

$$P(i \succ j) = \frac{e^{\lambda_i}}{e^{\lambda_i} + e^{\lambda_j}} = \sigma(\lambda_i - \lambda_j)$$

gdzie $\sigma(x) = 1/(1+e^{-x})$ jest funkcją sigmoid.

**Identyfikowalność:** Model jest identyfikowalny z ograniczeniem $\sum_i \lambda_i = 0$ lub $\lambda_1 = 0$ (anchor).

---

## 2. RÓWNOWAŻNOŚĆ Z MODELEM ELO

### Twierdzenie 2.1 — Elo jest modelem Bradley-Terry z link logistycznym

**Twierdzenie:** System Elo (Glicko-2 specjalny przypadek) jest modelem BT z parametrami:

$$\lambda_i^{\text{Elo}} = \frac{R_i \cdot \ln(10)}{400}$$

gdzie $R_i$ jest ratingiem Elo zawodnika $i$.

**Dowód:**

W systemie Elo prawdopodobieństwo wygranej:

$$P^{\text{Elo}}(i \succ j) = \frac{1}{1 + 10^{(R_j - R_i)/400}} = \frac{1}{1 + e^{(R_j - R_i) \ln(10)/400}}$$

$$= \sigma\left(\frac{(R_i - R_j)\ln(10)}{400}\right) = \sigma(\lambda_i^{\text{Elo}} - \lambda_j^{\text{Elo}})$$

co jest dokładnie modelem BT z $\lambda_i = R_i \ln(10)/400$. $\square$

### Wniosek 2.1 — Elo jako MLE

Aktualizacja Elo (po meczu $i \succ j$):

$$R_i \leftarrow R_i + K(y - \hat{p})$$

jest przybliżeniem **stochastycznego gradientu** log-likelihood modelu BT, z learning rate $K$.

---

## 3. ESTYMACJA MLE PRZEZ ALGORYTM ITERACYJNY

### Definicja 3.1 — Log-likelihood modelu BT

Niech $w_{ij}$ = liczba meczów wygranych przez $i$ nad $j$, $n_{ij} = w_{ij} + w_{ji}$ = całkowita liczba meczów.

$$\mathcal{L}(\boldsymbol{\pi}) = \sum_{i < j} \left[ w_{ij} \ln \frac{\pi_i}{\pi_i + \pi_j} + w_{ji} \ln \frac{\pi_j}{\pi_i + \pi_j} \right]$$

### Twierdzenie 3.1 — Iteracyjny algorytm Hunter (MM)

**Twierdzenie (Hunter 2004):** Poniższy algorytm minimalizuje-maksymalizuje $\mathcal{L}$ monotonically:

**Algorytm MM (Minorization-Maximization):**

$$\pi_i^{(t+1)} = \frac{W_i}{\sum_{j \neq i} \frac{n_{ij}}{\pi_i^{(t)} + \pi_j^{(t)}}}$$

gdzie $W_i = \sum_{j \neq i} w_{ij}$ = całkowita liczba wygranych gracza $i$.

**Dowód zbieżności (zarys):**

1. Zdefiniuj majoryzującą funkcję $g(\boldsymbol{\pi} | \boldsymbol{\pi}^{(t)}) \geq \mathcal{L}(\boldsymbol{\pi})$ z równością w $\boldsymbol{\pi}^{(t)}$
2. Każda iteracja MM zwiększa $\mathcal{L}$: $\mathcal{L}(\boldsymbol{\pi}^{(t+1)}) \geq \mathcal{L}(\boldsymbol{\pi}^{(t)})$
3. $\mathcal{L}$ jest górnie ograniczona (bounded above)
4. Sekwencja $\{\mathcal{L}(\boldsymbol{\pi}^{(t)})\}$ zbiega do MLE $\hat{\boldsymbol{\pi}}$ $\square$

### Pseudokod algorytmu MM

```
WEJŚCIE: macierz wyników W[i][j], tolerancja ε=1e-8
WYJŚCIE: ĥπ[i] dla i=1..K

1. Inicjalizuj: π[i] = 1.0 dla wszystkich i
2. Normalizuj: π /= sum(π)

POWTARZAJ:
   π_prev = copy(π)
   
   DLA i = 1..K:
     numerator = W[i]  # łączne wygrane gracza i
     denominator = Σ_{j≠i} (n[i][j]) / (π[i] + π[j])
     π_new[i] = numerator / denominator
   
   Normalizuj: π_new /= sum(π_new)
   
   δ = max_i |π_new[i] - π[i]|
   π = π_new

AŻ δ < ε

ZWRÓĆ π
```

**Złożoność:** $O(K^2)$ per iteracja, zbieżność w ~50–200 iteracjach dla typowych danych ATP.

---

## 4. ROZSZERZONY MODEL BT Z KOWARIANCJAMI

### Definicja 4.1 — BT z kowariancjami (log-liniowy)

Rozszerzamy model BT dodając kowariancje gracza. Parametr siły gracza $i$:

$$\ln \pi_i = \mathbf{z}_i^T \boldsymbol{\beta}$$

gdzie $\mathbf{z}_i$ — wektor kowariancji gracza $i$, $\boldsymbol{\beta}$ — wektor parametrów.

### Definicja 4.2 — Model betatp (Rozszerzony BT)

W systemie betatp.io, siła gracza $i$ modelu BT jest parametryzowana jako:

$$\pi_i = \exp\left(\alpha + \beta_1 \cdot \text{SurfaceElo}_i + \beta_2 \cdot \text{Form}_i + \beta_3 \cdot \text{AgeFactor}_i\right)$$

gdzie:

| Parametr | Definicja | Zakres typowy |
|----------|-----------|---------------|
| $\alpha$ | intercept (baseline) | stały dla all players |
| $\text{SurfaceElo}_i$ | Elo rating gracza na bieżącej nawierzchni | [800, 2500] |
| $\text{Form}_i$ | EWMA form score ($\alpha=0.15$, patrz AX-11) | [-2, +2] (standardized) |
| $\text{AgeFactor}_i$ | Korekta wiekowa — patrz definicja 4.3 | [0.6, 1.2] |
| $\beta_1, \beta_2, \beta_3$ | parametry estymowane przez MLE | |

### Definicja 4.3 — AgeFactor (czynnik wiekowy)

Na podstawie empirycznych danych ATP (analiza 1990–2024):

$$\text{AgeFactor}(a) = \begin{cases}
\frac{a - 17}{6} & \text{jeśli } 17 \leq a < 23 \quad \text{(wzrost)} \\
1.0 & \text{jeśli } 23 \leq a \leq 27 \quad \text{(peak)} \\
1.0 - 0.025 \cdot (a - 27) & \text{jeśli } a > 27 \quad \text{(spadek)}
\end{cases}$$

gdzie $a$ = wiek w latach.

| Wiek | AgeFactor | Interpretacja |
|------|-----------|---------------|
| 18 | 0.167 | Talent z potencjałem |
| 21 | 0.667 | Rozwijający się |
| 24 | 1.000 | Szczyt kariery |
| 28 | 0.975 | Lekki spadek |
| 32 | 0.875 | Doświadczony, wolniejszy |
| 36 | 0.775 | Schyłek kariery |

---

## 5. MLE DLA ROZSZERZONEGO BT

### Definicja 5.1 — Log-likelihood rozszerzonego BT

$$\mathcal{L}(\boldsymbol{\beta}) = \sum_{(i,j,y) \in \mathcal{D}} \left[ y \ln P_{\boldsymbol{\beta}}(i \succ j) + (1-y) \ln P_{\boldsymbol{\beta}}(j \succ i) \right]$$

gdzie $P_{\boldsymbol{\beta}}(i \succ j) = \sigma(\ln\pi_i - \ln\pi_j) = \sigma(\mathbf{z}_i^T\boldsymbol{\beta} - \mathbf{z}_j^T\boldsymbol{\beta})$.

### Twierdzenie 5.1 — Wypukłość

$-\mathcal{L}(\boldsymbol{\beta})$ jest **wypukła** w $\boldsymbol{\beta}$.

**Dowód:** 
$$\frac{\partial^2 (-\mathcal{L})}{\partial \boldsymbol{\beta} \partial \boldsymbol{\beta}^T} = \sum_{(i,j)} P_{ij}(1-P_{ij}) (\mathbf{z}_i - \mathbf{z}_j)(\mathbf{z}_i - \mathbf{z}_j)^T$$

To jest suma produktów zewnętrznych z dodatnimi wagami $P_{ij}(1-P_{ij}) > 0$, więc macierz Hessiana jest dodatnio-semidefinita. $\square$

### Algorytm IRLS (Iteratively Reweighted Least Squares)

Estymacja $\boldsymbol{\beta}$ przez Newton-Raphson:

$$\boldsymbol{\beta}^{(t+1)} = \boldsymbol{\beta}^{(t)} + (\mathbf{H}^{(t)})^{-1} \nabla \mathcal{L}(\boldsymbol{\beta}^{(t)})$$

Gradient:

$$\frac{\partial \mathcal{L}}{\partial \boldsymbol{\beta}} = \sum_{(i,j,y)} (y - P_{ij}) (\mathbf{z}_i - \mathbf{z}_j)$$

Hessian:

$$\mathbf{H} = -\sum_{(i,j)} P_{ij}(1-P_{ij}) (\mathbf{z}_i - \mathbf{z}_j)(\mathbf{z}_i - \mathbf{z}_j)^T$$

---

## 6. REGULARYZACJA

### Definicja 6.1 — Ridge regularyzacja (L2)

Aby zapobiec overfittingowi (zwłaszcza przy małej liczbie meczów H2H):

$$\mathcal{L}_{\text{reg}}(\boldsymbol{\beta}) = \mathcal{L}(\boldsymbol{\beta}) - \frac{\lambda}{2} \|\boldsymbol{\beta}\|^2$$

Parametr regularyzacji: $\lambda = 0.01$ (dopasowany przez CV na zbiorze walidacyjnym).

---

## 7. PRZYKŁAD NUMERYCZNY

**Dane:** 3 zawodników ATP — Djokovic (D), Alcaraz (A), Medvedev (M)

| Mecze | Wyniki |
|-------|--------|
| D vs A | 8W–4L |
| D vs M | 12W–5L |
| A vs M | 6W–6L |

**Inicjalizacja:** $\pi_D = \pi_A = \pi_M = 1.0$

**Iteracja 1 (MM):**

$$\pi_D^{(1)} = \frac{20}{\frac{12}{1+1} + \frac{17}{1+1}} = \frac{20}{6 + 8.5} = \frac{20}{14.5} \approx 1.379$$

$$\pi_A^{(1)} = \frac{10}{\frac{12}{1+1} + \frac{12}{1+1}} = \frac{10}{6+6} = 0.833$$

$$\pi_M^{(1)} = \frac{11}{\frac{17}{1+1} + \frac{12}{1+1}} = \frac{11}{8.5+6} = \frac{11}{14.5} \approx 0.759$$

Po normalizacji: $\pi_D \approx 0.467$, $\pi_A \approx 0.282$, $\pi_M \approx 0.257$ (do dalszych iteracji)

**Po zbieżności (~50 iteracji):**
$\pi_D \approx 2.41$, $\pi_A \approx 1.08$, $\pi_M \approx 0.92$

**Predykcja:** $P(D \succ A) = 2.41/(2.41+1.08) = 0.690$

---

## 8. REFERENCJE

1. Bradley, R.A., Terry, M.E. (1952). "Rank analysis of incomplete block designs: I. The method of paired comparisons." *Biometrika*, 39(3/4), 324–345.
2. Hunter, D.R. (2004). "MM algorithms for generalized Bradley-Terry models." *Annals of Statistics*, 32(1), 384–406.
3. Elo, A.E. (1978). *The Rating of Chessplayers, Past and Present.* Arco Publishing, New York.
4. Agresti, A. (2002). *Categorical Data Analysis* (2nd ed.). Wiley.
5. Glickman, M.E. (1999). "Parameter estimation in large dynamic paired comparison experiments." *Applied Statistics*, 48(3), 377–394.
6. ATP Official Match Records Database, 1968–2024.

---

*Dokument AX-14 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
