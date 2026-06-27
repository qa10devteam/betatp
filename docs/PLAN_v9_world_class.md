# betatp.io — PLAN v9.0 World-Class Rebuild
> Data: 2026-06-26 | Iteracje: 1200

---

## Design Read
**"Consumer dark AI SaaS dla mas — produkt pokazuje DANE, nie swoje imię. Equity curve jako hero. Typografia Geist Display. 1 akcent."**

- Page kind: Consumer AI betting SaaS — mobile-first app shell
- Audience: Polski user betting, 25-40, chce zarobić na tenisie
- Vibe: Stratagem × Pinnacle × Vercel — data-first premium dark
- Anti-defaults: NIE logo hero, NIE wartości bez sparkline, NIE casino energy

---

## Audit v8.0 — Top 5 problemów

| # | Problem | Impact | Fix |
|---|---------|--------|-----|
| 1 | H1 "betatp" = 40%vh — logo, nie produkt | -2.0pkt | Wordmark 60px, hero = EQUITY CURVE |
| 2 | Stats cards martwe — brak sparklines, trendu, kontekstu | -1.5pkt | Canvas mini-chart w każdej karcie |
| 3 | Typografia niespójna — 4 style jednocześnie | -0.8pkt | Jeden type scale: Geist Display |
| 4 | Brak equity curve jako product hero visual | -1.5pkt | Canvas animowana linia ROI +58.7% |
| 5 | Brak trust signals — nie wiadomo czy live | -0.5pkt | LIVE badge + verified data strip |

---

## Design System v9.0

### Tokens
```
Bg:      #030306  --s0: #050509  --s1: #09090f  --s2: #0e0e18  --s3: #141422
Borders: --bd1: rgba(255,255,255,.055)  --bd2: rgba(255,255,255,.1)
         --bd3: rgba(255,255,255,.18)
Text:    --t1: #f5f5ff  --t2: rgba(245,245,255,.52)  --t3: rgba(245,245,255,.2)
LIME:    #c2ff3d  (JEDEN akcent — wszędzie)
Mono:    JetBrains Mono
Display: Cabinet Grotesk 900
```

### Type Scale (jeden system)
```
Display: 88px/900/-.07em  — tylko H1 hero wordmark
H2:      42px/900/-.04em  — hero claim (FOCUS)
H3:      24px/800/-.02em  — section heads
Body:    14px/400/.01em   — paragraphs
Label:   10px/700/.14em MONO uppercase — eyebrows, stats labels
Mono:    12-16px/500/0    — numbers, data
```

---

## Nowy hero layout (ASCII wireframe)

```
┌────────────────────────────────┐
│  ● betatp  [v14]    WIMBLEDON  │  ← navbar 56px
├────────────────────────────────┤
│                                │
│  MODEL V14 · WIMBLEDON 2026    │  ← eyebrow 10px
│                                │
│  Algorytm, który widzi         │  ← H2 42px BOLD — FOCAL POINT
│  więcej niż rynek.             │    (NIE LOGO)
│                                │
│  ┌──────────────────────────┐  │
│  │  EQUITY CURVE CANVAS     │  │  ← AnimCanvas 180px — produkt hero
│  │  ▁▂▃▄▅▆▇█ +58.7%        │  │
│  │                          │  │
│  └──────────────────────────┘  │
│                                │
│  [+58.7%↑] [59.6%↑] [57 bets] │  ← stat pills z mini-sparkline
│                                │
│  [⚡ Dziś 3 typy]  [System]    │  ← CTA row
│                                │
├────────────────────────────────┤
│  · Ticker · social proof ·     │
└────────────────────────────────┘
```

---

## Podział zadań dla agentów

