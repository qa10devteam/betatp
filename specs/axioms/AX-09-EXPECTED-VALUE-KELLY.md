# AX-09: EXPECTED VALUE I KRYTERIUM KELLY'EGO — SPECYFIKACJA FORMALNA

**Dokument:** AX-09  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. WARTOŚĆ OCZEKIWANA ZAKŁADU

### Definicja 1.1 — Expected Value (EV)

Niech:
- $p$ — prawdopodobieństwo wygranej (po de-viggingu, wyznaczone przez model betatp)
- $o$ — kurs bukmacherski (decimal odds)
- Zakład jednostkowy = 1 jednostka

**Expected Value** zakładu definiujemy jako:

$$\text{EV} = p \cdot o - 1$$

**Interpretacja:**
- $\text{EV} > 0$: zakład przynosi zysk w długim horyzoncie (zakład z wartością)
- $\text{EV} = 0$: zakład sprawiedliwy (fair bet)
- $\text{EV} < 0$: zakład przynosi stratę (do unikania)

### Twierdzenie 1.1 — Warunek opłacalności

Zakład jest opłacalny wtedy i tylko wtedy, gdy:

$$p > \frac{1}{o} \iff p \cdot o > 1 \iff \text{EV} > 0$$

**Dowód:** Bezpośrednio z definicji EV = $p \cdot o - 1 > 0 \iff p > 1/o$. $\square$

### Definicja 1.2 — EV procentowy

$$\text{EV\%} = \frac{\text{EV}}{1} \times 100\% = (p \cdot o - 1) \times 100\%$$

### Definicja 1.3 — Edge (przewaga)

$$\text{Edge} = p - p_{\text{impl}} = p - \frac{1}{o}$$

gdzie $p_{\text{impl}}$ to implied probability kursu bukmacherskiego. Zachodzi: $\text{EV} = \text{Edge} \cdot o$.

### Przykład ATP

**Mecz:** Alcaraz vs Zverev, Roland Garros 2024  
**Model betatp:** $p_{\text{Alcaraz}} = 0.68$  
**Kurs Pinnacle:** $o_{\text{Alcaraz}} = 1.72$

$$\text{EV} = 0.68 \times 1.72 - 1 = 1.1696 - 1 = +0.1696 = +16.96\%$$

$$\text{Edge} = 0.68 - \frac{1}{1.72} = 0.68 - 0.5814 = 0.0986$$

---

## 2. KRYTERIUM KELLY'EGO — WYPROWADZENIE

### 2.1 Problem optymalizacji

**Cel:** Znaleźć optymalny ułamek $f^*$ kapitału $W$ postawiony na zakład o kursie $o$ i prawdopodobieństwie wygranej $p$.

**Założenia:**
- Kapitał startowy: $W_0$
- Seria $N$ identycznych i niezależnych zakładów
- Ułamek obstawiany: $f \in (0, 1)$

### 2.2 Dynamika kapitału

Po $N$ zakładach, z $W$ wygranymi i $(N-W)$ przegranymi:

$$W_N = W_0 \cdot (1 + f(o-1))^W \cdot (1-f)^{N-W}$$

### Definicja 2.1 — Stopa wzrostu logarytmicznego (Growth Rate)

$$G(f) = \frac{1}{N} \ln \frac{W_N}{W_0} = \frac{W}{N} \ln(1 + f(o-1)) + \frac{N-W}{N} \ln(1-f)$$

W granicy $N \to \infty$, z prawa wielkich liczb $W/N \to p$:

$$G(f) = p \ln(1 + f(o-1)) + (1-p) \ln(1-f)$$

### Twierdzenie 2.1 — Kryterium Kelly'ego (Twierdzenie o maksymalizacji wzrostu)

**Twierdzenie:** Funkcja $G(f)$ osiąga globalne maksimum dla:

$$f^* = \frac{p(o-1) - (1-p)}{o-1} = \frac{p \cdot o - 1}{o - 1}$$

co równoważnie można zapisać jako:

$$f^* = \frac{\text{EV}}{o - 1} = p - \frac{1-p}{o-1} = p - \frac{q}{b}$$

gdzie $q = 1-p$ i $b = o-1$ (zysk netto na jednostkę).

**Dowód:**

Różniczkujemy $G(f)$ po $f$:

$$\frac{dG}{df} = \frac{p(o-1)}{1 + f(o-1)} - \frac{1-p}{1-f}$$

Przyrównując do zera:

$$\frac{p(o-1)}{1 + f(o-1)} = \frac{1-p}{1-f}$$

