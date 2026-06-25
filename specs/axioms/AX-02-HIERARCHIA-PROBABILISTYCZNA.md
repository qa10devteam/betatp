# AX-02: HIERARCHIA PROBABILISTYCZNA
## Formalna Definicja 5-Poziomowej Struktury Probabilistycznej

**Dokument:** AX-02  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-01

---

## 1. Wprowadzenie

Niniejszy dokument formalizuje pięciopoziomową hierarchię probabilistyczną meczu tenisowego. Hierarchia ta jest konsekwencją Aksjomatu A1 (AX-01): przy założeniu iid Bernoulli na poziomie punktu, wszystkie wyższe poziomy są deterministycznymi funkcjami parametrów $(p_A, p_B)$.

Definiujemy precyzyjnie każdy poziom przez rachunki kombinatoryczne, rekurencje i wzory zamknięte.

---

## 2. Diagram Hierarchii

```
MECZ (Match)
  └─ SET (Set) × (2 lub 3 z 3, lub 3 z 5)
       └─ GEM (Game) × (6+)
            └─ PUNKT (Point) × (4+)
                 └─ WYNIK PUNKTU: {0=przegrana, 1=wygrana serwującego}
```

Formalnie definiujemy:

$$\text{Level}_0 = \text{Punkt}, \quad \text{Level}_1 = \text{Gem}, \quad \text{Level}_2 = \text{Tiebreak}, \quad \text{Level}_3 = \text{Set}, \quad \text{Level}_4 = \text{Mecz}$$

---

## 3. Poziom 0 — Punkt (Point)

### Definicja 3.1 (Miara Probabilistyczna Punktu)

Niech $p_s \in (0,1)$ będzie parametrem serwisowym (cf. AX-01, Def. 2.2). Dla każdego punktu serwowanego przez zawodnika $S$:

$$\mathbb{P}(\text{S wygrywa punkt}) = p_s$$
$$\mathbb{P}(\text{S przegrywa punkt}) = 1 - p_s =: q_s$$

### Definicja 3.2 (Przestrzeń Stanów Punktu)

Zbiór możliwych wyników punktu:

$$\Omega_{\text{pt}} = \{W, L\}$$

gdzie $W$ = wygrana serwującego, $L$ = przegrana serwującego.

$$\mathbb{P}: \Omega_{\text{pt}} \to [0,1], \quad \mathbb{P}(W) = p_s, \quad \mathbb{P}(L) = q_s$$

---

## 4. Poziom 1 — Gem (Game)

### Definicja 4.1 (Stan Gemu)

Stan gemu opisuje para $(a, b) \in \{0,1,2,3,4\}^2$ oznaczająca liczbę punktów zdobytych przez serwującego i returnującego, z konwencją:

$$\text{score}(a) = \begin{cases} 0 & a = 0 \\ 15 & a = 1 \\ 30 & a = 2 \\ 40 & a = 3 \end{cases}$$

Stan deuce: $a = b = 3$.

### Definicja 4.2 (Przestrzeń Stanów Gemu)

$$\mathcal{S}_G = \{(a,b) : a \in \{0,1,2,3\}, b \in \{0,1,2,3\}\} \cup \{\text{Deuce}, \text{Adv-S}, \text{Adv-R}\}$$

### Twierdzenie 4.1 (Rekurencyjna Formuła dla P(Gem))

Niech $G(a,b)$ będzie prawdopodobieństwem wygrania gemu przez serwującego ze stanu $(a,b)$. Wtedy:

$$G(a, b) = p_s \cdot G(a+1, b) + q_s \cdot G(a, b+1)$$

z warunkami brzegowymi:
- $G(4, b) = 1$ dla $b \leq 2$
- $G(a, 4) = 0$ dla $a \leq 2$
- $G(4, 3) = 1$, $G(3, 4) = 0$
- Stan deuce: $G(3,3) = \frac{p_s^2}{p_s^2 + q_s^2}$

### Twierdzenie 4.2 (Zamknięta Formuła dla P(Gem))

Przez bezpośrednie wyliczenie ścieżek kombinatorycznych:

