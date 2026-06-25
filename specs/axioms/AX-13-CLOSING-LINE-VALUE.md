# AX-13: CLOSING LINE VALUE (CLV) — SPECYFIKACJA FORMALNA

**Dokument:** AX-13  
**Wersja:** 1.0.0  
**System:** betatp.io — silnik predykcji tenisowej  
**Status:** OBOWIĄZUJĄCY  
**Data:** 2025-06

---

## 1. DEFINICJA I UZASADNIENIE

### Definicja 1.1 — Closing Line Value (CLV)

Niech:
- $o_{\text{bet}}$ — kurs, po którym złożono zakład (opening/mid odds)
- $o_{\text{close}}$ — kurs zamknięcia rynku (Pinnacle Sports, ostatnie kursy przed meczem)

**Closing Line Value** (kursowy):

$$\text{CLV} = \frac{o_{\text{bet}}}{o_{\text{close}}} - 1$$

**CLV procentowy:**

$$\text{CLV\%} = \left(\frac{o_{\text{bet}}}{o_{\text{close}}} - 1\right) \times 100$$

### Definicja 1.2 — CLV w przestrzeni prawdopodobieństw

Po de-viggingu (metodą Power, AX-08):

$$p_{\text{bet}} = \text{devig}(o_{\text{bet}})$$
$$p_{\text{close}} = \text{devig}(o_{\text{close}})$$

$$\text{CLV}_p = p_{\text{close}} - p_{\text{bet}}$$

Interpretacja: $\text{CLV}_p > 0$ oznacza, że rynek zamknął się wyżej niż cena zakładu (kurs był lepszy niż closing).

### Relacja między CLV kursowym a probabilistycznym

$$\text{CLV} = \frac{o_{\text{bet}}}{o_{\text{close}}} - 1 \approx \frac{p_{\text{close}} - p_{\text{bet}}}{p_{\text{bet}}} \cdot (1 - \text{vig})$$

dla małych różnic i przy założeniu liniowej relacji kurs–prawdopodobieństwo.

---

## 2. HIPOTEZA EFEKTYWNOŚCI RYNKU — UZASADNIENIE CLV

### Hipoteza 2.1 — Semi-Strong Efficiency (Pinnacle)

Pinnacle Sports działa według modelu **semi-strong form market efficiency**: jego closing odds wbudowują całą publicznie dostępną informację. Empirycznie potwierdzone badaniami Kuypersa (2000) i Foresta (2008).

**Formalna implikacja:**

Niech $\mathbb{P}^*$ = "prawdziwe" prawdopodobieństwo (unknowable). Niech $p_{\text{close}}$ = implied probability Pinnacle po de-viggingu.

$$\mathbb{E}[p_{\text{close}} - \mathbb{P}^* | \mathcal{F}_{\text{close}}] \approx 0$$

gdzie $\mathcal{F}_{\text{close}}$ = sigma-algebra informacji dostępnej przy zamknięciu.

### Twierdzenie 2.1 — Pozytywne CLV implikuje długoterminową opłacalność

**Twierdzenie:** Jeśli gracz konsekwentnie osiąga $\mathbb{E}[\text{CLV}] = c > 0$ na $N$ zakładach, to jego długoterminowy ROI (zwrot z inwestycji) zbliża się do $c$ przy $N \to \infty$.

**Dowód:**

Niech $b_k$ = zakład k, $o_k^{\text{bet}}$ = obstawiony kurs, $o_k^{\text{close}}$ = closing kurs.

Z hipotezy efektywności rynku:

$$\mathbb{E}\left[\frac{y_k \cdot o_k^{\text{bet}} - 1}{1}\right] = \mathbb{E}\left[(y_k \cdot o_k^{\text{bet}} - 1)\right]$$

Rozpisując przez ceny zamknięcia:

$$\mathbb{E}[y_k \cdot o_k^{\text{bet}} - 1] = \mathbb{E}\left[\frac{o_k^{\text{bet}}}{o_k^{\text{close}}} \cdot (y_k \cdot o_k^{\text{close}} - 1) + \left(\frac{o_k^{\text{bet}}}{o_k^{\text{close}}} - 1\right)\right]$$

Ponieważ $\mathbb{E}[y_k \cdot o_k^{\text{close}} - 1 | p_{\text{close}}] = p_{\text{close}} \cdot o_{\text{close}} - 1 \approx 0$ (Pinnacle ~1% marża):

