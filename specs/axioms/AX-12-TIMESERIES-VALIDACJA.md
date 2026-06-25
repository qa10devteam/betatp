# AX-12: TIME-SERIES WALIDACJA — SPECYFIKACJA FORMALNA

**Dokument:** AX-12  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. ZASADA WALK-FORWARD VALIDATION

### Definicja 1.1 — Walk-Forward Validation

W kontekście szeregów czasowych standardowa $k$-krotna kross-walidacja jest **zakazana** (narusza zasadę braku przecieku czasowego). Stosujemy wyłącznie **Walk-Forward Validation** (WFV).

**Definicja formalna:** Niech $\mathcal{D} = \{(x_1, y_1, t_1), \ldots, (x_n, y_n, t_n)\}$ będzie posortowanym chronologicznie zbiorem meczów. Dla liczby podziałów $S$, $s$-ty split definiujemy jako:

$$\mathcal{D}_s^{\text{train}} = \{(x_i, y_i) : t_i < T_s\}$$
$$\mathcal{D}_s^{\text{val}} = \{(x_i, y_i) : T_s \leq t_i < T_s + \Delta_s\}$$

gdzie $T_s$ — punkty podziału (cutoff dates), $\Delta_s$ — długość okna walidacyjnego.

### Aksjomat 1.1 — Monotonia w czasie

$$T_1 < T_2 < T_3 < T_4 < T_5$$
$$\mathcal{D}_s^{\text{train}} \subset \mathcal{D}_{s+1}^{\text{train}} \quad \text{(zbiory treningowe rosną)}$$

---

## 2. SPECYFIKACJA 5 PODZIAŁÓW — ATP 1990–2025

### Definicja 2.1 — Graniczne daty podziałów

| Split | $T_s$ (cutoff) | Zbiór treningowy | Zbiór walidacyjny | $n_{\text{train}}$ | $n_{\text{val}}$ |
|-------|----------------|------------------|-------------------|--------------------|------------------|
| 1 | 2005-01-01 | 1990–2004 | 2005–2008 | ~55,000 | ~12,000 |
| 2 | 2009-01-01 | 1990–2008 | 2009–2012 | ~67,000 | ~13,500 |
| 3 | 2013-01-01 | 1990–2012 | 2013–2016 | ~80,500 | ~14,000 |
| 4 | 2017-01-01 | 1990–2016 | 2017–2020 | ~94,500 | ~14,500 |
| 5 | 2021-01-01 | 1990–2020 | 2021–2024 | ~109,000 | ~12,000 |

**Zbiór testowy (hold-out):** 2025-01-01 — 2025-12-31 (nigdy nie widziany przez model)

### Definicja 2.2 — Okno minimalne

Minimalny rozmiar zbioru treningowego: $n_{\text{train}}^{\min} = 10{,}000$ meczów.  
Minimalna długość okna walidacyjnego: 12 miesięcy.

---

## 3. ZAKAZANE SCENARIUSZE PRZECIEKU DANYCH

### Aksjomat 3.1 — Lista zakazanych operacji

Poniższe operacje są **bezwzględnie zakazane** w systemie betatp.io:

| ID | Scenariusz | Opis naruszenia |
|----|------------|-----------------|
| L01 | Future ranking | Użycie rankingu ATP z daty $\geq t_m$ |
| L02 | Future odds | Użycie closing odds jako cechy predykcyjnej |
| L03 | Future form | EWMA obliczone z meczem $m$ włącznie |
| L04 | Target encoding leak | Enkodowanie kategorii używając $y$ ze zbioru testowego |
| L05 | Scaler leak | Standaryzacja wektora z użyciem statystyk z val/test |
| L06 | H2H leak | Liczenie H2H z wynikiem meczu $m$ |
| L07 | Imputer leak | Imputacja median z całego datasetu (nie tylko train) |
| L08 | Cross-split leak | Użycie split-$k$ do parametryzacji split-$(k-1)$ |
| L09 | Kalibr. leak | Kalibracja (AX-10) na zbiorze testowym |
| L10 | Feature selection leak | Selekcja cech z korelacją do $y$ na całym datasecie |

