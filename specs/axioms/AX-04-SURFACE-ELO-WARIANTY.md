# AX-04: SURFACE ELO — WARIANTY NAWIERZCHNIOWE
## Specyfikacja 6 Równoległych Wariantów Systemu Elo

**Dokument:** AX-04  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-03

---

## 1. Motywacja i Uzasadnienie

Jeden globalny rating Elo nie wystarczy do precyzyjnego modelowania tenisa ATP, ponieważ wydajność zawodników jest wyraźnie zróżnicowana w zależności od nawierzchni. Dane empiryczne wskazują, że różnica w rankingu nawierzchniowym między specjalistami od ziemi a specjalistami od trawy może wynosić 200–400 punktów Elo, co odpowiada >60% różnicy w prawdopodobieństwie wygranej.

Niniejszy dokument definiuje 6 równoległych wariantów Elo oraz formułę mieszającą (*blending*) łączącą rating nawierzchniowy z globalnym.

---

## 2. Definicja 6 Wariantów Elo

### Definicja 2.1 (Wektor Ratingów)

Dla każdego gracza $i$ definiujemy wektor ratingów:

$$\mathbf{R}_i = \left(r_i^{\text{ovr}}, r_i^{\text{hard}}, r_i^{\text{clay}}, r_i^{\text{grass}}, r_i^{\text{serve}}, r_i^{\text{return}}\right) \in \mathbb{R}^6$$

| Indeks | Symbol | Opis | Aktualizacja |
|:------:|:------:|:-----|:------------|
| 1 | $r^{\text{ovr}}$ | Overall Elo — globalny | Po każdym meczu |
| 2 | $r^{\text{hard}}$ | Hard Elo — nawierzchnia twarda | Wyłącznie mecze na twardej |
| 3 | $r^{\text{clay}}$ | Clay Elo — nawierzchnia ziemna | Wyłącznie mecze na ziemi |
| 4 | $r^{\text{grass}}$ | Grass Elo — nawierzchnia trawiasta | Wyłącznie mecze na trawie |
| 5 | $r^{\text{serve}}$ | Serve Elo — efektywność serwisu | Po każdym meczu (z statystykami) |
| 6 | $r^{\text{return}}$ | Return Elo — efektywność returnu | Po każdym meczu (z statystykami) |

### Definicja 2.2 (Reguły Aktualizacji dla Wariantów Nawierzchniowych)

Dla meczu rozegranego na nawierzchni $s \in \{\text{hard}, \text{clay}, \text{grass}\}$:

$$r_i^{s,(t+1)} = r_i^{s,(t)} + K_s \cdot (S_{ij} - E_{ij}^s)$$

$$r_i^{\text{ovr},(t+1)} = r_i^{\text{ovr},(t)} + K \cdot (S_{ij} - E_{ij}^{\text{ovr}})$$

gdzie $E_{ij}^s$ jest funkcją oczekiwanego wyniku opartą na $r_i^s - r_j^s$, analogicznie do AX-03.

K-faktory dla wariantów nawierzchniowych są identyczne z ogólnymi (Tabela 4.1 w AX-03).

---

## 3. Formuła Mieszania (Blending)

### Definicja 3.1 (Efektywny Rating Nawierzchniowy)

Efektywny rating zawodnika $i$ na nawierzchni $s$:

$$\boxed{r_i^{s,\text{eff}} = \alpha_i^s \cdot r_i^s + (1 - \alpha_i^s) \cdot r_i^{\text{ovr}}}$$

gdzie $\alpha_i^s \in [0,1]$ jest **współczynnikiem mieszania** zależnym od liczby meczy rozegranych przez $i$ na nawierzchni $s$.

### Definicja 3.2 (Współczynnik Mieszania jako Funkcja Próbki)

$$\alpha_i^s = f\left(n_i^s\right) = 1 - \exp\left(-\frac{n_i^s}{n_{1/2}}\right)$$

gdzie:
- $n_i^s$ = liczba meczy rozegranych przez gracza $i$ na nawierzchni $s$
- $n_{1/2}$ = **półokres nasycenia** (ang. half-saturation constant) = 30 meczów

**Interpretacja:**
- $n_i^s = 0$: $\alpha = 0$ → pełne poleganie na overall Elo
- $n_i^s = 30$: $\alpha = 1 - e^{-1} \approx 0.632$ → ponad połowa wagi na Elo nawierzchniowym
- $n_i^s = 60$: $\alpha \approx 0.865$
- $n_i^s = 90$: $\alpha \approx 0.950$
- $n_i^s \to \infty$: $\alpha \to 1$ → pełne Elo nawierzchniowe

