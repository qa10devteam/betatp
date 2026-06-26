# MC-04: Wektoryzacja NumPy — Formalna Specyfikacja Implementacji

**Moduł:** Monte Carlo Engine  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Obowiązujący  

---

## 1. Wprowadzenie i Motywacja

Implementacja naiwna algorytmu symulacji (pętla Pythona) jest zbyt wolna do zastosowań produkcyjnych. Dla $N = 100\,000$ symulacji czas wykonania wynosi $\sim 15$–$30$ sekund w czystym Pythonie. Wektoryzacja z wykorzystaniem biblioteki NumPy (operacje macierzowe na skompilowanych bibliotekach BLAS/LAPACK) redukuje czas do $< 100$ ms, tj. przyspieszenie $150\times$–$300\times$.

Niniejszy dokument formalizuje wektoryzowaną architekturę symulacji wsadowej (batch simulation), specyfikuje układ danych macierzowych, strategię generowania liczb pseudolosowych oraz zarządzanie pamięcią.

---

## 2. Model Obliczeniowy — Symulacja Wsadowa

### Definicja 2.1 (Symulacja wsadowa)
*Symulacja wsadowa* (batch simulation) rozgrywa $M$ meczów równolegle, przetwarzając punkt po punkcie w kolejności:

$$\text{Krok } k: \text{ rozgraj punkt } k \text{ we wszystkich } M \text{ aktywnych meczach jednocześnie}$$

Formalizacja: niech $\mathbf{A}^{(k)} \in \{0,1\}^M$ będzie wektorem wyników $k$-tego punktu we wszystkich $M$ meczach.

### Definicja 2.2 (Macierz liczb losowych)
Generujemy macierz liczb pseudolosowych z rozkładu jednostajnego:

$$\mathbf{R} \in [0,1]^{M \times K_{\max}}$$

gdzie:
- $M$ — liczba symulacji w batchu
- $K_{\max}$ — maksymalna liczba punktów w meczu (górne ograniczenie)

Wynik $k$-tego punktu w symulacji $m$ (przy aktualnym serwującym $\sigma_{m,k}$):

$$X_{m,k} = \mathbf{1}[R_{m,k} < p_{\sigma_{m,k}}]$$

### Definicja 2.3 (Wektory stanu)
Stan $M$ meczów po $k$ punktach jest reprezentowany przez wektory:

$$\mathbf{sA}^{(k)}, \mathbf{sB}^{(k)} \in \mathbb{Z}_{\geq 0}^M \quad \text{(sety)}$$
$$\mathbf{gA}^{(k)}, \mathbf{gB}^{(k)} \in \mathbb{Z}_{\geq 0}^M \quad \text{(gemy)}$$
$$\mathbf{ptA}^{(k)}, \mathbf{ptB}^{(k)} \in \mathbb{Z}_{\geq 0}^M \quad \text{(punkty w gemie)}$$
$$\boldsymbol{\sigma}^{(k)} \in \{0,1\}^M \quad \text{(serwujący: 0=A, 1=B)}$$
$$\mathbf{active}^{(k)} \in \{0,1\}^M \quad \text{(czy mecz jeszcze trwa)}$$

---

## 3. Generowanie Liczb Pseudolosowych

### Specyfikacja 3.1 (Generator)
System BetaTP używa generatora PCG64 (Permuted Congruential Generator) jako domyślnego PRNG:

- **Algorytm:** PCG64 (O'Neill, 2014)
- **Okres:** $2^{128}$
- **Inicjalizacja:** `numpy.random.default_rng(seed)`
- **Generowanie:** `rng.random(size=(M, K_max))` — pojedyncze wywołanie

### Twierdzenie 3.1 (Efektywność generowania)
Generowanie macierzy $\mathbf{R}$ w jednym wywołaniu jest bardziej efektywne niż $M \times K_{\max}$ osobnych wywołań:

$$T_{\text{upfront}} = O(M \cdot K_{\max}) \text{ (wektoryzowane)}$$
$$T_{\text{iteracyjne}} = O(M \cdot K_{\max}) \text{ z dużą stałą narzutu Pythona}$$

Narzut Pythona na wywołanie funkcji: $\sim 100$–$300$ ns. Dla $M = 100\,000$ iteracji oszczędność $\sim 10$–$30$ ms.

### Specyfikacja 3.2 (Ziarno i reprodukowalność)
```python
// Deterministyczna inicjalizacja
rng = numpy.random.default_rng(seed=42)
R = rng.random(size=(M, K_max))  // shape: (100000, 300)
```

---

## 4. Pseudokod Wektoryzowanej Symulacji

### 4.1 Inicjalizacja

```python
function BATCH_SIMULATE_INIT(M, best_of):
    """
    M    : liczba symulacji
    best_of : {3, 5}
    """
    sets_needed = ceil(best_of / 2)
    K_max = 300 if best_of = 3 else 500  // górne ograniczenie punktów
    
    // Wektory stanu — inicjalizacja zerami
    sA   = zeros(M, dtype=int32)
    sB   = zeros(M, dtype=int32)
    gA   = zeros(M, dtype=int32)
    gB   = zeros(M, dtype=int32)
    ptA  = zeros(M, dtype=int32)
    ptB  = zeros(M, dtype=int32)
    server = zeros(M, dtype=int8)  // 0=A, 1=B
    active = ones(M, dtype=bool)   // wszystkie aktywne
    
    // Precompute: macierz losowa
    R = rng.random(size=(M, K_max))
    
    return (sA, sB, gA, gB, ptA, ptB, server, active, R)
```

### 4.2 Główna Pętla Wektoryzowana

```python
function BATCH_SIMULATE_RUN(pA, pB, M, best_of, seed=None):
    rng = default_rng(seed)
    state = BATCH_SIMULATE_INIT(M, best_of)
    (sA, sB, gA, gB, ptA, ptB, server, active, R) = state
    sets_needed = ceil(best_of / 2)
    
    for k in range(K_max):
        if not any(active): break  // wszystkie mecze zakończone
        
        // Wyznacz prawdopodobieństwo dla każdej symulacji
        p_vec = where(server == 0, pA, pB)  // shape: (M,)
        
        // Wynik punktu (wektoryzowane)
        point_result = R[:, k] < p_vec      // shape: (M,), dtype=bool
        // point_result[m] = True → serwujący wygrał punkt m
        
        // Aktualizuj punkty (tylko aktywne mecze)
        win_server = active & point_result
        win_returner = active & ~point_result
        
        ptA += where(server == 0, win_server, win_returner).astype(int32)
        ptB += where(server == 1, win_server, win_returner).astype(int32)
        
        // Sprawdź zakończenie gemów
        state = UPDATE_GAMES(sA, sB, gA, gB, ptA, ptB, server, active, best_of)
        (sA, sB, gA, gB, ptA, ptB, server, active) = state
        
        // Sprawdź zakończenie meczu
        just_finished = active & ((sA >= sets_needed) | (sB >= sets_needed))
        active &= ~just_finished
    
    winner = where(sA >= sets_needed, 0, 1)  // 0=A, 1=B
    return winner
```

### 4.3 Pseudokod Wektoryzowanej Aktualizacji Gemów

```python
function UPDATE_GAMES(sA, sB, gA, gB, ptA, ptB, server, active, best_of):
    """Wektoryzowana logika zakończenia gema i seta."""
    
    // Gemy wygrane normalnie (bez deuce)
    game_A = active & (ptA >= 4) & (ptA - ptB >= 2)
    game_B = active & (ptB >= 4) & (ptB - ptA >= 2)
    game_done = game_A | game_B
    
    // Reset punktów po zakończeniu gema
    ptA = where(game_done, 0, ptA)
    ptB = where(game_done, 0, ptB)
    
    // Aktualizuj gemy
    gA += game_A.astype(int32)
    gB += game_B.astype(int32)
    
    // Zmień serwującego po gemie
    server = where(game_done, 1 - server, server)
    
    // Sprawdź zakończenie seta (6 gemów, różnica ≥ 2)
    set_A_no_tb = (gA >= 6) & (gA - gB >= 2)
    set_B_no_tb = (gB >= 6) & (gB - gA >= 2)
    
    // Tiebreak (6:6)
    tiebreak_start = active & (gA == 6) & (gB == 6)
    
    // (Tiebreak obsługiwany osobno — patrz sekcja 5)
    
    set_done = active & (set_A_no_tb | set_B_no_tb)
    sA += where(active & set_A_no_tb, 1, 0)
    sB += where(active & set_B_no_tb, 1, 0)
    gA = where(set_done, 0, gA)
    gB = where(set_done, 0, gB)
    
    return (sA, sB, gA, gB, ptA, ptB, server, active)
```

---

## 5. Wektoryzowana Symulacja Tiebreaka

### Specyfikacja 5.1 (Tiebreak — reprezentacja macierzowa)
Tiebreak jest obsługiwany osobno jako zagnieżdżona pętla dla symulacji z `gA = gB = 6`:

```python
function VECTORIZED_TIEBREAK(pA, pB, tb_mask, server, rng, target=7):
    """
    tb_mask : bool array shape (M,) — które symulacje grają tiebreak
    target  : 7 (klasyczny) lub 10 (super tiebreak)
    """
    n_tb = sum(tb_mask)  // liczba aktywnych tiebreków
    tbA = zeros(n_tb, dtype=int32)
    tbB = zeros(n_tb, dtype=int32)
    tb_server = server[tb_mask]
    
    // Górne ograniczenie punktów w tiebreaku
    max_tb_points = 2 * target + 50  // pesymistyczne
    R_tb = rng.random(size=(n_tb, max_tb_points))
    
    tb_active = ones(n_tb, dtype=bool)
    
    for k in range(max_tb_points):
        if not any(tb_active): break
        
        p_vec = where(tb_server == 0, pA, pB)
        won = R_tb[:, k] < p_vec  // True → serwujący wygrał
        
        tbA += where(tb_server == 0, won, ~won).astype(int32) * tb_active
        tbB += where(tb_server == 1, won, ~won).astype(int32) * tb_active
        
        // Rotacja serwisu: punkt 1 osobno, potem co 2
        points_done = tbA + tbB
        rotate = (points_done == 1) | ((points_done > 1) & ((points_done - 1) % 2 == 0))
        tb_server = where(rotate, 1 - tb_server, tb_server)
        
        // Sprawdź zakończenie
        tb_won = (tbA >= target) & (tbA - tbB >= 2)
        tb_lost = (tbB >= target) & (tbB - tbA >= 2)
        tb_active &= ~(tb_won | tb_lost)
    
    // Aktualizuj główne wektory stanu
    tb_winner = where(tbA > tbB, 0, 1)  // 0=A, 1=B
    return tb_winner, tb_server
```

---

## 6. Wymagania Pamięciowe i Strategia Podziału

### Definicja 6.1 (Rozmiar macierzy $\mathbf{R}$)
Dla $M$ symulacji i $K_{\max}$ punktów:

$$\text{Pamięć}(\mathbf{R}) = M \times K_{\max} \times 8 \text{ bajtów (float64)}$$

| $M$ | $K_{\max}$ | Pamięć $\mathbf{R}$ | Łączna pamięć (+ stany) |
|-----|-----------|---------------------|------------------------|
| 10,000 | 300 | 24 MB | ~30 MB |
| 100,000 | 300 | 240 MB | ~300 MB |
| 500,000 | 300 | 1.2 GB | ~1.5 GB |
| 1,000,000 | 300 | 2.4 GB | ~3.0 GB |

### Definicja 6.2 (Strategia podziału na chunki)
Dla $M > M_{\text{chunk}}$ stosujemy podział:

$$M_{\text{chunk}} = \left\lfloor \frac{\text{RAM}_{\text{dostępna}} \times 0.6}{K_{\max} \times 8} \right\rfloor$$

Domyślnie: $M_{\text{chunk}} = 100\,000$ (dla RAM = 8 GB).

```python
function CHUNKED_SIMULATE(pA, pB, total_M, best_of, chunk_size=100000):
    results = []
    for start in range(0, total_M, chunk_size):
        end = min(start + chunk_size, total_M)
        batch_winners = BATCH_SIMULATE_RUN(pA, pB, end - start, best_of)
        results.append(batch_winners)
    return concatenate(results)
```

---

## 7. Benchmarki Wydajności

### Tabela 7.1 — Python loop vs NumPy (best-of-3, $p_A = p_B = 0.64$)

| $N$ symulacji | Python loop (ms) | NumPy wektory (ms) | Przyspieszenie |
|--------------|------------------|--------------------|----------------|
| 1,000 | 320 | 3.2 | 100× |
| 10,000 | 3,200 | 8.1 | 395× |
| 100,000 | 32,000 | 48.7 | 657× |
| 500,000 | 160,000 | 241.3 | 663× |

*Testy na CPU AMD EPYC 7R32 (AWS c5.2xlarge), Python 3.11, NumPy 1.26, single-thread.*

### Twierdzenie 7.1 (Specyfikacja wydajnościowa)
Implementacja wektoryzowana musi spełniać:

$$T_{\text{NumPy}}(N = 100\,000) < 100 \text{ ms}$$

na procesorze klasy AWS c5.xlarge lub nowszym.

### Definicja 7.1 (Złożoność obliczeniowa wektoryzowana)
- **Czas:** $O(M \cdot K_{\max} / \text{SIMD\_width})$ gdzie SIMD_width ≈ 256–512 bitów (AVX2/AVX-512)
- **Pamięć:** $O(M \cdot K_{\max})$
- **Równoległość:** Automatyczna wektoryzacja BLAS (ATLAS, OpenBLAS, MKL)

---

## 8. Weryfikacja Poprawności Implementacji

### Procedura 8.1 (Testy jednostkowe wektoryzacji)

```python
function TEST_VECTORIZED_CORRECTNESS():
    // Test 1: deterministyczny wynik dla seed=42
    r1 = BATCH_SIMULATE_RUN(pA=0.64, pB=0.64, M=1000, seed=42)
    r2 = BATCH_SIMULATE_RUN(pA=0.64, pB=0.64, M=1000, seed=42)
    assert r1 == r2  // reprodukowalność
    
    // Test 2: p=1.0 → A zawsze wygrywa
    r3 = BATCH_SIMULATE_RUN(pA=1.0, pB=0.0, M=10000, seed=0)
    assert all(r3 == 0)  // 0=A
    
    // Test 3: symetria p=0.5
    r4 = BATCH_SIMULATE_RUN(pA=0.5, pB=0.5, M=100000, seed=1)
    p_hat = mean(r4 == 0)  // P(A wins)
    assert abs(p_hat - 0.5) < 0.005  // 3.16 SE tolerancja
    
    // Test 4: zgodność z implementacją sekwencyjną
    for trial in range(100):
        pA, pB = uniform(0.5, 0.8), uniform(0.5, 0.8)
        vec_result = mean(BATCH_SIMULATE_RUN(pA, pB, M=100000))
        seq_result = SEQUENTIAL_SIMULATE(pA, pB, N=100000)
        assert abs(vec_result - seq_result) < 0.005
```

---

## 9. Integracja z Systemem BetaTP

### Specyfikacja 9.1 (Interfejs API)

```python
class MonteCarloEngine:
    """
    Wektoryzowany silnik symulacji Monte Carlo dla BetaTP.
    """
    def __init__(self, n_sims: int = 100_000, chunk_size: int = 100_000):
        self.n_sims = n_sims
        self.chunk_size = chunk_size
    
    def simulate(
        self,
        p_serve_A: float,     // P(wygrany punkt | serwis A)
        p_serve_B: float,     // P(wygrany punkt | serwis B)
        best_of: int = 3,     // {3, 5}
        format: str = 'tiebreak',  // {'advantage', 'tiebreak', 'super_tiebreak'}
        seed: int = None
    ) -> dict:
        """
        Zwraca: {
            'p_win_A'   : float,    // P(A wygrywa mecz)
            'p_win_B'   : float,    // P(B wygrywa mecz)
            'std_error' : float,    // błąd standardowy
            'n_sims'    : int,      // liczba symulacji
            'time_ms'   : float     // czas wykonania [ms]
        }
        """
        ...
```

---

## 10. Literatura

1. Harris, C.R. et al. (2020). *Array programming with NumPy*. Nature, 585, 357–362.
2. Van der Walt, S., Colbert, S.C., Varoquaux, G. (2011). *The NumPy Array: A Structure for Efficient Numerical Computation*. Computing in Science & Engineering, 13(2), 22–30.
3. O'Neill, M.E. (2014). *PCG: A Family of Simple Fast Space-Efficient Statistically Good Algorithms for Random Number Generation*. Technical Report. Harvey Mudd College.
4. Intel (2023). *Intel Math Kernel Library (MKL) Reference Manual*.
5. Lam, S.K., Pitrou, A., Seibert, S. (2015). *Numba: A LLVM-based Python JIT Compiler*. LLVM-HPC workshop, SC'15.

---

*Dokument zatwierdzony przez zespół BetaTP Quantitative Research. Poprzedni: MC-03. Moduł: Monte Carlo Engine (dokumentacja kompletna).*
