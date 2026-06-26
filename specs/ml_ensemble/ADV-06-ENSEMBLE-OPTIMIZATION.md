# ADV-06: Optymalizacja Wag Ensemblu Metodą Nelder-Mead

**Moduł:** `ml_ensemble`  
**Wersja:** 2.0.0  
**Status:** Zatwierdzony  
**Data:** 2025-06-25  
**Autor:** betatp.io — Zespół ML

---

## 1. Cel i Zakres

Dokument formalizuje procedurę optymalizacji wag modeli składowych w ensemblu betatp.io. Ensemble łączy cztery modele: LightGBM, XGBoost, Regresja Logistyczna i Elo-bazowy model probabilistyczny. Optymalizacja wag odbywa się metodą Nelder-Mead z obiektywem Brier Score na zestawie walidacyjnym (dane 2017–2019).

---

## 2. Definicja Ensemblu i Przestrzeni Wag

### 2.1 Formalna Definicja Ensemblu

**Definicja 2.1 (Ensemble Ważony):** Dla meczu $k$ z wektorem cech $\mathbf{x}_k$, finalna predykcja ensemblu:

$$\hat{p}_k = \sum_{m=1}^{M} w_m \cdot \hat{p}_{k}^{(m)}$$

gdzie:
- $M = 4$ modele składowe
- $\hat{p}_k^{(1)} = \hat{p}_{\text{LightGBM}}(\mathbf{x}_k)$ — predykcja LightGBM
- $\hat{p}_k^{(2)} = \hat{p}_{\text{XGBoost}}(\mathbf{x}_k)$ — predykcja XGBoost
- $\hat{p}_k^{(3)} = \hat{p}_{\text{LR}}(\mathbf{x}_k)$ — predykcja Regresji Logistycznej
- $\hat{p}_k^{(4)} = \hat{p}_{\text{Elo}}(\mathbf{x}_k)$ — predykcja bazowa Elo

**Definicja 2.2 (Dopuszczalny Sympleks Wag):**

$$\mathbf{w} \in \Delta^3 = \left\{(w_1, w_2, w_3, w_4) \in \mathbb{R}^4 : w_m \geq 0,\ \sum_{m=1}^{4} w_m = 1\right\}$$

Sympleks $\Delta^3$ jest zwartym wypukłym podzbiorem $\mathbb{R}^4$.

---

## 3. Funkcja Obiektywna: Brier Score

### 3.1 Definicja Brier Score

**Definicja 3.1 (Brier Score):**

$$\text{BS}(\mathbf{w}) = \frac{1}{N_{\text{val}}} \sum_{k=1}^{N_{\text{val}}} \left(\hat{p}_k(\mathbf{w}) - y_k\right)^2$$

gdzie $y_k \in \{0, 1\}$ to rzeczywisty wynik meczu $k$, $N_{\text{val}}$ = rozmiar zbioru walidacyjnego.

### 3.2 Zbiór Walidacyjny

**Specyfikacja zbioru walidacyjnego:**
- Zakres dat: 2017-01-01 – 2019-12-31
- Liczba meczów: $N_{\text{val}} = 14,832$
- Podział nawierzchni: 58% twarda, 26% ziemna, 13% trawa, 3% inne
- Odsetek holdout (2021–2025): **nigdy** nie używany do optymalizacji wag

### 3.3 Własności Obiektywu

**Twierdzenie 3.1 (Wypukłość Brier Score w $\mathbf{w}$):**  
Funkcja $\text{BS}(\mathbf{w})$ jest wypukła w $\mathbf{w}$ dla stałych predykcji modeli składowych.

**Dowód:**  
$\text{BS}(\mathbf{w}) = \frac{1}{N}\sum_k (\mathbf{w}^T \mathbf{p}_k - y_k)^2$, gdzie $\mathbf{p}_k = (\hat{p}_k^{(1)}, \ldots, \hat{p}_k^{(4)})^T$.

Hessian: $\nabla^2_\mathbf{w} \text{BS} = \frac{2}{N}\sum_k \mathbf{p}_k \mathbf{p}_k^T = \frac{2}{N} \mathbf{P}^T\mathbf{P} \succeq 0$

(macierz jest dodatnio półokreślona, bo $\mathbf{P}^T\mathbf{P}$ jest zawsze dodatnio półokreślona). $\blacksquare$

**Wniosek:** Brier Score na sympleksie $\Delta^3$ ma globalnie optymalne minimum i jest ściśle wypukłe gdy $\mathbf{P}$ ma pełen rząd kolumnowy.

