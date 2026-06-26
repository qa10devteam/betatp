# AX-10: KALIBRACJA PRAWDOPODOBIEŃSTWA — SPECYFIKACJA FORMALNA

**Dokument:** AX-10  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. WPROWADZENIE — PROBLEM KALIBRACJI

### Definicja 1.1 — Model dobrze skalibrowany

Model predykcyjny $\mathcal{M}$ jest **dobrze skalibrowany** (ang. *calibrated*) jeśli dla dowolnego podzbioru przewidywań z wartością $\hat{p} = p_0$:

$$P(Y=1 \mid \hat{p} = p_0) = p_0$$

Innymi słowy: dla wszystkich meczów, gdzie model przewiduje 70% szansę wygranej, faktycznie 70% z nich kończy się wygraną.

### Motywacja

Modele klasyfikacji binarnej (gradient boosting, sieci neuronowe) często wyjściowo **nie są** dobrze skalibrowane:
- Gradient boosting: tendencja do zbyt pewnych predykcji (skrajne $\hat{p}$ blisko 0 lub 1)
- Regresja logistyczna: dobrze kalibrowana z natury (pod modelem logistycznym)
- Random Forest: tendencja do skupiania się wokół $\hat{p} \in [0.3, 0.7]$

### Definicja 1.2 — Diagram rzetelności (Reliability Diagram)

Diagram rzetelności jest wykresem:
- Oś X: $\hat{p}$ (przewidziane prawdopodobieństwo)
- Oś Y: $\bar{y}$ (obserwowana frakcja pozytywna)
- Idealna kalibracja: prosta $y = x$

---

## 2. EXPECTED CALIBRATION ERROR (ECE)

### Definicja 2.1 — ECE

Niech $n$ próbek zostanie podzielonych na $M$ równych kubełków (bins) $B_1, B_2, \ldots, B_M$ według wartości $\hat{p}$.

**Expected Calibration Error:**

$$\text{ECE} = \sum_{m=1}^{M} \frac{|B_m|}{n} \cdot \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$

gdzie:

$$\text{conf}(B_m) = \frac{1}{|B_m|} \sum_{i \in B_m} \hat{p}_i \quad \text{(średnia ufność)}$$

$$\text{acc}(B_m) = \frac{1}{|B_m|} \sum_{i \in B_m} y_i \quad \text{(frakcja pozytywna)}$$

### Definicja 2.2 — Maximum Calibration Error (MCE)

$$\text{MCE} = \max_{m \in \{1,\ldots,M\}} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$

### Definicja 2.3 — Protokół kalibracji systemu betatp.io

**Parametry standardowe:**
- $M = 10$ kubełków (bins równomiernych: $[0, 0.1), [0.1, 0.2), \ldots, [0.9, 1.0]$)
- Minimalna liczba próbek per bin: $|B_m| \geq 30$
- Wymagany rozmiar zbioru kalibracyjnego: $n \geq 500$

**Protokół:**
1. Zbierz predykcje $\hat{p}_i$ i etykiety $y_i \in \{0, 1\}$ ze zbioru walidacyjnego
2. Dla $m = 1, \ldots, 10$: oblicz $\text{conf}(B_m)$ i $\text{acc}(B_m)$
3. Oblicz ECE zgodnie z definicją 2.1
4. Jeśli ECE > 0.03: uruchom rekalibrację (patrz § 4)

### Twierdzenie 2.1 — Relacja ECE–Brier Score

Zachodzi nierówność:

$$\text{ECE}^2 \leq \text{BS}$$

gdzie $\text{BS} = \frac{1}{n} \sum_i (\hat{p}_i - y_i)^2$ (Brier Score).

**Dowód (szkic):** Brier Score dekomponuje się na kalibrację i refinement:
$$\text{BS} = \text{Calibration} + \text{Resolution} - \text{Uncertainty}$$
ECE mierzy tylko komponent kalibracyjny, stąd $\text{ECE} \leq \sqrt{\text{BS}}$. $\square$

---

## 3. METODY KALIBRACJI

### 3.1 Platt Scaling

#### Definicja 3.1 — Platt Scaling

Platt Scaling (1999) dopasowuje sigmoidalną transformację do predykcji modelu:

$$\hat{p}_{\text{cal}} = \sigma(A \cdot s + B) = \frac{1}{1 + e^{-(As + B)}}$$

