# AX-07: LIVE IN-PLAY RECALCULATION
## Formalna Specyfikacja Przeliczania Prawdopodobieństw w Trakcie Meczu

**Dokument:** AX-07  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-01, AX-02, AX-06

---

## 1. Wprowadzenie

Systemy in-play (live betting) wymagają aktualizacji prawdopodobieństwa wygranej meczu po każdym zagranym punkcie — w czasie rzeczywistym, z latencją poniżej 50 ms. Niniejszy dokument formalizuje przestrzeń stanów meczu, definicję prawdopodobieństwa warunkowego, algorytm aktualizacji stanu oraz analityczne konsekwencje modelu iid dla rynków live.

---

## 2. Przestrzeń Stanów Meczu

### Definicja 2.1 (Pełna Przestrzeń Stanów)

Stan meczu w dowolnym momencie rozgrywki opisuje krotka:

$$\mathcal{S} = \left(m_A, m_B, s_A, s_B, g_A, g_B, \text{srv}\right)$$

gdzie:

| Symbol | Opis | Zakres |
|:------:|:-----|:------:|
| $m_A$ | Liczba setów wygranych przez A | $\{0, 1, 2\}$ (Bo3), $\{0,\ldots,4\}$ (Bo5) |
| $m_B$ | Liczba setów wygranych przez B | jak wyżej |
| $s_A$ | Liczba gemów A w bieżącym secie | $\{0,\ldots,7\}$ |
| $s_B$ | Liczba gemów B w bieżącym secie | $\{0,\ldots,7\}$ |
| $g_A$ | Liczba punktów A w bieżącym gemie | $\{0,1,2,3,\text{D},\text{Adv}\}$ |
| $g_B$ | Liczba punktów B w bieżącym gemie | $\{0,1,2,3,\text{D},\text{Adv}\}$ |
| $\text{srv}$ | Aktualny serwujący | $\{A, B\}$ |

### Definicja 2.2 (Kodowanie Stanu Gemu)

Dla oszczędności pamięci, stan gemu $(g_A, g_B)$ jest kodowany jako liczba całkowita:

$$\text{gem\_code}(g_A, g_B) = 5 \cdot g_A + g_B + \text{offset}$$

gdzie offset = 0 dla stanów regularnych $(0-3, 0-3)$ i wartości specjalne dla Deuce/Adv.

Liczba unikalnych stanów gemu: **17** (16 regularnych + Deuce + Adv-A + Adv-B).

### Definicja 2.3 (Kompletna Przestrzeń Stanów)

Całkowita liczba możliwych stanów meczu (format Bo3):

$$|\mathcal{S}| = |\{(m_A, m_B)\}| \times |\{(s_A, s_B)\}| \times |\{(g_A, g_B)\}| \times |\{\text{srv}\}|$$

$$= 6 \times 49 \times 17 \times 2 = 9{,}996 \approx 10{,}000 \text{ stanów}$$

Wszystkie prawdopodobieństwa warunkowe mogą być **prekomputowane** i zapisane w tablicy wyszukiwań.

---

## 3. Prawdopodobieństwo Warunkowe

### Definicja 3.1 (In-Play Probability)

Niech $\mathcal{S}_t$ będzie stanem meczu w chwili $t$ (po zagraniu $t$-tego punktu). Definiujemy **in-play probability** jako:

$$\boxed{P_t(A) = \mathbb{P}\left(A \text{ wygrywa mecz} \mid \mathcal{S}_t, p_A, p_B\right)}$$

Jest to prawdopodobieństwo warunkowe wygranej $A$ z aktualnego stanu, przy założeniu iid parametrów $(p_A, p_B)$.

### Twierdzenie 3.1 (Markowowskość Procesu Stanów)

Proces $\{\mathcal{S}_t\}_{t \geq 0}$ jest łańcuchem Markowa:

$$\mathbb{P}(\mathcal{S}_{t+1} \mid \mathcal{S}_t, \mathcal{S}_{t-1}, \ldots, \mathcal{S}_0) = \mathbb{P}(\mathcal{S}_{t+1} \mid \mathcal{S}_t)$$

**Dowód:** Wynika bezpośrednio z Aksjomatu A1 — wynik każdego punktu jest niezależny od historii, zatem przyszły stan zależy wyłącznie od bieżącego stanu, nie od ścieżki do niego. $\blacksquare$