$$\boxed{P_G(p_s) = \sum_{k=0}^{3} \binom{3+k}{k} p_s^4 q_s^k + \binom{6}{3} p_s^3 q_s^3 \cdot \frac{p_s^2}{p_s^2 + q_s^2}}$$

**Dowód:** Ścieżki wygranej bez deuce kończą się po $4+k$ punktach ($k \in \{0,1,2,3\}$), gdzie serwujący wygrywa ostatni punkt. Liczba takich ścieżek wynosi $\binom{3+k}{k}$ (serwujący ma 3 wygrane wśród pierwszych $3+k$ punktów, ostatni punkt jest wygraną serwującego). Ścieżki przez deuce: najpierw osiągnięcie 3-3 ($\binom{6}{3}$ ścieżek, prawdopodobieństwo $p_s^3 q_s^3$), następnie wygrana $\frac{p_s^2}{p_s^2+q_s^2}$. $\blacksquare$

### Tabela 4.1: Wartości $P_G(p_s)$ dla wybranych $p_s$

| $p_s$ | $P_G$ | Interpretacja |
|:-----:|:-----:|:-------------|
| 0.50 | 0.500 | Brak przewagi serwisowej |
| 0.60 | 0.736 | Słaby serwis |
| 0.69 | 0.822 | Clay — min ATP |
| 0.715 | 0.862 | Clay — mediana ATP |
| 0.740 | 0.896 | Hard — min ATP |
| 0.755 | 0.913 | Hard — mediana ATP |
| 0.765 | 0.924 | Grass — mediana ATP |
| 0.790 | 0.947 | Grass — max ATP |

---

## 5. Poziom 2 — Tiebreak

### Definicja 5.1 (Stan Tiebreaka)

Stan tiebreaka opisuje para $(a, b) \in \{0,\ldots,7\}^2$ z mechanizmem deuce przy stanie 6-6.

Serwis w tiebreaku zmienia się co 2 punkty (z wyjątkiem pierwszego punktu). Dla uproszczenia modelu stosujemy efektywne prawdopodobieństwo:

$$p_{\text{tb}} = \frac{p_A \cdot \mathbb{1}[\text{A serwuje}] + (1-p_B) \cdot \mathbb{1}[\text{B serwuje}]}{1}$$

Uśredniając przez przeplecione serwisy:

$$\bar{p}_{\text{tb}} = \frac{p_A + (1-p_B)}{2}$$

### Twierdzenie 5.1 (Zamknięta Formuła dla P(Tiebreak))

$$\boxed{P_{TB}(\bar{p}) = \sum_{k=0}^{5} \binom{6+k}{k} \bar{p}^7 (1-\bar{p})^k + \binom{12}{6} \bar{p}^6 (1-\bar{p})^6 \cdot \frac{\bar{p}^2}{\bar{p}^2 + (1-\bar{p})^2}}$$

**Dowód:** Analogiczny do Twierdzenia 4.2 z progiem wygranej $= 7$ zamiast $4$. $\blacksquare$

### Tabela 5.1: Wartości $P_{TB}(\bar{p})$

| $\bar{p}$ | $P_{TB}$ |
|:---------:|:--------:|
| 0.50 | 0.500 |
| 0.55 | 0.606 |
| 0.60 | 0.710 |
| 0.65 | 0.806 |
| 0.70 | 0.884 |

---

## 6. Poziom 3 — Set

### Definicja 6.1 (Stan Seta)

Stan seta opisuje krotka $(s_A, s_B, \text{srv})$ gdzie $s_A, s_B \in \{0,\ldots,7\}$ to liczba gemów, a $\text{srv} \in \{A, B\}$ wskazuje serwującego w bieżącym gemie.

### Definicja 6.2 (Macierz Przejścia Seta)

Niech $p_{\text{gem,A}} = P_G(p_A)$, $p_{\text{gem,B}} = P_G(p_B)$.

Prawdopodobieństwo wygrania gemu przez $A$:
- gdy $A$ serwuje: $\alpha_A = p_{\text{gem,A}}$
- gdy $B$ serwuje: $\alpha_B = 1 - p_{\text{gem,B}}$

### Twierdzenie 6.1 (Rekurencja Seta)