$$\mathbb{E}[\text{profit}_k] \approx \mathbb{E}\left[\frac{o_k^{\text{bet}}}{o_k^{\text{close}}} - 1\right] = \mathbb{E}[\text{CLV}_k]$$

Z prawa wielkich liczb:

$$\frac{1}{N} \sum_{k=1}^{N} \text{profit}_k \xrightarrow{N \to \infty} \mathbb{E}[\text{CLV}] = c > 0$$

$$\text{ROI} \xrightarrow{N \to \infty} c > 0 \quad \square$$

### Wniosek 2.1 — CLV jako miara przyszłości

CLV jest **wiodącym wskaźnikiem** (leading indicator) rentowności. ROI jest wskaźnikiem **opóźnionym** (lagging) — wymaga tysięcy zakładów do oceny. CLV daje sygnał na bieżąco.

---

## 3. PROTOKÓŁ ŚLEDZENIA CLV

### Definicja 3.1 — Rekord zakładu

Każdy zakład jest rejestrowany jako krotek:

$$b = (b_{\text{id}},\ \text{player},\ t_{\text{bet}},\ o_{\text{bet}},\ t_{\text{close}},\ o_{\text{close}},\ y,\ \text{stake},\ \text{source})$$

| Pole | Typ | Opis |
|------|-----|------|
| $b_{\text{id}}$ | UUID | Unikalny identyfikator zakładu |
| player | string | ID zawodnika (ATP format) |
| $t_{\text{bet}}$ | timestamp | Czas złożenia zakładu |
| $o_{\text{bet}}$ | float | Kurs w momencie zakładu |
| $t_{\text{close}}$ | timestamp | Czas zamknięcia rynku |
| $o_{\text{close}}$ | float | Kurs zamknięcia Pinnacle |
| $y$ | {0,1} | Wynik (1 = wygrana) |
| stake | float | Kwota zakładu |
| source | enum | {pinnacle, bet365, betfair, ...} |

### Definicja 3.2 — Protokół zbierania closing odds

1. **Źródło:** wyłącznie **Pinnacle Sports** — jedyny rynek uznany za efficient
2. **Czas snapshotu:** ostatnie kursy ≤ 5 minut przed meczem
3. **Fallback:** jeśli Pinnacle brak, użyj Betfair Exchange closing (z uwagą w logu)
4. **De-vigging:** obligatoryjny Power method (AX-08) na closing odds

### Definicja 3.3 — Rolling Mean CLV

$$\overline{\text{CLV}}_N = \frac{1}{N} \sum_{k=1}^{N} \text{CLV}_k$$

**Rolling window** (ruchoma, ostatnie $W$ zakładów):

$$\overline{\text{CLV}}_W(t) = \frac{1}{W} \sum_{k=t-W+1}^{t} \text{CLV}_k$$

Standardowe okno: $W = 100$ zakładów.

---

## 4. ANALIZA STATYSTYCZNA CLV

### Definicja 4.1 — Test istotności CLV

Niech $\mu_{\text{CLV}} = \mathbb{E}[\text{CLV}]$ i $\sigma_{\text{CLV}} = \text{Std}(\text{CLV})$.

**Test hipotezy H₀:** $\mu_{\text{CLV}} = 0$ (brak edge)

Statystyka $t$:

$$t = \frac{\overline{\text{CLV}}_N}{\sigma_{\text{CLV}} / \sqrt{N}}$$

Przy $N \geq 100$: rozkład $t(N-1) \approx \mathcal{N}(0,1)$.

**Próg istotności:** $p < 0.05$, tj. $|t| > 1.96$.

### Definicja 4.2 — Minimalny wymagany $N$ dla testu

Dla wykrycia $\mu_{\text{CLV}} = 0.02$ (2%) przy $\sigma_{\text{CLV}} \approx 0.15$ (typowe ATP), $\alpha=0.05$, $\beta=0.20$:

$$N_{\min} = \left(\frac{(z_\alpha + z_\beta) \cdot \sigma}{\mu}\right)^2 = \left(\frac{(1.96 + 0.84) \cdot 0.15}{0.02}\right)^2 \approx 441$$

Wniosek: minimum **441 zakładów** do statystycznie istotnej oceny CLV.

### Tabela interpretacji CLV