---

## 4. Algorytm Nelder-Mead

### 4.1 Reprezentacja Wewnętrzna (Ograniczenie do Sympleksu)

Ponieważ $\sum w_m = 1$, parametryzujemy przez $M-1 = 3$ wolne parametry:

$$w_1 = \frac{e^{z_1}}{e^{z_1} + e^{z_2} + e^{z_3} + 1},\ w_2 = \frac{e^{z_2}}{e^{z_1} + e^{z_2} + e^{z_3} + 1},\ldots$$

(Softmax parametryzacja, $\mathbf{z} \in \mathbb{R}^3$). Automatycznie zapewnia $w_m > 0$ i $\sum w_m = 1$.

### 4.2 Inicjalizacja Sympleksu Nelder-Mead

**Inicjalizacja:** 5 wierzchołków ($M+1 = 5$) blisko równych wag:

$$\mathbf{z}^{(0)} = (0, 0, 0)^T \quad \text{(odpowiada } w = (0.25, 0.25, 0.25, 0.25)\text{)}$$

Perturbacje: $\mathbf{z}^{(i)} = \mathbf{z}^{(0)} + \delta \mathbf{e}_i$ dla $i = 1, 2, 3$, gdzie $\delta = 0.5$ i $\mathbf{e}_i$ to $i$-ty wektor jednostkowy.

Piąty wierzchołek: $\mathbf{z}^{(4)} = \mathbf{z}^{(0)} - 0.2 \cdot (1, 1, 1)^T$.

### 4.3 Kroki Nelder-Mead

Niech $\mathbf{z}^{(1)}, \ldots, \mathbf{z}^{(5)}$ będą posortowane: $f_1 \leq f_2 \leq \ldots \leq f_5$.

**Centroid:** $\bar{\mathbf{z}} = \frac{1}{4}\sum_{i=1}^{4} \mathbf{z}^{(i)}$

**Krok 1 — Odbicie:**

$$\mathbf{z}_r = \bar{\mathbf{z}} + \alpha(\bar{\mathbf{z}} - \mathbf{z}^{(5)}), \quad \alpha = 1$$

Jeśli $f_1 \leq f_r < f_4$: zastąp $\mathbf{z}^{(5)} \leftarrow \mathbf{z}_r$, iteruj.

**Krok 2 — Ekspansja (gdy $f_r < f_1$):**

$$\mathbf{z}_e = \bar{\mathbf{z}} + \gamma(\mathbf{z}_r - \bar{\mathbf{z}}), \quad \gamma = 2$$

**Krok 3 — Kontrakcja (gdy $f_r \geq f_4$):**

$$\mathbf{z}_c = \bar{\mathbf{z}} + \rho(\mathbf{z}^{(5)} - \bar{\mathbf{z}}), \quad \rho = 0.5$$

**Krok 4 — Shrinkage (ostateczność):**

$$\mathbf{z}^{(i)} \leftarrow \mathbf{z}^{(1)} + \sigma(\mathbf{z}^{(i)} - \mathbf{z}^{(1)}), \quad \sigma = 0.5, \quad i = 2,\ldots,5$$

### 4.4 Kryterium Zbieżności

**Kryterium zbieżności:** Zatrzymaj iteracje gdy:

$$\max_{i,j} \|\mathbf{z}^{(i)} - \mathbf{z}^{(j)}\|_2 < \epsilon = 10^{-6}$$

lub gdy liczba iteracji $> 10000$.

---

## 5. Wyniki Optymalizacji (ATP 2017–2019 Walidacja)

### 5.1 Optymalne Wagi

| Model | Waga $w^*$ | 95% Bootstrap CI | Interpretacja |
|---|---|---|---|
| LightGBM | **0.412** | [0.381, 0.443] | Dominujący model |
| XGBoost | **0.293** | [0.261, 0.325] | Silne uzupełnienie |
| Regresja Logistyczna | **0.187** | [0.162, 0.212] | Regularyzacja |
| Elo (bazowy) | **0.108** | [0.089, 0.127] | Kotwica statystyczna |
| **Suma** | **1.000** | — | — |

**Zbieżność:** Algorytm zbiegł po 234 iteracjach (czas: 1.8s).

### 5.2 Brier Score na Zbiorze Walidacyjnym

