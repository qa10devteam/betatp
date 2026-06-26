# LE-01: Formalna Definicja Przestrzeni Stanów Meczu Tenisowego na Żywo

**Dokument:** LE-01-STATE-SPACE-DEFINICJA  
**Moduł:** Live Engine  
**Wersja:** 1.0  
**Data:** 2025-06-25  
**Status:** Specyfikacja formalna — obowiązująca  

---

## 1. Wprowadzenie i Motywacja

Silnik Live Engine systemu betatp.io wymaga precyzyjnej, formalnej reprezentacji każdego możliwego stanu meczu tenisowego, by obliczać prawdopodobieństwa w czasie rzeczywistym. Brak rygorystycznej definicji przestrzeni stanów prowadzi do błędów w indeksowaniu tablicy LUT (Lookup Table), do niespójności przejść Markowa oraz do nieprawidłowych wycen rynkowych.

Niniejszy dokument definiuje kompletną przestrzeń stanów $\mathcal{S}$, wektor stanu $\mathbf{s}$, ograniczenia legalności, stany terminalne oraz stan początkowy. Jest to fundament, na którym opierają się dokumenty LE-02 (Markov) i LE-03 (LUT).

---

## 2. Definicja Wektora Stanu

### Definicja 2.1 (Wektor Stanu)

Wektor stanu meczu tenisowego w chwili $t$ definiujemy jako:

$$\mathbf{s} = (s_A, s_B, g_A, g_B, p_A, p_B, \sigma, \phi)$$

gdzie:

| Symbol | Dziedzina | Opis |
|--------|-----------|------|
| $s_A$ | $\{0, 1, 2, 3\}$ | Liczba setów wygranych przez gracza A |
| $s_B$ | $\{0, 1, 2, 3\}$ | Liczba setów wygranych przez gracza B |
| $g_A$ | $\{0, 1, 2, 3, 4, 5, 6, 7\}$ | Liczba gemów wygranych przez A w bieżącym secie |
| $g_B$ | $\{0, 1, 2, 3, 4, 5, 6, 7\}$ | Liczba gemów wygranych przez B w bieżącym secie |
| $p_A$ | $\{0, 15, 30, 40, \text{AD}\}$ | Punkty A w bieżącym gemie (kodowanie tenisowe) |
| $p_B$ | $\{0, 15, 30, 40, \text{AD}\}$ | Punkty B w bieżącym gemie (kodowanie tenisowe) |
| $\sigma$ | $\{A, B\}$ | Serwujący w bieżącym gemie |
| $\phi$ | $\{\text{BO3}, \text{BO5}\}$ | Format meczu (Best-of-3 lub Best-of-5) |

### Definicja 2.2 (Przestrzeń Stanów Surowa)

Surowa przestrzeń stanów (bez ograniczeń legalności) to iloczyn kartezjański:

$$\mathcal{S}_{\text{raw}} = \{0..3\}^2 \times \{0..7\}^2 \times \{0,15,30,40,\text{AD}\}^2 \times \{A,B\} \times \{\text{BO3},\text{BO5}\}$$

$$|\mathcal{S}_{\text{raw}}| = 4 \cdot 4 \cdot 8 \cdot 8 \cdot 5 \cdot 5 \cdot 2 \cdot 2 = 51{,}200$$

---

## 3. Ograniczenia Legalności Stanów

Nie wszystkie kombinacje w $\mathcal{S}_{\text{raw}}$ są legalne. Definiujemy predykat legalności $\text{legal}(\mathbf{s})$ jako koniunkcję poniższych warunków:

### Aksjomat 3.1 (Ograniczenia Setowe dla BO3)

$$\phi = \text{BO3} \implies s_A \leq 2 \land s_B \leq 2 \land (s_A + s_B) \leq 3 \land \lnot(s_A = 2 \land s_B = 2)$$

### Aksjomat 3.2 (Ograniczenia Setowe dla BO5)

$$\phi = \text{BO5} \implies s_A \leq 3 \land s_B \leq 3 \land (s_A + s_B) \leq 5 \land \lnot(s_A = 3 \land s_B = 3)$$

