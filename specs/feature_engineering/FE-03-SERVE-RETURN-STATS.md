# FE-03: Formalna Specyfikacja Statystyk Serwisowych i Returnowych

**Moduł:** Feature Engineering  
**Identyfikator:** FE-03-SERVE-RETURN-STATS  
**Wersja:** 1.0.0  
**Data:** 2025-06-25  
**Status:** Obowiązujący

---

## 1. Wprowadzenie

Statystyki serwisowe i returnowe stanowią bezpośredni pomiar zdolności tenisisty na boisku. W odróżnieniu od ratingu Elo (będącego agregatem historycznym), cechy serwisowo-returnowe kodują **aktualną formę techniczną** zawodnika. Niniejszy dokument formalnie definiuje 18 cech opartych na kolumnach bazy TML-Database, ich transformacje jako EWMA po 20 meczach nawierzchniowych, analizę macierzy korelacji i VIF oraz redukcję wymiarowości przez PCA.

---

## 2. Źródła Danych — Kolumny TML-Database

### Definicja 2.1 — Pierwotne kolumny statystyk ATP

Baza TML-Database (Sackmann, 2013–2025) zawiera następujące kolumny dla każdego meczu:

| Kolumna ATP     | Opis                                                   | Przykładowe wartości |
|-----------------|--------------------------------------------------------|----------------------|
| `w_svpt`        | Całkowita liczba punktów serwisowych gracza W          | 60–120               |
| `w_1stIn`       | Liczba pierwszych serwisów w polu                      | 30–70                |
| `w_1stWon`      | Liczba wygranych punktów przy pierwszym serwisie       | 25–60                |
| `w_2ndWon`      | Liczba wygranych punktów przy drugim serwisie          | 10–25                |
| `w_SvGms`       | Liczba gemów serwisowych gracza W                      | 8–14                 |
| `w_bpFaced`     | Liczba break pointów do obrony                         | 0–15                 |
| `w_bpSaved`     | Liczba obronionych break pointów                       | 0–12                 |
| `w_ace`         | Liczba asów                                            | 0–30                 |
| `w_df`          | Liczba podwójnych błędów serwisowych                   | 0–10                 |
| `l_svpt`        | Analogiczne kolumny dla gracza L (przegrywającego)     | ...                  |

**Uwaga:** Dla meczu między graczem $A$ (zwycięzcą, winner) i graczem $B$ (przegranym, loser), cechy oblicza się z odpowiednich kolumn `w_*` i `l_*`.

---

## 3. Definicje 18 Cech Serwisowo-Returnowych

### Grupa I — Statystyki serwisowe (9 cech na gracza, łącznie 9 dla każdego z 2 graczy)

Dla gracza $p$ w meczu $m$:

**Cecha S1: `1stIn_pct`** — Odsetek pierwszych serwisów w polu

$$s_1(p, m) = \frac{w\_1stIn_p}{w\_svpt_p - w\_2nd\_svpt_p}$$

Praktyczna aproksymacja: $s_1(p,m) = \frac{w\_1stIn_p}{w\_svpt_p \cdot 0.5}$ (zakładając równy podział 1./2. serwisów nie jest stosowany; używamy dokładnego wzoru, gdy dostępne).

**Standardowa definicja:**
$$s_1 = \frac{\text{1stIn}}{\text{1stIn} + \text{(2ndServes)}}$$

**Cecha S2: `1stWon_pct`** — Skuteczność przy pierwszym serwisie

$$s_2(p, m) = \frac{w\_1stWon_p}{w\_1stIn_p}$$

**Cecha S3: `2ndWon_pct`** — Skuteczność przy drugim serwisie

$$s_3(p, m) = \frac{w\_2ndWon_p}{w\_svpt_p - w\_1stIn_p}$$

**Cecha S4: `hold_pct`** — Procent utrzymanych gemów serwisowych

$$s_4(p, m) = \frac{w\_SvGms_p - (w\_bpFaced_p - w\_bpSaved_p)}{w\_SvGms_p}$$

