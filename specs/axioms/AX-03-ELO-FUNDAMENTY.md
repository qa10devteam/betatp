# AX-03: ELO — FUNDAMENTY
## Formalna Specyfikacja Systemu Ratingowego Elo dla Tenisa

**Dokument:** AX-03  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-01, AX-02

---

## 1. Wprowadzenie i Motywacja

System Elo, oryginalnie opracowany przez Arpad Elo dla szachów (1960), stanowi fundament systemu ratingowego betatp.io. Niniejszy dokument formalizuje adaptację Elo dla tenisa, uzasadnia wybór parametrów oraz udowadnia optymalne właściwości statystyczne systemu.

Kluczową cechą systemu Elo jest jego interpretowalność jako **estymatora największej wiarygodności (MLE)** parametrów siły graczy w modelu logistycznym. Tej własności poświęcony jest rozdział 6.

---

## 2. Definicje Podstawowe

### Definicja 2.1 (Rating Elo)

Dla gracza $i$ w chwili $t$ definiujemy **rating Elo** jako liczbę rzeczywistą:

$$r_i^{(t)} \in \mathbb{R}, \quad r_i^{(t)} \in [0, 4000]$$

Skala jest umowna. W betatp.io przyjmujemy wartość centralną $\mu_0 = 1500$ (rating inicjalny nowych graczy).

### Definicja 2.2 (Różnica Ratingów)

$$\Delta_{ij}^{(t)} = r_i^{(t)} - r_j^{(t)}$$

### Definicja 2.3 (Funkcja Oczekiwanego Wyniku)

Oczekiwany wynik gracza $i$ w meczu przeciwko $j$:

$$\boxed{E_{ij} = \frac{1}{1 + 10^{-\Delta_{ij}/400}}}$$

Jest to funkcja logistyczna z bazą 10 i skala $s = 400$. Równoważnie:

$$E_{ij} = \sigma\left(\frac{\Delta_{ij}}{400} \cdot \ln(10)\right) = \sigma\left(\frac{\Delta_{ij}}{173.7}\right)$$

gdzie $\sigma(x) = \frac{1}{1+e^{-x}}$ jest standardową funkcją sigmoidalną.

### Definicja 2.4 (Wynik Rzeczywisty)

$$S_{ij} = \begin{cases} 1 & \text{gracz } i \text{ wygrał mecz} \\ 0 & \text{gracz } i \text{ przegrał mecz} \end{cases}$$

---

## 3. Reguła Aktualizacji Elo

### Definicja 3.1 (Reguła Aktualizacji — Forma Podstawowa)

Po meczu pomiędzy graczem $i$ (rating $r_i$) a graczem $j$ (rating $r_j$), nowe ratingi:

$$\boxed{r_i^{(t+1)} = r_i^{(t)} + K \cdot (S_{ij} - E_{ij})}$$

$$r_j^{(t+1)} = r_j^{(t)} + K \cdot (S_{ji} - E_{ji}) = r_j^{(t)} - K \cdot (S_{ij} - E_{ij})$$

Gdzie $K$ jest **współczynnikiem aktualizacji** (K-factor).

### Właściwość 3.1 (Zachowanie sumy ratingów)

$$r_i^{(t+1)} + r_j^{(t+1)} = r_i^{(t)} + r_j^{(t)}$$

**Dowód:** $K(S_{ij} - E_{ij}) - K(S_{ij} - E_{ij}) = 0$ (korzystamy z $S_{ji} = 1 - S_{ij}$, $E_{ji} = 1 - E_{ij}$). $\blacksquare$

---

## 4. Specyfikacja K-Faktorów dla Tenisa ATP

### Definicja 4.1 (Kategorie Turniejów ATP)

| Kategoria | Kod | K-factor | Przykłady |
|:----------|:---:|:--------:|:----------|
| Grand Slam | G | **48** | Australian Open, Roland Garros, Wimbledon, US Open |
| Masters 1000 | M | **36** | Indian Wells, Miami, Madrid, Rome, Canada, Cincinnati, Shanghai, Paris, Monte Carlo |
| ATP 500 | 500 | **28** | Dubai, Rotterdam, Barcelona, Halle, Queen's Club, Hamburg, Washington, Tokyo, Vienna, Basel |
| ATP 250 | 250 | **24** | Wszystkie pozostałe turnieje ATP Tour |
| Davis Cup / ATP Finals | DC/F | **24** | Jako 250 |