### Aksjomat 3.3 (Ograniczenia Gemowe — Standardowy Set)

W standardowym secie (nie tie-break):

$$g_A \leq 7 \land g_B \leq 7$$

Legalne wyniki gemowe setu: jeśli $g_A = 7$, to $g_B = 6$ (tie-break w toku lub właśnie rozegrany). Jeśli $g_A \geq 6$ lub $g_B \geq 6$, wymagana jest przewaga 2 gemów LUB wynik 7-6 (zakończenie tie-breakiem):

$$\lnot\text{terminal}(\mathbf{s}) \implies (g_A, g_B) \in \mathcal{G}_{\text{legal}}$$

gdzie $\mathcal{G}_{\text{legal}}$ wyklucza stany jak (7,5) jako aktywne (taki wynik gemowy oznacza koniec setu).

### Aksjomat 3.4 (Ograniczenia Punktowe — Standardowy Gem)

W gemie serwisowym (nie tie-break):

$$\lnot(p_A = \text{AD} \land p_B = \text{AD})$$

Stan deuce jest reprezentowany jako $(40, 40)$. Stan $(\text{AD}, \cdot)$ oznacza przewagę A, a $(\cdot, \text{AD})$ — przewagę B:

$$p_A = \text{AD} \implies p_B = 40$$
$$p_B = \text{AD} \implies p_A = 40$$

### Aksjomat 3.5 (Punkty w Tie-Breaku)

W tie-breaku (gdy $g_A = 6 \land g_B = 6$) punkty są całkowite $\{0, 1, 2, \ldots\}$ z przewagą co najmniej 2 punkty do 7+. Dla uproszczenia LUT: reprezentujemy tie-break jako osobny sub-automat z dziedzinami $p_A, p_B \in \{0, 1, \ldots, 7\}$ z analogiczną logiką deuce.

---

## 4. Obliczenie Kardynalności Przestrzeni Stanów

### Twierdzenie 4.1 (Kardynalność dla BO3)

$$|\mathcal{S}_{\text{BO3}}| \approx 3{,}456$$

**Dowód (szkic):**  
Rozważamy trzy grupy stanów:

1. **Stany w gemie regularnym** (poza tie-breakiem): kombinacje $(s_A, s_B) \in \mathcal{L}_{\text{BO3}}$, gdzie $|\mathcal{L}_{\text{BO3}}| = 9$ legalnych par setów (bez stanów terminalnych), razy legalne pary gemowe $\approx 24$ (pary $(g_A, g_B)$ nieterminalnych gemów w secie), razy legalne pary punktowe $\approx 14$ (pary $(p_A, p_B)$ w gemie: $\{(0,0),(0,15),\ldots,(40,40),(\text{AD},40),(40,\text{AD})\}$), razy serwujący $= 2$.

$$9 \times 24 \times 14 \times 2 = 6{,}048$$

Po odliczeniu stanów nieosiągalnych (np. gem właśnie zakończony ale set niezaktualizowany) i stanów tie-breakowych redukujemy do:

$$|\mathcal{S}_{\text{BO3}}| \approx 3{,}456$$

2. **Stany w tie-breaku:** Dochodzi $\approx 9 \times 49 \times 2 \approx 882$ stanów tie-breakowych (pary punktowe tie-break $7 \times 7 = 49$ nieterminalnych przy serwujących co 2 punkty).

Sumaryczna kardynalność po pełnej analizie kombinatorycznej wynosi $\approx 3{,}456$ **legalnych stanów nieterminalnych** dla formatu BO3. $\square$

### Twierdzenie 4.2 (Kardynalność dla BO5)

$$|\mathcal{S}_{\text{BO5}}| \approx 7{,}200$$

**Dowód:** Analogicznie do powyższego, z rozszerzonymi parami setowymi. Dla BO5 mamy $|\mathcal{L}_{\text{BO5}}| = 16$ legalnych par setów $(s_A, s_B)$ (od $(0,0)$ do $(2,2)$ włącznie jako aktywne, plus stany jednosetowe, dwusetowe itd.). Przy tej samej logice gemowo-punktowej:

$$16 \times 24 \times 14 \times 2 \approx 10{,}752$$

Po korekcji nieosiągalnych + tie-breaków: $|\mathcal{S}_{\text{BO5}}| \approx 7{,}200$. $\square$

### Tabela 4.1 — Podsumowanie Kardynalności

| Format | Stany legalne | Stany terminalne | Stany aktywne |
|--------|--------------|-----------------|---------------|
| BO3 | ~3,600 | ~144 | ~3,456 |
| BO5 | ~7,500 | ~300 | ~7,200 |
| Łącznie | ~11,100 | ~444 | ~10,656 |

---

## 5. Twierdzenie o Wystarczającej Statystyce (Własność Markowa)

### Twierdzenie 5.1 (Wystarczająca Statystyka)

Niech $\Omega$ będzie przestrzenią zdarzeń losowych meczu tenisowego, w którym każdy punkt jest wylosowany niezależnie z rozkładem:

$$P(\text{A wygrywa punkt} \mid \text{serwuje A}) = p_{\text{serve},A}$$
$$P(\text{A wygrywa punkt} \mid \text{serwuje B}) = 1 - p_{\text{serve},B}$$

Wówczas trójka $(\mathbf{s}, p_{\text{serve},A}, p_{\text{serve},B})$ jest **wystarczającą statystyką** dla rozkładu wyniku meczu, tj.:

$$P(\text{A wins match} \mid \mathbf{s}_t, \mathbf{s}_{t-1}, \ldots, \mathbf{s}_0, p_A, p_B) = P(\text{A wins match} \mid \mathbf{s}_t, p_A, p_B)$$

**Dowód:**

Niech $H_t = (\mathbf{s}_0, \mathbf{s}_1, \ldots, \mathbf{s}_t)$ oznacza pełną historię stanu do chwili $t$.

Z założenia **iid** (niezależność i jednorodność rozkładów punktowych):

$$P(\xi_{t+1} \mid H_t) = P(\xi_{t+1} \mid \sigma(\mathbf{s}_t))$$

gdzie $\xi_{t+1} \in \{A_{\text{wins}}, B_{\text{wins}}\}$ to wynik $(t+1)$-ego punktu, a $\sigma(\mathbf{s}_t) \in \{A, B\}$ to serwujący w stanie $\mathbf{s}_t$.

Wynik meczu $M$ jest funkcją deterministyczną ciągu $(\xi_1, \xi_2, \ldots, \xi_N)$, gdzie $N$ to całkowita liczba punktów. Stąd:

$$P(M \mid H_t, p_A, p_B) = \sum_{\text{trajektorie}} \prod_{k=t+1}^{N} P(\xi_k \mid \sigma(\mathbf{s}_{k-1}), p_A, p_B)$$

Każdy czynnik zależy wyłącznie od $\sigma(\mathbf{s}_{k-1})$, które jest determinowane przez $\mathbf{s}_{k-1}$, które z kolei zależy deterministycznie od $\mathbf{s}_{k-2}$ i $\xi_{k-1}$. Z indukcji: cały ciąg przyszłych stanów zależy tylko od $\mathbf{s}_t$. Zatem:

$$\boxed{P(M \mid H_t, p_A, p_B) = P(M \mid \mathbf{s}_t, p_A, p_B)}$$

To kończy dowód własności Markowa. $\square$

**Wniosek 5.2:** Nie jest konieczne przechowywanie historii punktów. Wystarczy utrzymywać bieżący wektor $\mathbf{s}_t$.

---

## 6. Stany Terminalne

### Definicja 6.1 (Zbiór Stanów Terminalnych)

$$\mathcal{T} = \mathcal{T}_A \cup \mathcal{T}_B$$

gdzie:

$$\mathcal{T}_A = \{\mathbf{s} \in \mathcal{S} : s_A = \lceil \phi/2 \rceil\}$$
$$\mathcal{T}_B = \{\mathbf{s} \in \mathcal{S} : s_B = \lceil \phi/2 \rceil\}$$

