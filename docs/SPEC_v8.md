# betatp.io — SPEC v8.0
> "Doświadczenie AI które zmieni bieg historii projektów AI"
> Data: 2026-06-26 | Autor: Hermes Web Architect

---

## Design Read
**"Premium dark consumer AI — opowieść algorytmu dla mas. Jeden accent, czysty spacing, cinematic motion."**
- Page kind: Consumer AI SaaS landing / mobile-first app shell
- Audience: Masowy user, betting enthusiast, niekoniecznie techniczny
- Vibe: Dark tech premium — Vercel/Linear darkness + DraftKings energy + Bloomberg precision
- Anti-pattern: NIE jest to casino site. To jest NAUKOWE narzędzie.

---

## Dials
- DESIGN_VARIANCE: 8 (asymetria, nie chaos)
- MOTION_INTENSITY: 9 (cinematic, motywowane)
- VISUAL_DENSITY: 5 (dane czytelne, nie cockpit)

---

## Problemy audytu (do naprawienia)

| # | Problem | Priorytet |
|---|---------|-----------|
| 1 | Logo 40vh — dominuje stronę | 🔴 KRYTYCZNY |
| 2 | 5+ kolorów akcentów jednocześnie | 🔴 KRYTYCZNY |
| 3 | Tło-szum: sylwetka + panele + gradient + watermark | 🔴 KRYTYCZNY |
| 4 | Watermark "VALUE BET" — tanie casino feel | 🔴 KRYTYCZNY |
| 5 | Brak focal point / hierarchii wizualnej | 🔴 KRYTYCZNY |
| 6 | Panele po prawej ucięte przez ekran | 🔴 KRYTYCZNY |
| 7 | Brak wyraźnego CTA na hero | 🔴 KRYTYCZNY |
| 8 | Statystyki stat-pills bez spójnego systemu | 🟡 WAŻNY |
| 9 | Ticker za mały tekst, za mały kontrast | 🟡 WAŻNY |
| 10 | Karty holograficzne wyglądają tanio | 🟡 WAŻNY |
| 11 | Overlay 5-fazowy OK koncepcyjnie, ale flow przerywany | 🟡 WAŻNY |
| 12 | Copy "Bukmacher się myli" — zbyt agresywne | 🟢 DROBNY |

---

## Design System v8.0

### Paleta — 1 accent, czyste neutraly
```
Akcent:     --lime: #c2ff3d (JEDEN, konsekwentny wszędzie)
Tło:        --bg: #020208   --s0: #06060f   --s1: #0a0a1a
Surface:    --s2: #10101f   --s3: #171728   --s4: #1f1f35
Bordery:    --bd0: rgba(255,255,255,.03)
            --bd1: rgba(255,255,255,.07)
            --bd2: rgba(255,255,255,.12)
Tekst:      --t1: #f0f0ff   --t2: rgba(240,240,255,.55)
            --t3: rgba(240,240,255,.22)
TYLKO akcent sekundarny (sparingly):
            --gold: #ffd700  (tylko dla jackpot tier)
            --cyan: #00f2e8  (tylko dla confirmations)
USUWAMY:    violet, pink, blue, red, orange jako akcenty UI
            (pozostają tylko w CS2 rarity system)
```

### Typografia — jeden system
```
Display: Cabinet Grotesk 900 — hero headline
Body:    Cabinet Grotesk 400/700 — copy, labels
Mono:    JetBrains Mono — liczby, kody, ticker
NIE używamy: 3+ rozmiarów fontu w jednej sekcji
```

### Spacing — 8px grid
```
4, 8, 12, 16, 24, 32, 48, 64, 96 px
Padding sekcji: min 16px horizontal
```

---

## Architektura ekranów

### Screen 0 — HOME (przeprojektowany)

