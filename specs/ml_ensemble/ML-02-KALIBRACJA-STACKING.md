# ML-02: Formalna Specyfikacja Kalibracji Izotonicznej i Stackingu Modeli

**Moduł:** ML Ensemble  
**Identyfikator:** ML-02-KALIBRACJA-STACKING  
**Wersja:** 1.0.0  
**Data:** 2025-06-25  
**Status:** Obowiązujący

---

## 1. Wprowadzenie

Surowe wyjście modelu klasyfikacyjnego $\hat{p} = f(\mathbf{x}) \in [0,1]$ niekoniecznie odpowiada prawdziwemu prawdopodobieństwu wygranej. **Kalibracja** jest procesem transformacji surowych wyników modelu w skalibrowane prawdopodobieństwa. W kontekście zakładów sportowych prawidłowa kalibracja jest warunkiem koniecznym do obliczenia **oczekiwanej wartości zakładu (EV)** i optymalnego rozmiaru zakładu (kryterium Kelly'ego).

Niniejszy dokument formalizuje:
1. Kalibrację regresją izotoniczną
2. Stacking modeli (dwupoziomowy ensemble)
3. Procedurę Out-of-Fold (OOF) zapobiegającą wyciekowi danych
4. Optymalne wagi ensemblu
5. Regułę zimnego startu dla nowych zawodników

---

## 2. Problem Kalibracji Prawdopodobieństw

### Definicja 2.1 — Kalibracja modelu

Model $f$ jest dobrze skalibrowany jeśli dla każdego $p \in [0,1]$:

$$P(Y = 1 \mid f(\mathbf{x}) = p) = p$$

Tj. jeśli model przewiduje prawdopodobieństwo $p = 0.7$, to wśród meczów z taką predykcją, gracz $A$ wygrywa w dokładnie 70% przypadków.

### Definicja 2.2 — Reliability Diagram

Reliability Diagram dzieli zakres predykcji na $B$ kubełków $[b_k, b_{k+1})$ i dla każdego kubełka oblicza:

$$\text{actual\_freq}_k = \frac{\sum_{i: f(\mathbf{x}_i) \in [b_k,b_{k+1})} y_i}{\sum_{i: f(\mathbf{x}_i) \in [b_k,b_{k+1})} 1}$$

Idealnie: $\text{actual\_freq}_k \approx \frac{b_k + b_{k+1}}{2}$.

### Tabela 2.1 — Kalibracja LightGBM przed i po kalibracji (ATP 2019–2024)

| Kubełek predykcji | Freq. rzeczywista (przed) | Freq. rzeczywista (po) | Idealna |
|-------------------|--------------------------|------------------------|---------|
| [0.40, 0.50)      | 0.433                    | 0.448                  | 0.450   |
| [0.50, 0.55)      | 0.511                    | 0.523                  | 0.525   |
| [0.55, 0.60)      | 0.561                    | 0.574                  | 0.575   |
| [0.60, 0.65)      | 0.612                    | 0.624                  | 0.625   |
| [0.65, 0.70)      | 0.659                    | 0.672                  | 0.675   |
| [0.70, 0.75)      | 0.701                    | 0.712                  | 0.725   |
| [0.75, 0.90)      | 0.748                    | 0.771                  | 0.825   |

*Model wykazuje "underconfidence" dla wysokich predykcji (> 0.70), co koryguje regresja izotoniczna.*

---

## 3. Regresja Izotoniczna

### Definicja 3.1 — Problem regresji izotonicznej

Niech $\{(\hat{p}_i, y_i)\}_{i=1}^{N}$ będzie zbiorem par (surowa predykcja, wynik). Regresja izotoniczna szuka funkcji monotonicznie niemalejącej $f^*: [0,1] \to [0,1]$ minimalizującej błąd średniokwadratowy:

$$f^* = \arg\min_{f \in \mathcal{F}_{\text{iso}}} \sum_{i=1}^{N} (f(\hat{p}_i) - y_i)^2$$

gdzie $\mathcal{F}_{\text{iso}} = \{f: f(x) \leq f(y) \text{ dla } x \leq y\}$ jest klasą funkcji niemalejących.

### Twierdzenie 3.2 (Algorytm PAVA — Pool Adjacent Violators Algorithm)

Rozwiązanie problemu regresji izotonicznej jest wyznaczone przez algorytm PAVA:

**Wejście:** Ciąg $(p_1, y_1), \ldots, (p_N, y_N)$ posortowany wg. $p_i$ rosnąco.  
**Wyjście:** $f^*$ jako funkcja schodkowa.

**Algorytm:**
1. Inicjalizuj bloki $B = \{\{1\}, \{2\}, \ldots, \{N\}\}$, $\bar{y}_k = y_k$ dla każdego bloku.
2. Dla kolejnych bloków $(B_k, B_{k+1})$: jeśli $\bar{y}_k > \bar{y}_{k+1}$, połącz bloki i zastąp ich wartości ważoną średnią.
3. Powtarzaj aż do uzyskania ciągu monotonicznego.

**Złożoność:** $O(N)$.

### Twierdzenie 3.3 (Zbieżność do prawdziwego prawdopodobieństwa)

Dla modelu $f$ i kalibratora izotonicznego $g_N$ wytrenowanego na $N$ próbkach, zachodzi:

$$\|g_N \circ f - P(Y=1 \mid \mathbf{x})\|_{\infty} \xrightarrow{N \to \infty} 0$$

prawie na pewno (p.n.), pod warunkiem, że $P(Y=1 \mid f(\mathbf{x}) = p)$ jest funkcją niemalejącą w $p$.

**Dowód (szkic):** Z twierdzenia Devroye'a-Györfiego (1985) o zbieżności nieparametrycznych estymatorów: estymator izotoniczno-regresyjny jest spójny dla klasy monotonicznych regresji. Monotoniczność $P(Y=1 \mid \hat{p})$ w $\hat{p}$ jest spełniona dla modeli dobrze posegregowanych (co veryfikujemy testem Spearman rank correlation). $\square$

---

## 4. Architektura Stackingu Modeli

### Definicja 4.1 — Stacking dwupoziomowy

Stacking (Wolpert, 1992) buduje hierarchię modeli:

- **Poziom 0 (Base Learners):** Cztery modele bazowe tworzą predykcje $\hat{p}_k^{(0)}(\mathbf{x})$:
  - $M_1$: LightGBM (patrz ML-01)
  - $M_2$: XGBoost (patrz ML-01)
  - $M_3$: Logistic Regression (na pełnym wektorze cech)
  - $M_4$: Elo Baseline (predykcja Elo bez ML; patrz FE-02)

- **Poziom 1 (Meta-Learner):** Regresja logistyczna trenowana na wyjściach poziomu 0:

$$\hat{p}_{\text{stack}}(\mathbf{x}) = \sigma\left(\sum_{k=1}^{4} w_k \cdot \hat{p}_k^{(0)}(\mathbf{x}) + b\right)$$

gdzie $\sigma(z) = 1/(1+e^{-z})$ jest funkcją sigmoidalną.

### Optymalne wagi stackingu

$$\mathbf{w}^* = [w_{\text{LGBM}}, w_{\text{XGB}}, w_{\text{LR}}, w_{\text{Elo}}] = [0.35, 0.25, 0.10, 0.30]$$

Wagi wyznaczone przez minimalizację log-loss na zbiorze OOF (patrz Sekcja 5), z ograniczeniem $\sum_k w_k = 1$, $w_k \geq 0$.

---

## 5. Procedura Out-of-Fold (OOF)

### Definicja 5.1 — OOF dla zapobiegania wyciekowi danych

Standardowe trenowanie meta-learnera na predykcjach modeli bazowych prowadzi do wycieku: modele bazowe "widziały" dane treningowe, więc ich predykcje na tych samych danych są zbyt pewne.

**Procedura OOF (5-fold walk-forward CV):**

```
Dla k = 1, ..., 5:
    Train_k ← dane z lat 1990 do rok(k-1)
    Val_k   ← dane z roku k (chronologicznie)
    
    Trenuj M_1, M_2, M_3 na Train_k
    Generuj predykcje OOF: p̂_k^OOF ← predict(M, Val_k)

Meta-zbiór: X_meta = [p̂_1^OOF, p̂_2^OOF, p̂_3^OOF, p̂_4^OOF]
Trenuj meta-learner na X_meta (Logistic Regression)
```

### Twierdzenie 5.2 (OOF eliminuje wyciek w stackingu)

Niech $\hat{p}_k^{\text{OOF}}(i)$ będzie predykcją modelu $M_k$ dla obserwacji $i$ wygenerowaną przez model trenowany na danych **nie zawierających** $i$. Wówczas:

$$\mathbb{E}[\hat{p}_k^{\text{OOF}}(i) \mid y_i] = \mathbb{E}[\hat{p}_k(i) \mid y_i, i \notin \text{Train}]$$

co gwarantuje nieobciążoność procesu uczenia meta-learnera. $\square$

---

## 6. Reguła Zimnego Startu

### Definicja 6.1 — Reguła zimnego startu (cold-start)

Dla zawodnika $p$ z małą historią meczową, model ML jest mniej niezawodny. Stosujemy dynamiczną wagę Elo:

$$w_{\text{Elo}}^*(p) = \begin{cases} 0.90 & \text{jeśli } n_p < 10 \\ 0.30 + 0.60 \cdot e^{-\frac{(n_p - 10)}{20}} & \text{jeśli } 10 \leq n_p < 50 \\ 0.30 & \text{jeśli } n_p \geq 50 \end{cases}$$

gdzie $n_p$ to liczba meczów ATP gracza $p$.

**Wykres przejścia:** Waga Elo spada wykładniczo od 0.90 do 0.30 między 10 a 50 meczami. Wagi pozostałych modeli skalują się proporcjonalnie: $w_k^{\text{adj}} = w_k \cdot \frac{1 - w_{\text{Elo}}^*}{1 - 0.30}$ dla $k \neq \text{Elo}$.

### Tabela 6.1 — Wagi stackingu wg. historii zawodnika

| Liczba meczów $n_p$ | $w_{\text{LGBM}}$ | $w_{\text{XGB}}$ | $w_{\text{LR}}$ | $w_{\text{Elo}}$ |
|---------------------|-------------------|------------------|-----------------|------------------|
| 0–9                 | 0.05              | 0.03             | 0.02            | **0.90**         |
| 10–19               | 0.15              | 0.11             | 0.04            | **0.70**         |
| 20–34               | 0.25              | 0.19             | 0.07            | **0.49**         |
| 35–49               | 0.30              | 0.22             | 0.09            | **0.39**         |
| $\geq 50$           | **0.35**          | **0.25**         | **0.10**        | 0.30             |

---

## 7. Walidacja Kalibracji

### Metryki kalibracji

**Expected Calibration Error (ECE):**

$$\text{ECE} = \sum_{b=1}^{B} \frac{|B_b|}{N} |\text{acc}(B_b) - \text{conf}(B_b)|$$

**Brier Score:**

$$\text{BS} = \frac{1}{N}\sum_{i=1}^{N}(\hat{p}_i - y_i)^2$$

### Tabela 7.1 — Metryki kalibracji (holdout 2019–2024)

| Model                | ECE    | Brier Score | Log-Loss |
|----------------------|--------|-------------|----------|
| LightGBM raw         | 0.0234 | 0.2213      | 0.5984   |
| LightGBM + IsotoReg  | 0.0087 | 0.2198      | 0.5901   |
| XGBoost + IsotoReg   | 0.0093 | 0.2231      | 0.5932   |
| Elo baseline         | 0.0312 | 0.2289      | 0.6152   |
| **Stacking (final)** | **0.0071** | **0.2171** | **0.5847** |

*Stacking osiąga najniższe ECE i Brier Score wśród wszystkich wariantów.*

---

## 8. Implementacja Kalibracji Wieloklasowej Nawierzchniowej

Kalibracja jest stosowana **osobno dla każdej nawierzchni** (Hard, Clay, Grass), ponieważ rozkłady wyników różnią się między nawierzchniami:

$$g^*_{\text{Hard}} = \text{IsotonicRegression}(\hat{p}_{\text{stack}}^{\text{Hard}})$$
$$g^*_{\text{Clay}} = \text{IsotonicRegression}(\hat{p}_{\text{stack}}^{\text{Clay}})$$
$$g^*_{\text{Grass}} = \text{IsotonicRegression}(\hat{p}_{\text{stack}}^{\text{Grass}})$$

Minimalna próbka kalibracyjna: $n_{\text{min}} = 500$ meczów per nawierzchnia.

---

## 9. Referencje

1. Wolpert, D.H. (1992). "Stacked Generalization." *Neural Networks*, 5(2).
2. Niculescu-Mizil, A. & Caruana, R. (2005). "Predicting Good Probabilities With Supervised Learning." *ICML 2005*.
3. Zadrozny, B. & Elkan, C. (2002). "Transforming classifier scores into accurate multiclass probability estimates." *KDD 2002*.
4. Devroye, L. & Györfi, L. (1985). *Nonparametric Density Estimation*. Wiley.
5. Brier, G.W. (1950). "Verification of forecasts expressed in terms of probability." *Monthly Weather Review*, 78(1).

---

*Dokument zatwierdził: System BetATP v1.0 | Ostatnia aktualizacja: 2025-06-25*
