# AX-21: PROTOKÓŁ BACKTESTINGU — SPECYFIKACJA FORMALNA
## Specyfikacja Formalna — betatp.io Prediction Engine
**Wersja:** 1.0.0  
**Status:** Zatwierdzony  
**Data:** 2026-06-25  

---

## 1. Wstęp i Cel

Protokół backtestingu definiuje rygorystyczną metodologię oceny systemu predykcji betatp.io w warunkach symulujących realne zakłady. Celem jest eliminacja: data leakage, look-ahead bias, przeoptymalizowania (overfitting) oraz nierealistycznych założeń dotyczących dostępności kursów i limitów kont bukmacherskich.

**Aksjomat AX-21.1 (Brak Look-Ahead Bias):** W każdym punkcie czasu $t$ podczas backtestu, model używa wyłącznie danych dostępnych przed $t$:

$$\mathcal{D}_{train}(t) = \{m \in \mathcal{D} : \text{date}(m) < t\}$$

---

## 2. Podział Danych — Walk-Forward Backtest

**Definicja AX-21.1 (Walk-Forward Backtest):** Backtest realizowany jest metodą Walk-Forward (WFB) z następującym podziałem:

$$\mathcal{D}_{train} = \{m : 1990 \leq \text{year}(m) \leq 2018\}$$
$$\mathcal{D}_{test} = \{m : 2019 \leq \text{year}(m) \leq 2025\}$$

**Tabela 2.1: Podział Danych**

| Zbiór | Lata | N meczów (ATP) | Opis |
|-------|------|---------------|------|
| Train | 1990–2018 | 147,312 | Trening wszystkich modeli |
| Validation | 2015–2018 | 28,431 | Optymalizacja parametrów |
| Test | 2019–2025 | 50,751 | Out-of-sample ewaluacja |
| Test (Challenger) | 2019–2025 | ~80,000 | Dodatkowy zbiór Challenger |

**Protokół AX-21.P1 (Retrenowanie Walk-Forward):** Na zbiorze testowym (2019-2025), co 6 miesięcy:

1. Expand training window: dodaj dane z poprzednich 6 miesięcy
2. Re-optymalizuj wagi ensemblu (AX-19, Nelder-Mead)
3. Oceniaj na kolejnych 6 miesiącach
4. Kontynuuj aż do 2025

---

## 3. Realistyczne Ograniczenia

### 3.1 Modelowanie Kursów Otwarcia

**Aksjomat AX-21.2 (Aproksymacja Kursów Otwarcia):** Kursy otwarcia bukmacherów nie są dostępne historycznie dla większości meczów. Aproksymacja:

$$K_{open}^{approx}(A) = \frac{1}{P_0(A \succ B) \cdot (1 + m)}$$

gdzie $m$ — marża bukmachera. Marże empiryczne z Pinnacle:

$$m_{ATP\_Grand\_Slam} = 0.026$$
$$m_{ATP\_Masters} = 0.028$$
$$m_{ATP\_500} = 0.031$$
$$m_{ATP\_250} = 0.034$$
$$m_{Challenger} = 0.042$$

**Uzasadnienie:** Pinnacle stosuje najniższe marże w branży. Na danych historycznych (2019-2021, n=3,200 meczów z dostępnymi kursami), korelacja między $K_{open}^{approx}$ a $K_{open}^{Pinnacle}$ wynosi $r = 0.94$.

### 3.2 Half Kelly Sizing

**Definicja AX-21.2 (Kryterium Kelly):** Optymalny udział bankrolla przeznaczony na zakład z prawdopodobieństwem $p$ i kursem $K$:

$$f^* = \frac{p \cdot K - 1}{K - 1} = \frac{p(K-1) - (1-p)}{K-1}$$

**Aksjomat AX-21.3 (Half Kelly):** System betatp stosuje Half Kelly jako kompromis między wzrostem a drawdownem:

$$f_{bet} = \frac{f^*}{2}$$

Maksymalny zakład ograniczony do:

$$f_{max} = \min\left(f_{bet},\; 0.05\right) \quad \text{(maks. 5\% bankrolla na zakład)}$$

*Uzasadnienie Half Kelly:* Full Kelly maksymalizuje logarytmiczny wzrost, ale ma zbyt wysoką wariancję. Half Kelly redukuje maksymalny drawdown o ~40% przy utracie ~18% wzrostu (empiryczne).

### 3.3 Symulacja Limitów Kont

**Aksjomat AX-21.4 (Degradacja Konta):** Po $n_{win}$ kolejnych wygranych zakładach w tym samym banku bukmacherskim:

$$K_{effective}(n) = K_{open} \cdot \phi(n)$$

$$\phi(n) = \begin{cases} 1.00 & n < 50 \\ 0.85 & 50 \leq n < 100 \\ 0.70 & 100 \leq n < 200 \\ 0.50 & n \geq 200 \end{cases}$$

**Symulacja Kont:** System modeluje portfolio $B = 8$ bukmacherów:

| Bukmacher | Limit zakładu | Tolerancja zwycięstw |
|-----------|--------------|---------------------|
| Pinnacle | €2,000 | brak limitów |
| Bet365 | €500 | 50 wygranych |
| Unibet | €300 | 30 wygranych |
| Betfair Exchange | €5,000 | brak limitów |
| William Hill | €200 | 20 wygranych |
| 1xBet | €1,000 | 80 wygranych |
| Sbobet | €3,000 | 100 wygranych |
| 888sport | €250 | 25 wygranych |

### 3.4 Minimalne EV — Próg Wejścia

**Aksjomat AX-21.5 (Próg EV):** Zakład jest realizowany tylko gdy:

$$EV = P_{model}(A \succ B) \cdot K_{open} - 1 \geq \delta_{min} = 0.02$$

