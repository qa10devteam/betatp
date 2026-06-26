# CLV-06: Statystyczne Testy Istotności CLV

**Moduł:** betatp.io CLV TRACKER  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Zatwierdzone  

---

## 1. Cel i Zakres

Niniejszy dokument formalizuje **kompletny zestaw testów statystycznych** służących ocenie istotności CLV w systemie betatp.io. Definiuje cztery główne testy, analizę mocy, minimalne wykrywalne efekty oraz tabele liczebności próby. Wszystkie testy implementowane są w module `clv_tracker.statistics`.

---

## 2. Test 1 — t-test dla Średniej CLV

### Definicja 2.1 — Sformułowanie Hipotez

Dla serii CLV $\{CLV_1, \ldots, CLV_N\}$ definiujemy:

$$H_0: \mu_{CLV} = 0 \qquad \text{(brak przewagi nad rynkiem)}$$
$$H_1: \mu_{CLV} > 0 \qquad \text{(dodatnia przewaga nad rynkiem)}$$

### Definicja 2.2 — Statystyka t

$$t = \frac{\overline{CLV} - 0}{s_{CLV} / \sqrt{N}} = \frac{\overline{CLV} \cdot \sqrt{N}}{s_{CLV}}$$

gdzie:
$$\overline{CLV} = \frac{1}{N} \sum_{i=1}^N CLV_i, \qquad s_{CLV} = \sqrt{\frac{\sum_{i=1}^N (CLV_i - \overline{CLV})^2}{N-1}}$$

### Definicja 2.3 — Reguła Decyzyjna

Dla testu jednostronnego na poziomie $\alpha = 0.05$, przy $N \geq 30$:

$$\text{Odrzuć } H_0 \iff t > t_{0.05, N-1} \approx 1.645$$

Równoważnie: $p\text{-value} = P(T_{N-1} > t) < 0.05$.

### Tabela 2.4 — Wartości Krytyczne t

| $N$ | $t_{0.05, N-1}$ (jedn.) | $t_{0.025, N-1}$ (dwustr.) | $t_{0.005, N-1}$ |
|---|---|---|---|
| 30 | 1.699 | 2.045 | 2.756 |
| 50 | 1.677 | 2.009 | 2.678 |
| 100 | 1.660 | 1.984 | 2.626 |
| 200 | 1.653 | 1.972 | 2.601 |
| 441 | 1.648 | 1.966 | 2.588 |
| 500 | 1.648 | 1.965 | 2.586 |
| ∞ | 1.645 | 1.960 | 2.576 |

### Przykład 2.5 — Obliczenie dla Typowej Próby

Dane: $N = 300$, $\overline{CLV} = 0.018$ (1.8%), $s_{CLV} = 0.052$ (5.2%):

$$t = \frac{0.018 \times \sqrt{300}}{0.052} = \frac{0.018 \times 17.32}{0.052} = \frac{0.3118}{0.052} \approx 5.996$$

$t = 5.996 > 1.648$, więc odrzucamy $H_0$ z $p \approx 0.000001$. Wynik silnie istotny.

### Implementacja

```python
from scipy import stats
import numpy as np

def t_test_clv(clv_series: np.ndarray) -> dict:
    n = len(clv_series)
    mean_clv = np.mean(clv_series)
    std_clv = np.std(clv_series, ddof=1)
    t_stat = mean_clv / (std_clv / np.sqrt(n))
    p_value = stats.t.sf(t_stat, df=n-1)  # jednostronny
    ci_95 = stats.t.interval(0.95, df=n-1,
                              loc=mean_clv,
                              scale=std_clv/np.sqrt(n))
    return {
        "n": n, "mean_clv": mean_clv, "std_clv": std_clv,
        "t_stat": t_stat, "p_value": p_value,
        "ci_95_lower": ci_95[0], "ci_95_upper": ci_95[1],
        "significant_05": p_value < 0.05
    }
```

---

## 3. Test 2 — Bootstrap Przedziały Ufności

### Definicja 3.1 — Procedura Bootstrapowa

Bootstrapowy przedział ufności eliminuje założenie normalności rozkładu CLV. Algorytm:

**Wejście:** $\{CLV_1, \ldots, CLV_N\}$, liczba iteracji $B = 10000$

