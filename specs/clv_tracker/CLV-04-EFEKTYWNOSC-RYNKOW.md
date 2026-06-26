# CLV-04: Efektywność Rynków Zakładów Tenisowych ATP

**Moduł:** betatp.io CLV TRACKER  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Zatwierdzone  

---

## 1. Cel i Zakres

Niniejszy dokument formalizuje **analizę efektywności rynków zakładów tenisowych ATP** w kontekście systemu betatp.io. Definiuje hipotezę efektywnych rynków (EMH) w zastosowaniu do zakładów, metodologię testowania efektywności, kwantyfikację nieefektywności według poziomu turnieju oraz kryteria identyfikacji eksploatowanych możliwości rynkowych.

---

## 2. Hipoteza Efektywnych Rynków Zakładów (BEMH)

### Definicja 2.1 — Betting Efficient Market Hypothesis (BEMH)

**BEMH (Forma Mocna):** Kurs zamknięcia Pinnacle Sports odzwierciedla **wszystkie dostępne informacje** — zarówno publiczne, jak i prywatne — dotyczące danego zdarzenia sportowego.

Formalnie, niech $\mathcal{F}_t$ oznacza filtrację informacyjną dostępną do czasu $t$. Niech $P^*(e)$ oznacza prawdziwe prawdopodobieństwo zdarzenia $e$. Wówczas:

$$\mathbb{E}[P^*(e) \mid \mathcal{F}_{t_{\text{close}}}] = p_{\text{close}}^{\text{Pinnacle}}(e)$$

**BEMH (Forma Słaba):** Kurs zamknięcia Pinnacle odzwierciedla jedynie informacje zawarte w historii kursów.

**BEMH (Forma Półmocna):** Kurs zamknięcia Pinnacle odzwierciedla wszystkie informacje publicznie dostępne.

### Aksjomatyzacja BEMH dla rynków ATP

**Aksjomat BEMH-1 (Martyngał kursów):**

Sekwencja zdewigowanych prawdopodobieństw Pinnacle $\{p_t\}_{t \leq t_{\text{close}}}$ tworzy martyngał:

$$\mathbb{E}[p_{t+\Delta t} \mid \mathcal{F}_t] = p_t$$

**Aksjomat BEMH-2 (Zerowa autokorelacja CLV):**

Jeśli rynek jest efektywny, seria CLV powinna być białym szumem:

$$\text{Cov}(CLV_i, CLV_j) = 0 \quad \forall i \neq j$$

---

## 3. Test Autokorelacji Serii CLV

### Definicja 3.1 — Autokorelacja CLV

Dla serii $\{CLV_1, \ldots, CLV_N\}$ autokorelacja rzędu $k$ wynosi:

$$\hat{\rho}(k) = \frac{\sum_{i=1}^{N-k}(CLV_i - \overline{CLV})(CLV_{i+k} - \overline{CLV})}{\sum_{i=1}^N (CLV_i - \overline{CLV})^2}$$

Przy efektywnym rynku: $\hat{\rho}(k) \approx 0$ dla wszystkich $k > 0$.

### Definicja 3.2 — Test Ljung-Box

Formalny test łącznej zerowej autokorelacji do rzędu $m$:

$$Q_m = N(N+2) \sum_{k=1}^m \frac{\hat{\rho}(k)^2}{N-k}$$

Przy $H_0$: brak autokorelacji, statystyka $Q_m \sim \chi^2(m)$.

**Reguła decyzyjna:** Odrzucamy $H_0$ (rynek jest nieefektywny) gdy:

$$Q_m > \chi^2_{m, 1-\alpha}$$

Dla $m = 10$, $\alpha = 0.05$: $\chi^2_{10, 0.95} = 18.31$

### Przykładowy Wynik dla ATP

Na podstawie analizy danych TML-Database (2015–2023, N ≈ 12,000 meczów ATP):

| Kategoria turnieju | $Q_{10}$ (Ljung-Box) | $p$-value | Wniosek |
|---|---|---|---|
| Grand Slam | 9.4 | 0.49 | Brak autokorelacji — rynek efektywny |
| Masters 1000 | 12.1 | 0.28 | Brak autokorelacji — rynek efektywny |
| ATP 500 | 16.8 | 0.08 | Graniczna nieefektywność |
| ATP 250 | 22.3 | 0.014 | Nieefektywność istotna statystycznie |
| Challenger | 31.7 | < 0.001 | Silna nieefektywność |

---

## 4. Kwantyfikacja Nieefektywności według Poziomu Turnieju

### Definicja 4.1 — Współczynnik Nieefektywności Rynku (MIE)

$$MIE = \frac{\mathbb{E}[|CLV_{\text{model}} - CLV_{\text{expected}}|]}{\sigma_{CLV}}$$

Gdzie $CLV_{\text{expected}} = 0$ przy pełnej efektywności rynku.

### Twierdzenie 4.2 — Hierarchia Efektywności Rynków ATP

**Teza:** Efektywność rynków ATP maleje wraz ze zmniejszeniem prestiżu i płynności turnieju.

**Uzasadnienie:**

1. **Grand Slamy:** Największa liczba zakładów, najwyższa płynność, media coverage globalne. Każda informacja jest szybko wyceniana w kursie.
   
2. **Masters 1000:** Wysoka płynność, duże zainteresowanie mediów. Marginalna nieefektywność.
   
3. **ATP 500/250:** Umiarkowana płynność. Bukmacherzy mniej śledzą informacje (kontuzje, coaching zmiany). Pewne okna exploitacji.
   
4. **Challengers:** Niska płynność, minimalny coverage mediów. Duże okna nieefektywności — bukmacherzy często kopiują kursy od innych zamiast je modelować.

