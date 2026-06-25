# AX-06: MONTE CARLO SILNIK
## Formalna Specyfikacja Silnika Symulacji Monte Carlo

**Dokument:** AX-06  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-01, AX-02, AX-03, AX-04, AX-05

---

## 1. Wprowadzenie

Silnik Monte Carlo betatp.io wyznacza rozkłady prawdopodobieństwa wyników meczów tenisowych przez symulację $N = 100{,}000$ rozgrywek. Uzupełnia on analityczne formuły z AX-02 o możliwość obliczania złożonych statystyk (np. rozkłady wyników setowych, oczekiwany czas trwania), których zamknięte formuły analityczne są trudne do wyprowadzenia.

---

## 2. Przestrzeń Probabilistyczna

### Definicja 2.1 (Przestrzeń Probabilistyczna Meczu)

Definiujemy przestrzeń probabilistyczną:

$$(\Omega_M, \mathcal{F}_M, \mathbb{P}_M)$$

gdzie:

**$\Omega_M$** — przestrzeń zdarzeń elementarnych (pełne sekwencje wszystkich punktów meczu):

$$\Omega_M = \bigcup_{n=n_{\min}}^{n_{\max}} \{0,1\}^n$$

gdzie $n_{\min}$ = minimalna liczba punktów w meczu (np. Bo3 bez deuce: $3 \times 4 \times 4 \times 2 = 96$ punktów) i $n_{\max}$ = maksymalna liczba punktów (teoretycznie nieograniczona przy deuces, praktycznie klamrowana do $n_{\max} = 500$).

**$\mathcal{F}_M$** — $\sigma$-algebra generowana przez zdarzenia o postaci:

$$A_k = \{\omega \in \Omega_M : X_k(\omega) = 1\}$$

(gracz serwujący wygrywa $k$-ty punkt meczu).

**$\mathbb{P}_M$** — miara probabilistyczna określona przez Aksjomat A1:

$$\mathbb{P}_M(\omega) = \prod_{k: \text{serwuje A}} p_A^{X_k(\omega)} (1-p_A)^{1-X_k(\omega)} \cdot \prod_{k: \text{serwuje B}} p_B^{X_k(\omega)} (1-p_B)^{1-X_k(\omega)}$$

### Definicja 2.2 (Zmienne Losowe Wyników)

Na $(\Omega_M, \mathcal{F}_M, \mathbb{P}_M)$ definiujemy zmienne losowe:

$$W_A: \Omega_M \to \{0,1\} \quad (W_A = 1 \Leftrightarrow \text{A wygrywa mecz})$$

$$\text{ScoreSet}: \Omega_M \to \{(s_A, s_B): s_A + s_B \in \{2,3\} \text{ (Bo3)}\}$$

$$N_G: \Omega_M \to \mathbb{N} \quad \text{(całkowita liczba gemów)}$$

$$D_{\min}: \Omega_M \to \mathbb{R}_+ \quad \text{(czas trwania meczu w minutach)}$$

---

## 3. Algorytm Symulacji

### Definicja 3.1 (Algorytm Symulacji Gemu — Vectorized)

```python
def simulate_game_vectorized(p_serve: float, N: int, rng) -> np.ndarray:
    """
    Symuluje N gemów równolegle.
    Zwraca: tablica boolowska [N] — czy serwujący wygrał gem.
    """
    # Symulacja punktów bez deuce: P(4-0), P(4-1), P(4-2)
    # Dla P(deuce) i dalej: symulacja geometryczna
    
    # Macierz punktów: [N, MAX_POINTS_PER_GAME]
    points = rng.random((N, MAX_POINTS)) < p_serve  # [N, K]
    
    # Wyznacz kto wygrał gem przez akumulację
    server_wins = np.cumsum(points, axis=1)
    receiver_wins = np.cumsum(~points, axis=1)
    
    # Gem wygrany przez serwującego gdy server_wins >= 4 i server_wins - receiver_wins >= 2
    # Implementacja przez forward-tracking stanu
    return _resolve_game_outcomes(server_wins, receiver_wins)
```

### Definicja 3.2 (Algorytm Symulacji Meczu — Pseudokod Formalny)

```
Algorytm SIMULATE_MATCH:
Wejście: p_A, p_B, format ∈ {Bo3, Bo5}, N = 100_000, seed
Wyjście: wyniki[N] — wektor boolowski (A wygrywa)

1. Inicjalizuj RNG: rng = np.random.default_rng(seed)
2. Inicjalizuj liczniki: wins_A[N] = 0, wins_B[N] = 0
3. Inicjalizuj serwującego: server[N] = A (alternuje per mecz w Bo3/Bo5)
4. Dla każdego seta s = 1, ..., max_sets:
   a. Symuluj set: set_result[N] = SIMULATE_SET(p_A, p_B, server[N], N, rng)
   b. Zaktualizuj: wins_A += (set_result == A); wins_B += (set_result == B)
   c. Wyznacz zakończone mecze: done[N] = (wins_A == required) | (wins_B == required)
   d. Dla nie-zakończonych: alternuj server dla kolejnego seta
   e. Jeżeli all(done): przerwij
5. Zwróć: (wins_A == required)
```

