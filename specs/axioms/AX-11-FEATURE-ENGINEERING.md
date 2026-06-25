# AX-11: FEATURE ENGINEERING — SPECYFIKACJA FORMALNA

**Dokument:** AX-11  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. ZASADY OGÓLNE I GRANICE DANYCH

### Definicja 1.1 — Wektor cech

Niech $\mathbf{x}_{ij} \in \mathbb{R}^d$ będzie wektorem cech meczu $m$ pomiędzy zawodnikami $i$ (home/server) i $j$ (away). Wymiar $d \geq 50$.

### Aksjomat 1.1 — Zasada braku przecieku danych (No Future Leakage)

**AKSJOMAT:** Dla każdego meczu $m$ z datą $t_m$, KAŻDA cecha $x_k \in \mathbf{x}_{ij}$ musi spełniać:

$$x_k = f(\mathcal{D}_{t < t_m})$$

gdzie $\mathcal{D}_{t < t_m}$ oznacza zbiór danych z datami ściśle wcześniejszymi niż $t_m$.

**Konsekwencje:**
- Rankingi: używamy stanu rankingu ATP na dzień $t_m - 1$
- Statystyki: agregaty do dnia $t_m - 1$ włącznie
- H2H: tylko mecze zakończone przed $t_m$
- Kursy bukmacherskie: NIGDY nie używać closing odds jako cechy wejściowej

### Aksjomat 1.2 — Symetria cech

Wektor cech jest konstruowany jako różnica (A - B): dla każdej cechy skalarne $f_k^A$ i $f_k^B$:

$$x_k = f_k^A - f_k^B$$

Gwarantuje to, że $\mathbf{x}_{AB} = -\mathbf{x}_{BA}$ (zmiana kolejności zawodników odwraca znak).

---

## 2. EWMA — WYKŁADNICZO WAŻONA ŚREDNIA KROCZĄCA

### Definicja 2.1 — EWMA

Dla zmiennej $v_t$ (statystyk zawodnika) z czasem $t$, **Exponentially Weighted Moving Average** z parametrem zaniku $\alpha$ definiujemy rekurencyjnie:

$$\text{EWMA}_t = \alpha \cdot v_t + (1 - \alpha) \cdot \text{EWMA}_{t-1}$$

z inicjalizacją $\text{EWMA}_0 = v_0$ (pierwsza obserwacja).

**Parametr systemowy betatp.io:**

$$\alpha = 0.15$$

### Uzasadnienie wyboru $\alpha = 0.15$

Efektywny półokres życia obserwacji:

$$\tau_{1/2} = \frac{\ln(0.5)}{\ln(1 - \alpha)} = \frac{\ln(0.5)}{\ln(0.85)} \approx \frac{-0.6931}{-0.1625} \approx 4.27 \text{ meczów}$$

Interpretacja: poprzedni mecz ma wagę $0.85 \times$ wagi bieżącego. Po 4 meczach waga spada do 50%.

### Własność 2.1 — Wagi czasowe

Waga obserwacji sprzed $k$ meczów:

$$w_k = \alpha \cdot (1-\alpha)^k$$

| $k$ (meczów temu) | Waga $w_k$ | Skumulowana |
|--------------------|------------|-------------|
| 0 (bieżący) | 0.1500 | 0.1500 |
| 1 | 0.1275 | 0.2775 |
| 2 | 0.1084 | 0.3859 |
| 3 | 0.0921 | 0.4780 |
| 5 | 0.0664 | 0.6302 |
| 10 | 0.0296 | 0.8031 |
| 20 | 0.0065 | 0.9548 |

### Definicja 2.2 — EWMA ważona powierzchnią

Dla uwzględnienia różnych nawierzchni (hard, clay, grass, indoor):

$$\text{EWMA}_{\text{surf},t} = \alpha_s \cdot v_t \cdot \mathbb{1}[s_t = s] + (1-\alpha_s) \cdot \text{EWMA}_{\text{surf},t-1}$$

gdzie $\alpha_s = 0.20$ dla bieżącej nawierzchni, aktualizacja tylko gdy $s_t = s$.

---

## 3. BLOK 1 — CECHY ELO

### Definicja 3.1 — Elo różnicowe

| ID | Cecha | Formuła |
|----|-------|---------|
| F01 | Elo diff (ogólne) | $\text{Elo}_A - \text{Elo}_B$ |
| F02 | Elo diff (nawierzchnia) | $\text{Elo}_A^{\text{surf}} - \text{Elo}_B^{\text{surf}}$ |
| F03 | Elo diff (hard) | $\text{Elo}_A^{H} - \text{Elo}_B^{H}$ |
| F04 | Elo diff (clay) | $\text{Elo}_A^{C} - \text{Elo}_B^{C}$ |
| F05 | Elo diff (grass) | $\text{Elo}_A^{G} - \text{Elo}_B^{G}$ |
| F06 | Elo win prob | $P_{\text{Elo}} = \sigma((\text{Elo}_A - \text{Elo}_B)/400 \cdot \ln 10)$ |
| F07 | Elo momentum | $\Delta\text{Elo}_A^{(5)} - \Delta\text{Elo}_B^{(5)}$ (zmiana Elo ostatnie 5 meczów) |

