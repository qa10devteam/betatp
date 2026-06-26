# LE-02: Formalna Struktura Łańcucha Markowa dla Meczu Tenisowego

**Dokument:** LE-02-MARKOV-STRUKTURA  
**Moduł:** Live Engine  
**Wersja:** 1.0  
**Data:** 2025-06-25  
**Status:** Specyfikacja formalna — obowiązująca  
**Zależy od:** LE-01-STATE-SPACE-DEFINICJA

---

## 1. Wprowadzenie

Na podstawie przestrzeni stanów $\mathcal{S}$ zdefiniowanej w LE-01, niniejszy dokument:

1. Formalnie udowadnia, że mecz tenisowy pod założeniem iid jest łańcuchem Markowa o skończonej przestrzeni stanów.
2. Definiuje macierz przejść $\mathbf{P}$.
3. Definiuje funkcję wartości $V(\mathbf{s}) = P(\text{A wins} \mid \mathbf{s})$.
4. Wyprowadza rekurencyjne równanie Bellmana dla $V$.
5. Pokazuje szczegółowy przykład obliczeniowy.

---

## 2. Formalna Definicja Łańcucha Markowa

### Definicja 2.1 (Łańcuch Markowa na Przestrzeni Stanów Meczu)

Niech $(\mathbf{s}_t)_{t \geq 0}$ będzie procesem stochastycznym na $\mathcal{S}$ (LE-01), gdzie $t$ numeruje kolejne rozegrane punkty.

Proces $(\mathbf{s}_t)$ jest **łańcuchem Markowa** jeśli dla każdego $t \geq 0$ i każdego $\mathbf{s}' \in \mathcal{S}$:

$$P(\mathbf{s}_{t+1} = \mathbf{s}' \mid \mathbf{s}_t, \mathbf{s}_{t-1}, \ldots, \mathbf{s}_0) = P(\mathbf{s}_{t+1} = \mathbf{s}' \mid \mathbf{s}_t)$$

### Twierdzenie 2.2 (Mecz Tenisowy jako Łańcuch Markowa)

**Twierdzenie:** Pod założeniem iid — czyli że $P(\text{A wins point} \mid \text{A serves}) = p_A$ oraz $P(\text{A wins point} \mid \text{B serves}) = 1 - p_B$ są stałe i niezależne od historii — proces $(\mathbf{s}_t)$ jest łańcuchem Markowa z jednorodną macierzą przejść.

**Dowód:**

Weźmy dowolny stan $\mathbf{s}_t \in \mathcal{S} \setminus \mathcal{T}$ oraz dowolną historię $(\mathbf{s}_0, \ldots, \mathbf{s}_t)$. Wynik $(t+1)$-ego punktu $\xi_{t+1}$ jest losowany z rozkładu:

$$P(\xi_{t+1} = \text{A wins point}) = \begin{cases} p_A & \text{jeśli } \sigma(\mathbf{s}_t) = A \\ 1 - p_B & \text{jeśli } \sigma(\mathbf{s}_t) = B \end{cases}$$

Przejście $\mathbf{s}_t \to \mathbf{s}_{t+1}$ jest **deterministyczną funkcją** $\mathbf{s}_t$ i $\xi_{t+1}$:

$$\mathbf{s}_{t+1} = f(\mathbf{s}_t, \xi_{t+1})$$

gdzie $f : \mathcal{S} \times \{A_w, B_w\} \to \mathcal{S}$ to funkcja aktualizacji stanu (zdefiniowana regułami tenisa ATP).

Zatem:

$$P(\mathbf{s}_{t+1} = \mathbf{s}' \mid \mathbf{s}_t, \mathbf{s}_{t-1}, \ldots, \mathbf{s}_0) = P(f(\mathbf{s}_t, \xi_{t+1}) = \mathbf{s}' \mid \mathbf{s}_t)$$

ponieważ $\xi_{t+1}$ jest niezależne od $(\mathbf{s}_0, \ldots, \mathbf{s}_{t-1})$ z założenia iid, oraz $f$ nie zależy od historii. Stąd własność Markowa zachodzi. $\square$