**Kroki:**
1. Dla $b = 1, \ldots, B$: wylosuj z powrotem próbę $\{CLV_1^{(b)}, \ldots, CLV_N^{(b)}\}$
2. Oblicz $\overline{CLV}^{(b)} = \frac{1}{N} \sum_{i=1}^N CLV_i^{(b)}$
3. Sortuj $\{\overline{CLV}^{(1)}, \ldots, \overline{CLV}^{(B)}\}$
4. Wyznacz percentyle:

$$CI_{95\%}^{\text{bootstrap}} = \left[\hat{q}_{0.025},\ \hat{q}_{0.975}\right]$$

gdzie $\hat{q}_p$ = $p$-ty percentyl rozkładu bootstrapowego.

### Definicja 3.2 — Bootstrap Percentile Method

$$\hat{q}_p = \inf\left\{x : \hat{F}_B(x) \geq p\right\}$$

gdzie $\hat{F}_B(x) = \frac{1}{B}\sum_{b=1}^B \mathbf{1}[\overline{CLV}^{(b)} \leq x]$.

### Definicja 3.3 — BCa Bootstrap (Bias-Corrected Accelerated)

Dla małych próbek preferujemy metodę BCa korygującą odchylenie:

$$CI_{95\%}^{\text{BCa}} = \left[\hat{q}_{\alpha_1},\ \hat{q}_{\alpha_2}\right]$$

gdzie $\alpha_1, \alpha_2$ są skorygowane o bias $\hat{z}_0$ i przyspieszenie $\hat{a}$.

### Implementacja

```python
def bootstrap_ci_clv(clv_series: np.ndarray,
                     B: int = 10_000,
                     alpha: float = 0.05) -> dict:
    n = len(clv_series)
    boot_means = np.array([
        np.mean(np.random.choice(clv_series, size=n, replace=True))
        for _ in range(B)
    ])
    ci_lower = np.percentile(boot_means, 100 * alpha / 2)
    ci_upper = np.percentile(boot_means, 100 * (1 - alpha / 2))
    return {
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "bootstrap_mean": np.mean(boot_means),
        "significant": ci_lower > 0  # CLV > 0 z 95% pewnością
    }
```

---

## 4. Test 3 — Test Współczynnika Wariancji (Variance Ratio Test)

### Definicja 4.1 — Variance Ratio Statistic

Variance Ratio Test (Lo & MacKinlay, 1988) testuje, czy CLV jest białym szumem:

$$VR(k) = \frac{\hat{\sigma}^2(k)}{\hat{\sigma}^2(1)}$$

gdzie $\hat{\sigma}^2(q) = \frac{1}{q} \cdot \frac{\sum_{t=q}^T (CLV_t - CLV_{t-q} - q\hat{\mu})^2}{T-q}$

Przy białym szumie: $\mathbb{E}[VR(k)] = 1$.

### Definicja 4.2 — Statystyka Testowa

$$Z(k) = \frac{VR(k) - 1}{\phi(k)^{1/2}} \xrightarrow{d} \mathcal{N}(0, 1)$$

gdzie dla jednorodnej wariancji:

$$\phi(k) = \frac{2(2k-1)(k-1)}{3kT}$$

**Hipotezy:**
$$H_0: VR(k) = 1 \quad \text{(białyszum, brak autokorelacji)}$$
$$H_1: VR(k) \neq 1 \quad \text{(korelacja seryjna)}$$

### Interpretacja

| $VR(k)$ | Interpretacja |
|---|---|
| $VR(k) \approx 1$ | Seria CLV jest białym szumem — rynek efektywny |
| $VR(k) > 1$ | Dodatnia korelacja — trendy, możliwa eksploatacja |
| $VR(k) < 1$ | Ujemna korelacja (mean-reversion) |

---

## 5. Test 4 — Istotność ROI

### Definicja 5.1 — Statystyka t dla ROI

Niech $r_i = \text{pnl}_i / \text{stake}_i$ oznacza stopę zwrotu $i$-tego zakładu. Test:

$$H_0: \mu_{ROI} = 0, \qquad H_1: \mu_{ROI} > 0$$

$$t_{ROI} = \frac{\overline{r} \cdot \sqrt{N}}{s_r}$$

### Definicja 5.2 — Porównanie Testów CLV vs ROI

Kluczowe różnice statystyczne:

$$\frac{s_{CLV}}{s_{ROI}} \approx \frac{\sigma_{\text{kursy}}}{\sigma_{\text{wyniki}}} \approx \frac{0.05}{0.95} \approx 0.053$$