gdzie $\sigma(x) = 1/(1 + 10^{-x/400})$ — standardowa funkcja Elo.

---

## 4. BLOK 2 — FORMA EWMA

| ID | Cecha | Definicja |
|----|-------|-----------|
| F08 | Win rate EWMA | EWMA wygranych (0/1) $\alpha=0.15$ |
| F09 | Win rate EWMA (nawierzchnia) | EWMA wygranych na bieżącej nawierzchni |
| F10 | Win rate EWMA (5 meczów) | Prosta średnia z 5 ostatnich meczów |
| F11 | Sets won % EWMA | EWMA frakcji wygranych setów |
| F12 | Games won % EWMA | EWMA frakcji wygranych gemów |
| F13 | Tiebreak win % | EWMA wygranych tie-breaków |
| F14 | 3rd set win % | EWMA wygranych decydujących setów |

---

## 5. BLOK 3 — STATYSTYKI SERWIS/RETURN

### Definicja 5.1 — Kluczowe wskaźniki serwisowe

Niech $\text{ACE}$, $\text{DF}$, $\text{1stIn}$, $\text{1stWon}$, $\text{2ndWon}$, $\text{bpSaved}$ to standardowe statystyki ATP.

| ID | Cecha | Formuła | Benchm. ATP Top100 |
|----|-------|---------|-------------------|
| F15 | Ace% diff | $\text{ACE}/\text{svPts}_A - \text{ACE}/\text{svPts}_B$ | ~7.5% |
| F16 | DF% diff | $\text{DF}/\text{svPts}_A - \text{DF}/\text{svPts}_B$ | ~3.2% |
| F17 | 1stIn% diff | $\text{1stIn}/\text{svPts}$ diff | ~62% |
| F18 | 1stWon% diff | $\text{1stWon}/\text{1stIn}$ diff | ~74% |
| F19 | 2ndWon% diff | $\text{2ndWon}/(\text{svPts}-\text{1stIn})$ diff | ~52% |
| F20 | Hold% EWMA diff | EWMA hold rate | ~78% |
| F21 | Break% EWMA diff | EWMA break rate (return) | ~25% |
| F22 | Return points won % diff | $(1 - \text{oppHold\%})$ diff | ~36% |
| F23 | Serve rating diff | $0.5(\text{1stWon}+\text{2ndWon})/\text{svPts}$ | ~65% |
| F24 | Return rating diff | Analogicznie dla return | ~35% |

Wszystkie statystyki obliczone jako EWMA($\alpha=0.15$) z danych historycznych.

---

## 6. BLOK 4 — HEAD-TO-HEAD (FILTROWANY PO NAWIERZCHNI)

### Definicja 6.1 — H2H z filtrowaniem

Niech $\mathcal{H}_{ij}^s$ = zbiór meczów H2H na nawierzchni $s$.

| ID | Cecha | Formuła |
|----|-------|---------|
| F25 | H2H wins diff (all) | $n_{\text{won}}^{A,\text{all}} - n_{\text{won}}^{B,\text{all}}$ |
| F26 | H2H win% (all) | $n_{\text{won}}^A / (n_{\text{won}}^A + n_{\text{won}}^B)$, NaN→0.5 |
| F27 | H2H win% (surface) | Analogicznie dla $\mathcal{H}_{ij}^s$ |
| F28 | H2H win% (last 3) | Ostatnie 3 mecze H2H |
| F29 | H2H count | $|\mathcal{H}_{ij}|$ (całkowita liczba meczów) |

**Reguła NaN:** Gdy $|\mathcal{H}_{ij}^s| = 0$, F27 = 0.0 (brak informacji). Gdy $|\mathcal{H}_{ij}| < 3$, F28 = F26 (fallback).

---

## 7. BLOK 5 — ZMĘCZENIE I HARMONOGRAM

Szczegółowe definicje w dokumencie AX-15.

| ID | Cecha | Definicja |
|----|-------|-----------|
| F30 | FatigueScore diff | $\text{FS}(A, t_m) - \text{FS}(B, t_m)$ |
| F31 | Days since last match diff | $\text{days}_A - \text{days}_B$ |
| F32 | Sets played last 7 days diff | $\text{sets7}_A - \text{sets7}_B$ |
| F33 | Travel distance diff | $\text{km}_A - \text{km}_B$ (szacowany) |
| F34 | Timezone crossings diff | $\Delta\text{TZ}_A - \Delta\text{TZ}_B$ |

---

## 8. BLOK 6 — KONTEKST TURNIEJU

