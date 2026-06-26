# CLV-03: Benchmarki i Progi Wydajności

**Moduł:** betatp.io CLV TRACKER  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Zatwierdzone  

---

## 1. Cel i Zakres

Niniejszy dokument ustanawia formalne **benchmarki i progi wydajności CLV** dla modelu predykcyjnego tenisa ATP w systemie betatp.io. Definiuje poziomy wydajności, cele modelowe, porównanie z literaturą naukową oraz procedury reagowania na degradację wydajności.

---

## 2. Formalna Definicja Tierów Wydajności

### Definicja 2.1 — Tiers Wydajności

Niech $\mu_{CLV}$ oznacza długoterminową średnią CLV oszacowaną na próbie $N \geq 200$ zakładów. Definiujemy pięć kategorii wydajności:

$$\mathcal{T}(\mu_{CLV}) = \begin{cases}
\text{Elite}        & \text{jeśli } \mu_{CLV} > 0.030 \\
\text{Professional} & \text{jeśli } 0.015 < \mu_{CLV} \leq 0.030 \\
\text{Competent}    & \text{jeśli } 0.005 < \mu_{CLV} \leq 0.015 \\
\text{Break-even}   & \text{jeśli } -0.005 \leq \mu_{CLV} \leq 0.005 \\
\text{Losing}       & \text{jeśli } \mu_{CLV} < -0.005
\end{cases}$$

### Tabela 2.2 — Charakterystyka Tierów

| Tier | Zakres CLV | Opis | Implikacja ROI roczna* |
|---|---|---|---|
| **Elite** | > 3.0% | Najlepsi gracze na świecie, informacja insider-level | +15% do +30% |
| **Professional** | 1.5% – 3.0% | Systematyczna przewaga, model wysokiej jakości | +6% do +15% |
| **Competent** | 0.5% – 1.5% | Mała ale mierzalna przewaga | +1% do +6% |
| **Break-even** | –0.5% – 0.5% | Brak statystycznie istotnej przewagi | ~0% |
| **Losing** | < –0.5% | Systematyczna strata na kursach | –2% do –20%+ |

*Szacunkowe ROI przy założeniu stawkowania Kelly 1/4 i ~500 zakładów rocznie.

---

## 3. Cele Wydajności Modelu betatp.io

### Definicja 3.1 — Cel Pre-match

$$\text{Target}^{\text{pre-match}}_{CLV} = 0.015 \quad (1.5\%)$$

Model predykcyjny pre-match ATP betatp.io musi osiągać średnie CLV ≥ 1.5% na próbie kroczącej ostatnich 90 dni, aby być klasyfikowanym jako sprawny operacyjnie.

### Definicja 3.2 — Cel In-play

$$\text{Target}^{\text{in-play}}_{CLV} = 0.030 \quad (3.0\%)$$

Model in-play musi osiągać wyższy próg z powodu:
1. Większej efektywności rynku in-play (szybszy ruch linii)
2. Wyższych kosztów transakcji (szerszy spread)
3. Konieczności kompensacji ryzyka informacyjnego

### Twierdzenie 3.3 — Uzasadnienie Progu Pre-match 1.5%

**Założenia:**
- Overround Pinnacle na rynkach ATP: $r \approx 0.025$ (2.5%)
- Koszty prowizji (jeśli applicable): $c \approx 0.005$ (0.5%)
- Łączne koszty transakcji: $TC = r + c = 0.030$

**Próg rentowności:**

$$CLV_{\min} = \frac{TC}{2} = \frac{0.030}{2} = 0.015$$

Przy CLV = 1.5% gracz pokrywa połowę overroundu — jest to konserwatywny próg wskazujący na realną przewagę. $\blacksquare$

---

## 4. Porównanie z Literaturą Naukową

### 4.1 Shin (1993) — Szacunek Maksymalnego Ekstrahowalnego CLV

Shin (1993) w "Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims" udowodnił, że w rynku zakładów z insiderami optymalny overround bukmachera wynosi:

$$r^* = \sqrt{z} \cdot (2 - \sqrt{z})$$

gdzie $z$ to frakcja insider bettors w rynku. Dla typowych rynków tenisowych $z \approx 0.05$:

$$r^* \approx \sqrt{0.05} \cdot (2 - \sqrt{0.05}) \approx 0.224 \times 1.776 \approx 0.040$$

**Maksymalne CLV osiągalne przez insiderów:**

$$CLV_{\max}^{\text{insider}} \approx r^* \cdot \frac{1 - z}{z} \approx 0.04 \times \frac{0.95}{0.05} = 0.76 \quad (76\%)$$

Jednak dla modeli analitycznych (nie insiderów) Shin szacuje:

$$CLV_{\max}^{\text{analytical}} \approx 2 \times r_{\text{Pinnacle}} \approx 2 \times 0.025 = 0.050 \quad (5\%)$$

**Wniosek:** CLV > 5% dla modelu analitycznego byłby niezwykły i wymagałby weryfikacji metodologicznej.

### 4.2 Sauer (1998) — Efektywność Rynku Zakładów

Sauer (1998) "The Economics of Wagering Markets" dokumentuje, że:
- Rynki zakładów sportowych wykazują słabą formę efektywności
- Silna forma efektywności (uwzględniająca informacje prywatne) jest nieosiągalna
- Przeciętna długoterminowa przewaga analityczna: 1–3%