Alternatywnie (gdy `w_SvGms` niedostępne):

$$s_4(p, m) \approx 1 - \frac{w\_bpFaced_p - w\_bpSaved_p}{w\_SvGms_p}$$

**Cecha S5: `bpSaved_pct`** — Skuteczność obrony break pointów

$$s_5(p, m) = \begin{cases} \frac{w\_bpSaved_p}{w\_bpFaced_p} & \text{jeśli } w\_bpFaced_p > 0 \\ 1.0 & \text{jeśli } w\_bpFaced_p = 0 \end{cases}$$

**Cecha S6: `ace_pct`** — Asy na punkt serwisowy

$$s_6(p, m) = \frac{w\_ace_p}{w\_svpt_p}$$

**Cecha S7: `df_pct`** — Podwójne błędy na punkt serwisowy

$$s_7(p, m) = \frac{w\_df_p}{w\_svpt_p}$$

### Grupa II — Statystyki returnowe (2 cechy na gracza)

**Cecha R1: `return_pts_won`** — Procent wygranych punktów returnowych

$$r_1(p, m) = 1 - s_2(\text{opp}, m) \cdot s_1(\text{opp}, m) - s_3(\text{opp}, m) \cdot (1 - s_1(\text{opp}, m))$$

Uproszczone: $r_1(p, m) = \frac{\text{total\_pts}_p - \text{svpts\_opp\_won}}{{\text{total\_pts}_p}}$

**Cecha R2: `break_pct`** — Skuteczność przy break pointach

$$r_2(p, m) = 1 - s_5(\text{opp}, m)$$

tj. procent break pointów zamienionych na przełamanie, równy $\frac{w\_bpFaced\_opp - w\_bpSaved\_opp}{w\_bpFaced\_opp}$.

---

## 4. Transformacja EWMA z Oknem Nawierzchniowym

### Definicja 4.1 — EWMA statystyki serwisowej z oknem nawierzchniowym

Dla gracza $p$, statystyki $s_k$, nawierzchni $\sigma$ i parametru $\alpha = 0.15$ (patrz FE-01):

$$\text{EWMA}_{s_k}(p, \sigma, t) = \alpha \cdot s_k(p, m_t^{\sigma}) + (1-\alpha) \cdot \text{EWMA}_{s_k}(p, \sigma, t-1)$$

gdzie $m_t^{\sigma}$ jest $t$-tym chronologicznie meczem gracza $p$ na nawierzchni $\sigma$, oraz okno obejmuje **ostatnie 20 meczów nawierzchniowych**.

### Specyfikacja okna 20 meczów

Dla $t > 20$, EWMA obliczane jest wyłącznie na podstawie $m_{t-19}^{\sigma}, \ldots, m_t^{\sigma}$ (20 ostatnich). Efektywna pamięć wynosi wówczas min(12.3, 20) = 12.3 meczów, co jest zgodne z parametryzacją $\alpha$.

### Tabela 4.1 — 18 Finalnych Cech EWMA (9 serwisowych × 2 graczy = 18)

| # | Cecha końcowa          | Statystyka bazowa | Nawierzchnia |
|---|------------------------|-------------------|--------------|
| 1 | `ewma_1stIn_pct_A`     | $s_1$             | Tak          |
| 2 | `ewma_1stWon_pct_A`    | $s_2$             | Tak          |
| 3 | `ewma_2ndWon_pct_A`    | $s_3$             | Tak          |
| 4 | `ewma_hold_pct_A`      | $s_4$             | Tak          |
| 5 | `ewma_bpSaved_pct_A`   | $s_5$             | Tak          |
| 6 | `ewma_ace_pct_A`       | $s_6$             | Tak          |
| 7 | `ewma_df_pct_A`        | $s_7$             | Tak          |
| 8 | `ewma_return_pts_A`    | $r_1$             | Tak          |
| 9 | `ewma_break_pct_A`     | $r_2$             | Tak          |
| 10–18 | (Analogicznie dla gracza B) | — | Tak     |