| $\overline{\text{CLV}}_N$ | Interpretacja | Działanie |
|---------------------------|---------------|-----------|
| < -2% | Negatywny edge | Przegląd modelu — KRYTYCZNE |
| [-2%, 0%) | Marginalnie ujemny | Monitoruj, rewizja cech |
| [0%, 1%) | Neutralny | Obserwuj rolling window |
| [1%, 2%) | Słaby pozytywny | Akceptowalny, kontynuuj |
| [2%, 4%) | Dobry pozytywny | ✓ Optymalny zakres |
| > 4% | Silny pozytywny | Sprawdź limitowanie przez bukmachera |

---

## 5. DEKOMPOZYCJA CLV

### Definicja 5.1 — Komponenty CLV

$$\text{CLV}_{\text{total}} = \text{CLV}_{\text{model}} + \text{CLV}_{\text{timing}} + \text{CLV}_{\text{line}} + \varepsilon$$

gdzie:
- $\text{CLV}_{\text{model}}$: edge wynikający z lepszego modelu prawdopodobieństwa
- $\text{CLV}_{\text{timing}}$: edge wynikający z wczesnego zakładu (przed ruchem rynku)
- $\text{CLV}_{\text{line}}$: edge wynikający z wyboru bukmachera (najlepszy kurs)
- $\varepsilon$: szum stochastyczny

### Metoda rozdzielenia

Porównaj $\text{CLV}$ z:
- **Opening CLV:** $o_{\text{bet}} / o_{\text{open}} - 1$ (wyłącznie timing)
- **Model CLV:** $p_{\text{close}} / p_{\text{model}} - 1$ (wyłącznie model)

---

## 6. ALERTY I MONITORING

### Definicja 6.1 — Warunki alertów CLV

| Alert | Warunek | Akcja |
|-------|---------|-------|
| CLV_DROP | $\overline{\text{CLV}}_{50}$ spada poniżej 0 przez 2 tygodnie | Rewizja modelu |
| CLV_SPIKE | $\overline{\text{CLV}}_{10} > 8\%$ | Sprawdź limitowanie konta |
| SAMPLE_LOW | $N < 50$ (rolling) | Nie reportuj CLV — zbyt mała próba |
| CLOSE_MISSING | $o_{\text{close}} = \text{NaN}$ dla > 5% zakładów | Alert data pipeline |

---

## 7. WORKED EXAMPLE — ATP 2024

### Przykład śledzenia CLV

**Zakład 1:** Sinner vs Medvedev, Miami Open 2024
- $t_{\text{bet}}$: 3 dni przed meczem, $o_{\text{bet}} = 1.95$
- $t_{\text{close}}$: dzień meczu, $o_{\text{close}} = 1.78$
- $\text{CLV} = 1.95/1.78 - 1 = +9.55\%$
- Wynik $y = 1$ (Sinner wygrał), profit = +0.95j

**Zakład 2:** Rublev vs Tsitsipas, Monte Carlo 2024
- $o_{\text{bet}} = 2.15$, $o_{\text{close}} = 2.20$
- $\text{CLV} = 2.15/2.20 - 1 = -2.27\%$
- Wynik $y = 0$ (Rublev przegrał), profit = -1j

**Rolling mean CLV po 2 zakładach:**

$$\overline{\text{CLV}}_2 = \frac{9.55\% + (-2.27\%)}{2} = +3.64\%$$

---

## 8. REFERENCJE

1. Kuypers, T. (2000). "Information and efficiency: An empirical study of a fixed odds betting market." *Applied Economics*, 32(11), 1353–1363.
2. Pinnacle Sports (2022). "How to beat the closing line." pinnacle.com/en/betting-articles/
3. Buchdahl, J. (2016). *Squares & Sharps, Suckers & Sharks.* High Stakes Publishing.
4. Levitt, S.D. (2004). "Why are gambling markets organised so differently from financial markets?" *Economic Journal*, 114(495), 223–246.
5. Foresta, D. (2008). "Market efficiency in fixed-odds betting markets." *Journal of Sports Economics*, 9(4).
6. ATP Pinnacle Historical Odds Database, Oddsportal.com, 2005–2024.

---

*Dokument AX-13 | betatp.io | Wersja 1.0.0 | © 2025 betatp.io — Wszelkie prawa zastrzeżone*