### Wniosek 3.1 (Wystarczalność Stanu)

Na mocy Twierdzenia 3.1, $P_t(A)$ jest deterministyczną funkcją wyłącznie $(\mathcal{S}_t, p_A, p_B)$:

$$P_t(A) = \Phi(\mathcal{S}_t; p_A, p_B)$$

dla pewnej funkcji $\Phi: \mathcal{S} \times (0,1)^2 \to [0,1]$.

---

## 4. Rekurencyjna Definicja $\Phi$

### Definicja 4.1 (Rekurencja dla P(A wygrywa mecz | stan))

Definiujemy $\Phi$ rekurencyjnie:

**Poziom punktu:**

$$\Phi(\mathcal{S}; p_A, p_B) = p_{\text{srv}} \cdot \Phi(\mathcal{S}^+; p_A, p_B) + (1-p_{\text{srv}}) \cdot \Phi(\mathcal{S}^-; p_A, p_B)$$

gdzie:
- $p_{\text{srv}} = p_A$ jeżeli $\text{srv} = A$, $p_{\text{srv}} = p_B$ jeżeli $\text{srv} = B$
- $\mathcal{S}^+$ = stan po wygraniu punktu przez serwującego
- $\mathcal{S}^-$ = stan po przegranym punkcie przez serwującego

**Warunki brzegowe:**

$$\Phi(\mathcal{S}_{\text{wygrał A}}; \cdot) = 1, \quad \Phi(\mathcal{S}_{\text{wygrał B}}; \cdot) = 0$$

gdzie $\mathcal{S}_{\text{wygrał A}}$ to dowolny stan końcowy z $m_A = \lceil n_{\max}/2 \rceil$ setami.

### Definicja 4.2 (Macierz Przejść Stanu)

Definiujemy funkcję przejścia:

$$T: \mathcal{S} \times \{0,1\} \to \mathcal{S}$$

$$T(\mathcal{S}, 1) = \mathcal{S}^+ \quad \text{(serwujący wygrywa punkt)}$$

$$T(\mathcal{S}, 0) = \mathcal{S}^- \quad \text{(serwujący przegrywa punkt)}$$

Funkcja $T$ implementuje zasady tenisa i jest deterministyczna.

---

## 5. Algorytm Aktualizacji Stanu

### Specyfikacja 5.1 (Algorytm POINT_RESULT_UPDATE)

```
Algorytm POINT_RESULT_UPDATE:
Wejście: stan S = (m_A, m_B, s_A, s_B, g_A, g_B, srv), wynik r ∈ {0,1}
Wyjście: nowy stan S'

1. Wyznacz zwycięzcę punktu:
   winner = srv if r == 1 else opponent(srv)

2. Zaktualizuj stan gemu:
   (g_A', g_B') = update_game_score(g_A, g_B, winner)
   
3. Sprawdź zakończenie gemu:
   gem_winner = check_game_end(g_A', g_B')
   
4. Jeżeli gem_winner ≠ None:
   (s_A', s_B') = update_set_score(s_A, s_B, gem_winner)
   (g_A', g_B') = (0, 0)  // reset gemu
   srv' = next_server(srv)  // alternacja serwisu
   
   5. Sprawdź zakończenie seta:
      set_winner = check_set_end(s_A', s_B')
      
   6. Jeżeli set_winner ≠ None:
      (m_A', m_B') = update_match_score(m_A, m_B, set_winner)
      (s_A', s_B') = (0, 0)  // reset seta
      
      7. Sprawdź zakończenie meczu:
         match_winner = check_match_end(m_A', m_B', format)
         if match_winner ≠ None: return TERMINAL_STATE(match_winner)
   else:
      (m_A', m_B') = (m_A, m_B)
      (s_A', s_B') = (s_A', s_B')
else:
   (m_A', m_B') = (m_A, m_B)
   (s_A', s_B') = (s_A, s_B)
   srv' = srv  // serwis nie zmienia się w trakcie gemu

8. Zwróć S' = (m_A', m_B', s_A', s_B', g_A', g_B', srv')
```

### Specyfikacja 5.2 (Złożoność Algorytmu)

- Złożoność czasowa: $O(1)$ — stała liczba operacji warunkowych
- Złożoność pamięciowa: $O(1)$ — stan jest kompaktową krotką 7 liczb całkowitych

---

## 6. Prekomputacja Tablicy Prawdopodobieństw