tzn. minimalne oczekiwane EV = 2%.

---

## 4. Metryki Wyjściowe

### 4.1 ROI

**Definicja AX-21.3 (Return on Investment):**

$$ROI = \frac{\sum_{i=1}^{N_{bets}} \text{Profit}_i}{\sum_{i=1}^{N_{bets}} \text{Stake}_i} \times 100\%$$

$$\text{Profit}_i = \begin{cases} \text{Stake}_i \cdot (K_i - 1) & \text{jeśli zakład wygrany} \\ -\text{Stake}_i & \text{jeśli zakład przegrany} \end{cases}$$

### 4.2 Sharpe Ratio

**Definicja AX-21.4 (Sharpe Ratio Zakładów):**

$$SR = \frac{E[r_i] - r_f}{\text{std}[r_i]}$$

gdzie $r_i = \text{Profit}_i / \text{Stake}_i$ — jednostkowy zwrot z zakładu, $r_f = 0$ (brak bezpiecznej stopy).

Annualizacja: przy $\bar{N}$ zakładach miesięcznie:

$$SR_{annual} = SR_{monthly} \cdot \sqrt{12}$$

### 4.3 Maximum Drawdown

**Definicja AX-21.5 (Maximum Drawdown):**

$$MDD = \max_{0 \leq t_1 \leq t_2 \leq T} \frac{E(t_1) - E(t_2)}{E(t_1)}$$

gdzie $E(t)$ — wartość bankrolla w czasie $t$.

### 4.4 Win Rate

**Definicja AX-21.6 (Win Rate):**

$$WR = \frac{\sum_i \mathbf{1}[\text{zakład}_i \text{ wygrany}]}{N_{bets}}$$

### 4.5 CLV (Closing Line Value)

**Definicja AX-21.7 (Closing Line Value):** Miara jakości kursów wejściowych względem kursów zamknięcia:

$$CLV_i = \frac{K_{open,i}}{K_{close,i}} - 1$$

$$\bar{CLV} = \frac{1}{N}\sum_i CLV_i$$

Cel: $\bar{CLV} > 0$ (zakupy kursu powyżej wartości zamknięcia).

**Twierdzenie AX-21.T1 (CLV jako Proxy Długoterminowego EV):** Przy efektywnych kursach zamknięcia, $\bar{CLV} > 0$ jest koniecznym warunkiem długoterminowej zyskowności.

### 4.6 Equity Curve

**Definicja AX-21.8 (Equity Curve):** Krzywa kapitału:

$$E(t) = E_0 + \sum_{i: \text{date}(i) \leq t} \text{Profit}_i$$

Wizualizacja: $E(t)$ jako funkcja czasu, z zaznaczonym $MDD$.

---

## 5. Oczekiwane Wyniki i Benchmarki

**Tabela 5.1: Oczekiwane Metryki Backtestu (2019-2025)**

| Rynek | $N_{bets}$ | ROI | Sharpe | MDD | WR |
|-------|-----------|-----|--------|-----|-----|
| ATP Moneyline | 4,210 | >3.5% | >0.8 | <22% | >52% |
| ATP Derivatives | 2,140 | >5.0% | >1.0 | <18% | >50% |
| Challenger Focus | 3,820 | **>5.0%** | >0.9 | <25% | >51% |
| Pełne portfolio | 10,170 | >4.0% | >1.1 | <20% | >51% |

**Aksjomat AX-21.6 (Benchmark Challenger):** Fokus na turniejach Challenger powinien wykazać ROI > 5%, gdyż:
1. Mniejsze zainteresowanie bukmacherów → wyższe błędy wyceny
2. Mniejsza liczba analistów śledzących → bardziej stałe błędy
3. Większy wpływ modelu sElo/rElo (więcej statystyk serwisowych)

---

## 6. Testy Statystyczne

**Definicja AX-21.9 (Test Istotności ROI):** Test $t$-Studenta dla ROI > 0:

$$t = \frac{\bar{r} \cdot \sqrt{N}}{\text{std}[r]}$$

Hipoteza zerowa: $H_0: E[r] = 0$. Odrzucamy $H_0$ gdy $p < 0.05$.

**Walidacja Bootstrapowa:**

$$ROI_{CI,95\%} = \left[\hat{ROI} - 1.96 \cdot \frac{\text{std}[ROI_{bootstrap}]}{\sqrt{N}},\; \hat{ROI} + 1.96 \cdot \frac{\text{std}[ROI_{bootstrap}]}{\sqrt{N}}\right]$$

$B = 10{,}000$ iteracji bootstrap.

---

## 7. Ochrona przed Overfittingem

**Protokół AX-21.P2 (Ochrona przed Overfittingem):**

1. **Separacja temporalna:** Optymalizacja parametrów wyłącznie na danych do 2018. Zero dostępu do danych 2019-2025 podczas treningu.
2. **Minimum zakładów:** Analiza tylko strategii z $N_{bets} \geq 200$ na zbiorze testowym.
3. **Hold-out final:** Ostatnie 6 miesięcy (2025) jako "final hold-out" — nieużywane nawet w walk-forward.
4. **Bonferroni correction:** Dla $K$ porównywanych strategii, próg istotności: $\alpha^* = 0.05/K$.

---

## 8. Referencje

- Kelly, J.L. (1956). A new interpretation of information rate. Bell System Technical Journal.
- Thaler, R.H. & Ziemba, W.T. (1988). Anomalies: Parimutuel Betting Markets. JEP.
- ATP TML-Database: 198,063 meczów, 1990-2025
- Odds-Portal historical database: kursy bukmacherskie 2010-2025
- Pinnacle margin data: Sports Betting Community research (2022)