| ID | Cecha | Typ | Wartości |
|----|-------|-----|---------|
| F35 | Tournament level | Kategorialny | Slam=4, Masters=3, 500=2, 250=1 |
| F36 | Round number | Numeryczny | R128=1, ..., F=7 |
| F37 | Surface encoding | Kategorialny | Hard=0, Clay=1, Grass=2, Indoor=3 |
| F38 | Is Grand Slam | Binarny | $\{0, 1\}$ |
| F39 | Prize money log | Numeryczny | $\ln(\text{prize\_money\_USD})$ |
| F40 | Home advantage | Numeryczny | +1 (gracz A), −1 (gracz B), 0 (neutral) |

---

## 9. BLOK 7 — PROFIL GRACZA

| ID | Cecha | Definicja |
|----|-------|-----------|
| F41 | Age diff | $\text{age}_A - \text{age}_B$ (lata) |
| F42 | Age²diff | $\text{age}_A^2 - \text{age}_B^2$ (nieliniowość) |
| F43 | ATP rank diff | $\text{rank}_B - \text{rank}_A$ (sign: niższy rank = lepiej) |
| F44 | ATP rank log diff | $\ln(\text{rank}_B) - \ln(\text{rank}_A)$ |
| F45 | ATP rank points diff | $\text{pts}_A - \text{pts}_B$ |
| F46 | Hand encoding | $(\text{R}=1, \text{L}=-1)$: $\text{hand}_A - \text{hand}_B$ |
| F47 | Years on tour diff | $\text{yrs}_A - \text{yrs}_B$ |
| F48 | Career titles diff | $\ln(1+\text{titles}_A) - \ln(1+\text{titles}_B)$ |

---

## 10. BLOK 8 — CECHY MCP (SHOT-BY-SHOT)

### Definicja 10.1 — MCP Features

MCP (Match Charting Project, Tennis Abstract) dostarcza dane uderzeń. Cechy agregowane jako EWMA z ostatnich $K=10$ meczów:

| ID | Cecha | Definicja |
|----|-------|-----------|
| F49 | Forehand winner % diff | EWMA FH winners / total points |
| F50 | Backhand error % diff | EWMA BH unforced errors / total points |
| F51 | Net approaches win % diff | EWMA wygranych po podejściu do siatki |
| F52 | Rally length preference diff | Średnia długość wymiany EWMA |
| F53 | Return depth rating diff | Głębokość returnu (0=płytki, 1=głęboki) |
| F54 | 2nd serve pressure index diff | Agresja na 2nd serve returnie |

**Dostępność:** MCP dane dostępne dla ~60% meczów ATP Top50. Brakujące: imputer mediany grupowej (nawierzchnia × poziom turnieju).

---

## 11. NORMALIZACJA WEKTORA CECH

### Definicja 11.1 — Standardyzacja

Dla każdej cechy $x_k$, stosujemy standaryzację z-score na zbiorze treningowym:

$$\tilde{x}_k = \frac{x_k - \mu_k^{\text{train}}}{\sigma_k^{\text{train}}}$$

**Ważne:** $\mu_k$ i $\sigma_k$ obliczane WYŁĄCZNIE na zbiorze treningowym, nie walidacyjnym/testowym.

### Definicja 11.2 — Clipping

$$\hat{x}_k = \text{clip}(\tilde{x}_k,\ -5,\ +5)$$

Wartości powyżej 5 odchyleń standardowych są przycinane do $\pm 5$.

---

## 12. PEŁNA TABLICA CECH

| Block | ID | Nazwa | Typ |
|-------|----|-------|-----|
| Elo | F01–F07 | Elo rating features | Numeryczny |
| Forma | F08–F14 | EWMA form | Numeryczny |
| Serwis | F15–F24 | Serve/Return stats | Numeryczny |
| H2H | F25–F29 | Head-to-Head | Numeryczny |
| Fatigue | F30–F34 | Fatigue/Scheduling | Numeryczny |
| Turniej | F35–F40 | Tournament context | Mieszany |
| Profil | F41–F48 | Player profile | Numeryczny |
| MCP | F49–F54 | Shot-by-shot | Numeryczny |
| **Łącznie** | **F01–F54** | **54 cechy** | — |

---

## 13. REFERENCJE

1. ATP Match Statistics Database, 1990–2024.
2. Tennis Abstract MCP (Match Charting Project), Jeff Sackmann, 2014–2024.
3. Kovalchik, S.A. (2016). "Searching for the GOAT of tennis win prediction." *Journal of Quantitative Analysis in Sports*, 12(3), 127–138.
4. Sipko, M., Knottenbelt, W. (2015). "Machine Learning for the Prediction of Professional Tennis Matches." *Imperial College Computing Student Workshop*.
5. Huang, T., Weng, R. (2011). "A generalized Bradley-Terry model: From group competition to individual skill." *Pattern Recognition*, 44(3), 760–771.

---

*Dokument AX-11 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