### Uzasadnienie K-faktorów

K-faktory odzwierciedlają **prestiż i wagę informacyjną** turnieju:
- Wyższe $K$ → szybsza aktualizacja na podstawie wyniku
- Grand Slam oferuje największą liczbę meczy (do 7) i najsilniejsze pole, zatem jeden wynik ma większą siłę sygnału
- Wartości dobrane empirycznie, tak aby szybkość konwergencji była optymalna (patrz Twierdzenie 6.2)

### Tabela 4.2: Wrażliwość aktualizacji na wynik

Zmiana ratingu po niespodziewanej wygranej ($E_{ij} = 0.2$, $S_{ij} = 1$):

| K-factor | $\Delta r = K(1 - 0.2)$ |
|:--------:|:-----------------------:|
| 24 | +19.2 |
| 28 | +22.4 |
| 36 | +28.8 |
| 48 | +38.4 |

---

## 5. Inicjalizacja Ratingów

### Definicja 5.1 (Rating Inicjalny)

Dla gracza $i$ wchodzącego do systemu z pozycją $\text{rank}_i$ w rankingu ATP:

$$r_i^{(0)} = r_{\text{init}}(\text{rank}_i)$$

Funkcja inicjalizacji:

$$r_{\text{init}}(\text{rank}) = 1500 - \frac{400}{\ln(10)} \cdot \ln\left(\frac{\text{rank}}{1}\right) + \epsilon$$

gdzie $\epsilon \sim \mathcal{N}(0, \sigma_{\text{init}}^2)$, $\sigma_{\text{init}} = 25$ to szum inicjalizacyjny zapobiegający degeneracji.

### Tabela 5.1: Przybliżone ratingi inicjalne wg. rankingu ATP

| Ranking ATP | Rating Elo (przybliżony) |
|:-----------:|:------------------------:|
| 1 | ~2100 |
| 10 | ~1950 |
| 50 | ~1800 |
| 100 | ~1700 |
| 200 | ~1620 |
| 500 | ~1540 |
| 1000+ | ~1500 |

### Korekta 5.1 (Inicjalizacja z historii meczów)

Jeżeli dostępna jest historia meczów gracza (np. przy retrospektywnym ładowaniu danych), rating inicjalny jest szacowany przez uruchomienie algorytmu Elo na pełnej historii meczów z danym $K$-factorem.

---

## 6. Elo jako Estymator Największej Wiarygodności

### Twierdzenie 6.1 (Elo jako MLE)

**Twierdzenie:** Aktualizacja Elo jest gradientowym krokiem optymalizacji log-wiarygodności modelu logistycznego wyników meczów.

**Model logistyczny:** Przyjmujemy, że wynik meczu $S_{ij} \in \{0,1\}$ jest zmienną Bernoulliego:

$$\mathbb{P}(S_{ij} = 1) = E_{ij}(r_i, r_j) = \frac{1}{1 + 10^{-(r_i - r_j)/400}}$$

**Log-wiarygodność** dla zbioru meczów $\mathcal{D} = \{(i_k, j_k, s_k)\}_{k=1}^{N}$:

$$\mathcal{L}(\mathbf{r}) = \sum_{k=1}^{N} \left[ s_k \ln E_{i_k j_k} + (1-s_k) \ln(1-E_{i_k j_k}) \right]$$

**Gradient** względem $r_i$:

$$\frac{\partial \mathcal{L}}{\partial r_i} = \frac{\ln(10)}{400} \sum_{k: i_k = i} (s_k - E_{i_k j_k})$$

**Krok gradientu** w kierunku maksymalizacji $\mathcal{L}$:

$$r_i \leftarrow r_i + \eta \cdot \frac{\partial \mathcal{L}}{\partial r_i} = r_i + \frac{\eta \ln(10)}{400} (s - E_{ij})$$

Identyfikując $K = \frac{\eta \ln(10)}{400}$, otrzymujemy regułę Elo. Zatem:

$$\boxed{\eta = \frac{400 K}{\ln(10)} \approx 173.7 \cdot K / 400 \cdot 400 = 173.7 \cdot K}$$

Dla $K = 32$: $\eta \approx 32 \cdot 173.7 / 400 \approx 13.9$ (współczynnik uczenia się SGD). $\blacksquare$

### Twierdzenie 6.2 (Zbieżność)