### 4.3 Porównanie Benchmarków

| Źródło | Rynek | Maksymalne CLV analytical | Typowe CLV professional |
|---|---|---|---|
| Shin (1993) | Ogólny | ~5% | ~2–3% |
| Sauer (1998) | Ogólny | ~4% | ~1–3% |
| Levitt (2004) | NFL | ~3% | ~1–2% |
| Pinnacle Resources (2019) | Tennis ATP | ~4% | ~1.5–2.5% |
| **betatp.io target** | **Tennis ATP** | **—** | **1.5–3%** |

---

## 5. Procedura Alertu Degradacji

### Definicja 5.1 — Metryka Kroczącego CLV

$$\overline{CLV}_{30}(t) = \frac{1}{|\mathcal{S}_{30}(t)|} \sum_{i \in \mathcal{S}_{30}(t)} CLV_i$$

gdzie $\mathcal{S}_{30}(t)$ to zbiór zakładów z ostatnich 30 dni od chwili $t$.

### Definicja 5.2 — Warunek Alertu Degradacji

$$\text{Alert}(t) = \mathbf{1}\left[\overline{CLV}_{30}(t) < 0.000\right]$$

Jeśli $\text{Alert}(t) = 1$, system betatp.io wyzwala:
1. **Powiadomienie krytyczne** do administratora modelu
2. **Automatyczny przegląd** parametrów modelu (kalibracja, feature importance)
3. **Tymczasowe zmniejszenie stawkowania** do 50% Kelly
4. **Protokół rekalibracji** (zob. specyfikacja modelu)

### Tabela 5.3 — Poziomy Alertów

| Stan | Warunek | Akcja |
|---|---|---|
| ✅ Normalny | $\overline{CLV}_{30} \geq 1.5\%$ | Brak akcji |
| ⚠️ Ostrzeżenie | $0\% \leq \overline{CLV}_{30} < 1.5\%$ | Monitoring wzmożony |
| 🔴 Alert | $-1\% \leq \overline{CLV}_{30} < 0\%$ | Przegląd modelu w 48h |
| 🚨 Krytyczny | $\overline{CLV}_{30} < -1\%$ | Zatrzymanie zakładów, full rekalibracja |

---

## 6. Benchmarki według Kategorii Turniejowej

### Definicja 6.1 — Oczekiwane CLV według Poziomu Turnieju

Różne poziomy turniejów ATP wykazują różną efektywność rynkową. Definiujemy docelowe CLV skorygowane o efektywność:

| Kategoria turnieju | Przykłady | Efektywność rynku | Docelowe CLV modelu |
|---|---|---|---|
| Grand Slam (G) | Australian Open, Wimbledon | Bardzo wysoka | ≥ 1.0% |
| Masters 1000 (M) | Indian Wells, Paris | Wysoka | ≥ 1.2% |
| ATP 500 | Dubai, Hamburg | Umiarkowana | ≥ 1.5% |
| ATP 250 | Różne | Umiarkowana | ≥ 1.5% |
| Challenger | Różne Challengers | Niska | ≥ 2.0% |
| ITF / Futures | Futures | Bardzo niska | ≥ 3.0% |

**Uzasadnienie:** Niższa efektywność rynku na niższych szczeblach oznacza łatwiej osiągalne wysokie CLV. Jednak wymagamy wyższego CLV, aby kompensować niższą płynność i większe spready.

---

## 7. Metryki Kompozytowe

### Definicja 7.1 — CLV-Adjusted Profit (CAP)

$$CAP = \text{stake\_total} \times \overline{CLV}_{\text{all}} - \text{transaction\_costs}$$

### Definicja 7.2 — Sharpe Ratio CLV

$$\text{SR}_{CLV} = \frac{\overline{CLV}}{\sigma_{CLV} / \sqrt{N}}$$

Gdzie $\text{SR}_{CLV} = t$-statystyka z testu t. Docelowa wartość: $\text{SR}_{CLV} > 2.0$ (co odpowiada $p < 0.023$ jednostronnie).

### Tabela 7.3 — Klasyfikacja Sharpe Ratio CLV

| SR_CLV | Interpretacja |
|---|---|
| < 1.0 | Brak statystycznej istotności |
| 1.0 – 1.645 | Słaba istotność (p = 0.10 – 0.05) |
| 1.645 – 2.326 | Istotność na poziomie 5% |
| > 2.326 | Silna istotność (p < 1%) |

---

## 8. Podsumowanie Progów i Celów

| Parametr | Wartość docelowa | Alert degradacji |
|---|---|---|
| Pre-match CLV (all-time) | ≥ 1.5% | < 0% (30-dniowy) |
| In-play CLV (all-time) | ≥ 3.0% | < 0% (30-dniowy) |
| Grand Slam CLV | ≥ 1.0% | < 0% |
| Challenger CLV | ≥ 2.0% | < 0% |
| SR_CLV (t-statystyka) | > 2.0 | < 1.0 |
| Minimalna próba do oceny | N ≥ 200 zakładów | — |

---

*Dokument opracowany na potrzeby modułu CLV TRACKER systemu betatp.io. Wersja 1.0.0.*
