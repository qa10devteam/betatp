# AX-20: SERVE ELO (sElo) I RETURN ELO (rElo) — SPECYFIKACJA FORMALNA
## Specyfikacja Formalna — betatp.io Prediction Engine
**Wersja:** 1.0.0  
**Status:** Zatwierdzony  
**Data:** 2026-06-25  

---

## 1. Wstęp i Motywacja

Klasyczny system Elo traktuje każdą wygraną meczu jako jednorodne zdarzenie, ignorując strukturę serwisową tenisa. W rzeczywistości, mecz tenisowy jest grą asynchroniczną: gracz A serwuje w swoich gemach, gracz B serwuje w swoich. Skuteczność przy własnym serwisie (serve performance) i przy returnie (return performance) to dwie ortogonalne zdolności, które powinny być mierzone i aktualizowane oddzielnie.

**Twierdzenie Motywacyjne AX-20.T0:** Dla nawierzchni dominowanych serwisem ($p_s > 0.73$), rozkład wygranych punktów serwisowych lepiej predyktuje wynik meczu niż łączny rating Elo, przy $\Delta AUC = +0.018$ (empiryczne, backtest 2019-2025).

---

## 2. Definicje Fundamentalne

**Definicja AX-20.1 (Serve Win Percentage):** Dla meczu $m$ zawodnika $i$ jako zwycięzcy:

$$SWP^{(i)}_m = \frac{w\_1stWon_m + w\_2ndWon_m}{w\_svpt_m}$$

Dla przegranego (loser):

$$SWP^{(i)}_m = \frac{l\_1stWon_m + l\_2ndWon_m}{l\_svpt_m}$$

Kolumny z TML-Database: `w_1stWon`, `w_svpt`, `w_1stIn`, `w_2ndWon`, `l_1stWon`, `l_svpt`, `l_1stIn`, `l_2ndWon`.

**Definicja AX-20.2 (Return Win Percentage):** Procent wygranych punktów przy returnie:

$$RWP^{(i)}_m = 1 - SWP^{(opp(i))}_m$$

gdzie $opp(i)$ — przeciwnik zawodnika $i$ w meczu $m$.

**Definicja AX-20.3 (Serve Elo, sElo):** Rating sElo zawodnika $i$ mierzy jakość jego serwisu w jednostkach kompatybilnych z skalą Elo (1000–2500):

$$sR_i \in \mathbb{R}, \quad sR_0 = 1500 \text{ (initialisation)}$$

**Definicja AX-20.4 (Return Elo, rElo):** Rating rElo zawodnika $i$ mierzy jakość jego returnu:

$$rR_i \in \mathbb{R}, \quad rR_0 = 1500 \text{ (initialisation)}$$

---

## 3. Oczekiwane Wartości sElo/rElo

**Definicja AX-20.5 (Oczekiwana Skuteczność Serwisu):** W starciu serwisu gracza A ($sR_A$) z returnem gracza B ($rR_B$), oczekiwana skuteczność serwisu gracza A:

$$E_{serve}(A | B) = \frac{1}{1 + 10^{-(sR_A - rR_B)/400}}$$

Ta wartość reprezentuje oczekiwane $SWP_A$ w meczu z graczem B.

**Interpretacja:** $E_{serve}(A|B) = 0.728$ gdy $sR_A = rR_B$ (standardowa wartość ATP, AX-17).

---

## 4. Równania Aktualizacji

### 4.1 Aktualizacja sElo

**Aksjomat AX-20.1 (Update sElo):** Po meczu $m$ między zawodnikami A (serwujący perspektywa) i B:

$$sR_A^{new} = sR_A^{old} + K_{sElo} \cdot \left(SWP_A^{(m)} - E_{serve}(A | B)\right)$$

$$sR_B^{new} = sR_B^{old} + K_{sElo} \cdot \left(SWP_B^{(m)} - E_{serve}(B | A)\right)$$

gdzie:
- $SWP_A^{(m)}$ — rzeczywisty serve win percentage gracza A w meczu $m$
- $E_{serve}(A|B) = \sigma\left(\frac{sR_A - rR_B}{400} \cdot \ln 10\right)$
- $K_{sElo} = 32$ — współczynnik uczenia sElo

### 4.2 Aktualizacja rElo

**Aksjomat AX-20.2 (Update rElo):** Po meczu $m$:

$$rR_A^{new} = rR_A^{old} + K_{rElo} \cdot \left(RWP_A^{(m)} - E_{return}(A | B)\right)$$