**Hero layout (nowy):**
```
┌─────────────────────────────────────┐
│  [logo-pill]          [live-dot]    │  ← 48px top
├─────────────────────────────────────┤
│                                     │
│   [algo-eyebrow]                    │  ← "MODEL V14 · WIMBLEDON 2026"
│                                     │
│   BETATP                            │  ← H1: 80-96px, left-aligned
│                                     │
│   Algorytm, który widzi więcej      │  ← subtitle: 18px
│   niż rynek.                        │
│                                     │
│   [+58.7%] [59.6%] [57 picks]       │  ← stat row: 3 clean pills
│                                     │
│   [→ DAILY KUPON]  [SYSTEM]         │  ← CTA row: primary + ghost
│                                     │
├─────────────────────────────────────┤
│  [ticker — social proof]            │  ← zawsze widoczny
└─────────────────────────────────────┘
```

**Tło (czysty WebGL):**
- Aurora GLSL shader — subtelny, 10-15% opacity (nie zdominowuje)
- Three.js neural — opacity 15%, za contentem, nie przed
- BRAK zdjęcia tenisisty (zbyt wiele warstw = szum)
- BRAK watermark VALUE BET
- BRAK floating panel-cards po prawej

**Karty nawigacyjne (nowy styl):**
- Full-width stack (nie side-by-side na mobile)
- Czysty border z lime accent
- Prawdziwy AI asset z fal.media jako hero image
- Stat badge na karcie: `ROI +58.7%` / `Kelly live`

---

### Screen 1 — DAILY KUPON

**Nav bar:**
- Mniejszy, czystszy
- Back arrow + tytuł + live dot + badge

**Pick cards (uproszczone):**
- Usuwamy: zbędne warstwy rarity glow
- Zostawiamy: prob bars, reasoning, odds, kelly
- Dodajemy: jednolita sekcja "Dlaczego model tak twierdzi"

---

### Screen 2 — OVERLAY (5 faz)

**Faza 1 — Scan:** Czysty progress z 4 barami (OK)
**Faza 2 — Found:** Count up z burst (OK)
**Faza 3 — Suspense:** 3-2-1 countdown (OK — ale bez tęczy)
**Faza 4 — Slot:** CS2 reel (OK — serce UX)
**Faza 5 → Hero:** Flip cards do cards-area

---

## Motion Plan

### Intro (3.2s)
```
0.0s: Logo fade in (cubic-bezier back.out 1.5)
0.7s: Subtext slide up
1.0s: Neural bars pulse
1.4s: Msg opacity
2.6s: Fade out → hero enter
```

### Hero Enter (2.0s stagger)
```
0.0s: eyebrow slide up + fade
0.2s: H1 scale 0.95→1.0 + fade
0.5s: subtitle
0.7s: stat pills stagger 0.08s each
0.9s: market chips stagger 0.04s
1.1s: CTA pulse in
1.3s: Cards slide up (nie z boku)
```

### Sound
```
Ambient: Dm maj7 (D+F+A+C) z LFO vibrato → fade in 5s
Intro: silence (żadnych dźwięków podczas intro)
Pick: spatial audio (pan L→C→R dla 3 kart)
Slot: zachowane (CS2 sound design)
```

---

## To-Do List (iteracje)

- [ ] **IT-1** Przepisać hero HTML — nowa hierarchia, brak VALUE BET
- [ ] **IT-2** Czysty paleta CSS — usunąć stare zmienne, zostać przy 1 akcencie
- [ ] **IT-3** Hero background — tylko GLSL aurora, brak zdjęcia
- [ ] **IT-4** Stat pills — nowy design, spójny grid
- [ ] **IT-5** CTA cards — nowy styl, full-width friendly
- [ ] **IT-6** Ticker — większy tekst, czystsza kontrast
- [ ] **IT-7** Overlay scan — dodać neural scan line
- [ ] **IT-8** Pick cards — glassmorphism clean
- [ ] **IT-9** Intro JS — hero enter z nowym timingiem
- [ ] **IT-10** Three.js — zmniejszyć opacity, nie dominuje