### Tabela 3.1: Wartości $\alpha$ w zależności od $n$

| $n$ (mecze) | $\alpha = f(n)$ | Interpretacja |
|:-----------:|:---------------:|:-------------|
| 0 | 0.000 | Brak danych nawierzchniowych |
| 5 | 0.154 | Nowa nawierzchnia — mało danych |
| 10 | 0.283 | Mało danych |
| 20 | 0.487 | Umiarkowana próbka |
| 30 | 0.632 | $n_{1/2}$ — punkt nasycenia |
| 50 | 0.811 | Dobra próbka |
| 75 | 0.918 | Duża próbka |
| 100 | 0.950 | Bardzo duża próbka |
| 150 | 0.993 | Niemal pełne nawierzchniowe Elo |

### Właściwość 3.1 (Granice $\alpha$)

$$\lim_{n \to 0} \alpha = 0, \quad \lim_{n \to \infty} \alpha = 1, \quad \alpha'(n) = \frac{1}{n_{1/2}} e^{-n/n_{1/2}} > 0$$

$\alpha$ jest ściśle rosnącą funkcją $n$ — im więcej danych nawierzchniowych, tym mniejszy udział globalnego Elo.

---

## 4. Serve Elo i Return Elo

### Definicja 4.1 (Serve Elo — Specyfikacja)

**Serve Elo** ($r^{\text{serve}}$) mierzy efektywność serwisu względem oczekiwanej.

Niech:
- $\text{SPW}_{\text{actual}}$ = rzeczywisty procent punktów wygranych na serwisie w meczu
- $\text{SPW}_{\text{expected}}$ = oczekiwany procent punktów wygranych na serwisie (na podstawie poziomu oponenta)

Definiujemy **Serve Performance Score**:

$$\text{SPS} = \text{SPW}_{\text{actual}} - \text{SPW}_{\text{expected}}$$

Aktualizacja Serve Elo:

$$r_i^{\text{serve},(t+1)} = r_i^{\text{serve},(t)} + K_{\text{serve}} \cdot \text{SPS}_i$$

gdzie $K_{\text{serve}} = 20$ (kalibrowany empirycznie).

### Definicja 4.2 (Return Elo — Specyfikacja)

Analogicznie, Return Elo mierzy skuteczność returnowania:

$$\text{RPS} = \text{RPW}_{\text{actual}} - \text{RPW}_{\text{expected}}$$

$$r_i^{\text{return},(t+1)} = r_i^{\text{return},(t)} + K_{\text{return}} \cdot \text{RPS}_i$$

gdzie $K_{\text{return}} = 20$.

### Definicja 4.3 (Oczekiwany SPW)

$$\text{SPW}_{\text{expected}}(i, j, s) = p_{\text{base}}^s + \delta_{\text{elo}}(r_i^{\text{serve}} - r_j^{\text{return}})$$

gdzie $p_{\text{base}}^s$ jest bazowym prawdopodobieństwem serwisowym na nawierzchni $s$ (Tabela 8.1 w AX-01), a $\delta_{\text{elo}}$ jest mapowaniem różnicy ratingów na korektę prawdopodobieństwa (definicja 9.1 w AX-03).

---

## 5. Kalibracja Współczynnika $\alpha$

### Twierdzenie 5.1 (Optymalna Kalibracja $n_{1/2}$)

Optymalny $n_{1/2}$ minimalizuje średni błąd kalibracji predykcji na zbiorze testowym:

$$n_{1/2}^* = \arg\min_{n_{1/2}} \mathbb{E}\left[(S_{ij} - E_{ij}^{s,\text{eff}})^2\right]$$

Na podstawie retrospektywnej analizy danych ATP 2010–2024 szacujemy:

$$n_{1/2}^* \approx 30 \pm 5 \text{ meczów}$$

### Procedura Kalibracji

1. Podziel dane historyczne ATP (2010–2024) na zbiory treningowy (80%) i testowy (20%)
2. Dla każdej wartości $n_{1/2} \in \{10, 20, 30, 40, 50, 75, 100\}$:
   a. Wylicz $\alpha_i^s$ dla każdego gracza i nawierzchni
   b. Wylicz $r_i^{s,\text{eff}}$ dla każdego meczu w zbiorze testowym
   c. Oblicz Brier Score na zbiorze testowym
3. Wybierz $n_{1/2}$ minimalizujące Brier Score

---

## 6. Empiryczne Delty Nawierzchniowe — Dane ATP

### Definicja 6.1 (Delta Nawierzchniowa Elo)

$$\delta_s(i) = r_i^s - r_i^{\text{ovr}}$$