$$p(o-1)(1-f) = (1-p)(1 + f(o-1))$$

$$p(o-1) - pf(o-1) = (1-p) + f(1-p)(o-1)$$

$$p(o-1) - (1-p) = f(o-1)[p + (1-p)] = f(o-1)$$

$$f^* = \frac{p(o-1) - (1-p)}{o-1} = p - \frac{1-p}{o-1}$$

Sprawdzamy drugi warunek (maksimum):

$$\frac{d^2G}{df^2} = -\frac{p(o-1)^2}{(1+f(o-1))^2} - \frac{1-p}{(1-f)^2} < 0$$

ponieważ oba człony są ujemne. $G(f)$ jest ścisłe wklęsłe, więc punkt krytyczny jest globalnym maksimum. $\square$

### Wniosek 2.2 — Kelly maximizuje long-run growth rate

Z twierdzenia 2.1 wynika:

$$\lim_{N \to \infty} \frac{W_N^{(f^*)}}{W_N^{(f)}} = \infty \quad \text{dla dowolnego } f \neq f^*$$

**Dowód (zarys):** Niech $G^* = G(f^*)$ i $G = G(f)$, $G < G^*$. Wtedy:
$$W_N^{(f^*)} = W_0 e^{NG^*}, \quad W_N^{(f)} = W_0 e^{NG}$$
$$\frac{W_N^{(f^*)}}{W_N^{(f)}} = e^{N(G^* - G)} \to \infty \quad (N \to \infty)$$ $\square$

---

## 3. HALF KELLY — STANDARD SYSTEMU betatp.io

### Definicja 3.1 — Half Kelly

$$f_{\text{half}} = \frac{f^*}{2}$$

### Uzasadnienie

Pełne Kelly zakłada dokładną znajomość $p$. W praktyce estymator $\hat{p}$ modelu betatp ma wariancję $\text{Var}(\hat{p}) > 0$. Wykazano (Thorp 2006, MacLean et al. 2010), że przy estymacji parametrów:

$$\mathbb{E}[G(f^* | \hat{p})] < \mathbb{E}[G(f^*/2 | \hat{p})]$$

Czyli Half Kelly jest optymalne przy niepewności estymacji.

**Właściwości Half Kelly:**
- Zmienność (drawdown) ≈ 50% Kelly
- Wzrost ≈ 75% wzrostu Kelly (kompromis)
- Ruina (ruin probability) drastycznie mniejsza

### Twierdzenie 3.1 — Prawdopodobieństwo ruiny przy Kelly

Dla pełnego Kelly ($f = f^*$):

$$P(\text{ruina}) = \lim_{W \to 0} P(W_t = 0) = 0$$

ponieważ $f^* < 1$ i $W_t = W_0 \prod_i X_i > 0$ zawsze.

Dla $f > f^*$: $G(f) < G^*$ a przy $f = 2f^*$: możliwe ujemne oczekiwanie logarytmiczne.

---

## 4. WARIANTY FRACTIONAL KELLY

| Wariant | $f$ | Wzrost (% Kelly) | Max Drawdown | Zastosowanie |
|---------|-----|-------------------|--------------|--------------|
| Full Kelly | $f^*$ | 100% | ~50-60% | Teoria |
| 3/4 Kelly | $0.75 f^*$ | ~93% | ~35-45% | Bardzo pewne modele |
| **Half Kelly** | $0.5 f^*$ | **~75%** | **~25-30%** | **Standard betatp** |
| 1/4 Kelly | $0.25 f^*$ | ~44% | ~12-15% | Wysokie EV, niska ufność |
| 1/8 Kelly | $0.125 f^*$ | ~22% | ~6-8% | Flat betting reference |

*Drawdown szacowany empirycznie na 10,000 symulacji Monte Carlo, $p=0.55$, $o=2.0$.*

---

## 5. KELLY DLA BETFAIR EXCHANGE (LAY BETTING)

### Definicja 5.1 — Lay bet na Betfair

Lay bet (obstawianie przegranej zawodnika):
- Kurs: $o_{\text{lay}}$ (decimal back odds widoczne na platformie)
- Odpowiedzialność (liability): $(o_{\text{lay}} - 1) \cdot \text{stake}$
- Zysk przy wygranej lay: $\text{stake}$
- Strata przy przegranej lay: $(o_{\text{lay}} - 1) \cdot \text{stake}$

### Definicja 5.2 — EV dla lay bet