Rozkład $r_i$ (ROI per zakład) jest prawie binarny: $r_i \approx o_{\text{open},i} - 1$ (wygrana) lub $-1$ (przegrana). Wariancja jest znacznie wyższa niż CLV.

**Twierdzenie 5.3 (Przewaga CLV nad ROI w testowaniu):**

Przy tych samych parametrach ($\mu$, $N$), moc testu CLV > moc testu ROI:

$$\text{Power}_{CLV}(N, \mu) > \text{Power}_{ROI}(N, \mu) \quad \forall N, \mu > 0$$

**Dowód:** Moc testu t zależy od SNR = $\mu/\sigma$. Ponieważ $\sigma_{CLV} \ll \sigma_{ROI}$ i $\mathbb{E}[CLV] \approx \mathbb{E}[ROI]$ (asymptotycznie), $\text{SNR}_{CLV} \gg \text{SNR}_{ROI}$. $\blacksquare$

---

## 6. Analiza Mocy i Minimalne Wykrywalne Efekty

### Definicja 6.1 — Moc Testu

Moc testu t (jednostronnego) dla prawdziwego CLV = $\delta$:

$$\text{Power}(N, \delta, \sigma, \alpha) = P\left(T_{N-1} > t_{1-\alpha, N-1} - \frac{\delta \sqrt{N}}{\sigma}\right)$$

Przy $\sigma = 0.05$, $\alpha = 0.05$, dążymy do mocy $\geq 0.80$ (standard).

### Definicja 6.2 — Minimalny Wykrywalny Efekt (MDE)

Dla danych $N$, $\sigma$, $\alpha$, docelowej mocy $\beta$:

$$MDE = (z_\alpha + z_\beta) \cdot \frac{\sigma}{\sqrt{N}}$$

Dla $N = 500$, $\sigma = 0.05$, $\alpha = 0.05$ (jedn.), $\beta = 0.80$:

$$MDE = (1.645 + 0.842) \cdot \frac{0.05}{\sqrt{500}} = 2.487 \times 0.002236 \approx 0.00556 \approx \boxed{0.556\%}$$

**Interpretacja:** Przy 500 zakładach wykrywamy CLV > 0.556% z 80% mocą.

**Korekta dla MDE = 0.37% z zadania:**

Przy $N = 500$, $\sigma = 5\%$, $\alpha = 0.05$, moc obliczamy:

$$\delta = 0.0037, \quad \text{SNR} = \frac{0.0037 \sqrt{500}}{0.05} = \frac{0.0037 \times 22.36}{0.05} = \frac{0.0827}{0.05} = 1.654$$

$$\text{Power} = \Phi(1.654 - 1.645) = \Phi(0.009) \approx 0.504 \approx 50\%$$

**Wniosek:** Przy N=500 i MDE=0.37% moc wynosi ~50%, nie 80%. Dla MDE=0.37% przy mocy 80%:

$$N = \left(\frac{(1.645 + 0.842) \times 0.05}{0.0037}\right)^2 = \left(\frac{0.1244}{0.0037}\right)^2 = 33.6^2 \approx 1129$$

---

## 7. Tabela Analizy Mocy

### Tabela 7.1 — Liczebność Próby dla Mocy 80%

Wymagane $N$ do wykrycia prawdziwego CLV na poziomie 80% mocy (α=0.05, jedn., σ=5%):

| Prawdziwe CLV (δ) | $N$ wymagane | Przybliżony czas* |
|---|---|---|
| 0.5% | 1,386 | ~2.8 lat |
| 1.0% | 347 | ~8 miesięcy |
| 1.5% | 155 | ~3.7 miesiąca |
| 2.0% | 87 | ~2 miesiące |
| 2.5% | 56 | ~7 tygodni |
| 3.0% | 39 | ~5 tygodni |
| 4.0% | 22 | ~3 tygodnie |
| 5.0% | 14 | ~2 tygodnie |

*Przy założeniu 500 zakładów/rok.

### Tabela 7.2 — Liczebność Próby dla Mocy 95%

Wymagane $N$ do wykrycia prawdziwego CLV na poziomie 95% mocy (α=0.05, jedn., σ=5%):

| Prawdziwe CLV (δ) | $N$ wymagane (moc 95%) | $N$ wymagane (moc 80%) | Stosunek |
|---|---|---|---|
| 0.5% | 2,165 | 1,386 | 1.56× |
| 1.0% | 542 | 347 | 1.56× |
| 1.5% | 241 | 155 | 1.56× |
| 2.0% | 136 | 87 | 1.56× |
| 2.5% | 87 | 56 | 1.56× |
| 3.0% | 61 | 39 | 1.56× |
| 5.0% | 22 | 14 | 1.57× |

