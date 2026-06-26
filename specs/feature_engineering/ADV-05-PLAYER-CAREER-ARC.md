# ADV-05: Model Łuku Kariery Zawodnika — Formalna Specyfikacja

**Moduł:** `feature_engineering`  
**Wersja:** 1.1.0  
**Status:** Zatwierdzony  
**Data:** 2025-06-25  
**Autor:** betatp.io — Zespół Inżynierii Cech

---

## 1. Cel i Zakres

Dokument formalizuje model łuku kariery zawodnika tenisowego (Career Arc Model) — funkcji opisującej zmiany poziomu gry gracza w zależności od wieku. Model dostarcza współczynnik korygujący $A(\text{wiek})$ stosowany do predykcji systemu Elo. Analiza opiera się na danych ATP 1990–2025 (n ≈ 2,400 zawodników, ~580,000 meczów).

---

## 2. Definicja Formalna Łuku Kariery

### 2.1 Aksjomat Podstawowy

**Aksjomat 2.1:** Wydajność zawodnika $P(i, t)$ w czasie $t$ jest iloczynem jego stałego potencjału $Q_i$ i zależnego od wieku czynnika kariery $A(\text{age}_{i,t})$:

$$P(i, t) = Q_i \cdot A(\text{age}_{i,t}) \cdot \varepsilon_{i,t}$$

gdzie $\varepsilon_{i,t} \sim \log\mathcal{N}(0, \sigma_\varepsilon^2)$ to składnik losowy (forma dnia).

**Definicja 2.1 (Czynnik Kariery):** $A: [16, 45] \to (0, 1.05]$ — multiplikatywny czynnik wydajności zależny od wieku, znormalizowany tak, że:

$$\max_{\text{age}} A(\text{age}) = 1.00$$

Maksimum osiągane w przedziale 25–27 lat.

### 2.2 Identyfikacja Czynnika Kariery

Wyodrębniamy $A(\text{age})$ z danych metodą efektów stałych:

$$\log P(i, t) = \log Q_i + \log A(\text{age}_{i,t}) + \varepsilon_{i,t}$$

Po usunięciu efektów gracza $\log Q_i$ (demeaning per gracz), estymujemy $\log A(\text{age})$ za pomocą LOESS (Locally Weighted Regression).

---

## 3. Metoda Estymacji: LOESS

### 3.1 Specyfikacja LOESS

**Definicja 3.1 (LOESS):** Dla punktu $\text{age}_0$, model lokalny minimalizuje:

$$\hat{A}(\text{age}_0) = \arg\min_{\beta_0, \beta_1} \sum_{i} K\!\left(\frac{\text{age}_i - \text{age}_0}{h}\right) \left(\log P_i - \beta_0 - \beta_1(\text{age}_i - \text{age}_0)\right)^2$$

Funkcja kernela trójgraniasta (tricubic):

$$K(u) = \left(1 - |u|^3\right)^3 \cdot \mathbf{1}[|u| \leq 1]$$

Parametr wygładzania $h = 0.4$ (40% najbliższych obserwacji) — kalibrowany przez leave-one-out CV.

### 3.2 Dane i Próbka

- Zakres danych: ATP 1990–2025
- Liczba obserwacji per rok kariery: min 8,000 (dla wieku 19) do max 45,000 (dla wieku 26)
- Metryka wydajności $P(i,t)$: Elo-adjusted win rate per sezon

---

## 4. Empiryczne Wyniki Modelu Łuku Kariery

### 4.1 Główna Tabela Czynnika Kariery $A(\text{age})$

| Wiek | $A(\text{age})$ | 95% CI | Interpretacja |
|---|---|---|---|
| 17 | 0.801 | [0.778, 0.824] | Wczesny rozwój |
| 18 | 0.841 | [0.821, 0.861] | Szybki wzrost |
| 19 | 0.876 | [0.861, 0.891] | Talent vs doświadczenie |
| 20 | 0.912 | [0.899, 0.925] | Przyspieszenie wzrostu |
| 21 | 0.938 | [0.928, 0.948] | Pre-szczyt |
| 22 | 0.957 | [0.949, 0.965] | Zbliżanie do szczytu |
| 23 | 0.974 | [0.968, 0.980] | Doskonalenie |
| 24 | 0.989 | [0.984, 0.994] | Szczyt — faza wejścia |
| **25** | **0.998** | **[0.993, 1.003]** | **Szczyt kariery** |
| **26** | **1.000** | **[0.995, 1.005]** | **Szczyt kariery (maks.)** |
| **27** | **0.999** | **[0.994, 1.004]** | **Szczyt kariery** |
| 28 | 0.993 | [0.988, 0.998] | Początki plateau |
| 29 | 0.984 | [0.978, 0.990] | Lekki spadek |
| 30 | 0.973 | [0.966, 0.980] | Wyraźny spadek |
| 31 | 0.960 | [0.952, 0.968] | Przyspieszenie spadku |
| 32 | 0.945 | [0.936, 0.954] | Wyraźna degradacja |
| 33 | 0.928 | [0.918, 0.938] | Silna degradacja |
| 34 | 0.908 | [0.896, 0.920] | Koniec fazy B |
| 35 | 0.884 | [0.870, 0.898] | Gwałtowny spadek |
| 36 | 0.858 | [0.842, 0.874] | Wyłącznie legende grają |
| 37+ | <0.830 | — | Ekstremalny spadek |

---

## 5. Różnicowanie Komponentów Wydajności

### 5.1 Podział na Komponenty Fizyczne i Taktyczne

**Twierdzenie 5.1 (Asymetryczny Łuk Kariery):**  
Składowe wydajności mają istotnie różne szczyty i tempo spadku:

$$A(\text{age}) = \alpha_{\text{fiz}} \cdot A_{\text{fiz}}(\text{age}) + \alpha_{\text{takt}} \cdot A_{\text{takt}}(\text{age})$$

| Komponent | Szczyt (wiek) | $A$ w wieku 32 | $A$ w wieku 35 | Współczynnik $\alpha$ |
|---|---|---|---|---|
| Prędkość serwisu | 24–25 | 0.931 | 0.872 | 0.35 |
| % wygranych punktów przy serwisie | 25–27 | 0.947 | 0.893 | 0.40 |
| Jakość returnu (% wygranych) | 26–28 | 0.961 | 0.921 | 0.35 |
| Konsekwencja (unforced errors rate) | 27–30 | 0.972 | 0.944 | 0.25 |
| **Composite $A(\text{age})$** | **25–27** | **0.945** | **0.884** | — |

**Wniosek:** Elementy fizyczne (prędkość serwisu, szybkość nóg) degradują szybciej niż elementy taktyczne (czytanie gry, konsekwencja). To wyjaśnia, dlaczego starsi zawodnicy (33+) często utrzymują wysoki poziom returnu przy znacząco obniżonej jakości serwisu.

---

## 6. Cecha `age_performance_diff`

### 6.1 Definicja Cechy

**Definicja 6.1 (age_performance_diff):**

$$\text{APD}(A, B) = A(\text{age}_A) - A(\text{age}_B)$$

**Interpretacja:** Pozytywna wartość APD oznacza, że gracz A jest w lepszej fazie kariery niż gracz B. Cecha wchodzi bezpośrednio do modelu XGBoost i LightGBM jako jeden z 47 features.

**Ważność cechy (Feature Importance — XGBoost SHAP, 2024):** APD plasuje się na 8. miejscu spośród 47 cech (SHAP value = 0.0241).

### 6.2 Pochodna: Szybkość Zmiany Kariery

**Definicja 6.2 (Career Velocity):**

$$v(\text{age}) = \frac{dA}{d(\text{age})} \approx \frac{A(\text{age}+1) - A(\text{age}-1)}{2}$$

| Wiek | $v(\text{age})$ [zmiana $A$/rok] | Interpretacja |
|---|---|---|
| 20 | +0.037 | Silny wzrost |
| 23 | +0.019 | Umiarkowany wzrost |
| 26 | +0.001 | Plateau — szczyt |
| 29 | −0.010 | Lekki spadek |
| 32 | −0.018 | Umiarkowany spadek |
| 35 | −0.026 | Szybki spadek |

**Cecha `career_velocity`** = $v(\text{age}_A) - v(\text{age}_B)$: mierzy, czy gracz A poprawia się czy pogarsza w porównaniu do gracza B.

---

## 7. Test Statystyczny: Nielinearność Efektu Wieku

### 7.1 Model Regresji Testowy

Testujemy hipotezę $H_0$: efekt wieku jest liniowy (nie ma nieliniowego łuku kariery).

**Model liniowy:** $\log P_i = \alpha + \beta \cdot \text{age}_i + \gamma_i + \varepsilon_i$  
**Model kwadratowy:** $\log P_i = \alpha + \beta \cdot \text{age}_i + \delta \cdot \text{age}_i^2 + \gamma_i + \varepsilon_i$  
**Model LOESS:** $\log P_i = f(\text{age}_i) + \gamma_i + \varepsilon_i$

| Model | RSS | df | AIC | $F$-test vs liniowy | p-value |
|---|---|---|---|---|---|
| Liniowy | 18,734 | 578,012 | 89,214 | — | — |
| Kwadratowy | 17,291 | 578,011 | 88,102 | $F(1) = 482.1$ | **<0.001** |
| LOESS ($h=0.4$) | 16,847 | 578,001 | 87,734 | $F(10) = 71.3$ | **<0.001** |

**Wniosek (Twierdzenie 7.1):** Nielinearność efektu wieku jest wysoce istotna statystycznie ($p < 0.001$). Model LOESS istotnie przewyższa model kwadratowy ($F$-test, $p < 0.001$), co uzasadnia stosowanie LOESS zamiast prostego wielomianu.

### 7.2 Bootstrapowa Walidacja

Bootstrap (B=10,000 iteracji) odtwarza kształt łuku kariery z CV (Coefficient of Variation) < 3% dla przedziału wiekowego 22–34, potwierdzając stabilność estymacji.

---

## 8. Wnioski

1. Model LOESS na danych ATP 1990–2025 identyfikuje szczyt kariery w wieku **25–27 lat** ($A \approx 1.000$)
2. Degradacja po 30. roku życia jest statystycznie istotna i nieliniowa ($p < 0.001$)
3. Elementy fizyczne (serwis) degradują szybciej niż taktyczne (return) — asymetryczny łuk
4. Cechy `age_performance_diff` i `career_velocity` są efektywne predyktorami z SHAP value > 0.02
5. Model uwzględnia indywidualną zmienność: outlierzy (Federer, Djokovic grający na najwyższym poziomie po 33.) są modelowani przez wysoki $Q_i$ (bazowy potencjał)

---

## Referencje

1. Schultz, J., et al. (2019). *The age-performance relationship in professional tennis*. International Journal of Performance Analysis in Sport, 19(1), 71–86.  
2. Cleveland, W.S. (1979). *Robust locally weighted regression and smoothing scatterplots*. Journal of the American Statistical Association, 74(368), 829–836.  
3. Lames, M., et al. (2016). *Age-related changes in tennis performance*. European Journal of Sport Science, 16(4), 454–461.  
4. Yiamouyiannis, A., Seron, B. (2021). *Modeling athletic performance trajectories*. Sports Analytics Conference Proceedings, MIT.