### Twierdzenie 3.1 — Konsekwencja przecieku

Jeśli jakikolwiek scenariusz z listy L01–L10 jest aktywny, to estymaty metryczne na zbiorze walidacyjnym są **obciążone dodatnio** i nie mogą służyć do oceny modelu.

**Dowód (zasada):** Niech $\mathcal{I}$ = informacja przyszłości włączona do $x$. Wtedy $\mathbb{E}[\text{Acc}(f) | \mathcal{I}] > \mathbb{E}[\text{Acc}(f) | \neg\mathcal{I}]$, bo model uczy się na nieistniejących w produkcji korelacjach. $\square$

---

## 4. METRYKI OCENY MODELU

### Definicja 4.1 — Accuracy

$$\text{Acc} = \frac{1}{n} \sum_{i=1}^{n} \mathbb{1}[\hat{y}_i = y_i]$$

gdzie $\hat{y}_i = \mathbb{1}[\hat{p}_i \geq 0.5]$.

### Definicja 4.2 — Brier Score

$$\text{BS} = \frac{1}{n} \sum_{i=1}^{n} (\hat{p}_i - y_i)^2$$

Brier Skill Score (vs. baseline $\hat{p} = 0.5$):

$$\text{BSS} = 1 - \frac{\text{BS}}{\text{BS}_{\text{ref}}} = 1 - \frac{\text{BS}}{0.25}$$

### Definicja 4.3 — Log-Loss

$$\text{LL} = -\frac{1}{n} \sum_{i=1}^{n} \left[ y_i \ln \hat{p}_i + (1-y_i) \ln(1-\hat{p}_i) \right]$$

### Definicja 4.4 — ROI (Return on Investment)

Niech $\mathcal{B}$ = zbiór zakładów złożonych przez system (po filtrach EV, Kelly):

$$\text{ROI} = \frac{\sum_{b \in \mathcal{B}} \text{profit}_b}{\sum_{b \in \mathcal{B}} \text{stake}_b}$$

### Definicja 4.5 — Closing Line Value (CLV)

Patrz AX-13 dla pełnej definicji. Dla walidacji:

$$\text{CLV}_{\text{mean}} = \frac{1}{|\mathcal{B}|} \sum_{b \in \mathcal{B}} \text{CLV}_b$$

### Definicja 4.6 — AUC-ROC

$$\text{AUC} = P(\hat{p}_{y=1} > \hat{p}_{y=0})$$

---

## 5. MINIMALNE PROGI AKCEPTOWALNOŚCI

### Twierdzenie 5.1 — Progi wydajności systemu betatp.io

Model jest akceptowalny do wdrożenia produkcyjnego wtedy i tylko wtedy gdy spełnia WSZYSTKIE poniższe warunki na zbiorze walidacyjnym (uśrednione po 5 splitach):

| Metryka | Próg minimalny | Próg docelowy | Uwagi |
|---------|---------------|---------------|-------|
| Accuracy | ≥ 0.630 | ≥ 0.660 | Benchmark Elo: ~0.630 |
| Brier Score | ≤ 0.220 | ≤ 0.205 | Niższy = lepszy |
| BSS | ≥ 0.040 | ≥ 0.080 | vs. losowy baseline |
| Log-Loss | ≤ 0.620 | ≤ 0.595 | Niższy = lepszy |
| AUC-ROC | ≥ 0.670 | ≥ 0.700 | |
| ECE | ≤ 0.030 | ≤ 0.020 | (AX-10) |
| CLV_mean | ≥ 0.005 | ≥ 0.015 | +0.5% per zakład |
| ROI (symulacja) | ≥ -0.01 | ≥ 0.05 | Na zakładach EV>3% |

### Definicja 5.1 — Niestabilność modelu

Model jest oznaczony jako **niestabilny** jeśli odchylenie standardowe Accuracy po 5 splitach przekracza:

$$\sigma_{\text{Acc}} > 0.025$$