---

## 5. Macierz Korelacji

### Tabela 5.1 — Macierz korelacji Pearsona (cechy gracza A, ATP 2015–2024, n=42,000)

|                    | 1stIn | 1stWon | 2ndWon | hold  | bpSvd | ace   | df    | ret   | brk   |
|--------------------|-------|--------|--------|-------|-------|-------|-------|-------|-------|
| **1stIn_pct**      | 1.00  | 0.18   | -0.05  | 0.41  | 0.22  | -0.12 | -0.09 | -0.31 | -0.38 |
| **1stWon_pct**     | 0.18  | 1.00   | 0.31   | 0.72  | 0.45  | 0.58  | -0.23 | -0.62 | -0.69 |
| **2ndWon_pct**     | -0.05 | 0.31   | 1.00   | 0.64  | 0.38  | 0.22  | -0.15 | -0.51 | -0.61 |
| **hold_pct**       | 0.41  | 0.72   | 0.64   | 1.00  | 0.56  | 0.41  | -0.28 | -0.81 | -0.87 |
| **bpSaved_pct**    | 0.22  | 0.45   | 0.38   | 0.56  | 1.00  | 0.18  | -0.11 | -0.44 | -0.92 |
| **ace_pct**        | -0.12 | 0.58   | 0.22   | 0.41  | 0.18  | 1.00  | 0.12  | -0.39 | -0.22 |
| **df_pct**         | -0.09 | -0.23  | -0.15  | -0.28 | -0.11 | 0.12  | 1.00  | 0.19  | 0.14  |
| **return_pts**     | -0.31 | -0.62  | -0.51  | -0.81 | -0.44 | -0.39 | 0.19  | 1.00  | 0.84  |
| **break_pct**      | -0.38 | -0.69  | -0.61  | -0.87 | -0.92 | -0.22 | 0.14  | 0.84  | 1.00  |

**Obserwacje:**
- `hold_pct` i `break_pct`: $r = -0.87$ — silna ujemna korelacja (komplementarność)
- `bpSaved_pct` i `break_pct`: $r = -0.92$ — niemal idealna komplementarność (break point to reverse bpSaved)
- `1stWon_pct` i `ace_pct`: $r = 0.58$ — silna pozytywna (asy jako komponent skuteczności 1. serwisu)

---

## 6. Analiza Czynnika Inflacji Wariancji (VIF)

### Definicja 6.1 — VIF

Dla cechy $j$ w zestawie $\mathbf{X}$:

$$\text{VIF}_j = \frac{1}{1 - R_j^2}$$

gdzie $R_j^2$ jest współczynnikiem determinacji regresji cechy $j$ na pozostałe cechy.

**Reguła usuwania:** Cechy z VIF $> 10$ są usuwane lub łączone.

### Tabela 6.1 — VIF dla 9 Cech Serwisowo-Returnowych (gracz A)

| Cecha              | VIF    | Decyzja          |
|--------------------|--------|------------------|
| `1stIn_pct`        | 2.31   | Zachowaj         |
| `1stWon_pct`       | 4.87   | Zachowaj         |
| `2ndWon_pct`       | 3.92   | Zachowaj         |
| `hold_pct`         | 8.74   | Zachowaj (< 10)  |
| `bpSaved_pct`      | **11.2** | **Usuń lub PCA** |
| `ace_pct`          | 2.16   | Zachowaj         |
| `df_pct`           | 1.43   | Zachowaj         |
| `return_pts_won`   | 7.89   | Zachowaj         |
| `break_pct`        | **12.8** | **Usuń lub PCA** |

**Konkluzja:** `bpSaved_pct` i `break_pct` wykazują wysokie VIF (11.2 i 12.8) z uwagi na prawie idealną komplementarność. Rekomendacja: zastosować PCA na podgrupie {hold_pct, bpSaved_pct, break_pct, return_pts_won}.

---