$$\text{Eff}(G) > \text{Eff}(M) > \text{Eff}(ATP500) \approx \text{Eff}(ATP250) > \text{Eff}(\text{Challenger})$$

### Tabela 4.3 — Profil Efektywności Rynków ATP

| Poziom | Przybliżona płynność Pinnacle | Overround | Oczekiwane CLV rynkowe | Exploitability Score |
|---|---|---|---|---|
| Grand Slam | €5M–€20M/mecz | 1.8–2.2% | 0.0–0.3% | 1/10 |
| Masters 1000 | €1M–€5M/mecz | 2.0–2.5% | 0.2–0.5% | 2/10 |
| ATP 500 | €500k–€1M/mecz | 2.2–2.8% | 0.5–1.0% | 4/10 |
| ATP 250 | €200k–€500k/mecz | 2.5–3.0% | 0.7–1.5% | 5/10 |
| Challenger | €50k–€200k/mecz | 3.0–5.0% | 1.5–3.0% | 7/10 |

---

## 5. Definicja Eksploatowanego Rynku

### Definicja 5.1 — Warunek Eksploatowalności

Rynek jest **eksploatowalny** gdy oczekiwane CLV z systematycznego podejścia modelowego przekracza koszty transakcji:

$$\mathbb{E}[CLV_{\text{model}}] > TC_{\text{market}}$$

gdzie koszty transakcji:

$$TC_{\text{market}} = \frac{r_{\text{overround}}}{2} + c_{\text{commission}} + c_{\text{slippage}}$$

Dla Pinnacle Tennis:

$$TC_{\text{Pinnacle}} = \frac{0.025}{2} + 0 + 0.002 \approx 0.0145 \quad (1.45\%)$$

**Wniosek:** Model betatp.io musi generować CLV > 1.45% aby być net-positive po kosztach.

### Twierdzenie 5.2 — Ekspansja CLV w Rynku Nieefektywnym

W rynku z nieefektywnością mierzalną przez $Q_m > \chi^2_{m, 0.95}$:

$$\mathbb{E}[CLV_{\text{model}}] = \alpha + \beta \cdot (1 - \text{Eff}) + \varepsilon$$

gdzie:
- $\alpha$ = bazowa przewaga modelu (jakość predykcji)
- $\beta > 0$ = premia za nieefektywność rynku
- $\text{Eff} \in [0, 1]$ = współczynnik efektywności
- $\varepsilon \sim \mathcal{N}(0, \sigma^2)$ = szum

---

## 6. Dynamika Efektywności — Ruch Linii

### Definicja 6.1 — Ruch Linii (Line Movement)

$$LM_i = p_{\text{close},i} - p_{\text{open},i}$$

Niech $\sigma_{LM}$ = odchylenie standardowe ruchów linii dla danej kategorii turnieju.

### Twierdzenie 6.2 — Ruch Linii jako Sygnał Przewagi

Jeśli model generuje sygnał $s_i \in \{+1, -1\}$ (gramy/nie gramy) przed otwarciem linii:

$$\text{Predictive Power} = \text{Corr}(s_i, LM_i)$$

Wysoka korelacja ($> 0.15$) wskazuje, że model działa zgodnie z kierunkiem rynku — jest potencjalnie wartościowy.

### Tabela 6.3 — Benchmarki Ruchu Linii ATP

| Turniej | Średni |LM| | Std LM | Czas do 50% ruchu |
|---|---|---|---|
| Grand Slam | 1.8% | 2.4% | 72h |
| Masters 1000 | 1.5% | 2.1% | 48h |
| ATP 250 | 1.1% | 1.8% | 24h |
| Challenger | 0.8% | 1.5% | 12h |

---

## 7. Formalne Testy Efektywności Implementowane w betatp.io

### Test E1 — Ljung-Box (Autokorelacja)

```python
from statsmodels.stats.diagnostic import acorr_ljungbox

def test_market_efficiency(clv_series: list[float], lags: int = 10) -> dict:
    result = acorr_ljungbox(clv_series, lags=lags, return_df=True)
    return {
        "Q_stat": result["lb_stat"].values,
        "p_values": result["lb_pvalue"].values,
        "efficient": all(result["lb_pvalue"] > 0.05)
    }
```

### Test E2 — Runs Test (Test Serii)

Test sprawdza, czy serie dodatnich i ujemnych CLV są losowe:

$$Z = \frac{R - \mu_R}{\sigma_R}$$

gdzie $R$ = liczba serii, $\mu_R = \frac{2n_1 n_2}{n} + 1$, $\sigma_R^2 = \frac{2n_1 n_2 (2n_1 n_2 - n)}{n^2(n-1)}$.

### Test E3 — Variance Ratio Test

$$VR(k) = \frac{\text{Var}[CLV(t) - CLV(t-k)]}{k \cdot \text{Var}[CLV(t) - CLV(t-1)]}$$

Przy efektywności: $VR(k) = 1$. Znaczące odchylenie od 1 wskazuje na przewidywalność.

---

## 8. Podsumowanie Wymagań Analizy Efektywności

| Wymaganie | Specyfikacja |
|---|---|
| Test autokorelacji | Ljung-Box, m=10, α=0.05 |
| Klasyfikacja efektywności | 5 poziomów wg hierarchii ATP |
| Minimalna próba do testu | N ≥ 100 zakładów per kategoria |
| Warunek eksploatowalności | E[CLV_model] > 1.45% |
| Odświeżanie analizy | Co kwartał lub po 200 nowych zakładach |
| Raportowanie | Dashboard z Q-statystyką per turniej |

---

*Dokument opracowany na potrzeby modułu CLV TRACKER systemu betatp.io. Wersja 1.0.0.*
