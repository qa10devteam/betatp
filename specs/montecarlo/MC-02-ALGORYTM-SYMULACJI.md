# MC-02: Formalny Algorytm Symulacji Meczu Tenisowego

**Moduł:** Monte Carlo Engine  
**Wersja:** 1.0.0  
**Data:** 2025-01-01  
**Status:** Obowiązujący  

---

## 1. Wprowadzenie

Niniejszy dokument zawiera formalną specyfikację algorytmu symulacji pojedynczego meczu tenisowego. Specyfikacja obejmuje: definicję wejść i wyjść, formalny opis stanu gry, reguły punktacji dla wszystkich formatów rozgrywki, obsługę wszystkich przypadków brzegowych oraz pseudokod implementacji. Specyfikacja jest podstawą implementacji w języku Python z wykorzystaniem biblioteki NumPy.

---

## 2. Sygnatura Algorytmu

### Definicja 2.1 (Wejście algorytmu)
Algorytm symulacji przyjmuje parametry:

$$\text{Input} = (p_A,\ p_B,\ \text{best\_of},\ \text{format},\ \text{seed})$$

gdzie:
- $p_A \in (0, 1)$ — prawdopodobieństwo wygrania punktu przez zawodnika A przy własnym serwisie
- $p_B \in (0, 1)$ — prawdopodobieństwo wygrania punktu przez zawodnika B przy własnym serwisie
- $\text{best\_of} \in \{3, 5\}$ — format meczu (do wygrania 2 lub 3 setów)
- $\text{format} \in \{$`advantage`, `tiebreak`, `super_tiebreak`$\}$ — format ostatniego seta
- $\text{seed} \in \mathbb{N} \cup \{$`None`$\}$ — ziarno generatora liczb pseudolosowych

### Definicja 2.2 (Wyjście algorytmu)
Pełna trajektoria meczu:

$$\text{Output} = (\omega,\ S,\ \text{winner},\ \text{stats})$$

gdzie:
- $\omega = (x_1, \ldots, x_N) \in \{0,1\}^N$ — sekwencja wyników punktów
- $S = [(s_1^A, s_1^B), \ldots, (s_k^A, s_k^B)]$ — wyniki setów
- $\text{winner} \in \{A, B\}$ — zwycięzca meczu
- $\text{stats}$ — statystyki (asy, break pointy, itp.)

---

## 3. Stan Gry

### Definicja 3.1 (Krotka stanu gry)
Stan gry w dowolnym momencie meczu jest opisany krotką:

$$\mathcal{S} = (s_A,\ s_B,\ g_A,\ g_B,\ pt_A,\ pt_B,\ \sigma)$$

gdzie:
- $s_A, s_B \in \{0, 1, 2, 3\}$ — liczba wygranych setów przez zawodnika A i B
- $g_A, g_B \in \{0, 1, \ldots, 7\}$ — liczba gemów w bieżącym secie
- $pt_A, pt_B \in \{0, 1, 2, 3, 4, \ldots\}$ — punkty w bieżącym gemie (reprezentacja rozszerzona)
- $\sigma \in \{A, B\}$ — aktualny serwujący

### Definicja 3.2 (Stan początkowy)
$$\mathcal{S}_0 = (0, 0, 0, 0, 0, 0, \sigma_0)$$

gdzie $\sigma_0 \in \{A, B\}$ jest ustalony przed meczem (losowanie lub zgodnie z protokołem).

### Definicja 3.3 (Stan końcowy)
Stan $\mathcal{S}$ jest *stanem końcowym* wtedy i tylko wtedy, gdy:
- $s_A = \lceil \text{best\_of}/2 \rceil$, lub
- $s_B = \lceil \text{best\_of}/2 \rceil$

Dla best-of-3: wymagane 2 sety. Dla best-of-5: wymagane 3 sety.

---

## 4. Reguły Punktacji — Formalizacja

### 4.1 Punktacja w Gemie

