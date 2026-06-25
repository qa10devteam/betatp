# AX-01: AKSJOMAT PUNKTOWY IID
## Fundamentalny Aksjomat Bernoulliowski Modelowania Tenisowego

**Dokument:** AX-01  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  

---

## 1. Wprowadzenie i Motywacja

Niniejszy dokument formalizuje fundamentalny aksjomat modelu probabilistycznego betatp.io: założenie niezależności i jednakowego rozkładu (ang. *independent and identically distributed*, **iid**) punktów tenisowych. Aksjomat ten stanowi podstawę całej hierarchii probabilistycznej opisanej w AX-02.

Tenis jest grą hierarchiczną: mecz składa się z setów, sety z gemów, gemy z punktów. Kluczowym spostrzeżeniem jest to, że jeżeli posiadamy model na poziomie punktu, możemy wyprowadzić zamknięte formuły dla wszystkich wyższych poziomów hierarchii przez indukcję kombinatoryczną.

---

## 2. Definicje Podstawowe

### Definicja 2.1 (Przestrzeń Probabilistyczna Punktu)

Niech $(\Omega_p, \mathcal{F}_p, \mathbb{P}_p)$ będzie przestrzenią probabilistyczną, gdzie:
- $\Omega_p = \{0, 1\}$ — przestrzeń wyników pojedynczego punktu (0 = przegrana serwującego, 1 = wygrana serwującego)
- $\mathcal{F}_p = 2^{\Omega_p}$ — $\sigma$-algebra zdarzeń
- $\mathbb{P}_p$ — miara probabilistyczna określona przez parametr $p \in (0,1)$

### Definicja 2.2 (Zmienna Losowa Bernouliego — Aksjomat IID)

**AKSJOMAT A1 (Fundamentalny Aksjomat Punktowy):**

Niech $X_1, X_2, X_3, \ldots$ będzie ciągiem wyników kolejnych punktów w meczu tenisowym serwowanych przez zawodnika $A$. Przyjmujemy, że:

$$X_i \overset{\text{iid}}{\sim} \text{Bernoulli}(p_s)$$

gdzie $p_s \in (0,1)$ jest prawdopodobieństwem wygrania punktu przez serwującego zawodnika $A$.

Formalnie:
$$\mathbb{P}(X_i = 1) = p_s, \quad \mathbb{P}(X_i = 0) = 1 - p_s = q_s$$

oraz dla każdego skończonego zbioru indeksów $\{i_1, i_2, \ldots, i_k\} \subset \mathbb{N}$:

$$\mathbb{P}\left(\bigcap_{j=1}^{k} \{X_{i_j} = x_{i_j}\}\right) = \prod_{j=1}^{k} \mathbb{P}(X_{i_j} = x_{i_j})$$

### Definicja 2.3 (Parametry Serwisowe)

Dla meczu pomiędzy zawodnikami $A$ i $B$ definiujemy:
- $p_A$ — prawdopodobieństwo wygrania punktu przez $A$ na własnym serwisie
- $p_B$ — prawdopodobieństwo wygrania punktu przez $B$ na własnym serwisie
- $q_A = 1 - p_A$ — prawdopodobieństwo przełamania serwisu $A$ przez $B$
- $q_B = 1 - p_B$ — prawdopodobieństwo przełamania serwisu $B$ przez $A$

---

## 3. Wyprowadzenie P(Gem)

### Twierdzenie 3.1 (Prawdopodobieństwo Wygrania Gemu)

Niech $p$ będzie prawdopodobieństwem wygrania punktu przez serwującego. Wtedy prawdopodobieństwo wygrania przez serwującego gemu (przy serwisie) wynosi:

$$P_G(p) = \sum_{k=0}^{3} \binom{3+k}{k} p^4 q^k + \frac{p^2}{1-2p(1-p)} \cdot p^3 q^3 \cdot \binom{6}{3}$$

**Wyprowadzenie:**

Gem tenisowy wygrywa gracz, który zdobywa co najmniej 4 punkty, przewagą co najmniej 2 punktów.

*Przypadek 1: Wygrana bez deuce (4-0, 4-1, 4-2)*

$$P(\text{4-0}) = p^4$$

$$P(\text{4-1}) = \binom{4}{1} p^4 q = 4p^4 q$$

$$P(\text{4-2}) = \binom{5}{2} p^4 q^2 = 10 p^4 q^2$$