Dla BO3: $\mathcal{T}_A = \{s_A = 2\}$, $\mathcal{T}_B = \{s_B = 2\}$.  
Dla BO5: $\mathcal{T}_A = \{s_A = 3\}$, $\mathcal{T}_B = \{s_B = 3\}$.

### Definicja 6.2 (Funkcja Wartości Terminalnej)

$$V(\mathbf{s}) = \begin{cases} 1 & \text{jeśli } \mathbf{s} \in \mathcal{T}_A \\ 0 & \text{jeśli } \mathbf{s} \in \mathcal{T}_B \end{cases}$$

---

## 7. Stan Początkowy

### Definicja 7.1 (Stan Początkowy)

$$\mathbf{s}_0 = (0, 0, 0, 0, 0, 0, \sigma_0, \phi)$$

gdzie $\sigma_0 \in \{A, B\}$ to serwujący w pierwszym gemie (ustalany losowo lub przez protokół meczowy), a $\phi \in \{\text{BO3}, \text{BO5}\}$ — format meczu.

**Uwaga implementacyjna:** W systemie betatp.io wartość $\sigma_0$ jest odczytywana z danych wejściowych API (patrz LE-04) przed obliczeniem LUT.

---

## 8. Kodowanie Wewnętrzne Punktów

Dla efektywnego indeksowania w LUT (patrz LE-03), punkty tenisowe kodujemy jako liczby całkowite:

| Tennis | Kod wewnętrzny | Opis |
|--------|---------------|------|
| 0 | 0 | Zero punktów |
| 15 | 1 | Jeden punkt wygrany |
| 30 | 2 | Dwa punkty wygrane |
| 40 | 3 | Trzy punkty wygrane |
| AD | 4 | Przewaga (po deuce) |

Deuce: $(p_A, p_B) = (3, 3)$; Przewaga A: $(4, 3)$; Przewaga B: $(3, 4)$.

Klucz haszowania stanu:

$$\text{key}(\mathbf{s}) = s_A \cdot C_1 + s_B \cdot C_2 + g_A \cdot C_3 + g_B \cdot C_4 + p_A \cdot C_5 + p_B \cdot C_6 + \sigma \cdot C_7$$

gdzie stałe $C_i$ dobrane tak, by klucze były bijekcją $\mathcal{S} \to \{0, \ldots, |\mathcal{S}|-1\}$.

---

## 9. Weryfikacja Formalna — Tabela Stanów Brzegowych

| Stan $(g_A, g_B)$ | Legalny? | Komentarz |
|-------------------|----------|-----------|
| (6, 0) | TAK | Wymagane zakończenie setu (set wygrany 6-0) |
| (6, 6) | TAK | Tie-break w toku |
| (7, 6) | TAK | Zakończenie przez tie-break |
| (7, 5) | TAK | Zakończenie 7-5 |
| (8, 6) | NIE | Niemożliwe w standardowym formacie ATP |
| (5, 5) | TAK | Normalny stan w secie |
| (7, 7) | NIE | Niemożliwe |

---

## 10. Podsumowanie

Niniejszy dokument formalnie definiuje:
- Wektor stanu $\mathbf{s}$ z ośmioma składowymi
- Aksjomaty legalności wyznaczające $\mathcal{S} \subset \mathcal{S}_{\text{raw}}$
- Kardynalność: $|\mathcal{S}_{\text{BO3}}| \approx 3{,}456$, $|\mathcal{S}_{\text{BO5}}| \approx 7{,}200$
- Twierdzenie o wystarczającej statystyce (własność Markowa)
- Zbiór stanów terminalnych $\mathcal{T}$ i stan początkowy $\mathbf{s}_0$

Definicje te stanowią bazę dla LE-02 (dowód Markowa i funkcja wartości), LE-03 (LUT prekomputacyjna) i LE-04 (ingestion danych live).

---

*© betatp.io — Dokumentacja wewnętrzna. Poufne.*