### AGENT A — Hero Section (hero_fragment.html)
**Plik wyjściowy:** `/home/ubuntu/betatp/fragments/hero_fragment.html`
**Zawiera:**
1. Nowy hero CSS (wszystkie zmienne token + type scale + hero styles)
2. Nowy hero HTML:
   - Navbar (logo pill 56px, live badge)
   - Eyebrow "MODEL V14 · WIMBLEDON 2026"  
   - H2 claim "Algorytm, który widzi więcej niż rynek." — FOCAL POINT (nie H1 logo)
   - Wordmark "betatp" MAŁY pod H2 (56px, opacity .28) — decoration not hero
   - Equity Curve Canvas (animowana, drawn on load, +58.7% w prawym rogu)
   - 3 stat pills z mini canvas sparkline (inline canvas 60x24px)
   - CTA row: primary + ghost
   - Market chips
3. Equity curve JS (animowana linia z Canvas 2D, draw path w 1.2s)
4. Sparkline JS (mini charts 60x24px per stat pill)

### AGENT B — Nav Cards + Stats (cards_fragment.html)
**Plik wyjściowy:** `/home/ubuntu/betatp/fragments/cards_fragment.html`
**Zawiera:**
1. Nav cards redesign — nowy styl:
   - Asymetryczny layout (nie dwie równe karty)
   - Duża karta "Daily Kupon" (2/3 szerokości) + mała "System" (1/3)
   - Glassmorphism border-gradient
   - Equity curve mini preview na karcie Daily Kupon
   - LIVE badge na Daily Kupon
2. Trust strip sekcja (pod kartami):
   - "Dane z ATP Official · The Odds API · Pinacle consensus"
   - 3 logo pillsy (ATP, Pinnacle, Oddschecker)
3. Ticker redesign — większy font (11px), lepszy kontrast

### AGENT C — Pick Cards + Overlay Polish (picks_fragment.html)
**Plik wyjściowy:** `/home/ubuntu/betatp/fragments/picks_fragment.html`
**Zawiera:**
1. Pick card redesign v2:
   - Prob bars z animowanymi fill (2 kolumny: Model P vs Market P side-by-side)
   - Edge indicator — visual "delta" arrow chart
   - Cleaner reasoning section
   - ROI/Kelly w single hero stat w karcie
2. Overlay ceremony:
   - Phase 1 scan — terminal-style monospace output
   - Phase 4 slot — cleaner reel (mniejsze padding, lepszy focus)
   - Phase 5 → flip — nowy flip card (pokazuje equity curve mini)
3. Coupon summary — equity curve jako tło

---

## Instrukcje dla agentów

Każdy agent:
1. Czyta SPEC z tego pliku
2. Czyta aktualny `/home/ubuntu/betatp/frontend/index.html` (żeby zrozumieć istniejący kod)
3. Buduje swój fragment jako STANDALONE HTML z komentarzem `<!-- FRAGMENT: HERO/CARDS/PICKS -->`
4. Zapisuje do `/home/ubuntu/betatp/fragments/<name>_fragment.html`
5. Fragment zawiera TYLKO swój zakres: CSS w `<style>` tagu + HTML w body div + JS w `<script>` tagu
6. Nie duplikuje zmiennych tokena — używa `var(--lime)` etc. (tokeny są w głównym pliku)
7. Zwraca opis co zbudował + klucze CSS klasy które eksportuje

---

## Stack constraints (vanilla HTML/JS, NIE React)
- GSAP (już załadowany z CDN w main file)
- Web Audio API (vanilla)
- Canvas 2D (vanilla)
- CSS variables dla tokenów
- JetBrains Mono + Cabinet Grotesk (już załadowane)
- BRAK Three.js (za ciężki)
- BRAK WebGL (hero = Canvas 2D wystarczy)

---

## Merge plan (po agentach)
1. Czytam hero_fragment.html → wyciągam CSS do `<style>`, HTML do `.hero-*` sekcji, JS do końca
2. Czytam cards_fragment.html → wyciągam do sekcji nav-cards i trust strip
3. Czytam picks_fragment.html → wyciągam do pick cards CSS + JS
4. Builduje kompletny nowy index.html jako replace całego pliku
5. Test lokalny na http.server
6. Vision audit (5 screenshotów)
7. Git commit + push + GitHub Pages deploy