Niech $\mathcal{S}(s_A, s_B \mid \text{srv})$ oznacza prawdopodobieństwo wygrania seta przez $A$ ze stanu $(s_A, s_B)$ gdy serwuje gracz $\text{srv}$:

$$\mathcal{S}(s_A, s_B \mid A) = \alpha_A \cdot \mathcal{S}(s_A+1, s_B \mid B) + (1-\alpha_A) \cdot \mathcal{S}(s_A, s_B+1 \mid B)$$

$$\mathcal{S}(s_A, s_B \mid B) = \alpha_B \cdot \mathcal{S}(s_A+1, s_B \mid A) + (1-\alpha_B) \cdot \mathcal{S}(s_A, s_B+1 \mid A)$$

**Warunki brzegowe:**

| Warunek | Wartość |
|:--------|:-------:|
| $\mathcal{S}(6, b \mid \cdot)$ dla $b \leq 4$ | 1 |
| $\mathcal{S}(a, 6 \mid \cdot)$ dla $a \leq 4$ | 0 |
| $\mathcal{S}(7, 5 \mid \cdot)$ | 1 |
| $\mathcal{S}(5, 7 \mid \cdot)$ | 0 |
| $\mathcal{S}(6, 6 \mid \cdot)$ | $P_{TB}(\bar{p})$ |

### Lemat 6.1 (Prawdopodobieństwo Wyniku Seta)

Prawdopodobieństwo wygrania seta przez $A$ wynikiem $6:k$ (dla $k \in \{0,1,2,3,4\}$):

$$P(6:k) = \binom{5+k}{k} \prod_{i=0}^{k+5} P(\text{A wygrywa gem}_i) \cdot P(\text{B wygrywa gem}_j)$$

gdzie produkt jest brany po odpowiednich sekwencjach naprzemiennych serwisów.

---

## 7. Poziom 4 — Mecz

### Definicja 7.1 (Stan Meczu)

Stan meczu opisuje krotka $(m_A, m_B, \text{format})$ gdzie $m_A, m_B$ to liczba setów, a format $\in \{\text{Bo3}, \text{Bo5}\}$.

### Twierdzenie 7.1 (Zamknięta Formuła — Best of 3)

Niech $P_S = \mathcal{S}(0, 0 \mid A)$ (prawdopodobieństwo wygrania pierwszego seta przez $A$), $P_{S,2}$ — drugiego, $P_{S,3}$ — trzeciego (zależy od serwującego na początku każdego seta).

W uproszczeniu symetrycznym:

$$P_M^{(3)} = P_S^2 + 2P_S(1-P_S)P_S = P_S^2(3 - 2P_S)$$

Bardziej precyzyjnie (uwzględniając różne serwisy na początku setów):

$$P_M^{(3)} = P_{S1} \cdot P_{S2|w_1} + P_{S1}(1-P_{S2|w_1}) \cdot P_{S3|w_1,l_2} + (1-P_{S1}) \cdot P_{S2|l_1} \cdot P_{S3|l_1,w_2}$$

### Twierdzenie 7.2 (Zamknięta Formuła — Best of 5)

$$\boxed{P_M^{(5)} = P_S^3 + 3P_S^3(1-P_S) + 6P_S^3(1-P_S)^2 = P_S^3 \sum_{k=0}^{2} \binom{2+k}{k}(1-P_S)^k}$$

---

## 8. Twierdzenie Główne — Determinizm Hierarchiczny

### Twierdzenie 8.1 (Determinizm Hierarchiczny)

**Twierdzenie:** Przy założeniu Aksjomatu A1, wszystkie prawdopodobieństwa hierarchiczne są deterministycznymi funkcjami analitycznymi pary $(p_A, p_B) \in (0,1)^2$:

$$P_G = f_G(p_A), \quad P_G' = f_G(p_B)$$
$$P_{TB} = f_{TB}(p_A, p_B)$$
$$P_S = f_S(p_A, p_B)$$
$$P_M = f_M(p_A, p_B)$$

Funkcje $f_G, f_{TB}, f_S, f_M$ są wielomianami (lub ułamkami wielomianowymi) na $(0,1)$.

**Dowód:**