#### Tabela 4.1 — Reprezentacja punktów w gemie

| Liczba punktów | Notacja tenisowa | Wartość $pt_i$ |
|----------------|-----------------|----------------|
| 0              | 0               | 0              |
| 1              | 15              | 1              |
| 2              | 30              | 2              |
| 3              | 40              | 3              |
| 4+             | Deuce/Advantage | $\geq 4$       |

#### Definicja 4.1 (Zakończenie gema — bez deuce)
Zawodnik $i$ wygrywa gem jeśli:

$$pt_i = 4 \land pt_j < 3, \quad j \neq i$$

#### Definicja 4.2 (Deuce i przewaga)
Jeśli $pt_A \geq 3 \land pt_B \geq 3$, obowiązuje zasada deuce:
- Stan *deuce*: $pt_A = pt_B$
- Stan *przewaga*: $|pt_A - pt_B| = 1$
- Zawodnik $i$ wygrywa gem gdy: $pt_i - pt_j = 2 \land pt_i \geq 4$

**Funkcja przejścia gema:**

$$\text{GameWon}(pt_A, pt_B) = \begin{cases} A & \text{jeśli } pt_A \geq 4 \land pt_A - pt_B \geq 2 \\ B & \text{jeśli } pt_B \geq 4 \land pt_B - pt_A \geq 2 \\ \text{None} & \text{w przeciwnym razie} \end{cases}$$

### 4.2 Punktacja w Secie — Reguła Standardowa

#### Definicja 4.3 (Zakończenie seta — bez tiebreaka)
Zawodnik $i$ wygrywa set jeśli:

$$g_i \geq 6 \land g_i - g_j \geq 2, \quad j \neq i$$

#### Definicja 4.4 (Tiebreak klasyczny — do 7 z różnicą 2)
Tiebreak rozgrywany jest gdy $g_A = g_B = 6$ (w setach 1–4 lub w formacie `tiebreak`).

Niech $tb_A, tb_B$ — punkty w tiebreaku. Reguła zakończenia:

$$\text{TiebreakWon}(tb_A, tb_B) = \begin{cases} A & \text{jeśli } tb_A \geq 7 \land tb_A - tb_B \geq 2 \\ B & \text{jeśli } tb_B \geq 7 \land tb_B - tb_A \geq 2 \\ \text{None} & \text{w przeciwnym razie} \end{cases}$$

#### Definicja 4.5 (Serwis w tiebreaku)
W tiebreaku serwis zmienia się po pierwszym punkcie, a następnie co 2 punkty:

$$\sigma_{\text{tb}}(k) = \begin{cases} \sigma_0^{\text{tb}} & \text{jeśli } k = 1 \\ \text{zmiana co 2 pkt po } k = 1 \end{cases}$$

Formalnie: zawodnik $\sigma_0^{\text{tb}}$ serwuje punkt $k=1$; następnie serwis obraca się co 2 punkty.

#### Definicja 4.6 (Super tiebreak — do 10 z różnicą 2)
Rozgrywany zamiast trzeciego seta (format `super_tiebreak`, np. ATP Next Gen):

$$\text{SuperTBWon}(tb_A, tb_B) = \begin{cases} A & \text{jeśli } tb_A \geq 10 \land tb_A - tb_B \geq 2 \\ B & \text{jeśli } tb_B \geq 10 \land tb_B - tb_A \geq 2 \\ \text{None} & \text{w przeciwnym razie} \end{cases}$$

#### Definicja 4.7 (Advantage set — bez tiebreaka w ostatnim secie)
Format `advantage` (Wimbledon do 2018, Roland Garros do 2021):

$$\text{AdvSetWon}(g_A, g_B) = \begin{cases} A & \text{jeśli } g_A \geq 6 \land g_A - g_B \geq 2 \\ B & \text{jeśli } g_B \geq 6 \land g_B - g_A \geq 2 \\ \text{None} & \text{w przeciwnym razie} \end{cases}$$

---

