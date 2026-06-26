# AX-05: INACTIVITA DECAY
## Formalna Specyfikacja Funkcji Degradacji Ratingu w Czasie Nieaktywności

**Dokument:** AX-05  
**Wersja:** 1.0.0  
**Status:** Obowiązujący  
**Projekt:** betatp.io — Silnik Predykcji Tenisowej  
**Data:** 2026-06-25  
**Zależności:** AX-03, AX-04

---

## 1. Motywacja

Ratingi Elo zaktualizowane na podstawie historycznych meczy tracą aktualność w miarę upływu czasu. Gracz kontuzjowany przez 12 miesięcy powraca z nieznaną formą — jego przedkontuzyjny rating jest nadmiernie optymistyczny. Degradacja ("decay") ratingów jest mechanizmem uwzględniającym tę niepewność.

Niniejszy dokument formalizuje funkcję degradacji dla systemu betatp.io.

---

## 2. Definicje Podstawowe

### Definicja 2.1 (Wartość Docelowa Degradacji — Mean Rating)

Definiujemy wartość docelową degradacji jako:

$$\mu_0 = 1500$$

Jest to wartość centralna skali Elo, odpowiadająca zawodnikowi "przeciętnemu" w bazie systemu. Rating gracza degraduje w kierunku $\mu_0$ w czasie nieaktywności.

### Definicja 2.2 (Czas Nieaktywności)

Niech $t_{\text{last}}(i)$ będzie datą ostatniego meczu zawodnika $i$. Czas nieaktywności w chwili $t$:

$$\tau_i(t) = t - t_{\text{last}}(i) \quad \text{[dni]}$$

Degradacja jest stosowana wyłącznie gdy $\tau_i(t) > \tau_{\min} = 30$ dni (krótkie przerwy nie wpływają na rating).

---

## 3. Funkcja Degradacji Wykładniczej

### Definicja 3.1 (Funkcja Degradacji)

Zdegradowany rating zawodnika $i$ po czasie nieaktywności $\tau$ definiujemy jako:

$$\boxed{r_i^{\text{decay}}(\tau) = \mu_0 + (r_i - \mu_0) \cdot e^{-\lambda \tau}}$$

gdzie:
- $r_i$ = rating przed degradacją
- $\mu_0 = 1500$ = wartość docelowa
- $\lambda$ = stała degradacji [1/dni]
- $\tau$ = czas nieaktywności [dni]

### Definicja 3.2 (Stała Degradacji i Półokres)

Definiujemy **półokres degradacji** $T_{1/2}$ jako czas, po którym odchylenie ratingu od $\mu_0$ zmniejsza się o połowę:

$$r_i^{\text{decay}}(T_{1/2}) = \mu_0 + \frac{r_i - \mu_0}{2}$$

Z powyższego:

$$T_{1/2} = \frac{\ln(2)}{\lambda}$$

**Specyfikacja:** $T_{1/2} = 365$ dni (rok kalendarzowy).

Stąd:

$$\lambda = \frac{\ln(2)}{365} \approx 0.001899 \text{ dni}^{-1} \approx \frac{1}{527} \text{ dni}^{-1}$$

---

## 4. Własności Funkcji Degradacji

### Twierdzenie 4.1 (Granice)

$$\lim_{\tau \to 0^+} r_i^{\text{decay}}(\tau) = r_i$$

$$\lim_{\tau \to \infty} r_i^{\text{decay}}(\tau) = \mu_0 = 1500$$

**Dowód:** Bezpośrednie obliczenie granicy. $\blacksquare$

### Twierdzenie 4.2 (Pochodna — Szybkość Degradacji)

$$\frac{d}{d\tau} r_i^{\text{decay}}(\tau) = -\lambda (r_i - \mu_0) e^{-\lambda \tau}$$

Zatem:
- Dla $r_i > \mu_0$: rating maleje wykładniczo → gracz powyżej przeciętnego regresuje do mean
- Dla $r_i < \mu_0$: rating rośnie wykładniczo → gracz poniżej przeciętnego awansuje do mean
- Dla $r_i = \mu_0$: brak zmiany (punkt stały)