gdzie:
- $s = \hat{p}_{\text{raw}}$ lub $s = \log(\hat{p}_{\text{raw}} / (1-\hat{p}_{\text{raw}}))$ (log-odds)
- $A, B \in \mathbb{R}$ — parametry dopasowane przez MLE

#### Estymacja parametrów

Minimalizujemy log-loss na zbiorze kalibracyjnym $\mathcal{D}_{\text{cal}}$:

$$\min_{A, B} \mathcal{L}(A, B) = -\sum_{i=1}^{n} \left[ y_i \log \hat{p}_i^{\text{cal}} + (1-y_i) \log(1 - \hat{p}_i^{\text{cal}}) \right]$$

Rozwiązanie metodą gradientu. Funkcja $\mathcal{L}$ jest wypukła w $(A, B)$, więc istnieje globalne minimum.

#### Właściwości

- **Parametryczne:** zakłada liniową relację w log-odds
- **Dobra dla:** regresji logistycznej, SVM
- **Słabość:** niewystarczająca dla modeli z nieliniowymi odchyleniami

### 3.2 Isotonic Regression

#### Definicja 3.2 — Isotonic Regression

Isotonic Regression dopasowuje monotonicznie niemalejącą funkcję krok-schody $\hat{f}: [0,1] \to [0,1]$:

$$\hat{f} = \arg\min_{f: \text{niemalejąca}} \sum_{i=1}^{n} (y_i - f(\hat{p}_i))^2$$

Rozwiązanie wyznaczone przez **Pool Adjacent Violators Algorithm (PAVA)**.

#### PAVA — opis algorytmu

```
Dane: (p_1, y_1), ..., (p_n, y_n) posortowane rosnąco po p_i

1. Inicjalizuj: grupy G = [{(p_1, y_1)}, ..., {(p_n, y_n)}]
2. Dla i = 2 do n:
   a. Jeśli mean(G_i) < mean(G_{i-1}): 
      połącz G_i i G_{i-1} w jedną grupę
      powtórz aż do monotonii
3. Wyjście: f(p_i) = mean(grupy zawierającej i)
```

#### Własności

- **Nieparametryczne:** brak założeń o kształcie
- **Dobra dla:** każdego modelu z monotonicznymi odchyleniami
- **Słabość:** przeuczenie przy małych zbiorach kalibracyjnych

### 3.3 Porównanie metod kalibracji

| Metoda | Parametry | Monotoniczność | Złożoność | Odporność na małe zbiory |
|--------|-----------|----------------|-----------|--------------------------|
| Platt Scaling | 2 | Tak (z natury) | $O(n)$ | Wysoka |
| Isotonic Reg. | $n$ | Wymuszona | $O(n \log n)$ | Niska (≥200 próbek) |
| Beta Calibration | 3 | Nie | $O(n)$ | Wysoka |

**Decyzja betatp.io:**
- $n_{\text{cal}} \geq 200$: Isotonic Regression
- $n_{\text{cal}} < 200$: Platt Scaling
- Zawsze: walidacja przez ECE po kalibracji

---

## 4. PROTOKÓŁ REKALIBRACJI

### Definicja 4.1 — Warunek rekalibracji

Model wymaga rekalibracji jeśli:

$$\text{ECE} > 0.03$$

lub MCE > 0.08 w którymkolwiek z 10 kubełków.

### Algorytm rekalibracji

```
WEJŚCIE: model M, zbiór kalibracyjny D_cal
WYJŚCIE: model skalibrowany M_cal

1. Oblicz predykcje: ĥ_i = M(x_i) dla (x_i, y_i) ∈ D_cal
2. Oblicz ECE(ĥ, y)
3. JEŚLI ECE > 0.03:
   a. Wybierz metodę (IR lub Platt, patrz § 3.3)
   b. Dopasuj transformację g: [0,1] → [0,1]
   c. M_cal(x) = g(M(x))
4. Oblicz ECE(M_cal(D_cal), y)
5. ASSERT ECE_nowa < ECE_stara (weryfikacja poprawy)
6. LOGUJ: (timestamp, ECE_przed, ECE_po, metoda)
```

### Definicja 4.2 — Okno rekalibracji

Rekalibracja przeprowadzana:
- **Cyklicznie:** co 30 dni (miesięczny cykl turniejowy ATP)
- **Triggerowana:** gdy rolling-window ECE (ostatnie 100 zakładów) > 0.05

---

## 5. TABLICE KALIBRACJI — PRZYKŁAD

### Przykład: Model betatp przed kalibracją (sezon 2023)