## 5. Reguła Rotacji Serwisu

### Definicja 5.1 (Obrót serwisu między gemami)
Serwis przechodzi na przeciwnika po zakończeniu każdego gema (za wyjątkiem tiebreaka):

$$\sigma_{\text{next}} = \begin{cases} B & \text{jeśli } \sigma_{\text{current}} = A \\ A & \text{jeśli } \sigma_{\text{current}} = B \end{cases}$$

### Definicja 5.2 (Rotacja między setami)
Na początku nowego seta serwuje zawodnik, który **nie** serwował w ostatnim gemie poprzedniego seta (lub w tiebreaku pierwszego seta — drugi zawodnik zaczyna set).

---

## 6. Funkcja Przejścia Stanu

### Definicja 6.1 (Funkcja przejścia)
Funkcja $\mathcal{T} : \mathcal{S} \times \{0,1\} \to \mathcal{S}$ realizuje przejście stanu po rozegraniu jednego punktu:

$$\mathcal{T}(\mathcal{S}, x) = \mathcal{S}'$$

gdzie $x = 1$ oznacza wygraną serwującego, $x = 0$ — przegraną.

**Algorytm funkcji przejścia:**

```
function TRANSITION(S, x):
    (sA, sB, gA, gB, ptA, ptB, σ) ← S
    
    // Ustal zwycięzcę punktu
    if σ = A:
        winner_point ← A if x = 1 else B
    else:
        winner_point ← B if x = 1 else A
    
    // Aktualizuj punkty w gemie
    if winner_point = A: ptA ← ptA + 1
    else: ptB ← ptB + 1
    
    // Sprawdź zakończenie gema
    game_winner ← GameWon(ptA, ptB)
    if game_winner ≠ None:
        ptA, ptB ← 0, 0
        if game_winner = A: gA ← gA + 1
        else: gB ← gB + 1
        σ ← opposite(σ)
        
        // Sprawdź zakończenie seta
        set_winner ← SetWon(gA, gB, format, setNumber)
        if set_winner ≠ None:
            gA, gB ← 0, 0
            if set_winner = A: sA ← sA + 1
            else: sB ← sB + 1
    
    return (sA, sB, gA, gB, ptA, ptB, σ)
```

---

## 7. Pseudokod Głównego Algorytmu Symulacji

```python
function SIMULATE_MATCH(pA, pB, best_of, format, seed=None):
    """
    Symuluje pojedynczy mecz tenisowy.
    
    Parametry:
        pA    : float ∈ (0,1) — P(wygrany punkt | serwis A)
        pB    : float ∈ (0,1) — P(wygrany punkt | serwis B)
        best_of : {3, 5}
        format  : {'advantage', 'tiebreak', 'super_tiebreak'}
        seed    : int | None
    
    Zwraca:
        winner   : {'A', 'B'}
        trajectory: list[int]  — sekwencja x_i ∈ {0,1}
        score    : list[tuple] — wyniki setów
    """
    rng ← RandomGenerator(seed)
    S ← (0, 0, 0, 0, 0, 0, σ₀)   // stan początkowy
    sets_needed ← ceil(best_of / 2)
    trajectory ← []
    score ← []
    
    while S.sA < sets_needed AND S.sB < sets_needed:
        // Wyznacz parametr Bernoulliego
        p ← pA if S.σ = A else pB
        
        // Próbkowanie Bernoulliego
        x ← Bernoulli(p, rng)
        trajectory.append(x)
        
        // Przejście stanu
        S ← TRANSITION(S, x)
        
        // Zapisz wynik seta jeśli zakończony
        if set_just_finished(S):
            score.append((S.sA, S.sB))
    
    winner ← A if S.sA = sets_needed else B
    return (winner, trajectory, score)
```

---

## 8. Pseudokod Symulacji Tiebreaka