Niestabilny model wymaga dodatkowej regularyzacji lub rewizji feature engineeringu.

---

## 6. PROCEDURA WALIDACJI WALK-FORWARD

### Algorytm WFV

```
WEJŚCIE: D — pełny dataset chronologiczny
         S = 5 — liczba splitów
         M — architektura modelu

WYJŚCIE: metryki[s] dla s=1,...,5

DLA s = 1 DO 5:
  1. Zdefiniuj D_train_s = {(x_i, y_i, t_i) : t_i < T_s}
  2. Zdefiniuj D_val_s   = {(x_i, y_i, t_i) : T_s <= t_i < T_s + Δ_s}
  
  3. FE Pipeline (TYLKO na D_train_s):
     a. Oblicz EWMA params (μ, σ dla standaryzacji)
     b. Oblicz H2H histories
     c. Oblicz Elo ratings (iteracyjnie w czasie)
  
  4. Trenuj M na D_train_s → M_s
  
  5. Kalibracja (AX-10):
     a. D_cal = ostatnie 20% D_train_s
     b. Dopasuj kalibrator g_s
  
  6. Predykcja: ĥ_i = g_s(M_s(x_i)) dla (x_i, y_i) ∈ D_val_s
  
  7. Oblicz metryki_s: Acc, BS, LL, AUC, CLV

AGREGACJA:
  mean_metric = average(metryki[1..5])
  std_metric  = std(metryki[1..5])
  
WALIDACJA progów z § 5.1
```

---

## 7. ZBIÓR TESTOWY (HOLD-OUT)

### Aksjomat 7.1 — Izolacja zbioru testowego

Zbiór testowy (2025) jest używany **jednorazowo**, po finalnym wyborze modelu. Zabronione jest:
- Używanie test set do tuningu hiperparametrów
- Wielokrotne ewaluacje na test set (data snooping)
- Zmiana progu decyzyjnego po obejrzeniu wyników test

### Definicja 7.1 — Protokół test set

```
1. Zablokuj dostęp do D_test przed finalizacją modelu
2. Trenuj na D_train = D_{1990..2024}
3. Ewaluuj metryki TYLKO RAZ na D_test
4. Zapisz wyniki do immutable logu
```

---

## 8. ANALIZA STABILNOŚCI TEMPORALNEJ

### Definicja 8.1 — Temporal Drift

**Drift** jest wykrywany gdy:

$$|\text{Acc}_{s+1} - \text{Acc}_s| > 0.03 \quad \text{dla dowolnego } s$$

Drift sygnalizuje zmianę struktury danych (np. zmiana stylu gry w erze ATP).

### Znane punkty przełomowe w danych ATP

| Okres | Zmiana strukturalna |
|-------|---------------------|
| 1998–2002 | Dominacja serwis-wole, wzrost wysokich zawodników |
| 2003–2010 | Era Federer–Nadal, specjalizacja nawierzchniowa |
| 2011–2016 | Dominacja Djokovic, wydłużenie wymian |
| 2017–2020 | Wzrost generacji Zverev/Tsitsipas |
| 2021–2025 | Era Alcaraz/Sinner, powrót do agresywnego tenisa |

Modele trenowane wyłącznie na danych pre-2003 mogą mieć systematyczny drift na danych post-2017.

---

## 9. REFERENCJE

1. Bergmeir, C., Benítez, J.M. (2012). "On the use of cross-validation for time series predictor evaluation." *Information Sciences*, 191, 192–213.
2. Roberts, D.R. et al. (2017). "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure." *Ecography*, 40(8), 913–929.
3. Racine, J. (2000). "Consistent cross-validatory model-selection for dependent data." *Journal of Econometrics*, 99(2), 379–399.
4. Sackmann, J. (2015). "Tennis Abstract: ATP Match Statistics." tennis-abstract.com — dataset 1968–2024.
5. Kovalchik, S. (2020). "Extension of the Elo rating system to margin of victory in tennis." *International Journal of Forecasting*, 36(4).

---

*Dokument AX-12 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
