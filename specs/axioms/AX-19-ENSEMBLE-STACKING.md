# AX-19: ENSEMBLE STACKING — FORMALNY PROTOKÓŁ ŁĄCZENIA MODELI
## Specyfikacja Formalna — betatp.io Prediction Engine
**Wersja:** 1.0.0  
**Status:** Zatwierdzony  
**Data:** 2026-06-25  

---

## 1. Wstęp i Cel

Żaden pojedynczy model predykcji nie dominuje we wszystkich kontekstach tenisowych. Model Elo sprawdza się dla nowych zawodników i cold-start, LightGBM/XGBoost lepiej przechwytują nieliniowe interakcje cech, a regresja logistyczna zapewnia kalibrację prawdopodobieństw. Niniejszy aksjomat definiuje formalny protokół stackingu (ensemble learning) łączący cztery modele w optymalny predyktor.

---

## 2. Definicje i Notacja

**Definicja AX-19.1 (Przestrzeń Cech):** Wektor cech meczu $\mathbf{x} \in \mathcal{X} \subset \mathbb{R}^d$ obejmuje:

$$\mathbf{x} = (R_A, R_B, p_s^A, p_s^B, \sigma, \text{h2h}, \text{ranking\_diff}, \text{fatigue}, \ldots)^T$$

z $d = 47$ cechami (pełna lista w dokumentacji Feature Engineering).

**Definicja AX-19.2 (Modele Poziomu 0):** Zbiór $K = 4$ modeli bazowych:

$$\mathcal{M} = \{M_1, M_2, M_3, M_4\}$$

| Indeks | Model | Typ |
|--------|-------|-----|
| $M_1$ | Enhanced Elo | Analityczny |
| $M_2$ | LightGBM | Gradient Boosting |
| $M_3$ | XGBoost | Gradient Boosting |
| $M_4$ | Regresja Logistyczna | Liniowy |

**Definicja AX-19.3 (Predykcja Modelu Bazowego):** Każdy model $M_k$ produkuje skalarne prawdopodobieństwo:

$$\hat{p}_k(\mathbf{x}) = P_k(A \succ B \;|\; \mathbf{x}) \in [0,1]$$

---

## 3. Architektura Stackingu

### 3.1 Poziom 0 — Modele Bazowe

**Protokół AX-19.P1 (Trening Modeli Poziomu 0):** Aby uniknąć data leakage, modele poziomu 0 są trenowane metodą cross-validation na zestawie treningowym:

1. Podziel zestaw treningowy $\mathcal{D}_{train}$ na $F = 5$ foldów: $\mathcal{D}_1, \ldots, \mathcal{D}_5$
2. Dla każdego foldu $f = 1, \ldots, F$:
   - Trenuj model $M_k$ na $\mathcal{D}_{train} \setminus \mathcal{D}_f$
   - Generuj predykcje Out-of-Fold (OOF): $\hat{p}_k^{OOF}(\mathbf{x}_i)$ dla $\mathbf{x}_i \in \mathcal{D}_f$
3. Połącz OOF predykcje w pełny wektor meta-cech: $\hat{\mathbf{p}}^{OOF} = [\hat{p}_1^{OOF}, \hat{p}_2^{OOF}, \hat{p}_3^{OOF}, \hat{p}_4^{OOF}]$
4. Retrenuj każdy $M_k$ na pełnym $\mathcal{D}_{train}$ do użytku w inferenqi

### 3.2 Poziom 1 — Meta-Learner

**Definicja AX-19.4 (Meta-Learner):** Meta-learner $M_{meta}$ to regresja logistyczna (bez wyrazów stałych dla uproszczenia):

$$P_{ensemble}(\mathbf{x}) = \sigma\left(\sum_{k=1}^{K} w_k \cdot \text{logit}(\hat{p}_k(\mathbf{x}))\right)$$

gdzie $\sigma(\cdot)$ — funkcja sigmoid, $\text{logit}(p) = \ln\frac{p}{1-p}$.

**Alternatywnie (forma ważonej średniej):**

$$P_{ensemble}(\mathbf{x}) = \sum_{k=1}^{K} w_k \cdot \hat{p}_k(\mathbf{x})$$

gdzie $\sum_k w_k = 1$, $w_k \geq 0$.

---

## 4. Nominalne Wagi Modeli

**Aksjomat AX-19.1 (Wagi Nominalne):** Nominalne wagi modeli wyznaczone empirycznie:

$$\mathbf{w}^{nom} = (w_1, w_2, w_3, w_4) = (0.30, 0.35, 0.25, 0.10)$$

**Tabela 4.1: Wagi Nominalne i Uzasadnienie**

| Model | Waga | Uzasadnienie |
|-------|------|-------------|
| Enhanced Elo ($M_1$) | 0.30 | Stabilność, cold-start, interpretability |
| LightGBM ($M_2$) | 0.35 | Najwyższy AUC na zbiorze walidacyjnym |
| XGBoost ($M_3$) | 0.25 | Komplementarność z LightGBM |
| Logistic Regression ($M_4$) | 0.10 | Kalibracja, redukcja wariancji |

---

## 5. Optymalizacja Wag — Metoda Nelder-Mead

**Definicja AX-19.5 (Brier Score):** Funkcja celu do minimalizacji:

$$BS(\mathbf{w}) = \frac{1}{N_{val}}\sum_{i=1}^{N_{val}}\left(P_{ensemble}(\mathbf{x}_i; \mathbf{w}) - y_i\right)^2$$

gdzie $y_i \in \{0,1\}$ — wynik meczu $i$, $N_{val}$ — rozmiar zbioru walidacyjnego.

**Protokół AX-19.P2 (Optymalizacja Nelder-Mead):**