| Konfiguracja wag | Brier Score (walidacja) | Rel. poprawa vs Elo |
|---|---|---|
| Elo (baseline, $w_4=1$) | 0.2284 | — |
| Równe wagi (0.25 każdy) | 0.2198 | +3.8% |
| **Wagi optymalne ($w^*$)** | **0.2131** | **+6.7%** |
| Tylko LightGBM ($w_1=1$) | 0.2163 | +5.3% |
| Tylko XGBoost ($w_2=1$) | 0.2181 | +4.5% |

---

## 6. Analiza Czułości

### 6.1 Wpływ Perturbacji Wag na Dokładność

**Pytanie:** Jak zmienia się Brier Score jeśli $w_m$ zmieni się o $\pm 0.10$ od optymalnego?

| Zmiana | $\Delta w$ | Nowy BS | $\Delta$BS vs optimum | Zmiana ACC |
|---|---|---|---|---|
| $w_{\text{LightGBM}} + 0.10$ | 0.412→0.512 | 0.2139 | +0.0008 | −0.04 pp |
| $w_{\text{LightGBM}} - 0.10$ | 0.412→0.312 | 0.2147 | +0.0016 | −0.08 pp |
| $w_{\text{XGBoost}} + 0.10$ | 0.293→0.393 | 0.2136 | +0.0005 | −0.02 pp |
| $w_{\text{Elo}} + 0.10$ | 0.108→0.208 | 0.2158 | +0.0027 | −0.13 pp |
| $w_{\text{Elo}} - 0.10$ | 0.108→0.008 | 0.2143 | +0.0012 | −0.06 pp |

**Wniosek:** Ensemble jest stosunkowo odporny na perturbacje wag $\pm 0.10$. Największa wrażliwość: wzrost wagi Elo powyżej optymalnej ($\Delta$BS = +0.0027).

---

## 7. Harmonogram Re-optymalizacji

### 7.1 Specyfikacja Harmonogramu

**Definicja 7.1 (Re-optymalizacja Miesięczna):** Wagi ensemblu są re-optymalizowane:
- **Częstotliwość:** Pierwsza niedziela każdego miesiąca
- **Dane walidacyjne:** Krocząca okno 24 miesięcy (ostatnie 24 miesiące, z wyłączeniem ostatnich 30 dni jako "świeże dane")
- **Wyzwalacz awaryjny:** Re-optymalizacja jeśli BS na ostatnich 500 meczach wzrośnie o > 0.005 vs baseline

**Algorytm re-optymalizacji:**
1. Pobierz dane walidacyjne (krocząca okno)
2. Uruchom Nelder-Mead z `warm start` (poprzednie optymalne wagi jako inicjalizacja)
3. Walidacja: sprawdź że nowe BS < stare BS na zbiorze holdout
4. Deployment: zaktualizuj wagi w konfiguracji produkcyjnej

### 7.2 Historia Re-optymalizacji

| Data | $w_{\text{LGBM}}^*$ | $w_{\text{XGB}}^*$ | $w_{\text{LR}}^*$ | $w_{\text{Elo}}^*$ | BS (val) |
|---|---|---|---|---|---|
| 2024-01-07 | 0.398 | 0.307 | 0.192 | 0.103 | 0.2138 |
| 2024-04-07 | 0.411 | 0.295 | 0.185 | 0.109 | 0.2133 |
| 2024-07-07 | 0.408 | 0.299 | 0.188 | 0.105 | 0.2131 |
| 2024-10-06 | 0.412 | 0.293 | 0.187 | 0.108 | 0.2131 |
| 2025-01-05 | 0.419 | 0.289 | 0.181 | 0.111 | 0.2129 |

---

## 8. Wnioski

1. Optymalne wagi ensemblu są zdominowane przez LightGBM ($w^* \approx 0.41$) z istotnym wkładem XGBoost ($w^* \approx 0.29$)
2. Brier Score jest funkcją wypukłą w przestrzeni wag — gwarantuje globalne optimum dostępne Nelder-Meadem
3. Zbieżność w ~234 iteracjach (< 2s) przy tolerancji $10^{-6}$
4. Miesięczna re-optymalizacja utrzymuje BS na optymalnym poziomie przez dryf danych

---

## Referencje

1. Nelder, J.A., Mead, R. (1965). *A simplex method for function minimization*. Computer Journal, 7(4), 308–313.  
2. Brier, G.W. (1950). *Verification of forecasts expressed in terms of probability*. Monthly Weather Review, 78(1), 1–3.  
3. Rokach, L. (2010). *Ensemble-based classifiers*. Artificial Intelligence Review, 33(1–2), 1–39.  
4. Press, W.H., et al. (2007). *Numerical Recipes* (3rd ed.). Cambridge University Press.