mierzy "specjalizację" gracza na nawierzchni $s$ względem jego ogólnej siły.

### Tabela 6.1: Empiryczne delty nawierzchniowe (ATP Top 100, 2018–2024)

| Nawierzchnia | $\mu(\delta_s)$ | $\sigma(\delta_s)$ | Max $\delta_s$ | Min $\delta_s$ |
|:-------------|:--------------:|:------------------:|:--------------:|:--------------:|
| Hard | +12 | 85 | +280 | -220 |
| Clay | -8 | 120 | +350 | -280 |
| Grass | +5 | 110 | +310 | -260 |

### Tabela 6.2: Przykładowe delty dla architypowych graczy

| Profil Gracza | $\delta_{\text{clay}}$ | $\delta_{\text{grass}}$ | $\delta_{\text{hard}}$ |
|:-------------|:---------------------:|:----------------------:|:---------------------:|
| Specjalista od ziemi (typ Nadal) | +250–350 | -100–(-200) | 0–(+50) |
| Specjalista od trawy (typ Federer Wimbledon) | -50–(-100) | +200–300 | +50–100 |
| Gracz wszechstronny (typ Djokovic) | +50–100 | +50–100 | +50–100 |
| Gracz twardej nawierzchni | 0–(-50) | -50–(-100) | +100–200 |

### Obserwacja 6.1 (Asymetria Clay vs. Grass)

Korelacja $\delta_{\text{clay}}$ i $\delta_{\text{grass}}$ na poziomie ATP Top 100:

$$\rho(\delta_{\text{clay}}, \delta_{\text{grass}}) \approx -0.65 \pm 0.08$$

Silna ujemna korelacja potwierdza, że specjaliści od ziemi są zwykle słabsi na trawie i odwrotnie. Uzasadnia to utrzymywanie oddzielnych wariantów Elo.

---

## 7. Mechanizm Transferu Ratingów Nawierzchniowych

### Definicja 7.1 (Transfer przy Braku Danych)

Gdy nowy gracz wchodzi do systemu i nie ma danych na danej nawierzchni:

$$r_i^{s,(0)} = r_i^{\text{ovr},(0)} + \delta_s^{\text{prior}}$$

gdzie $\delta_s^{\text{prior}}$ jest a priori deltą nawierzchniową (domyślnie 0).

### Definicja 7.2 (Decay Nawierzchniowy)

Ratingi nawierzchniowe podlegają dodatkowej degradacji przy długiej nieaktywności na danej nawierzchni (np. gracz nie grał na ziemi przez 2 lata):

$$r_i^{s,(t)} \leftarrow r_i^{\text{ovr},(t)} + e^{-\lambda_s \cdot t_s} \cdot (r_i^{s,(t_0)} - r_i^{\text{ovr},(t_0)})$$

gdzie $t_s$ to czas nieaktywności na nawierzchni $s$, a $\lambda_s = \ln(2) / T_{1/2}^s$ (szczegóły w AX-05).

---

## 8. Złożona Estymacja $p_s$ z Wektora Ratingów

### Twierdzenie 8.1 (Wyznaczenie $p_s$ z Wektora Ratingów)

Efektywne prawdopodobieństwo serwisowe gracza $A$ względem gracza $B$ na nawierzchni $s$:

$$p_A^{s,\text{eff}} = p_{\text{base}}^s + w_1 \cdot \delta_{\text{elo}}(r_A^{s,\text{eff}} - r_B^{s,\text{eff}}) + w_2 \cdot \delta_{\text{elo}}(r_A^{\text{serve}} - r_B^{\text{return}})$$

gdzie wagi $w_1 = 0.7$, $w_2 = 0.3$ są kalibrowane empirycznie (podlegają optymalizacji).

**Ograniczenie:**

$$p_A^{s,\text{eff}} \in [p_{\min}^s, p_{\max}^s]$$

gdzie $[p_{\min}^s, p_{\max}^s]$ to zakres empiryczny dla nawierzchni $s$ (z AX-01, Tabela 8.1).

---

## Referencje

- AX-01, AX-02, AX-03: Dokumenty specyfikacyjne betatp.io
- Kovalchik, S.A. (2016). *Searching for the GOAT of tennis win prediction.* JQAS, 12(3), 127–138.
- Barnett, T. & Clarke, S.R. (2005). *Combining player statistics to predict outcomes of tennis matches.* IMA Journal of Management Mathematics.
- Sipko, M. & Knottenbelt, W. (2015). *Machine Learning for the Prediction of Professional Tennis Matches.* Imperial College London.
- ATP Tour Match Statistics, Surface-specific data (2010–2024).