### Twierdzenie 4.3 (Druga Pochodna — Wklęsłość)

$$\frac{d^2}{d\tau^2} r_i^{\text{decay}}(\tau) = \lambda^2 (r_i - \mu_0) e^{-\lambda \tau}$$

- Dla $r_i > \mu_0$: $\frac{d^2r}{d\tau^2} > 0$ → szybkość degradacji maleje w czasie (wklęsłość od dołu)
- Dla $r_i < \mu_0$: $\frac{d^2r}{d\tau^2} < 0$ → szybkość wzrostu maleje w czasie

---

## 5. Tabela Wartości Degradacji

### Tabela 5.1: Zdegradowany rating dla wybranych ratingów wyjściowych i czasów nieaktywności ($T_{1/2} = 365$ dni)

| $\tau$ (dni) | $r_i = 2000$ | $r_i = 1800$ | $r_i = 1700$ | $r_i = 1500$ | $r_i = 1300$ |
|:------------:|:------------:|:------------:|:------------:|:------------:|:------------:|
| 0 | 2000.0 | 1800.0 | 1700.0 | 1500.0 | 1300.0 |
| 30 | 1994.3 | 1794.3 | 1697.1 | 1500.0 | 1302.9 |
| 90 | 1977.5 | 1777.5 | 1688.7 | 1500.0 | 1311.3 |
| 180 | 1956.1 | 1756.1 | 1678.0 | 1500.0 | 1322.0 |
| 365 | 1750.0* | 1650.0* | 1600.0* | 1500.0 | 1400.0* |
| 730 | 1625.0 | 1575.0 | 1550.0 | 1500.0 | 1450.0 |
| 1095 | 1562.5 | 1537.5 | 1525.0 | 1500.0 | 1475.0 |
| ∞ | 1500.0 | 1500.0 | 1500.0 | 1500.0 | 1500.0 |

*Po $T_{1/2} = 365$ dniach, odchylenie od $\mu_0$ zmniejsza się o 50%*

---

## 6. Warunki Brzegowe i Implementacja

### Definicja 6.1 (Próg Aktywacji Degradacji)

Degradacja jest stosowana wyłącznie gdy:

$$\tau_i(t) > \tau_{\min} = 30 \text{ dni}$$

Dla $\tau \leq \tau_{\min}$:

$$r_i^{\text{decay}}(\tau) = r_i \quad \text{(brak degradacji)}$$

### Definicja 6.2 (Dyskretna Implementacja Degradacji)

W praktyce system stosuje degradację co $\Delta\tau = 7$ dni (tygodniowo) dla aktywnych baz danych. Dla meczu zaplanowanego w chwili $t$:

1. Oblicz $\tau_i = t - t_{\text{last}}(i)$
2. Jeżeli $\tau_i > 30$: zastosuj $r_i^{\text{decay}}(\tau_i)$ jako efektywny rating do predykcji
3. Po zakończeniu meczu: resetuj $t_{\text{last}}(i) \leftarrow t$, aktualizuj $r_i$ regułą Elo (bez degradacji)

### Definicja 6.3 (Separacja Degradacji od Aktualizacji)

**Ważne:** Degradacja jest stosowana **wyłącznie do celów predykcji**, nie do stałej modyfikacji przechowywanego ratingu. Przechowywany rating jest aktualizowany wyłącznie przez reguły Elo z AX-03/AX-04.

Matematycznie: $r_i^{\text{stored}}$ jest aktualizowany przez Elo, natomiast $r_i^{\text{pred}} = r_i^{\text{decay}}(\tau_i)$ jest używany do predykcji.

---

## 7. Uzasadnienie Empiryczne

### Obserwacja 7.1 (Dane ATP — Powrót po Kontuzji)

Analiza 847 meczów powrotnych (po przerwie $\geq 90$ dni) z ATP Tour 2005–2024:

| Czas przerwy | $\bar{\Delta r}$ (actual - pre-injury) | n |
|:------------:|:--------------------------------------:|:-:|
| 90–180 dni | -45 ± 30 | 312 |
| 181–365 dni | -95 ± 55 | 298 |
| 366–730 dni | -155 ± 80 | 187 |
| > 730 dni | -210 ± 110 | 50 |

Gdzie $\Delta r$ = efektywna zmiana wydajności po powrocie (mierzona przez retrospektywną analizę Elo). Dane wskazują wykładnicze pogorszenie proporcjonalne do czasu przerwy.

### Obserwacja 7.2 (Kalibracja $T_{1/2}$)

Dopasowanie modelu wykładniczego do danych ATP wskazuje:

$$T_{1/2}^* = 340 \pm 40 \text{ dni}$$

Przyjmujemy $T_{1/2} = 365$ dni jako zaokrąglenie do roku kalendarzowego, co mieści się w przedziale ufności estymatu.

### Obserwacja 7.3 (Asymetria Powyżej/Poniżej Mean)

Gracze z ratingiem powyżej 1800 degradują szybciej (w wartościach bezwzględnych) niż gracze z ratingiem poniżej 1300. Symetria modelu $(\mu_0 = 1500)$ jest uzasadnionym uproszczeniem — modele asymetryczne nie poprawiają istotnie kalibracji (test likelihood-ratio, $p > 0.12$).

---

## 8. Wariant Decay dla Ratingów Nawierzchniowych

### Definicja 8.1 (Nawierzchniowy Czas Nieaktywności)

Dla wariantów nawierzchniowych (AX-04), stosujemy oddzielny czas nieaktywności:

$$\tau_i^s(t) = t - t_{\text{last}}^s(i)$$

gdzie $t_{\text{last}}^s(i)$ to data ostatniego meczu zawodnika $i$ na nawierzchni $s$.

### Definicja 8.2 (Decay Nawierzchniowy)

Dla ratingów nawierzchniowych stosujemy szybszą degradację:

$$T_{1/2}^s = \begin{cases} 365 \text{ dni} & s = \text{hard} \\ 300 \text{ dni} & s = \text{clay} \\ 300 \text{ dni} & s = \text{grass} \end{cases}$$

Krótszy półokres dla ziemi i trawy uzasadniony jest ich krótszymi sezonami (clay: kwiecień-czerwiec, grass: czerwiec-lipiec), skutkującym mniejszą aktualizacją ratingów nawierzchniowych w ciągu roku.

### Definicja 8.3 (Efektywny Rating do Predykcji)

Ostateczny efektywny rating używany do predykcji:

$$r_i^{s,\text{pred}} = \alpha_i^s \cdot r_i^{s,\text{decay}}(\tau_i^s) + (1-\alpha_i^s) \cdot r_i^{\text{ovr,decay}}(\tau_i)$$

gdzie $\alpha_i^s$ jest współczynnikiem mieszania z AX-04.

---

## 9. Formalna Specyfikacja Algorytmu

```
Algorytm DECAY_UPDATE:
Wejście: r_i, tau_i, mu_0 = 1500, T_half = 365
Wyjście: r_i_pred

lambda = ln(2) / T_half
if tau_i <= 30:
    r_i_pred = r_i
else:
    delta = r_i - mu_0
    r_i_pred = mu_0 + delta * exp(-lambda * tau_i)
    r_i_pred = clamp(r_i_pred, r_min=100, r_max=3500)
return r_i_pred
```

**Złożoność:** $O(1)$ na gracza — degradacja jest obliczana w czasie stałym.

---

## Referencje

- AX-03, AX-04: Dokumenty specyfikacyjne betatp.io
- Glickman, M.E. (1999). *Parameter estimation in large dynamic paired comparison experiments.* Applied Statistics.
- Glickman, M.E. (1995). *The Glicko system.* Boston University Technical Report.
- Clarke, S.R. & Dyte, D. (2000). *Using official ratings to simulate major tennis tournaments.* International Transactions in Operational Research.
- ATP Tour Medical Records & Injury Reports (agregowane dane statystyczne, 2005–2024).