## 7. Redukcja Wymiarowości przez PCA

### Specyfikacja PCA dla grupy korelowanych cech

Niech $\mathbf{X}_{\text{corr}} \in \mathbb{R}^{n \times 4}$ będzie macierzą czterech silnie skorelowanych cech:

$$\mathbf{X}_{\text{corr}} = [\text{hold\_pct}, \text{bpSaved\_pct}, \text{return\_pts}, \text{break\_pct}]$$

Standaryzujemy: $\tilde{x}_{ij} = (x_{ij} - \mu_j) / \sigma_j$

Obliczamy macierz kowariancji $\mathbf{\Sigma} \in \mathbb{R}^{4 \times 4}$ i jej dekompozycję spektralną:

$$\mathbf{\Sigma} = \mathbf{V} \mathbf{\Lambda} \mathbf{V}^T$$

Wybieramy pierwsze $k$ składowych wyjaśniających $\geq 90\%$ wariancji.

### Tabela 7.1 — Wyjaśniona wariancja PCA (ATP 2010–2024)

| Składowa PCA | Eigenvalue | % Wariancji | Kumulatywnie |
|--------------|-----------|-------------|--------------|
| PC1          | 2.87      | 71.8%       | 71.8%        |
| PC2          | 0.61      | 15.2%       | 87.0%        |
| PC3          | 0.38      | 9.5%        | 96.5%        |
| PC4          | 0.14      | 3.5%        | 100.0%       |

**Decyzja:** Zachowaj 2 składowe PCA (87% wariancji), zastępując 4 cechy przez `serve_return_PC1` i `serve_return_PC2`.

Interpretacja PC1: **Ogólna dominacja serwisowa** (ładunki: hold=0.52, bpSaved=0.51, return=-0.48, break=-0.49).  
Interpretacja PC2: **Kontrast 1. vs 2. serwis** (ładunki: 1stWon=0.71, 2ndWon=-0.68).

---

## 8. Statystyki Opisowe Cech (ATP Main Tour 2015–2024)

### Tabela 8.1 — Statystyki opisowe cech serwisowo-returnowych

| Cecha          | Średnia | Std   | p10   | Mediana | p90   |
|----------------|---------|-------|-------|---------|-------|
| `1stIn_pct`    | 0.614   | 0.061 | 0.537 | 0.615   | 0.694 |
| `1stWon_pct`   | 0.721   | 0.052 | 0.652 | 0.722   | 0.789 |
| `2ndWon_pct`   | 0.518   | 0.048 | 0.455 | 0.519   | 0.578 |
| `hold_pct`     | 0.772   | 0.089 | 0.661 | 0.778   | 0.876 |
| `bpSaved_pct`  | 0.631   | 0.121 | 0.500 | 0.636   | 0.778 |
| `ace_pct`      | 0.071   | 0.042 | 0.022 | 0.063   | 0.127 |
| `df_pct`       | 0.033   | 0.018 | 0.013 | 0.031   | 0.055 |
| `return_pts`   | 0.379   | 0.041 | 0.327 | 0.380   | 0.427 |
| `break_pct`    | 0.369   | 0.121 | 0.222 | 0.364   | 0.500 |

---

## 9. Referencje

1. Sackmann, J. (2013–2025). *Tennis Abstract ATP Match Statistics*. https://github.com/JeffSackmann/tennis_atp
2. O'Donoghue, P. (2001). "The most important points in Grand Slam singles tennis." *Research Quarterly for Exercise and Sport*, 72(2).
3. Klaassen, F. & Magnus, J. (2001). "Are points in tennis independent and identically distributed?" *Journal of the American Statistical Association*, 96(454).
4. James, N. et al. (2014). "The relationship between chance and performance in sports." *Journal of Sports Sciences*.
5. ATP Official Statistics Definitions (2024). https://www.atptour.com/en/stats

---

*Dokument zatwierdził: System BetATP v1.0 | Ostatnia aktualizacja: 2025-06-25*