### Definicja 6.1 (Look-Up Table)

Dla zadanej pary $(p_A, p_B)$, prekomputujemy tablicę:

$$\text{LUT}[p_A][p_B][\mathcal{S}] = \Phi(\mathcal{S}; p_A, p_B)$$

dla wszystkich $\mathcal{S} \in \mathcal{S}$.

### Twierdzenie 6.1 (Wystarczalność Prekomputacji dla Wymagań Latencji)

Dostęp do prekomputowanej tablicy LUT ma latencję $O(1)$ = dostęp do pamięci (< 100 ns). Przy 10,000 stanach i typowej rozdzielczości siatki $(p_A, p_B) \in [0.55, 0.85]^2$ z krokiem 0.005:

$$|\text{LUT}| = 61 \times 61 \times 10{,}000 \approx 37 \text{ milionów wpisów}$$

Przy 4 bajtach na wpis (float32): $\approx 148$ MB RAM — akceptowalne.

### Specyfikacja 6.2 (Aktualizacja LUT po Zmianie Parametrów)

Jeżeli $(p_A, p_B)$ ulegają aktualizacji (np. po przechwyceniu nowych statystyk serwisowych), LUT jest regenerowana asynchronicznie w osobnym wątku, bez blokowania głównego wątku predykcji.

---

## 7. Wymagania Latencji

### Definicja 7.1 (Budżet Latencji)

Całkowity czas przetwarzania od odebrania zdarzenia punktowego do wysłania zaktualizowanych prawdopodobieństw:

$$t_{\text{total}} < 50 \text{ ms}$$

Podział budżetu latencji:

| Komponent | Budżet [ms] |
|:----------|:-----------:|
| Odebranie zdarzenia z API (sieć) | ≤ 10 |
| Parsowanie / deserializacja | ≤ 2 |
| Aktualizacja stanu (STATE_UPDATE) | ≤ 1 |
| Wyszukiwanie w LUT | ≤ 1 |
| Fallback Monte Carlo (jeśli brak LUT) | ≤ 30 |
| Serializacja / wysłanie odpowiedzi | ≤ 5 |
| **Razem** | **< 50** |

### Definicja 7.2 (Ścieżka Szybka vs. Wolna)

- **Ścieżka szybka (< 5 ms):** Wyszukiwanie LUT dla prekomputowanych $(p_A, p_B)$
- **Ścieżka wolna (< 50 ms):** MC z $N = 10{,}000$ iteracjami (SE < 0.005) dla dowolnych $(p_A, p_B)$

Ścieżka szybka jest używana gdy $(p_A, p_B)$ leżą na prekomputowanej siatce (interpolacja liniowa dla pośrednich wartości).

---

## 8. Właściwości Modelu IID a Rynki Live — Implikacje

### Twierdzenie 8.1 (Kluczowa Właściwość Rynku Live przy Założeniu IID)

Niech $\text{odds}_t^{\text{market}}(A)$ będą kursami rynku live dla wygranej $A$ w chwili $t$, a $P_t^{\text{model}}(A) = \Phi(\mathcal{S}_t; p_A, p_B)$ będzie prawdopodobieństwem modelowym.

**Twierdzenie:** Model iid generuje systematycznie **przewartościowane** prawdopodobieństwa po sekwencjach punktów, w których jeden gracz dominuje, oraz **niedowartościowane** po sekwencjach zrównoważonych.

**Wyjaśnienie:**

Model iid ignoruje "momentum" — empirycznie potwierdzoną dodatnią autokorelację wyników kolejnych punktów ($\rho_{t,t-1} \approx +0.03 \pm 0.01$, dane ATP 2018–2024). Skutkuje to:

1. **Po serii punktów dla A:** rynek uwzględnia momentum (A jest "gorący"), model iid nie → model **zaniża** $P(A)$ względem rynku
2. **Po serii punktów dla B:** odwrotnie → model **zawyża** $P(A)$ względem rynku

### Definicja 8.2 (Exploitable Edge)

Definiujemy **model edge** jako:

$$\text{edge}_t = P_t^{\text{model}}(A) - P_t^{\text{market}}(A)$$

Gdy $\text{edge}_t > \theta_{\min}$ (próg opłacalności zakładu po uwzględnieniu marży bukmachera), zakład na $A$ jest wartościowy.

### Obserwacja 8.1 (Przypadki Generowania Edge przez Model IID)