**Wzór ogólny:** $N_{95\%} \approx 1.56 \times N_{80\%}$ (wynika ze stosunku $(z_{0.05}+z_{0.05})^2/(z_{0.05}+z_{0.20})^2$).

### Tabela 7.3 — MDE dla Różnych N przy σ=5%

| N zakładów | MDE (moc 80%) | MDE (moc 95%) | Status betatp.io |
|---|---|---|---|
| 50 | 1.76% | 2.20% | ❌ Za mało |
| 100 | 1.24% | 1.56% | ⚠️ Słaba moc |
| 200 | 0.88% | 1.10% | ⚠️ Akceptowalne |
| **441** | **0.59%** | **0.74%** | **✅ Standard** |
| 500 | 0.56% | 0.70% | ✅ Dobre |
| 1000 | 0.39% | 0.49% | ✅ Bardzo dobre |
| 2000 | 0.28% | 0.35% | ✅ Doskonałe |

---

## 8. Procedura Pełnej Analizy Statystycznej

### Definicja 8.1 — Protokół Testowania

System betatp.io wykonuje pełny protokół statystyczny po każdych 50 nowych zakładach:

```
PROTOCOL_CLV_STATS:
  1. t_test(clv_series, alpha=0.05, one_sided=True)
  2. bootstrap_ci(clv_series, B=10000, alpha=0.05)
  3. variance_ratio_test(clv_series, k=5)
  4. ljung_box_test(clv_series, lags=10)
  5. power_analysis(n=len(clv_series), mean=mean_clv, std=std_clv)
  6. roi_t_test(pnl_series, stake_series, alpha=0.05)
  7. generate_report(all_above)
```

### Definicja 8.2 — Raport Statystyczny

Wymagane pola raportu:

| Pole | Opis | Próg alertu |
|---|---|---|
| `n_bets` | Liczba zakładów z CLV | < 100: ostrzeżenie |
| `mean_clv` | Średnie CLV | < 0%: alert |
| `std_clv` | Odchylenie standardowe CLV | > 15%: weryfikacja |
| `t_stat` | Statystyka t | < 1.645: brak istotności |
| `p_value` | p-value (jednostronny) | > 0.05: brak istotności |
| `ci_95_lower` | Dolna granica 95% CI | < -0.5%: alert |
| `ci_95_upper` | Górna granica 95% CI | — |
| `bootstrap_ci_lower` | Dolna granica bootstrap | < -0.5%: alert |
| `vr_stat` | Variance Ratio | < 0.8 lub > 1.2: nieefektywność |
| `lb_q10` | Ljung-Box Q(10) | > 18.31: autokorelacja |
| `power_at_current_clv` | Moc testu przy aktualnym CLV | < 0.50: za mała próba |
| `mde_80pct` | Minimalny wykrywalny efekt (80%) | — |

---

## 9. Podsumowanie Wymagań Statystycznych

| Test | Hipoteza | Alpha | Reguła odrzucenia |
|---|---|---|---|
| t-test | $H_0: \mu_{CLV}=0$ | 0.05 | $t > 1.645$ |
| Bootstrap CI | $H_0: \mu_{CLV} \leq 0$ | 0.05 | $CI_{\text{lower}} > 0$ |
| Variance Ratio | $H_0: VR=1$ | 0.05 | $|Z| > 1.96$ |
| Ljung-Box | $H_0: \rho_k=0$ | 0.05 | $Q_{10} > 18.31$ |
| ROI t-test | $H_0: \mu_{ROI}=0$ | 0.05 | $t > 1.645$ |

| Analiza Mocy | Parametry | Wynik |
|---|---|---|
| MDE przy N=500, σ=5%, moc=80% | $\alpha=0.05$ | **0.556%** |
| N wymagane dla CLV=2%, moc=80% | $\sigma=5\%, \alpha=0.05$ | **87** |
| N wymagane dla CLV=1.5%, moc=95% | $\sigma=5\%, \alpha=0.05$ | **241** |
| Standard betatp.io (moc=95%, CLV=2%) | $\sigma=5\%, \alpha=0.05$ | **N ≥ 441** |

---

*Dokument opracowany na potrzeby modułu CLV TRACKER systemu betatp.io. Wersja 1.0.0.*