| Bin | Zakres | $n_m$ | $\text{conf}(B_m)$ | $\text{acc}(B_m)$ | $|\text{conf} - \text{acc}|$ |
|-----|--------|--------|---------------------|-------------------|------------------------------|
| 1   | [0.0, 0.1) | 45  | 0.067 | 0.044 | 0.023 |
| 2   | [0.1, 0.2) | 123 | 0.152 | 0.138 | 0.014 |
| 3   | [0.2, 0.3) | 287 | 0.248 | 0.231 | 0.017 |
| 4   | [0.3, 0.4) | 412 | 0.352 | 0.341 | 0.011 |
| 5   | [0.4, 0.5) | 634 | 0.451 | 0.462 | 0.011 |
| 6   | [0.5, 0.6) | 598 | 0.551 | 0.558 | 0.007 |
| 7   | [0.6, 0.7) | 445 | 0.648 | 0.661 | 0.013 |
| 8   | [0.7, 0.8) | 312 | 0.748 | 0.763 | 0.015 |
| 9   | [0.8, 0.9) | 198 | 0.844 | 0.834 | 0.010 |
| 10  | [0.9, 1.0] | 67  | 0.934 | 0.910 | 0.024 |

**Łączna $n = 3121$**

$$\text{ECE} = \sum_{m=1}^{10} \frac{|B_m|}{3121} \cdot |\text{conf} - \text{acc}|$$

$$= \frac{45}{3121}(0.023) + \frac{123}{3121}(0.014) + \ldots + \frac{67}{3121}(0.024)$$

$$\text{ECE} \approx 0.0127$$

Ponieważ ECE = 0.013 < 0.03, model **nie wymaga** rekalibracji. ✓

---

## 6. DIAGRAM RZETELNOŚCI — SPECYFIKACJA

### Definicja 6.1 — Elementy diagramu rzetelności

Diagram rzetelności zawiera:
1. **Linia doskonała:** $y = x$ (ukośna, kolor niebieski przerywany)
2. **Krzywa modelu:** punkty $(\text{conf}(B_m), \text{acc}(B_m))$ dla $m=1,\ldots,M$
3. **Słupki błędów:** $\pm 2 \cdot \text{SE}(B_m)$ gdzie $\text{SE}(B_m) = \sqrt{\text{acc}(B_m)(1-\text{acc}(B_m))/|B_m|}$
4. **ECE label:** w rogu wykresu

### Interpretacja odchyleń

- Krzywa powyżej $y=x$: model **niedoszacowuje** (zbyt mała ufność)
- Krzywa poniżej $y=x$: model **przeszacowuje** (zbyt duża ufność)
- Typowy wzorzec Gradient Boosting w tenisie: przeszacowanie przy $\hat{p} \in [0.6, 0.9]$

---

## 7. METRYKI UZUPEŁNIAJĄCE

### Definicja 7.1 — Brier Score (BS)

$$\text{BS} = \frac{1}{n} \sum_{i=1}^{n} (\hat{p}_i - y_i)^2$$

- BS = 0: doskonały model
- BS = 0.25: model losowy (p = 0.5 zawsze)
- Benchmark ATP (2023): BS $\approx 0.21$–$0.23$

### Definicja 7.2 — Log-Loss (Binary Cross-Entropy)

$$\text{LL} = -\frac{1}{n} \sum_{i=1}^{n} \left[ y_i \log \hat{p}_i + (1-y_i) \log(1-\hat{p}_i) \right]$$

- LL = 0: doskonały model
- Benchmark naiwny (p = 0.5): LL = ln(2) ≈ 0.693
- Benchmark ATP model betatp: LL $\approx 0.58$–$0.62$

---

## 8. REFERENCJE

1. Platt, J. (1999). "Probabilistic outputs for support vector machines." *Advances in Large Margin Classifiers*, 61–74.
2. Niculescu-Mizil, A., Caruana, R. (2005). "Predicting good probabilities with supervised learning." *ICML 2005*, 625–632.
3. Guo, C., Pleiss, G., Sun, Y., Weinberger, K.Q. (2017). "On Calibration of Modern Neural Networks." *ICML 2017*.
4. DeGroot, M.H., Fienberg, S.E. (1983). "The comparison and evaluation of forecasters." *The Statistician*, 32(1–2), 12–22.
5. ATP Match Results Database, 2000–2024: dane kalibracji modelu na 50,000+ meczów.

---

*Dokument AX-10 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