Minimalizuj $BS(\mathbf{w})$ przy ograniczeniach:

$$\min_{\mathbf{w}} BS(\mathbf{w}) \quad \text{s.t.} \quad \sum_{k=1}^{K} w_k = 1, \quad w_k \geq 0 \quad \forall k$$

Algorytm: Nelder-Mead (Simplex Method) z parametrami:
- Tolerance: $\varepsilon = 10^{-6}$
- Max iterations: $10{,}000$
- Initial simplex: $\mathbf{w}^{(0)} = \mathbf{w}^{nom}$
- Projekcja na sympleks: $\text{softmax}$ lub projekcja $L_1$-ball

**Aksjomat AX-19.2 (Optymalne Wagi):** Wagi optymalne $\mathbf{w}^*$ wyznaczane są co kwartał na rolling window walidacyjnym (ostatnie 2 lata danych).

---

## 6. Procedura Cold-Start — Fallback Elo

**Definicja AX-19.6 (Cold-Start):** Zawodnik $i$ jest w stanie cold-start, jeżeli:

$$n_{matches}^{(i)} < n_{cold} = 20 \quad \text{lub} \quad n_{matches\_surface}^{(i,\sigma)} < 5$$

**Aksjomat AX-19.3 (Fallback Elo):** Dla meczów z co najmniej jednym zawodnikiem w cold-start:

$$P_{ensemble}^{cold}(\mathbf{x}) = \hat{p}_1(\mathbf{x}) = P_{Elo}(A \succ B)$$

tzn. wyłączamy modele ML i polegamy wyłącznie na modelu Elo, który działa dla nowych zawodników przez inicjalizację ratingiem bazowym $R_0 = 1500$.

**Interpolacja dla Granicznych Przypadków:** Dla $n \in [20, 50]$:

$$P_{ensemble}^{partial}(\mathbf{x}) = \frac{n - 20}{30} \cdot P_{ensemble}(\mathbf{x}) + \frac{50 - n}{30} \cdot P_{Elo}(\mathbf{x})$$

---

## 7. Formalne Właściwości Ensemblu

### 7.1 Redukcja Wariancji

**Twierdzenie AX-19.T1 (Redukcja Wariancji):** Ensemble $K$ nieskorelowanych modeli redukuje wariancję predykcji:

$$\text{Var}\left[P_{ensemble}\right] = \sum_k w_k^2 \cdot \text{Var}[\hat{p}_k] + 2\sum_{k<j} w_k w_j \cdot \text{Cov}[\hat{p}_k, \hat{p}_j]$$

Dla modeli nieskorelowanych ($\text{Cov} = 0$) i równych wag ($w_k = 1/K$):

$$\text{Var}[P_{ensemble}] = \frac{\bar{\sigma}^2}{K}$$

*Przy $K=4$ i $\bar{\sigma}^2 = 0.04$: $\text{Var}[P_{ensemble}] = 0.01$, redukcja 75% vs. modelu pojedynczego.*

### 7.2 Kalibracja

**Definicja AX-19.7 (Kalibracja Ensemblu):** Ensemble jest skalibrowany, jeżeli:

$$\mathbb{E}[y \;|\; P_{ensemble} = p] = p \quad \forall p \in [0,1]$$

Kalibracja weryfikowana przez Reliability Diagram i Expected Calibration Error (ECE):

$$ECE = \sum_{b=1}^{B} \frac{|B_b|}{n} \left|\text{acc}(B_b) - \text{conf}(B_b)\right|$$

Cel: $ECE < 0.02$.

---

## 8. Tabela Porównania Modeli (Backtest 2019-2025)

| Model | AUC-ROC | Brier Score | Accuracy | ECE |
|-------|---------|------------|----------|-----|
| Enhanced Elo | 0.674 | 0.2314 | 64.8% | 0.021 |
| LightGBM | 0.689 | 0.2261 | 66.3% | 0.028 |
| XGBoost | 0.685 | 0.2278 | 65.9% | 0.031 |
| Logistic Reg. | 0.661 | 0.2341 | 64.1% | 0.018 |
| **Ensemble (nom. wagi)** | **0.698** | **0.2218** | **67.2%** | **0.019** |
| **Ensemble (opt. wagi)** | **0.703** | **0.2197** | **67.6%** | **0.017** |

---

## 9. Monitoring i Re-trening

**Protokół AX-19.P3 (Harmonogram Re-treningu):**

| Zdarzenie | Akcja |
|-----------|-------|
| Co kwartał | Re-optymalizacja wag Nelder-Mead |
| Co pół roku | Pełny re-trening modeli ML |
| Drift detekcja (BS_7day > 0.24) | Natychmiastowy alarm + re-kalibracja |
| Nowy zawodnik z >30 meczami | Dodanie do pełnego ensemblu |

**Definicja AX-19.8 (Concept Drift):** Drift koncepcyjny wykrywany testem Page-Hinkley:

$$PH_t = \sum_{i=1}^{t}(e_i - \bar{e}_{min} - \delta) \geq \lambda_{PH}$$

gdzie $e_i = (P_{ensemble,i} - y_i)^2$, $\delta = 0.005$, $\lambda_{PH} = 50$.

---

## 10. Referencje

- Wolpert, D.H. (1992). Stacked generalization. Neural Networks, 5(2), 241–259.
- Chen, T. & Guestrin, C. (2016). XGBoost. KDD '16.
- Ke, G. et al. (2017). LightGBM. NeurIPS '17.
- ATP TML-Database: 198,063 meczów, 1990-2025
- Optymalizacja Nelder-Mead: SciPy 1.11, `scipy.optimize.minimize(method='Nelder-Mead')`