| Sytuacja rynkowa | Efekt modelu IID | Potencjalny edge |
|:-----------------|:-----------------|:----------------:|
| Przełamanie serwisu po serii błędów | Rynek: kursy silnie przesuwają się przeciw serwującemu (momentum); Model: nie uwzględnia momentum, $P$ zmienia się tylko przez zmianę stanu (gemów) | edge > 0 dla serwującego |
| Seria asów przy niezmienionym gemie | Rynek: kursy stabilne; Model: p_A stałe → $P$ stałe | Brak edge |
| Przerwa na toaletę / czas medyczny | Rynek: może reagować na percepcję zmiany rytmu; Model: stan niezmienny → $P$ niezmienione | edge potencjalny |
| Tie-break po setach wyrównanych | Rynek: może przeceniać lidera (wynik setowy odzwierciedla już aktualny stan) | Model koryguje przeszacowania |

### Twierdzenie 8.2 (Granica Exploitability przy Idealnym IID)

**Twierdzenie:** Przy założeniu, że rynek live jest efektywny w sensie Famy (kursy w pełni odzwierciedlają dostępne informacje), a model iid jest kompletny (uwzględnia wszystkie informacje wpływające na wynik), edge wynosi zero po uwzględnieniu marży.

**Wniosek:** Edge modelu iid wynika **wyłącznie** z:
1. Niedoskonałości rynku live (opóźnienia w aktualizacji kursów)
2. Pominięcia momentum przez model rynku (lub odwrotnie — nadmiernego uwzględnienia)
3. Błędów bukmacherów w estymacji $(p_A, p_B)$

Model betatp.io jest zatem narzędziem do identyfikacji punktów (2) i (3).

---

## 9. Formalna Specyfikacja Wyjść Systemu Live

### Definicja 9.1 (Obiekt Odpowiedzi Live)

```json
{
  "match_id": "<uuid>",
  "timestamp_ms": 1751000000000,
  "state": {
    "sets_A": 1, "sets_B": 0,
    "games_A": 3, "games_B": 2,
    "points_A": 2, "points_B": 1,
    "server": "A",
    "is_tiebreak": false
  },
  "probabilities": {
    "p_win_A": 0.6843,
    "p_win_B": 0.3157,
    "p_set_score": {
      "2:0": 0.3521, "2:1": 0.3322,
      "1:2": 0.2098, "0:2": 0.1059
    },
    "p_tiebreak_current_set": 0.2341,
    "e_games_remaining": 8.7,
    "e_duration_remaining_min": 39.2
  },
  "model_params": {
    "p_serve_A": 0.748,
    "p_serve_B": 0.731
  },
  "computation_time_ms": 3.2,
  "computation_method": "LUT"
}
```

### Definicja 9.2 (Szybkość Aktualizacji)

System live musi obsługiwać:

$$\text{throughput} \geq 100 \text{ eventów/sekundę}$$

co odpowiada $\sim$10 równoległym meczom z aktualizacją co punkt (typowo 1 punkt/10s per mecz).

---

## 10. Implementacja — Wymagania Niefunkcjonalne

| Wymaganie | Specyfikacja |
|:----------|:------------|
| Latencja (P99) | < 50 ms |
| Latencja (P50) | < 5 ms |
| Dostępność | 99.9% (8.7h downtime/rok) |
| Precyzja zmiennoprzecinkowa | float32 (błąd < 0.001%) |
| Protokół komunikacji | WebSocket (push) lub REST (pull) |
| Format danych | JSON / MessagePack |
| Persistence stanu | Redis (TTL 48h per mecz) |

---

## Referencje

- AX-01–AX-06: Dokumenty specyfikacyjne betatp.io
- Klaassen, F.J.G.M. & Magnus, J.R. (2001). *Are Points in Tennis IID?* JASA, 96(454).
- Fama, E.F. (1970). *Efficient Capital Markets: A Review of Theory and Empirical Work.* Journal of Finance.
- Easton, S. & Uylangco, K. (2010). *Forecasting Outcomes in Tennis Using Within-Match Betting Markets.* International Journal of Forecasting.
- Croxson, K. & Reade, J.J. (2014). *Information and Efficiency: Goal Arrivals in Soccer Betting.* Economic Journal.
- Abramowitz, M. & Stegun, I.A. (1972). *Handbook of Mathematical Functions.* Dover Publications.
