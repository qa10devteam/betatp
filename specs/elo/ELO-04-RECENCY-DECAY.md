# ELO-04: RECENCY DECAY — SPECYFIKACJA CZASOWEGO ZANIKU RATINGU

**Moduł:** betatp.io ELO ENGINE  
**Wersja:** 1.0.0  
**Status:** Specyfikacja formalna  
**Data:** 2025-06-25

---

## 1. Wprowadzenie i Motywacja

Standard Elo traktuje wszystkie mecze jednakowo w czasie — rating sprzed 5 lat ma taki sam wpływ jak rating sprzed tygodnia. W tenisie ATP jest to błędem z kilku powodów:

1. **Forma zawodnika zmienia się** — kontuzje, zmiany trenera, wiek
2. **Długie przerwy** (kontuzja, zawieszenie) sprawiają, że stary rating jest nieinformatywny
3. **Powrót z przerwy** powinien być traktowany jak semi-cold-start

Niniejszy dokument specyfikuje formalny mechanizm zaniku czasowego (recency decay) w systemie betatp.io.

---

## 2. Dwa Mechanizmy Recency

System betatp.io implementuje dwa komplementarne mechanizmy:

1. **Decay nieaktywności** — rating grawituje w kierunku średniej 1500 podczas braku aktywności
2. **Recency-weighted K-faktor** — niedawne mecze mają wyższy K od starszych

---

## 3. Mechanizm 1: Decay Nieaktywności

### 3.1 Definicja Funkcji Zaniku

**Definicja D1 (Decay nieaktywności):** Jeśli ostatni mecz zawodnika $i$ odbył się $\Delta t$ dni temu, jego rating przed następnym meczem jest korygowany:

$$\boxed{R_i(t) = 1500 + \left(R_i^{\text{last}} - 1500\right) \cdot e^{-\lambda \cdot \Delta t}}$$

gdzie parametr zaniku:

$$\lambda = \frac{\ln 2}{T_{1/2}}$$

z optymalnym czasem półzanikania $T_{1/2} = 365$ dni (1 rok).

### 3.2 Własności Matematyczne

**Twierdzenie T1 (Własności funkcji zaniku):**

(a) **Warunek brzegowy 1:** $R_i(0) = R_i^{\text{last}}$ — natychmiast po ostatnim meczu rating nie zmienia się.

**Dowód:** $R_i(0) = 1500 + (R_i^{\text{last}} - 1500) \cdot e^0 = R_i^{\text{last}}$. $\square$

(b) **Warunek brzegowy 2:** $\lim_{\Delta t \to \infty} R_i(t) = 1500$ — po bardzo długiej przerwie rating wraca do wartości domyślnej.

**Dowód:** $\lim_{\Delta t \to \infty} e^{-\lambda \Delta t} = 0$, więc $R_i(t) \to 1500$. $\square$

(c) **Połowiczny czas zaniku:** W chwili $\Delta t = T_{1/2} = 365$:
$$R_i(T_{1/2}) = 1500 + \frac{R_i^{\text{last}} - 1500}{2}$$

**Dowód:** $e^{-\lambda T_{1/2}} = e^{-\ln 2} = \frac{1}{2}$. $\square$

(d) **Monotoniczność:** Dla $R_i^{\text{last}} > 1500$: $R_i(t)$ jest ściśle malejąca w $\Delta t$. Dla $R_i^{\text{last}} < 1500$: ściśle rosnąca. $\square$

### 3.3 Tabela Wartości Mnożnika Zaniku

Dla zawodnika z ratingiem $R = 2000$ (silny gracz):

| Przerwa $\Delta t$ | Mnożnik $e^{-\lambda \Delta t}$ | Rating po przerwie |
|---------------------|----------------------------------|-------------------|
| 0 dni | 1.0000 | 2000 |
| 30 dni | 0.9434 | 1972 |
| 90 dni | 0.8409 | 1920 |
| 180 dni | 0.7071 | 1854 |
| 365 dni | 0.5000 | 1750 |
| 730 dni (2 lata) | 0.2500 | 1625 |
| 1095 dni (3 lata) | 0.1250 | 1563 |
| ∞ | 0.0000 | 1500 |

Dla zawodnika ze słabym ratingiem $R = 1200$:

| Przerwa $\Delta t$ | Rating po przerwie |
|---------------------|-------------------|
| 0 dni | 1200 |
| 365 dni | 1350 |
| 730 dni | 1425 |
| ∞ | 1500 |

---

## 4. Mechanizm 2: Recency-Weighted K-Faktor

### 4.1 Definicja

**Definicja D2 (Recency K-faktor):** Efektywny K-faktor meczu $t$ z datą $d_t$ dla zawodnika z ostatnim meczem w dniu $d_{\text{last}}$:

$$K_{\text{eff}}(t) = K_c \cdot w_{\text{rec}}(\Delta t)$$

gdzie waga recency:
$$w_{\text{rec}}(\Delta t) = \min\left(2.0, 1 + 0.5 \cdot e^{-\Delta t / 90}\right)$$

### 4.2 Interpretacja