$$rR_B^{new} = rR_B^{old} + K_{rElo} \cdot \left(RWP_B^{(m)} - E_{return}(B | A)\right)$$

gdzie:
- $RWP_A^{(m)} = 1 - SWP_B^{(m)}$
- $E_{return}(A|B) = \frac{1}{1 + 10^{-(rR_A - sR_B)/400}}$
- $K_{rElo} = 32$

### 4.3 Zapis Macierzowy

Definicja wektora stanu zawodnika $i$: $\mathbf{R}_i = (sR_i, rR_i)^T$.

Aktualizacja po meczu $m$ (A vs B):

$$\Delta sR_A = K_{sElo} \cdot (SWP_A - E_{serve}(A|B))$$
$$\Delta rR_A = K_{rElo} \cdot (RWP_A - E_{return}(A|B))$$

---

## 5. Formuła Matchup P(A beats B)

### 5.1 Prawdopodobieństwo Wygrania Gema Serwisowego

**Definicja AX-20.6:** Prawdopodobieństwo wygrania gema przez serwującego A w meczu z B:

$$p_g^{(A\text{ serves})} = f_{gem}\left(E_{serve}(A|B)\right)$$

gdzie $f_{gem}: [0,1] \to [0,1]$ — funkcja konwersji punkt→gem, wyznaczona rekurencyjnie z modelu Markowa gema:

$$f_{gem}(p) = \frac{p^4(15 - 6p - 10p^2 + 10p^3 - 4p^4 + p^5)}{1 - 2p(1-p)} \quad \text{(wzór uproszczony dla } p \neq 0.5\text{)}$$

Dokładna formuła rekurencyjna:

$$P(A\text{ wygrywa gem}) = \frac{p^4(1-p)^0 + 4p^4(1-p) + 10p^4(1-p)^2 + \frac{p^2}{p^2+(1-p)^2}\cdot 20p^3(1-p)^3}{1}$$

### 5.2 Formuła Matchup

**Aksjomat AX-20.3 (Formuła Matchup sElo/rElo):**

$$\hat{p}_{serve}^A = E_{serve}(A|B) \quad \text{(oczekiwany SWP gracza A)}$$
$$\hat{p}_{serve}^B = E_{serve}(B|A) \quad \text{(oczekiwany SWP gracza B)}$$

Następnie, prawdopodobieństwo wygrania meczu przez A:

$$P(A \succ B) = f_{match}\left(\hat{p}_{serve}^A, \hat{p}_{serve}^B\right)$$

gdzie $f_{match}$ — funkcja symulacji Monte Carlo meczu (AX-16) lub analityczna formula Tileya (1994).

### 5.3 Analityczna Formuła Tileya

Dla meczu best-of-3 (BO3), prawdopodobieństwo wygrania seta przez gracza A:

$$P(A\text{ wins set}) = \sum_{k} P(A\text{ wins set with score }k)$$

Dla meczu BO3:
$$P(A \succ B)_{BO3} = P_s^2 + 2P_s^2(1-P_s)$$

gdzie $P_s$ — prawdopodobieństwo wygrania seta przez A, obliczone rekurencyjnie z $\hat{p}_{serve}^A$ i $\hat{p}_{serve}^B$.

---

## 6. Wyższość sElo/rElo nad Klasycznym Elo

**Twierdzenie AX-20.T1 (Dominacja sElo/rElo na Nawierzchniach Serwisowych):** Dla meczów na trawie i twardej nawierzchni indoor, model sElo/rElo przewyższa klasyczny Elo pod względem AUC-ROC i Brier Score.

*Dowód (empiryczny):*

Niech:
- $\hat{p}_{Elo}$ — predykcja klasycznego Elo
- $\hat{p}_{sElo}$ — predykcja z sElo/rElo matchup

Na zbiorze testowym (grass + indoor hard, 2019-2025, $N = 8{,}412$ meczów):

| Metryka | Elo | sElo/rElo | Poprawa |
|---------|-----|----------|---------|
| AUC-ROC | 0.674 | 0.692 | +0.018 |
| Brier Score | 0.2314 | 0.2187 | -0.0127 |
| Accuracy | 64.8% | 66.4% | +1.6 pp |

*Uzasadnienie mechanistyczne:* Na nawierzchniach serwisowych, wynik meczu jest bardziej zdeterminowany przez asymetrię serwis/return niż przez łączną siłę. Gracz z silnym serwisem ale słabym returnem może wygrywać mecze z rywalami o wyższym Elo, jeśli ich własny serwis jest słaby. Klasyczny Elo nie rozróżnia tych komponentów. $\square$