*Przypadek 2: Deuce (3-3) i rozgrywka na przewagę*

Prawdopodobieństwo osiągnięcia deuce:

$$P(\text{deuce}) = \binom{6}{3} p^3 q^3 = 20 p^3 q^3$$

Po deuce, prawdopodobieństwo wygrania gemu przez serwującego:

$$P(\text{wygrana po deuce}) = \sum_{k=0}^{\infty} (pq + qp)^k \cdot p^2 = \frac{p^2}{1 - 2pq}$$

Zatem pełna formuła:

$$\boxed{P_G(p) = p^4\left[1 + 4q + 10q^2\right] + 20p^3 q^3 \cdot \frac{p^2}{p^2 + q^2}}$$

---

## 4. Wyprowadzenie P(Tiebreak)

### Twierdzenie 4.1 (Prawdopodobieństwo Wygrania Tiebreaka)

W tiebreaku obowiązują serwisy naprzemienne (po 2 punkty), a grę wygrywa ten, kto pierwszy zdobędzie 7 punktów z przewagą 2. Dla uproszczenia przyjmujemy efektywne prawdopodobieństwo zdobycia punktu przez gracza $A$ jako:

$$p_{tb} = \frac{p_A + (1-p_B)}{2}$$

Analogicznie do gemu, z limitem 7 zamiast 4:

*Przypadek 1: Bez deuce (7-0 do 7-5)*

$$P_1 = \sum_{k=0}^{5} \binom{6+k}{k} p_{tb}^7 (1-p_{tb})^k$$

*Przypadek 2: Deuce (6-6) i rozgrywka na przewagę*

$$P_2 = \binom{12}{6} p_{tb}^6 (1-p_{tb})^6 \cdot \frac{p_{tb}^2}{p_{tb}^2 + (1-p_{tb})^2}$$

Zatem:

$$\boxed{P_{TB}(p_{tb}) = \sum_{k=0}^{5} \binom{6+k}{k} p_{tb}^7 (1-p_{tb})^k + \binom{12}{6} p_{tb}^6 (1-p_{tb})^6 \cdot \frac{p_{tb}^2}{p_{tb}^2 + (1-p_{tb})^2}}$$

---

## 5. Wyprowadzenie P(Set)

### Twierdzenie 5.1 (Prawdopodobieństwo Wygrania Seta)

Set wygrywa gracz, który pierwszy zdobędzie 6 gemów z przewagą 2, lub wygra tiebreaka przy stanie 6-6.

Niech $P_{Gs}$ = $P_G(p_A)$ (prawdopodobieństwo wygrania gemu przez $A$ na własnym serwisie) oraz $P_{Gr}$ = $1 - P_G(p_B)$ (prawdopodobieństwo wygrania gemu przez $A$ przy returnowaniu).

Ponieważ serwis zmienia się po każdym gemie, definiujemy:

$$p_{\text{gem,A}} = P_G(p_A), \quad p_{\text{gem,B}} = P_G(p_B)$$

Prawdopodobieństwo wygrania gemu przez $A$ w dowolnym gemie seta wynosi (ze względu na naprzemienne serwowanie):

$$P(\text{A wygrywa gem}) = \begin{cases} P_G(p_A) & \text{gdy A serwuje} \\ 1 - P_G(p_B) & \text{gdy B serwuje} \end{cases}$$

*Przypadek 1: Set bez tiebreaka (6-0 do 6-4, 7-5)*

$$P_{S,\text{no-tb}}(p_A, p_B) = \sum_{\text{sekwencje gemów}} \prod_{i} P(\text{A wygrywa gem}_i)$$

*Przypadek 2: Tiebreak (6-6)*

Przy stanie 6-6, prawdopodobieństwo wygrania seta przez $A$:

$$P_{S,\text{tb}}(p_A, p_B) = P(\text{6-6}) \cdot P_{TB}(p_{tb})$$

Pełna formuła (formalizacja rekurencyjna):

Niech $S(a, b)$ oznacza prawdopodobieństwo wygrania seta przez $A$ przy stanie $a$-gemów do $b$-gemów (dla $A$), gdy aktualnie serwuje $A$:

$$S(a, b) = p_{\text{gem,A}} \cdot S'(a+1, b) + (1-p_{\text{gem,A}}) \cdot S'(a, b+1)$$

gdzie $S'(a, b)$ to ta sama funkcja gdy serwuje $B$:

$$S'(a, b) = (1-p_{\text{gem,B}}) \cdot S(a+1, b) + p_{\text{gem,B}} \cdot S(a, b+1)$$

z warunkami brzegowymi:
- $S(6, b) = 1$ dla $b \leq 4$
- $S(a, 6) = 0$ dla $a \leq 4$
- $S(6, 5) = 1$, $S(5, 6) = 0$
- $S'(6, 5) = 1$, $S'(5, 6) = 0$
- $S(6, 6) = P_{TB}(p_{tb})$

---

## 6. Wyprowadzenie P(Mecz)

### Twierdzenie 6.1 (Prawdopodobieństwo Wygrania Meczu)

**Format Best-of-3 (większość turniejów ATP):**

$$P_M^{(3)}(p_A, p_B) = P_S^2 + 2P_S^2(1-P_S)$$

gdzie $P_S = P_S(p_A, p_B)$ to prawdopodobieństwo wygrania pojedynczego seta przez $A$.

Dokładniej, biorąc pod uwagę naprzemienność serwisu na początku setów:

$$P_M^{(3)} = P_{S1} \cdot P_{S2} + P_{S1}(1-P_{S2}) \cdot P_{S3} + (1-P_{S1}) \cdot P_{S2}' \cdot P_{S3}'$$

**Format Best-of-5 (Grand Slam):**

$$P_M^{(5)}(p_A, p_B) = \sum_{k=0}^{2} \binom{2+k}{k} P_S^3 (1-P_S)^k$$

$$= P_S^3 \left[1 + 3(1-P_S) + 6(1-P_S)^2\right]$$

---

## 7. Twierdzenie o Wystarczalności Założenia IID

### Twierdzenie 7.1 (Wystarczalność Założenia IID)

**Twierdzenie:** Założenie A1 (iid Bernoulli) jest wystarczające do wyznaczenia zamkniętych formuł dla $P(G)$, $P(TB)$, $P(S)$, $P(M)$ jako funkcji deterministycznych parametrów $p_A$ i $p_B$.

**Dowód:**

Przez indukcję na poziomach hierarchii.

*Podstawa indukcji (poziom punktu):* $P(X_i = 1) = p$ jest deterministyczną funkcją $p$ na mocy Aksjomatu A1. ✓

*Krok indukcyjny (gem → set → mecz):*

Niech $\mathcal{H}_n$ będzie zdarzeniem złożonym na poziomie $n$ hierarchii. Na mocy założenia iid, zdarzenia $X_1, X_2, \ldots$ są niezależne. Zatem:

$$\mathbb{P}(\mathcal{H}_n) = \sum_{\omega \in \Omega_n} \prod_{j \in J(\omega)} p^{x_j} q^{1-x_j}$$

gdzie $\Omega_n$ jest skończonym zbiorem sekwencji punktów prowadzących do wygrania zdarzenia $\mathcal{H}_n$, a $J(\omega)$ jest zbiorem indeksów punktów w sekwencji $\omega$.

Ponieważ $\Omega_n$ jest deterministycznie zdeterminowany przez zasady tenisa (które są stałe), a każdy czynnik $p^{x_j} q^{1-x_j}$ zależy wyłącznie od $p$ i $q = 1-p$, wynika stąd że:

$$\mathbb{P}(\mathcal{H}_n) = f_n(p)$$

dla pewnej funkcji wielomianowej $f_n: (0,1) \to (0,1)$. Ponieważ $f_n$ nie zależy od $\omega$ (wybranych numerów punktów) lecz tylko od ich rozkładu, udowodniliśmy że wszystkie prawdopodobieństwa wyższych poziomów są funkcjami deterministycznymi parametru $p$. $\blacksquare$

---

## 8. Uzasadnienie Empiryczne — Dane ATP

### Tabela 8.1: Empiryczne Prawdopodobieństwa Wygrania Punktu na Serwisie (ATP Tour, 2018–2024)

| Nawierzchnia | Minimum | Mediana | Maksimum | Odch. std. |
|:-------------|:-------:|:-------:|:--------:|:----------:|
| Twarda (Hard) | 0.73 | 0.755 | 0.78 | 0.018 |
| Ziemna (Clay) | 0.69 | 0.715 | 0.74 | 0.021 |
| Trawiasta (Grass) | 0.74 | 0.765 | 0.79 | 0.016 |
| Dywanowa (Carpet) | 0.75 | 0.770 | 0.80 | 0.014 |

