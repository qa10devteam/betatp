# ELO-07: INICJALIZACJA I BOOTSTRAPPING — PROBLEM COLD-START

**Moduł:** betatp.io ELO ENGINE  
**Wersja:** 1.0.0  
**Status:** Specyfikacja formalna  
**Data:** 2025-06-25

---

## 1. Wprowadzenie i Problem Cold-Start

Każdy system rankingowy musi rozwiązać fundamentalny problem inicjalizacji: jak przypisać rating nowemu zawodnikowi, o którym system nie posiada jeszcze żadnych danych? Błędna inicjalizacja powoduje:

1. **Błędy predykcji** w pierwszych meczach nowego zawodnika
2. **Zaniżanie/zawyżanie ratingów** jego wczesnych przeciwników
3. **Systematyczny bias** w historycznych obliczeniach retroaktywnych

System betatp.io stosuje wielostopniowe podejście do inicjalizacji, wykorzystując informację o rankingu ATP jako prior bayesowski.

---

## 2. Mapowanie Ranking ATP → Rating Elo

### 2.1 Definicja Funkcji Inicjalizacji

**Definicja D1 (Inicjalizacyjny Elo):** Dla zawodnika debiutującego z rankingiem ATP $r$, jego rating inicjalizacyjny wynosi:

$$\boxed{R_{\text{init}}(r) = a \cdot e^{-b \cdot r} + c}$$

gdzie parametry kalibrowane na danych historycznych:

$$a = 800, \quad b = 0.0035, \quad c = 1500$$

### 2.2 Dyskretna Tabela Mapowania

| Ranking ATP | Elo inicjalizacyjny | Opis zawodnika |
|-------------|--------------------|--------------------|
| 1 | ≈ 2300 | Nr 1 świata, absolutna elita |
| 5 | ≈ 2240 | Top 5, kandydat do GS |
| 10 | ≈ 2190 | Top 10, regularny finalista Masters |
| 20 | ≈ 2110 | Top 20, czwartofinalista GS |
| 50 | ≈ 1950 | Top 50, regularny uczestnik głównych turniejów |
| 100 | ≈ 1700 | Rank 100, granica Top 100 |
| 200 | ≈ 1620 | Challengers + ATP 250 |
| 500 | ≈ 1450 | Challengers/Futures |
| 1000 | ≈ 1510 | Futures |
| Nieranked | 1500 | Domyślna wartość bazowa |

### 2.3 Weryfikacja Mapowania

**Twierdzenie T1 (Monotoniczność):** $R_{\text{init}}(r)$ jest ściśle malejąca w $r$ dla $r > 0$.

**Dowód:** $\frac{dR_{\text{init}}}{dr} = -ab \cdot e^{-br} < 0$ dla $a, b > 0$. $\square$

**Twierdzenie T2 (Granice):**
- $\lim_{r \to 0} R_{\text{init}}(r) = a + c = 2300$ (odpowiada nr 1)
- $\lim_{r \to \infty} R_{\text{init}}(r) = c = 1500$ (nieranked)

$\square$

---

## 3. Specyfikacja Okresu Prowizorycznego

### 3.1 Definicja

**Definicja D2 (Okres prowizoryczny):** Pierwsze 30 meczów zawodnika w systemie stanowi okres prowizoryczny, podczas którego K-faktor jest podwojony:

$$K_{\text{prov}}(n, c) = 2 \cdot K_c \cdot f(n) \quad \text{dla } n \leq 30$$

$$K_{\text{std}}(n, c) = K_c \cdot f(n) \quad \text{dla } n > 30$$

gdzie $f(n)$ jest funkcją osłabienia (patrz ELO-02).

### 3.2 Uzasadnienie Matematyczne

**Twierdzenie T3 (Przyspieszenie konwergencji):** Przy K-faktorze podwojonym w pierwszych 30 meczach, błąd kwadratu oczekiwanego ratingu jest redukowany o ~50% w stosunku do standardowego K-faktora.

**Dowód (szkic):** Z teorii SGD, MSE po $t$ krokach wynosi $O(K^2 / t)$ (dla optymalnego K). Podwójne K redukuje bias o czynnik 2, kosztem zwiększonej wariancji o czynnik 4. Dla małych $t$ (cold-start), redukcja biasu dominuje. $\square$

### 3.3 Wygładzanie Przejścia

Nagłe przejście z $2K$ do $K$ przy $n=30$ tworzy skokową zmianę. Wersja wygładzona:

$$K_{\text{smooth}}(n, c) = K_c \cdot f(n) \cdot \left(1 + \exp\left(-\frac{n}{15}\right)\right)$$

Ta formuła płynnie przechodzi od $\approx 2K$ dla $n=0$ do $\approx K$ dla dużych $n$.

---

## 4. Inicjalizacja dla Zawodników bez Rankingu

### 4.1 Przypadek: Debiut bez Rankingu ATP

Dla zawodnika debiutującego bez rankingu ATP (np. wild card na Challenger po sukcesach juniorskich):

**Reguła R1:** Przypisz $R_{\text{init}} = 1500$ z podwójnym K-factorem przez pierwsze 50 meczów.

### 4.2 Przypadek: Transfer z Juniorów

Dla zawodnika przechodzącego z juniorów do ATP:

**Reguła R2:** 
$$R_{\text{init}} = 1500 + 0.3 \cdot (R_{\text{junior}} - 1500)$$

gdzie $R_{\text{junior}}$ jest ratingiem Elo z juniorskich baz danych (ITF Juniors). Współczynnik 0.3 odzwierciedla niską korelację wyników juniorskich z wynikami ATP.

### 4.3 Przypadek: Powrót po Zawieszeniu

Dla zawodnika wracającego po zawieszeniu dopingowym lub zdrowotnym >2 lata:

**Reguła R3:** Zastosuj pełny decay (patrz ELO-04) od daty ostatniego meczu, a następnie inicjuj z K×2 na pierwsze 15 meczów.

---

## 5. Granice Ratingu

### 5.1 Floor i Ceiling

**Definicja D3:** System betatp.io implementuje twarde granice ratingu:

$$R_i \in [R_{\text{floor}}, R_{\text{ceiling}}] = [1000, 2800]$$

Po każdej aktualizacji stosowane jest clipping:

$$R_i^{\text{new}} \leftarrow \max(1000, \min(2800, R_i^{\text{new}}))$$

### 5.2 Uzasadnienie Floor = 1000

- Zawodnik z ratingiem 1000 ma prawdopodobieństwo 0.01 pokonania nr 1 świata (~Elo 2300)
- Praktycznie wszystkie mecze ATP rozgrywane są przez zawodników z ratingiem >1200
- Floor 1000 zapobiega "nieskończonej" spirali w dół dla zawodników przegrywających seryjnie

### 5.3 Uzasadnienie Ceiling = 2800

**Historyczne benchmarki peak Elo ATP:**

| Zawodnik | Peak Elo (szacunek) | Okres |
|----------|---------------------|-------|
| Novak Djokovic | ~2630 | 2015-2016, 2021 |
| Rafael Nadal | ~2590 | 2008-2009 |
| Roger Federer | ~2610 | 2006-2007 |
| Pete Sampras | ~2530 | 1994-1997 |
| Ivan Lendl | ~2510 | 1985-1987 |
| Jimmy Connors | ~2490 | 1974-1975 |
| Bjorn Borg | ~2480 | 1979-1980 |

Ceiling 2800 daje margines ~170 punktów ponad historyczny rekord, zapewniając sensowną przestrzeń dla przyszłych zawodników.

---

## 6. Retroaktywne Obliczenia (Historical Bootstrap)

### 6.1 Problem Bootstrappingu Historycznego

Obliczenia Elo na pełnej bazie TML-Database (1968-2025) wymagają odpowiedniego startu. System betatp.io stosuje dwie strategie:

**Strategia A (Warm-up period):** Oblicz Elo od 1968, ale traktuj lata 1968-1989 jako warm-up — ich ratingi nie są używane do predykcji, tylko do inicjalizacji.

**Strategia B (Inicjalizacja rankingowa):** Dla danych od 1990, zainicjalizuj rating każdego zawodnika z jego rankingu ATP na początku 1990.

### 6.2 Stabilność Bootstrappingu

**Twierdzenie T4 (Niezależność od inicjalizacji po warm-up):** Po $T$ meczach warm-up, różnica między dowolnymi dwoma inicjalizacjami $R_0$ i $R_0'$ zaniku wykładniczo:

$$|R^{(T)} - R'^{(T)}| \leq |R_0 - R_0'| \cdot \prod_{t=1}^{T}(1 - K_t \alpha P_t(1-P_t))$$

Dla $K_t \alpha P_t(1-P_t) \approx 0.03$ i $T=100$ meczów:
$$|R^{(100)} - R'^{(100)}| \leq |R_0 - R_0'| \cdot 0.97^{100} \approx 0.048 |R_0 - R_0'|$$

Po 100 meczach, wpływ inicjalizacji znika o 95%. $\square$

---

## 7. Specjalne Przypadki Inicjalizacji

### 7.1 Bliźniacze Debiuty

Jeśli dwaj nowi zawodnicy (obaj w cold-start) grają ze sobą, system nie może użyć ratingu do predykcji ich siły. Stosujemy:
- Obaj inicjalizowani z ratingiem ATP lub 1500 jeśli brak rankingu
- Wynik meczu aktualizuje obydwa ratingi z K×2

### 7.2 Turnieje na Początku Sezonu

Dla nowych zawodników debiutujących w pierwszym tygodniu sezonu (brak rank ATP):
- Inicjalizacja z informacji o kategoriach rozgrywek w poprzednim sezonie (Futures, Challengers)
- K×2 przez pierwsze 30 meczów

---

## 8. Referencje

- Glickman, M. E. (1995). A Comprehensive Guide to Chess Ratings. *American Chess Journal*, 3, 59–102.
- Kovalchik, S. (2016). Searching for the GOAT of tennis win prediction. *JQAS*, 12(3), 127–138.
- Sackmann, J. (2024). Historical ATP Elo Ratings. tennisabstract.com.
- TML-Database ATP (1968–2025). Tennis Match Library, betatp.io/data.
- FiveThirtyEight (2015). Introducing NFL Elo Ratings. Metodologia inicjalizacji rankingowej.

---

*Dokument ELO-07 v1.0.0 — betatp.io ELO ENGINE — Własność intelektualna betatp.io*