Niech $\hat{\mathbf{r}}^*$ będzie MLE parametrów siły graczy. Pod warunkiem że:
1. Każda para graczy rozgrywa wystarczającą liczbę meczy ($n_{ij} \to \infty$)
2. K-factor maleje zgodnie z $K_t = O(1/t)$

Algorytm Elo zbiega do $\hat{\mathbf{r}}^*$ w sensie:

$$\|\mathbf{r}^{(t)} - \hat{\mathbf{r}}^*\|_2 \xrightarrow{t \to \infty} 0 \quad \text{p.n.}$$

**Dowód:** Standardowy wynik zbieżności stochastycznego gradientu dla silnie wklęsłej log-wiarygodności. Szczegóły: patrz Glickman (1999). $\blacksquare$

### Wniosek 6.1

Stały K-factor nie zapewnia asymptotycznej zbieżności do MLE, ale jest pożądany w praktyce ze względu na **śledzenie zmian** wydajności graczy w czasie (gracze nie są stacjonarni).

---

## 7. Własności Statystyczne

### Definicja 7.1 (Błąd Predykcji)

Oczekiwany błąd kalibracji (brier score):

$$\text{BS} = \mathbb{E}\left[(S_{ij} - E_{ij})^2\right]$$

### Twierdzenie 7.1 (Brier Score dla skalibrowanego modelu)

Przy poprawnej kalibracji ($\mathbb{E}[S_{ij}] = E_{ij}$):

$$\text{BS} = E_{ij}(1 - E_{ij})$$

co jest minimalne dla $E_{ij} = 0.5$ (mecz o równych szansach) i wynosi 0.25.

### Definicja 7.2 (Niepewność Ratingu — Model Glickmana)

Rozszerzenie Elo o odchylenie standardowe ratingu $\phi_i$ (Rating Deviation, RD):

$$r_i \sim \mathcal{N}(\mu_i, \phi_i^2)$$

W podstawowym systemie betatp.io pomijamy $\phi_i$ (stały $K$-factor). Rozszerzenie Glicko-2 jest opcjonalne.

---

## 8. Normalizacja i Stabilność Numeryczna

### Definicja 8.1 (Klamrowanie Ratingu)

Aby zapobiec degeneracji numerycznej, stosujemy klamrowanie:

$$r_i^{(t)} \leftarrow \max(r_{\min}, \min(r_{\max}, r_i^{(t)}))$$

gdzie $r_{\min} = 100$, $r_{\max} = 3500$.

### Definicja 8.2 (Re-normalizacja puli graczy)

Opcjonalnie, po każdym cyklu turniejowym, re-normalizujemy ratingi puli aktywnych graczy:

$$r_i \leftarrow r_i - \bar{r} + 1500$$

gdzie $\bar{r}$ jest średnią ratingów aktywnych graczy. Zapobiega to dryfowi średniej puli.

---

## 9. Związek Rating Elo ↔ Parametr Serwisowy $p_s$

### Twierdzenie 9.1 (Mapowanie Elo → $p_s$)

Różnica ratingów Elo $\Delta r$ jest używana do estymacji prawdopodobieństwa wygrania punktu:

$$p_A = p_{\text{base}} + \delta_{\text{elo}}(\Delta r)$$

gdzie $p_{\text{base}}$ jest bazowym prawdopodobieństwem serwisowym dla nawierzchni (z tabeli 8.1 w AX-01), a:

$$\delta_{\text{elo}}(\Delta r) = \frac{E_{AB} - 0.5}{c_{\text{scale}}}$$

Stała $c_{\text{scale}}$ jest kalibrowana empirycznie tak, by odwzorowanie $\Delta r \to p_s$ było zgodne z danymi ATP. Wartość domyślna: $c_{\text{scale}} = 5.0$.

---

## Referencje

- Elo, A.E. (1978). *The Rating of Chessplayers, Past and Present.* Arco Publishing.
- Glickman, M.E. (1999). *Parameter estimation in large dynamic paired comparison experiments.* Applied Statistics, 48(3), 377–394.
- Herbrich, R., Minka, T., & Graepel, T. (2006). *TrueSkill™: A Bayesian Skill Rating System.* NIPS 2006.
- Kovalchik, S.A. (2016). *Searching for the GOAT of tennis win prediction.* Journal of Quantitative Analysis in Sports, 12(3), 127–138.
- ATP Tour Statistics (2018–2024). Dane historyczne meczów ATP.