### Definicja 3.3 (Algorytm Symulacji Seta — Pseudokod)

```
Algorytm SIMULATE_SET:
Wejście: p_A, p_B, server_first, N, rng
Wyjście: set_winner[N]

1. gems_A[N] = 0, gems_B[N] = 0, server[N] = server_first
2. Dla gemów g = 1, ..., MAX_GEMS_PER_SET (= 13):
   a. p_serve[N] = (server == A) ? p_A : p_B
   b. gem_result[N] = SIMULATE_GAME_VECTORIZED(p_serve, N, rng)
   c. active[N] = ~done[N]  // wyłącz zakończone sety
   d. Zaktualizuj gems_A[active], gems_B[active] wg. gem_result[active]
   e. Sprawdź zakończenie seta:
      - (gems_A == 6 i gems_B <= 4) lub (gems_A == 7 i gems_B == 5) → set A
      - (gems_B == 6 i gems_A <= 4) lub (gems_B == 7 i gems_A == 5) → set B
      - (gems_A == 6 i gems_B == 6) → SIMULATE_TIEBREAK → set winner
   f. Alternuj server[~done]
3. Zwróć set_winner
```

---

## 4. Kryterium Zbieżności (CLT)

### Twierdzenie 4.1 (Centralne Twierdzenie Graniczne dla Estymatora MC)

Niech $W_1, W_2, \ldots, W_N$ będą iid wynikami symulacji ($W_k = 1$ jeśli $A$ wygrywa $k$-tą symulację). Estymator MC:

$$\hat{P}_N = \frac{1}{N} \sum_{k=1}^{N} W_k$$

Na mocy CTG:

$$\sqrt{N}(\hat{P}_N - P) \xrightarrow{d} \mathcal{N}(0, P(1-P))$$

### Twierdzenie 4.2 (Standardowy Błąd Estymatora)

Standardowy błąd estymatora Monte Carlo:

$$\text{SE}(\hat{P}_N) = \sqrt{\frac{\hat{P}_N(1-\hat{P}_N)}{N}}$$

Maksimum błędu osiągane przy $P = 0.5$:

$$\text{SE}_{\max}(N) = \frac{1}{2\sqrt{N}}$$

### Twierdzenie 4.3 (Wystarczalność $N = 100{,}000$)

Dla $N = 100{,}000$:

$$\text{SE}_{\max} = \frac{1}{2\sqrt{100{,}000}} = \frac{1}{2 \times 316.2} \approx 0.00158$$

$$\text{SE}_{\max} < 0.002 \quad \blacksquare$$

Zatem przy $N = 100{,}000$ iteracjach standardowy błąd estymatora jest mniejszy niż $0.2\%$, co odpowiada przedziałowi ufności 95%:

$$\hat{P}_N \pm 1.96 \times 0.00158 = \hat{P}_N \pm 0.0031$$

Błąd jest pomijalny dla zastosowań zakładowych (minimalna kwota zakładu implikuje próg wrażliwości $\sim 0.5\%$).

### Tabela 4.1: Błąd standardowy vs. liczba iteracji

| $N$ | $\text{SE}_{\max}$ | 95% CI szerokość |
|:---:|:-----------------:|:----------------:|
| 1,000 | 0.01581 | ±0.031 |
| 10,000 | 0.00500 | ±0.010 |
| 50,000 | 0.00224 | ±0.004 |
| **100,000** | **0.00158** | **±0.003** |
| 500,000 | 0.000707 | ±0.001 |
| 1,000,000 | 0.000500 | ±0.001 |

---

## 5. Specyfikacja Wyjść Silnika

### Definicja 5.1 (Pełny Wektor Wyjść)

Silnik Monte Carlo oblicza następujące statystyki:

#### 5.1.1 P(A wygrywa mecz)

$$\hat{P}(A) = \frac{1}{N} \sum_{k=1}^{N} \mathbb{1}[W_k^{(A)} = 1]$$

$$\hat{P}(B) = 1 - \hat{P}(A)$$

#### 5.1.2 Rozkład Wyników Setowych

Dla formatu Bo3, rozkład prawdopodobieństwo każdego możliwego wyniku setowego:

$$\hat{P}(\text{score} = s) = \frac{|\{k : \text{ScoreSet}_k = s\}|}{N}$$

| Wynik | Symbol |
|:------|:------:|
| 2:0 (A wygrywa) | $\hat{P}_{2:0}$ |
| 2:1 (A wygrywa) | $\hat{P}_{2:1}$ |
| 1:2 (B wygrywa) | $\hat{P}_{1:2}$ |
| 0:2 (B wygrywa) | $\hat{P}_{0:2}$ |

Warunek normalizacji: $\hat{P}_{2:0} + \hat{P}_{2:1} + \hat{P}_{1:2} + \hat{P}_{0:2} = 1$.

#### 5.1.3 P(Tiebreak w secie $s$)

$$\hat{P}(\text{TB}_s) = \frac{|\{k : \text{set } s \text{ rozstrzygnięty tiebrakiem}\}|}{N}$$

#### 5.1.4 Oczekiwana liczba gemów

$$\hat{E}[N_G] = \frac{1}{N} \sum_{k=1}^{N} N_G^{(k)}$$

$$\hat{\sigma}[N_G] = \sqrt{\frac{1}{N-1} \sum_{k=1}^{N} (N_G^{(k)} - \hat{E}[N_G])^2}$$

#### 5.1.5 Oczekiwany czas trwania

$$\hat{E}[D_{\min}] = \hat{E}[N_G] \cdot \bar{d}_{\text{gem}}$$

gdzie $\bar{d}_{\text{gem}} = 4.5$ minuty/gem (mediana ATP, Hard surface, 2018–2024).

Tabela korekty:

| Nawierzchnia | $\bar{d}_{\text{gem}}$ [min] |
|:-------------|:----------------------------:|
| Hard | 4.5 |
| Clay | 5.2 |
| Grass | 3.8 |

---

## 6. Implementacja Wektorowa NumPy

### Specyfikacja 6.1 (Wymagania Implementacyjne)

Implementacja silnika MC musi spełniać:

1. **Wektoryzacja:** Wszystkie operacje wykonywane na tablicach NumPy rozmiaru $N$ bez pętli Pythona po iteracjach
2. **Generator liczb losowych:** `numpy.random.default_rng(seed)` (PCG64, kryptograficznie silny, szybki)
3. **Precyzja:** `float32` dla tablic punktów (wystarczająca, 4× szybsza niż `float64`)
4. **Pamięć:** Maksymalne zużycie pamięci $< 2$ GB dla $N = 100{,}000$

### Specyfikacja 6.2 (Wydajność Wymagana)

| Format | Czas obliczeń (100k iter.) | Platforma |
|:-------|:--------------------------:|:----------|
| Bo3 | < 500 ms | CPU (8 rdzeni) |
| Bo5 | < 800 ms | CPU (8 rdzeni) |
| Bo3 (GPU) | < 50 ms | CUDA GPU |

### Specyfikacja 6.3 (Reprodukowalność)

Seed generatora musi być ustawiany deterministycznie:

$$\text{seed} = \text{hash}(\text{match\_id} \| \text{timestamp})$$

Zapewnia to reprodukowalność wyników dla celów audytu i debugowania.

---

## 7. Walidacja Silnika Monte Carlo

### Twierdzenie 7.1 (Zgodność z Formułami Analitycznymi)

Wyniki silnika MC muszą być zgodne z analitycznymi wzorami z AX-02 do dokładności $\epsilon_{\text{tol}} = 0.005$:

$$\left|\hat{P}_{\text{MC}}(A) - P_{\text{analytic}}(A)\right| < \epsilon_{\text{tol}}$$

Weryfikacja przy inicjalizacji systemu: test porównawczy na 10,000 par $(p_A, p_B) \in [0.5, 0.9]^2$.

### Definicja 7.2 (Test Zgodności)

```
TEST_MC_VALIDATION:
Dla (p_A, p_B) in grid_search(0.55, 0.85, step=0.05):
    P_analytic = compute_analytic(p_A, p_B)
    P_mc = run_mc(p_A, p_B, N=100_000)
    assert |P_mc - P_analytic| < 0.005
```

---

## Referencje

- AX-01–AX-05: Dokumenty specyfikacyjne betatp.io
- Robert, C.P. & Casella, G. (2004). *Monte Carlo Statistical Methods.* Springer.
- Kroese, D.P., Taimre, T., & Botev, Z.I. (2011). *Handbook of Monte Carlo Methods.* Wiley.
- NumPy Team. (2020). *Array programming with NumPy.* Nature, 585, 357–362.
- Barnett, T. & Clarke, S.R. (2005). *Combining player statistics to predict outcomes of tennis matches.*
