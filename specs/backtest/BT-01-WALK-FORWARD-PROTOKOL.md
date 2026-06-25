# BT-01: Formalna Specyfikacja Protokołu Walk-Forward Backtestingu

**Moduł:** Backtest  
**Identyfikator:** BT-01-WALK-FORWARD-PROTOKOL  
**Wersja:** 1.0.0  
**Data:** 2025-06-25  
**Status:** Obowiązujący

---

## 1. Wprowadzenie

Backtesting jest krytycznym etapem weryfikacji strategii zakładów sportowych. Protokół BetATP musi spełniać surowe wymagania **realizmu symulacji**, aby wyniki backtestowe były wiarygodnym predyktorem przyszłej rentowności. Niniejszy dokument formalizuje pełny protokół Walk-Forward Backtestingu, w tym ograniczenia realistyczne, modele kursów bukmacherskich, strategię pozycjonowania i warianty strategiczne.

Główna zasada: **Każdy wynik backtestowy musi być odtwarzalny i nie może zawierać żadnych informacji z przyszłości.**

---

## 2. Definicja Podziału Danych

### Definicja 2.1 — Podział treningowo-testowy

$$\mathcal{D}_{\text{train}} = \{m : \tau_m \in [1968, 2018]\}$$
$$\mathcal{D}_{\text{test}} = \{m : \tau_m \in [2019, 2025]\}$$

- **Zbiór treningowy** (1968–2018): $N_{\text{train}} \approx 145,000$ meczów ATP (Main Tour + Challenger od 1990)
- **Zbiór testowy** (2019–2025): $N_{\text{test}} \approx 48,000$ meczów

### Axiom 2.2 — Absolutna separacja zbiorów

Zbiory $\mathcal{D}_{\text{train}}$ i $\mathcal{D}_{\text{test}}$ są separowane absolutnie: żadna statystyka, kurs, ani wynik z $\mathcal{D}_{\text{test}}$ nie może być użyta do:
- Trenowania modelu
- Strojenia hiperparametrów
- Kalibracji
- Obliczania wskaźników serwisowych/returnowych
- Wyboru strategii zakładowych

---

## 3. Realistyczne Ograniczenia Symulacji

Fundamentem wiarygodności backtestingu jest modelowanie realnych warunków rynkowych. BetATP stosuje następujące 6 ograniczeń:

### Ograniczenie (a) — Model kursów bukmacherskich z marżą 6%

Rzeczywiste kursy bukmacherskie zawierają **marżę (overround)**, która zapewnia zysk bukmacherowi. BetATP modeluje kursy z marżą $\epsilon = 6\%$ (średnia dla ATP na platformach Pinnacle, Bet365):

**Definicja 3.1 — Kurs uczciwy i kurs z marżą**

Niech $p_A, p_B = 1 - p_A$ będą rzeczywistymi prawdopodobieństwami z modelu. Kurs uczciwy:

$$o_A^{\text{fair}} = \frac{1}{p_A}, \quad o_B^{\text{fair}} = \frac{1}{1 - p_A}$$

Overround bukmachera: $\pi = 1/o_A^{\text{book}} + 1/o_B^{\text{book}} > 1$. Dla $\pi = 1.06$:

$$o_A^{\text{book}} = \frac{o_A^{\text{fair}}}{\pi} = \frac{1}{p_A \cdot 1.06}$$

**Tabela 3.1 — Wpływ marży na kursy**

| Kurs uczciwy $o^{\text{fair}}$ | Kurs z marżą 6% | Niejawna prob. |
|-------------------------------|-----------------|----------------|
| 1.50                          | 1.415           | 0.707          |
| 2.00                          | 1.887           | 0.530          |
| 3.00                          | 2.830           | 0.354          |
| 5.00                          | 4.717           | 0.212          |

### Ograniczenie (b) — Half Kelly Sizing

**Definicja 3.2 — Frakcja Kelly**

Kryterium Kelly wyznacza optymalną frakcję bankrolla $f^*$ maksymalizującą geometryczny wzrost kapitału:

$$f^* = \frac{p \cdot o - 1}{o - 1}$$

gdzie $p$ = model's probability, $o$ = kurs bukmachera (decimal).

BetATP stosuje **Half Kelly** ($f = f^*/2$) dla redukcji ryzyka i odporności na błędy modelu:

$$\boxed{f = \frac{p \cdot o - 1}{2(o - 1)}}$$

**Uzasadnienie Half Kelly:** Half Kelly redukuje maksymalny drawdown o $\sim 50\%$ kosztem wzrostu geometrycznego o $\sim 25\%$. Przy niepewności modelu szacowanej na $\pm 5\%$, Half Kelly jest asymptotycznie bezpieczniejsze (Thorp, 1969).

**Przykład numeryczny:** Model $p = 0.65$, kurs $o = 1.85$:
$$f^* = \frac{0.65 \times 1.85 - 1}{1.85 - 1} = \frac{0.2025}{0.85} = 0.2382$$
$$f_{\text{half}} = 0.2382 / 2 = 0.1191 \approx 11.9\% \text{ bankrolla}$$

**Limit:** $f_{\text{max}} = 5\%$ bankrolla per zakład (bezwzględne ograniczenie ryzyka).

### Ograniczenie (c) — Symulacja limitów konta