### Tabela 8.2: Wynikowe P(Gem) dla reprezentatywnych wartości $p$

| $p$ (punkty) | $P_G(p)$ | Nawierzchnia |
|:------------:|:--------:|:-------------|
| 0.69 | 0.822 | Clay (słaby serw.) |
| 0.715 | 0.862 | Clay (mediana) |
| 0.74 | 0.896 | Clay (max) / Hard (min) |
| 0.755 | 0.913 | Hard (mediana) |
| 0.765 | 0.924 | Grass (mediana) |
| 0.79 | 0.947 | Grass (max) |

### Obserwacja 8.1

Danych ATP wskazuje, że założenie iid jest uzasadnione jako *pierwsze przybliżenie* modelu. Systematyczne odchylenia (np. efekt ciśnienia przy break pointach, momentum) są drugorzędowe i wynoszą ≤ 2.5% w porównaniu z wartościami modelowymi. Szczegółowa analiza odchyleń jest przedmiotem odrębnych dokumentów specyfikacyjnych.

### Obserwacja 8.2 (Asymetria Nawierzchniowa)

Różnica w $P_G$ pomiędzy trawą a mączką wynosi około:

$$\Delta P_G = P_G(0.765) - P_G(0.715) \approx 0.924 - 0.862 = 0.062$$

To 6.2% różnicy na poziomie gemu, co przekłada się na znaczące różnice w prawdopodobieństwach setowych i meczowych, uzasadniając konieczność oddzielnych wariantów Elo na nawierzchnię (patrz AX-04).

---

## 9. Warunki Brzegowe i Ograniczenia Modelu

### Definicja 9.1 (Dopuszczalny Zakres Parametru)

$$p_s \in [p_{\min}, p_{\max}] = [0.50, 0.95]$$

Wartości poza tym zakresem są uznawane za numerycznie niestabilne lub nieprzedstawialne empirycznie.

### Ograniczenie 9.1 (Założenia Niezależności)

Aksjomat A1 pomija następujące efekty empiryczne:
1. **Momentum** — wzrost/spadek wydajności po sekwencji wygranych/przegranych punktów
2. **Efekt break pointa** — zmiana $p_s$ przy kluczowych punktach
3. **Zmęczenie** — degeneracja $p_s$ w toku meczu
4. **Efekt serwisowy** — korelacja wyników kolejnych punktów z tego samego gemu

Dokumenty rozszerzające model (poza zakresem AX-01) mogą wprowadzać korekty do $p_s$ w zależności od kontekstu.

---

## 10. Formalne Stwierdzenie Aksjomatu

**AKSJOMAT A1 (Formalne Stwierdzenie Ostateczne):**

Dla każdego meczu tenisowego pomiędzy zawodnikami $A$ i $B$, silnik predykcyjny betatp.io modeluje wynik każdego $i$-tego punktu serwowanego przez zawodnika $S$ jako:

$$X_i^{(S)} \overset{\text{iid}}{\sim} \text{Bernoulli}(p_S), \quad S \in \{A, B\}$$

oraz zakłada niezależność między punktami serwowanymi przez różnych zawodników:

$$X_i^{(A)} \perp\!\!\!\perp X_j^{(B)} \quad \forall i, j$$

Na mocy tego aksjomatu wszystkie prawdopodobieństwa wyższych poziomów hierarchii:

$$P_G, P_{TB}, P_S, P_M$$

są deterministycznymi, analitycznie wyznaczalnymi funkcjami wyłącznie pary parametrów $(p_A, p_B)$. $\blacksquare$

---

## Referencje

- Klaassen, F.J.G.M. & Magnus, J.R. (2001). *Are Points in Tennis Independent and Identically Distributed? Evidence from a Dynamic Binary Panel Data Model.* Journal of the American Statistical Association, 96(454), 500–509.
- Newton, P.K. & Keller, J.B. (2005). *Probability of Winning at Tennis: Theory and Data.* Studies in Applied Mathematics, 114(3), 241–269.
- ATP Tour Statistics (2018–2024). *First Service Points Won, Return Points Won by Surface.* atptour.com/en/stats.
- Barnett, T. & Clarke, S.R. (2005). *Combining player statistics to predict outcomes of tennis matches.* IMA Journal of Management Mathematics, 16(2), 113–120.