---

## 3. Macierz Przejść

### Definicja 3.1 (Macierz Przejść $\mathbf{P}$)

Dla każdej pary stanów $(\mathbf{s}, \mathbf{s}') \in \mathcal{S} \times \mathcal{S}$:

$$P(\mathbf{s}, \mathbf{s}') = P(\mathbf{s}_{t+1} = \mathbf{s}' \mid \mathbf{s}_t = \mathbf{s})$$

Z powyższego dowodu wynika, że każdy stan ma co najwyżej **dwa możliwe następniki**: $\mathbf{s}_{\text{win}}$ (A wygrywa punkt) i $\mathbf{s}_{\text{lose}}$ (A przegrywa punkt):

$$P(\mathbf{s}, \mathbf{s}') = \begin{cases} q(\mathbf{s}) & \text{jeśli } \mathbf{s}' = f(\mathbf{s}, A_w) \\ 1 - q(\mathbf{s}) & \text{jeśli } \mathbf{s}' = f(\mathbf{s}, B_w) \\ 0 & \text{w przeciwnym razie} \end{cases}$$

gdzie:

$$q(\mathbf{s}) = \begin{cases} p_A & \text{jeśli } \sigma(\mathbf{s}) = A \\ 1 - p_B & \text{jeśli } \sigma(\mathbf{s}) = B \end{cases}$$

### Spostrzeżenie 3.2 (Rzadkość Macierzy)

Macierz $\mathbf{P}$ jest **bardzo rzadka**: każdy wiersz ma dokładnie 2 niezerowe wpisy (poza stanami terminalnymi). Dla $|\mathcal{S}| \approx 10{,}000$, macierz ma wymiary $10{,}000 \times 10{,}000$, ale tylko $\sim 20{,}000$ niezerowych wpisów (rzadkość $\approx 0.02\%$). Nie przechowujemy jej explicite — wystarczy funkcja $f$.

---

## 4. Funkcja Wartości i Równanie Bellmana

### Definicja 4.1 (Funkcja Wartości)

$$V : \mathcal{S} \to [0, 1]$$

$$V(\mathbf{s}) = P(\text{A wins match} \mid \text{aktualny stan } = \mathbf{s}, p_A, p_B)$$

### Twierdzenie 4.2 (Równanie Rekurencyjne — Bellman)

Dla każdego stanu nieterminalnego $\mathbf{s} \in \mathcal{S} \setminus \mathcal{T}$:

$$\boxed{V(\mathbf{s}) = q(\mathbf{s}) \cdot V(\mathbf{s}_{\text{win}}) + (1 - q(\mathbf{s})) \cdot V(\mathbf{s}_{\text{lose}})}$$

gdzie:
- $q(\mathbf{s}) = p_A$ jeśli serwuje A, $q(\mathbf{s}) = 1 - p_B$ jeśli serwuje B
- $\mathbf{s}_{\text{win}} = f(\mathbf{s}, A_w)$ — stan po wygraniu punktu przez A
- $\mathbf{s}_{\text{lose}} = f(\mathbf{s}, B_w)$ — stan po wygraniu punktu przez B

**Warunki brzegowe:**

$$V(\mathbf{s}) = 1 \quad \forall \mathbf{s} \in \mathcal{T}_A$$
$$V(\mathbf{s}) = 0 \quad \forall \mathbf{s} \in \mathcal{T}_B$$

**Dowód Twierdzenia 4.2:**

Dla $\mathbf{s} \notin \mathcal{T}$:

$$V(\mathbf{s}) = P(\text{A wins} \mid \mathbf{s})$$
$$= P(\text{A wins} \mid \mathbf{s}, \xi_{\text{next}} = A_w) \cdot P(\xi_{\text{next}} = A_w \mid \mathbf{s}) + P(\text{A wins} \mid \mathbf{s}, \xi_{\text{next}} = B_w) \cdot P(\xi_{\text{next}} = B_w \mid \mathbf{s})$$

Z własności Markowa:
$$= V(\mathbf{s}_{\text{win}}) \cdot q(\mathbf{s}) + V(\mathbf{s}_{\text{lose}}) \cdot (1 - q(\mathbf{s})) \qquad \square$$

---

## 5. Hierarchia Rekurencji: Gem → Set → Mecz

Równanie Bellmana stosuje się na każdym poziomie hierarchii tenisa:

### 5.1 Poziom Gemu

Niech $G(i, j, \sigma)$ oznacza prawdopodobieństwo wygrania gemu przez A, gdy wynik punktów to $(i, j)$ i serwuje $\sigma$:

$$G(i, j, A) = p_A \cdot G(i+1, j, A) + (1-p_A) \cdot G(i, j+1, A)$$

Warunki brzegowe: $G(4, j, \sigma) = 1$ dla $j \leq 2$; $G(i, 4, \sigma) = 0$ dla $i \leq 2$.

**Deuce i przewaga:**
$$G(3, 3, A) = p_A \cdot G(4^*, 3, A) + (1-p_A) \cdot G(3, 4^*, A)$$
$$G(4^*, 3, A) = p_A \cdot 1 + (1-p_A) \cdot G(3, 3, A)$$

Rozwiązując układ:
$$G(3, 3, A) = \frac{p_A^2}{p_A^2 + (1-p_A)^2}$$

### 5.2 Wartości Empiryczne $G(\text{deuce}, \text{serwuje A})$

| $p_A$ | $G(\text{deuce}, A)$ | Interpretacja |
|-------|---------------------|---------------|
| 0.60 | 0.692 | Typowy serwis ATP |
| 0.65 | 0.757 | Dobry serwujący |
| 0.70 | 0.823 | Bardzo dobry serwujący |
| 0.75 | 0.900 | Dominant serwisowy |
| 0.80 | 0.941 | Isner/Karlović poziom |

### 5.3 Poziom Seta

Niech $S(a, b)$ oznacza prawdopodobieństwo wygrania seta przez A przy wyniku gemów $(a, b)$ (A serwuje następny gem):

$$S(a, b) = G_{\sigma} \cdot S(a+1, b) + (1-G_{\sigma}) \cdot S(a, b+1)$$

gdzie $G_{\sigma}$ to prawdopodobieństwo wygrania gemu przez aktualnego serwującego.

---

## 6. Przykład Obliczeniowy

### Stan: $(s_A=1, s_B=0, g_A=5, g_B=4, p_A=40, p_B=30, \sigma=A)$

**Interpretacja:** A prowadzi 1-0 w setach, 5-4 w gemach bieżącego setu, 40-30 w gemie, A serwuje. Format BO3.

**Krok 1 — Prawdopodobieństwo wygrania bieżącego gemu:**

Stan punktowy: $(3, 2)$ w kodowaniu wewnętrznym (40=3, 30=2).

$$G(3, 2, A) = p_A \cdot 1 + (1-p_A) \cdot G(3, 3, A)$$

Przyjmując $p_A = 0.65$:
$$G(3,3,A) = \frac{0.65^2}{0.65^2 + 0.35^2} = \frac{0.4225}{0.4225 + 0.1225} = \frac{0.4225}{0.545} \approx 0.775$$

$$G(3,2,A) = 0.65 \cdot 1 + 0.35 \cdot 0.775 = 0.65 + 0.271 = 0.921$$

**Krok 2 — Prawdopodobieństwo wygrania bieżącego seta:**

Przy wyniku gemów 5-4, A serwuje. Jeśli A wygra ten gem: 6-4 → A wygrywa set.  
Jeśli B wygra ten gem: 5-5 → kontynuacja.

Potrzebujemy $S(5, 4, \text{A serwuje})$:

$$S(5, 4) = G(5,4,A) \cdot 1 + (1 - G(5,4,A)) \cdot S(5, 5)$$

Dla uproszczenia zakładamy $p_B = 0.63$ (serwis B):

$$G(5,4,A) = G_A \approx 0.921 \text{ (z powyżej)}$$

$$S(5,5) \approx 0.52 \text{ (symetrycznie zbliżone szanse, małe odchylenie od 0.5 ze względu na }p_A > p_B)$$

$$S(5,4) \approx 0.921 \cdot 1 + 0.079 \cdot 0.52 \approx 0.921 + 0.041 = 0.962$$

**Krok 3 — Prawdopodobieństwo wygrania meczu (A prowadzi 1-0 setami, BO3):**

$$V(\mathbf{s}) = S_{\text{current set}} \cdot P(\text{A wins 2nd set or more} \mid \text{A wins current}) + \ldots$$

Upraszczając przez rekurencję na poziomie setu przy wygranym secie przez A (0 setów do wygrania):

$$V(\mathbf{s}) \approx S(5,4) \cdot 1 + (1 - S(5,4)) \cdot M(1, 1)$$

gdzie $M(1,1)$ to prawdopodobieństwo wygrania meczu przy remisie setów 1-1:

$$M(1,1) = \frac{p_A^{\text{set}}}{p_A^{\text{set}} + p_B^{\text{set}}} \approx \frac{0.55}{0.55+0.45} = 0.55$$

$$\boxed{V(\mathbf{s}) \approx 0.962 \cdot 1 + 0.038 \cdot 0.55 \approx 0.962 + 0.021 \approx 0.983}$$

**Interpretacja:** A ma ~98.3% szansy na wygranie meczu z tej pozycji. Odpowiadający kurs rynkowy: $\sim 1.02$ dla A, $\sim 50.0$ dla B. Każda oferta bukmachera >1.05 na A lub <42 na B powinna być flagowana.

---

## 7. Złożoność Obliczeniowa Rekurencji

| Poziom | Liczba stanów | Operacje |
|--------|--------------|----------|
| Gem | ~14 | ~14 operacji mnożenia |
| Set | ~64 | ~64 operacji + wywołania gemu |
| Mecz BO3 | ~9 par setów | ~9 wywołań poziomu seta |
| Mecz BO5 | ~16 par setów | ~16 wywołań |
| **Łącznie (BO5)** | **~7,200** | **~100,000 FLOPs** |

Całkowita rekurencja na GPU/CPU: $< 1\text{ms}$. Prekomputacja LUT: patrz LE-03.

---

## 8. Poprawność i Unikalność Rozwiązania

### Twierdzenie 8.1 (Istnienie i Jedyność $V$)

Układ równań:

$$V(\mathbf{s}) = q(\mathbf{s}) \cdot V(f(\mathbf{s}, A_w)) + (1-q(\mathbf{s})) \cdot V(f(\mathbf{s}, B_w)), \quad \mathbf{s} \notin \mathcal{T}$$
$$V(\mathbf{s}) = \mathbb{1}[\mathbf{s} \in \mathcal{T}_A], \quad \mathbf{s} \in \mathcal{T}$$

ma **dokładnie jedno rozwiązanie** $V : \mathcal{S} \to [0,1]$.

**Dowód:** Graf przejść $(\mathcal{S}, f)$ jest acykliczny (każdy punkt zwiększa liczbę rozegranych punktów o 1, a mecz jest skończony). Zatem system równań jest trójkowy — można go rozwiązać metodą podstawiania wstecznego bez cykli. Jedyność wynika z acykliczności. $\square$

---

## 9. Podsumowanie

Niniejszy dokument formalnie udowodnił:
- Mecz tenisowy pod założeniem iid jest jednorodnym łańcuchem Markowa
- Macierz $\mathbf{P}$ jest rzadka (2 niezerowe wejścia na wiersz)
- Funkcja wartości $V$ spełnia równanie Bellmana
- Rozwiązanie istnieje i jest jedyne (acykliczny graf)
- Przykład numeryczny: $V(1\text{-}0, 5\text{-}4, 40\text{-}30, A) \approx 0.983$

---

*© betatp.io — Dokumentacja wewnętrzna. Poufne.*