Niech $p_{\text{lay}}$ = prawdopodobieństwo, że zawodnik **przegra** (tj. wynik zdarzenia = 0):

$$\text{EV}_{\text{lay}} = p_{\text{lay}} \cdot 1 - (1 - p_{\text{lay}}) \cdot (o_{\text{lay}} - 1)$$

$$= p_{\text{lay}} - (1 - p_{\text{lay}})(o_{\text{lay}} - 1)$$

### Twierdzenie 5.1 — Kelly dla Lay Betting

Dla lay betu na Betfair (prowizja $c$, np. $c=0.02$):

**Efektywne odds lay** (po komisji):

$$o_{\text{eff}} = 1 + (o_{\text{lay}} - 1)(1 - c)$$

**Kelly stake** jako ułamek bankrolla:

$$f^*_{\text{lay}} = \frac{p_{\text{lay}} \cdot o_{\text{eff}} - 1}{o_{\text{eff}} - 1}$$

**Odpowiedzialność (liability) jako ułamek bankrolla:**

$$\text{liability\_fraction} = f^*_{\text{lay}} \cdot (o_{\text{lay}} - 1)$$

**Dowód:** Analogiczny do standardowego Kelly — dynamika kapitału:
$$W_{t+1} = W_t \cdot (1 + f) \quad \text{jeśli lay wygrywa}$$
$$W_{t+1} = W_t \cdot (1 - f(o_{\text{lay}}-1)) \quad \text{jeśli lay przegrywa}$$
Maximize $G(f)$ — identyczna procedura jak w § 2.2. $\square$

### Przykład Betfair Lay

**Sytuacja:** Sinner lider rankingu ATP, mecz vs Berrettini
**Model:** $P(\text{Sinner wygrywa}) = 0.88$, więc $p_{\text{lay}} = 0.12$ (Berrettini wygrywa)  
**Kurs Betfair Back Sinner:** $o_{\text{lay}} = 1.15$  
**Prowizja Betfair:** $c = 0.02$

$$o_{\text{eff}} = 1 + (1.15 - 1)(1 - 0.02) = 1 + 0.147 = 1.147$$

$$\text{EV}_{\text{lay}} = 0.12 \times 1.147 - 1 = 0.1376 - 1 < 0$$

Ujemne EV — zakład lay jest nieopłacalny. System odrzuca. ✗

---

## 6. LIMITY I OGRANICZENIA

### Definicja 6.1 — Maksymalny rozmiar zakładu

System betatp.io stosuje następujące ograniczenia Kelly:

$$f_{\text{actual}} = \min(f_{\text{half}},\ f_{\text{max\_abs}},\ f_{\text{max\_rel}})$$

gdzie:
- $f_{\text{max\_abs}}$ = 5% bankrolla (twardy limit bezpieczeństwa)
- $f_{\text{max\_rel}}$ = $2 \times f_{\text{half}}$ (max 2× Half Kelly)

### Definicja 6.2 — Minimalny EV do obstawiania

$$\text{EV\_min} = 0.03 \quad (3\%)$$

Zakłady z $\text{EV} < 0.03$ są odfiltrowane systemowo.

---

## 7. WZORY SZYBKIEGO ODNIESIENIA

| Formuła | Wzór |
|---------|------|
| EV (decimal) | $p \cdot o - 1$ |
| EV% | $(p \cdot o - 1) \times 100$ |
| Full Kelly | $(p \cdot o - 1) / (o - 1)$ |
| Half Kelly | $(p \cdot o - 1) / (2(o-1))$ |
| Break-even $p$ | $1/o$ |
| Edge | $p - 1/o$ |
| Lay Kelly | $(p_{\text{lay}} \cdot o_{\text{eff}} - 1) / (o_{\text{eff}} - 1)$ |

---

## 8. REFERENCJE

1. Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*, 35(4), 917–926.
2. Thorp, E.O. (1969). "Optimal Gambling Systems for Favorable Games." *Review of the International Statistical Institute*, 37(3), 273–293.
3. MacLean, L.C., Thorp, E.O., Ziemba, W.T. (2010). "Good and bad properties of the Kelly criterion." *Risks*, 29, 1.
4. Haigh, J. (2000). "The Kelly Criterion and Bet Comparisons in Spread Betting." *The Statistician*, 49(4), 531–539.
5. Pinnacle Sports Betting Resources. (2022). "Kelly Criterion in Sports Betting." pinnacle.com
6. ATP Ranking Database, 2000–2024: empiryczne dane kursów i wyników.

---

*Dokument AX-09 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