```python
function SIMULATE_TIEBREAK(pA, pB, target, σ_start, rng):
    """
    target = 7  (klasyczny) lub 10 (super tiebreak)
    """
    tbA, tbB ← 0, 0
    σ ← σ_start
    points_played ← 0
    
    while NOT TiebreakWon(tbA, tbB, target):
        p ← pA if σ = A else pB
        x ← Bernoulli(p, rng)
        
        if σ = A:
            if x = 1: tbA ← tbA + 1
            else:      tbB ← tbB + 1
        else:
            if x = 1: tbB ← tbB + 1
            else:      tbA ← tbA + 1
        
        points_played ← points_played + 1
        
        // Rotacja serwisu: pierwszy punkt osobno, potem co 2
        if points_played = 1:
            σ ← opposite(σ)
        elif (points_played - 1) % 2 = 0:
            σ ← opposite(σ)
    
    return (tbA, tbB, σ)
```

---

## 9. Tabela Przypadków Brzegowych

| Sytuacja | Warunek | Obsługa |
|----------|---------|---------|
| Deuce | $pt_A \geq 3 \land pt_B \geq 3 \land pt_A = pt_B$ | Kontynuuj gem, wymagana różnica 2 |
| Przewaga | $\|pt_A - pt_B\| = 1 \land \min \geq 3$ | Wygrana przy następnym punkcie |
| Tiebreak 6:6 | $g_A = g_B = 6$ (sety 1–4) | Graj tiebreak do 7 |
| Advantage set | $g_A = g_B = 6$ (ostatni set, format `advantage`) | Kontynuuj, wymagana różnica 2 gemów |
| Super tiebreak | Ostatni set remisowy, format `super_tiebreak` | Graj tiebreak do 10 |
| Nieskończona pętla | Format `advantage`, wyrównane gemy | Brak limitu iteracji (niezbędny timeout) |

---

## 10. Złożoność Obliczeniowa

### Twierdzenie 10.1 (Oczekiwana złożoność)
Oczekiwana liczba iteracji głównej pętli (równa oczekiwanej liczbie punktów) dla formatu best-of-3:

$$E[N] \leq C \cdot \frac{1}{\min(p_A, p_B, 1-p_A, 1-p_B)}$$

gdzie $C$ jest stałą zależną od formatu. W praktyce $E[N] \approx 100$ (dane ATP, patrz MC-01).

### Twierdzenie 10.2 (Złożoność pamięciowa)
Przechowywanie pełnej trajektorii wymaga $O(N_{\max})$ pamięci. Dla formatu bez advantage:

$$N_{\max}^{(3)} = 3 \cdot (13 \cdot 7) = 273 \text{ punktów (tiebreak w każdym secie)}$$

---

## 11. Walidacja Implementacji

### Tabela 11.1 — Przypadki testowe (wartości analityczne)

| $p_A$ | $p_B$ | $P(A \text{ wygrywa})$ analityczna | Tolerancja MC |
|-------|-------|----------------------------------|---------------|
| 0.60  | 0.60  | 0.5000                           | ±0.003        |
| 0.64  | 0.64  | 0.5000                           | ±0.003        |
| 0.70  | 0.60  | 0.7834                           | ±0.003        |
| 0.75  | 0.55  | 0.9241                           | ±0.002        |
| 1.00  | 0.00  | 1.0000                           | ±0.000        |

*Wartości analityczne obliczone metodą rekurencji (dokument MC-03).*

---

## 12. Referencje

1. ITF (2023). *Rules of Tennis*. International Tennis Federation.
2. ATP (2024). *Official Rulebook — ATP Tour*. Association of Tennis Professionals.
3. Newton, P.K., Keller, J.B. (2005). *Probability of winning at tennis*. Studies in Applied Mathematics, 114(3), 241–269.
4. Van Alen, J.H. (1968). *VASSS — Van Alen Simplified Scoring System*. USTA.

---

*Dokument zatwierdzony przez zespół BetaTP Quantitative Research. Poprzedni: MC-01. Następny: MC-03-KONWERGENCJA-CLT.md*