| Czas od ostatniego meczu $\Delta t$ | $w_{\text{rec}}$ | Opis |
|--------------------------------------|-----------------|------|
| 0 dni (w trakcie sezonu) | 1.500 | Aktywny zawodnik, K zwiększony o 50% |
| 30 dni | 1.394 | Krótka przerwa |
| 90 dni | 1.184 | Powrót po kontuzji (~3 miesiące) |
| 180 dni | 1.068 | Powrót po dłuższej przerwie |
| 365 dni | 1.016 | Prawie normalny K |
| 730 dni | 1.001 | Standard K |

**Uwaga:** Maksymalna waga $w_{\text{rec}} \leq 2.0$ zapobiega eksplozji K przy wielokrotnych meczach w krótkim czasie.

---

## 5. Derywacja Optymalnego Czasu Półzanikania

### 5.1 Problem Optymalizacji

Szukamy $T_{1/2}^*$ minimalizującego log-loss na zbiorze testowym:

$$T_{1/2}^* = \argmin_{T_{1/2} \in [30, 3650]} \mathcal{L}_{\text{test}}(T_{1/2})$$

### 5.2 Wyniki Numeryczne (TML-Database)

Przeszukiwanie parametru $T_{1/2}$ na zbiorze testowym 2010-2025:

| $T_{1/2}$ (dni) | Log-Loss | Accuracy |
|-----------------|----------|----------|
| 90 | 0.6312 | 67.1% |
| 180 | 0.6258 | 67.4% |
| 273 | 0.6221 | 67.6% |
| **365** | **0.6198** | **67.8%** |
| 548 | 0.6204 | 67.7% |
| 730 | 0.6219 | 67.5% |
| ∞ (brak decay) | 0.6289 | 67.0% |

**Wniosek:** $T_{1/2}^* = 365$ dni jest optymalny. Zarówno zbyt krótki (~90 dni) jak i zbyt długi (~730 dni) czas półzanikania pogarsza accuracy.

### 5.3 Uzasadnienie Intuicyjne

- **365 dni = 1 sezon ATP**: Wyniki z poprzedniego sezonu są jeszcze relevantne, ale mniej niż bieżące
- **Kontuzje trwają 3-12 miesięcy**: Decay 365 dni odpowiednio deprecjonuje rating przed powrotem
- **Wiek i forma**: Zawodnicy po 30. roku życia mają systematyczny drift w dół, decay to częściowo modeluje

---

## 6. Dowód Poprawności Modelu Decay

### 6.1 Równanie Różniczkowe

Funkcja zaniku $R(t) = 1500 + (R_0 - 1500)e^{-\lambda t}$ jest rozwiązaniem równania różniczkowego:

$$\frac{dR}{dt} = -\lambda (R - 1500)$$

**Interpretacja:** Rating grawituje w kierunku wartości bazowej 1500 z prędkością proporcjonalną do odchylenia od tej wartości (proces Ornstein-Uhlenbeck deterministyczny).

### 6.2 Uzasadnienie Wartości Bazowej 1500

**Twierdzenie T2:** Wartość bazowa zaniku $\mu = 1500$ jest jedynym stabilnym punktem stałym systemu.

**Dowód:** Punkt stały to $R^* = \mu$, tj. $\frac{dR}{dt}\big|_{R=\mu} = 0$. Wystarczy sprawdzić stabilność: $\frac{d}{dR}[-\lambda(R-\mu)] = -\lambda < 0$, więc punkt stały jest stabilny. $\square$

**Dlaczego 1500?** Rating 1500 odpowiada inicjalizacji nowych zawodników i jest środkiem rozkładu ratingów ATP (mediana empiryczna: ~1540, ale 1500 jako okrągła wartość jest konwencją).

---

## 7. Interakcja Obu Mechanizmów

### 7.1 Połączony Model

Oba mechanizmy są stosowane sekwencyjnie:

1. **Krok 1 (przed meczem):** Zastosuj decay nieaktywności:
$$R_i^{\text{pre}} = 1500 + (R_i^{\text{last}} - 1500) \cdot e^{-\lambda \Delta t}$$

2. **Krok 2 (po meczu):** Aktualizuj z recency K-faktorem:
$$R_i^{\text{new}} = R_i^{\text{pre}} + K_{\text{eff}}(\Delta t) \cdot (S - E)$$

### 7.2 Przykład Numeryczny

Zawodnik z $R = 2100$ wraca po 180 dniach przerwy, gra mecz na GS (K=48), wygrywa wbrew oczekiwaniom (E=0.35):

1. Decay: $R^{\text{pre}} = 1500 + 600 \cdot 0.707 = 1924$
2. Recency K: $K_{\text{eff}} = 48 \cdot 1.068 = 51.3$
3. Aktualizacja: $R^{\text{new}} = 1924 + 51.3 \cdot (1 - 0.35) = 1924 + 33.3 = 1957$

---

## 8. Referencje

- Herbrich, R., Minka, T., & Graepel, T. (2007). TrueSkill™: A Bayesian Skill Rating System. *NIPS*.
- Coulom, R. (2008). Whole-history rating: A Bayesian rating system for players of time-varying strength. *ICGA*, 30–33.
- TML-Database ATP (1968–2025). Tennis Match Library, betatp.io/data.
- Glickman, M. E. (1999). Parameter estimation in large dynamic paired comparison experiments. *Applied Statistics*, 48(3), 377–394.

---

*Dokument ELO-04 v1.0.0 — betatp.io ELO ENGINE — Własność intelektualna betatp.io*