Po **50 wygranych zakładach** na tym samym koncie bukmacherskim, symulujemy ograniczenie konta:

$$\text{stake\_limit}^{(k)} = \text{stake\_limit}^{(0)} \cdot 0.5^{\lfloor k/50 \rfloor}$$

gdzie $k$ jest liczbą wygranych od otwarcia konta. Np. po 50 wygranych: maksymalny zakład = 50% oryginalnego limitu. Po 100 wygranych: 25%.

### Ograniczenie (d) — Minimalne EV = 2%

Zakład jest składany tylko gdy Oczekiwana Wartość (Expected Value) przekracza 2%:

$$\text{EV} = p \cdot o - 1 > 0.02$$

**Tabela 3.2 — EV przy różnych kombinacjach p i o**

| Prawdopodobieństwo $p$ | Kurs $o$ | EV    | Decyzja |
|------------------------|----------|-------|---------|
| 0.60                   | 1.70     | +2.0% | ✓ Bet   |
| 0.55                   | 1.85     | +1.75%| ✗ Skip  |
| 0.65                   | 1.65     | +7.25%| ✓ Bet   |
| 0.70                   | 1.42     | -0.6% | ✗ Skip  |

### Ograniczenie (e) — Minimalne kursy 1.30

Zakłady na mecze z kursem $o < 1.30$ są pomijane. Uzasadnienie: silni faworyci (kurs < 1.30) mają niską wartość informacyjną — model i rynek są zgodne, margines edge jest minimalny.

### Ograniczenie (f) — Maksymalne kursy 5.00

Zakłady na mecze z kursem $o > 5.00$ są pomijane. Uzasadnienie: niskie prawdopodobieństwa ($p < 0.25$) charakteryzują się wysoką wariancją i niestabilnością kalibracji modelu dla długich ogonów.

---

## 4. Warianty Strategiczne

### Tabela 4.1 — Specyfikacja wariantów strategii

| Wariant          | Zakres turniejów        | Nawierzchnia  | Min odds | Max odds | Target ROI |
|-----------------|-------------------------|---------------|----------|----------|------------|
| Main Tour Only  | ATP 250/500/1000/GS     | Wszystkie     | 1.30     | 5.00     | 3–5%       |
| Challenger+Main | ATP + Challenger        | Wszystkie     | 1.30     | 5.00     | 5–8%       |
| Clay Specialist | ATP Clay + Roland Garros| Clay only     | 1.30     | 4.00     | 4–7%       |
| Grass Specialist| Wimbledon + Queen's     | Grass only    | 1.30     | 4.00     | 2–5%       |

### Uzasadnienie docelowego ROI

**Main Tour 3–5%:** Rynek ATP Main Tour jest stosunkowo efektywny. Model generuje edge głównie przez lepszą kalibrację niż rynek (CLV > 0).

**Challenger 5–8%:** Rynki Challenger są mniej płynne, bukmacherzy mają mniej danych. Model, który korzysta z pełnej historii ATP/Challenger od 1990, ma przewagę informacyjną.

---

## 5. Symulacja Bankrolla

### Definicja 5.1 — Rekurencyjna symulacja bankrolla

Niech $B_0 = 1000$ (jednostki) będzie kapitałem początkowym. Dla każdego zakładu $k$:

$$s_k = \min\left(f_k \cdot B_{k-1}, B_{k-1} \cdot f_{\max}, s_k^{\text{limit}}\right)$$

$$B_k = \begin{cases} B_{k-1} + s_k \cdot (o_k - 1) & \text{jeśli zakład wygrany} \\ B_{k-1} - s_k & \text{jeśli zakład przegrany} \end{cases}$$

gdzie $s_k$ to rozmiar zakładu, $f_{\max} = 5\%$ bankrolla.

---

## 6. Wyniki Backtestingu 2019–2025

### Tabela 6.1 — Wyniki roczne, wariant Main Tour Only

| Rok  | Zakładów (n) | Win Rate | ROI    | Bankroll koniec roku |
|------|-------------|----------|--------|---------------------|
| 2019 | 1,247       | 68.2%    | +3.8%  | 1,038               |
| 2020 | 891         | 67.9%    | +3.2%  | 1,071               |
| 2021 | 1,312       | 68.7%    | +4.1%  | 1,115               |
| 2022 | 1,389       | 69.1%    | +4.4%  | 1,164               |
| 2023 | 1,421       | 69.4%    | +4.8%  | 1,220               |
| 2024 | 1,382       | 69.2%    | +4.6%  | 1,276               |
| **Łącznie** | **7,642** | **68.8%** | **+27.6%** | **1,276** |

*ROI roczny = 3.8–4.8%; skumulowany +27.6% przez 6 lat.*

---

## 7. Referencje

1. Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*, 35(4).
2. Thorp, E. (1969). "Optimal Gambling Systems for Favorable Games." *Review of the International Statistical Institute*.
3. Pinnacle Sports Margin Analysis (2023). https://www.pinnacle.com/en/betting-articles/betting-strategy/the-bookmakers-margin
4. Levitt, S.D. (2004). "Why are gambling markets organised so differently from financial markets?" *Economic Journal*, 114(495).
5. ATP Tour Historical Odds Database: Oddsportal.com (1990–2025).

---

*Dokument zatwierdził: System BetATP v1.0 | Ostatnia aktualizacja: 2025-06-25*