Na mocy AX-01, Twierdzenia 7.1, każde zdarzenie hierarchiczne $\mathcal{H}$ jest sumą skończonej liczby wykluczających się sekwencji punktów:

$$\mathbb{P}(\mathcal{H}) = \sum_{\omega \in \mathcal{W}(\mathcal{H})} \mathbb{P}(\omega)$$

gdzie $\mathcal{W}(\mathcal{H})$ jest zbiorem wszystkich "wygrywających sekwencji" punktów prowadzących do $\mathcal{H}$.

Na mocy założenia iid:

$$\mathbb{P}(\omega) = \prod_{i: X_i^{(A)}=1} p_A \cdot \prod_{j: X_j^{(A)}=0} q_A \cdot \prod_{k: X_k^{(B)}=1} p_B \cdot \prod_{l: X_l^{(B)}=0} q_B$$

$$= p_A^{n_A^+} q_A^{n_A^-} p_B^{n_B^+} q_B^{n_B^-}$$

Suma po skończonej liczbie $\omega$ daje wielomian (lub ułamek wielomianowy dla nieskończonej sumy geometrycznej deuce) w zmiennych $(p_A, q_A, p_B, q_B)$, a ponieważ $q_A = 1-p_A$, $q_B = 1-p_B$, jest to wielomian (ułamek wielomianowy) w $(p_A, p_B)$. $\blacksquare$

### Wniosek 8.1 (Ciągłość i Różniczkowalność)

Funkcje $f_G, f_{TB}, f_S, f_M$ są klasy $C^\infty$ na $(0,1)^2$, co umożliwia numeryczne wyznaczanie gradientów do optymalizacji parametrów modelu.

---

## 9. Złożoność Obliczeniowa

### Tabela 9.1: Liczba stanów i złożoność obliczeniowa

| Poziom | Liczba stanów | Złożoność obliczeń $P$ |
|:-------|:-------------:|:----------------------:|
| Punkt | 2 | $O(1)$ |
| Gem | ~16 + deuce | $O(1)$ — wzór zamknięty |
| Tiebreak | ~49 + deuce | $O(1)$ — wzór zamknięty |
| Set | ~49 × 2 | $O(49)$ — dynamiczne programowanie |
| Mecz (Bo3) | ~9 × 2 | $O(9)$ — dynamiczne programowanie |
| Mecz (Bo5) | ~16 × 2 | $O(16)$ — dynamiczne programowanie |

Całkowita złożoność wyznaczenia $P_M(p_A, p_B)$: $O(1)$ (wszystkie formuły są zamknięte lub rozwiązywane w czasie stałym przez dynamiczne programowanie na małej siatce stanów).

---

## 10. Szczególne Własności Hierarchii

### Właściwość 10.1 (Monotoniczność)

Funkcje $f_G, f_S, f_M$ są ściśle rosnące względem $p_A$ i ściśle malejące względem $p_B$:

$$\frac{\partial f_G}{\partial p_A} > 0, \quad \frac{\partial f_S}{\partial p_A} > 0, \quad \frac{\partial f_M}{\partial p_A} > 0$$

### Właściwość 10.2 (Symetria)

$$f_M(p_A, p_B) + f_M(p_B, p_A) = 1$$

czyli jeśli $A$ ma prawdopodobieństwo $\pi$ wygranej meczu, to $B$ ma prawdopodobieństwo $1-\pi$.

### Właściwość 10.3 (Wartość środkowa)

$$f_M(p, p) = 0.5 \quad \forall p \in (0,1)$$

co wynika z symetrii — przy identycznych parametrach obaj zawodnicy mają równe szanse.

---

## Referencje

- AX-01: Aksjomat Punktowy IID (betatp.io specs)
- Klaassen & Magnus (2001): *Are Points in Tennis IID?*
- Newton & Keller (2005): *Probability of Winning at Tennis*
- Clarke, S.R. (1988): *Dynamic programming in one-day cricket — optimal scoring rates.* Journal of the Operational Research Society, 39(4), 331–337.
- Kingston, J.G. (1976): *Comparison of scoring systems in two-sided competitions.* Journal of Combinatorial Theory, Series A, 20(3), 357–362.