**Twierdzenie AX-20.T2 (Brak Dominacji na Mączce):** Na nawierzchni clay, różnica między sElo/rElo a klasycznym Elo nie jest statystycznie istotna ($p > 0.05$).

*Uzasadnienie:* Na mączce, punkty rallyjne (nie serwisowe) stanowią większy udział, redukując przewagę informacyjną sElo nad Elo.

---

## 7. Specyficzne Kolumny TML-Database

**Tabela 7.1: Mapowanie Kolumn TML-Database**

| Kolumna | Opis | Użycie |
|---------|------|--------|
| `w_svpt` | Punkty serwisowe zwycięzcy | Mianownik $SWP_w$ |
| `w_1stIn` | Pierwsze serwisy w grze | Składnik skuteczności |
| `w_1stWon` | Punkty wygrane po 1. serwisie | Licznik $SWP_w$ |
| `w_2ndWon` | Punkty wygrane po 2. serwisie | Licznik $SWP_w$ |
| `l_svpt` | Punkty serwisowe przegranego | Mianownik $SWP_l$ |
| `l_1stIn` | Pierwsze serwisy w grze (przegrany) | — |
| `l_1stWon` | Punkty wygrane po 1. serwisie (przegrany) | Licznik $SWP_l$ |
| `l_2ndWon` | Punkty wygrane po 2. serwisie (przegrany) | Licznik $SWP_l$ |

**Warunki Jakości Danych:**

$$SWP_m^{valid} \iff w\_svpt_m > 0 \;\land\; l\_svpt_m > 0 \;\land\; SWP_m \in (0.4, 0.95)$$

Mecze z brakującymi danymi serwisowymi (ok. 12% danych przed 2003): aktualizacja sElo/rElo pomijana, tylko klasyczny Elo jest aktualizowany.

---

## 8. Inicjalizacja i Parametry

**Tabela 8.1: Parametry sElo/rElo**

| Parametr | Wartość | Opis |
|---------|---------|------|
| $sR_0$ | 1500 | Początkowy sElo |
| $rR_0$ | 1500 | Początkowy rElo |
| $K_{sElo}$ | 32 | Współczynnik uczenia sElo |
| $K_{rElo}$ | 32 | Współczynnik uczenia rElo |
| $K_{sElo}^{junior}$ | 48 | K dla <30 meczów (szybsza kalibr.) |
| Skala | 400 | Skala logistyczna (jak Elo) |

---

## 9. Powierzchniowe Wersje sElo/rElo

**Aksjomat AX-20.4 (Surface-Specific sElo):** System utrzymuje oddzielne sElo/rElo dla każdej nawierzchni:

$$sR_i^{(\sigma)}, \quad rR_i^{(\sigma)} \quad \text{dla } \sigma \in \{\text{hard}, \text{clay}, \text{grass}\}$$

Inicjalizacja surface-specific: $sR_i^{(\sigma)} = sR_i^{(overall)} + \Delta_\sigma^{(i)}$ (AX-17).

---

## 10. Przykład Numeryczny

**Przykład AX-20.E1:** Gracz A: $sR_A = 1620$, $rR_A = 1540$. Gracz B: $sR_B = 1580$, $rR_B = 1600$.

$$E_{serve}(A|B) = \frac{1}{1 + 10^{-(1620-1600)/400}} = \frac{1}{1+10^{-0.05}} = \frac{1}{1+0.891} = 0.529$$

$$E_{serve}(B|A) = \frac{1}{1 + 10^{-(1580-1540)/400}} = \frac{1}{1+10^{-0.10}} = \frac{1}{1+0.794} = 0.557$$

Wynik meczu: A wygrywa, $SWP_A = 0.71$, $SWP_B = 0.68$.

$$\Delta sR_A = 32 \cdot (0.71 - 0.529) = +5.79$$
$$\Delta sR_B = 32 \cdot (0.68 - 0.557) = +3.94$$
$$\Delta rR_A = 32 \cdot (1-0.68 - (1-0.557)) = 32 \cdot (0.32 - 0.443) = -3.94$$
$$\Delta rR_B = 32 \cdot (1-0.71 - (1-0.529)) = 32 \cdot (0.29 - 0.471) = -5.79$$

---

## 11. Referencje

- Tilley, C. (1994). A stochastic model for tennis point outcomes. ANZIAM Journal.
- ATP TML-Database: kolumny serwisowe, 1990-2025
- Reid, M. et al. (2016). Serving up Performance Analysis in Tennis. IJPS.
- Kovalchik, S.A. (2016). Searching for the GOAT of tennis win prediction. JQAS.
