# betatp.io — KONTYNUACJA SESJA 3
> **Wczytaj ten plik w nowym wątku:**
> `przeczytaj /home/ubuntu/betatp/KONTYNUACJA_2026-06-26_sesja3.md i kontynuuj`

---

## 🔑 Podstawy projektu

| | |
|---|---|
| **Repo** | `https://github.com/qa10devteam/betatp` (private) |
| **Lokalizacja** | `/home/ubuntu/betatp/` |
| **Live URL** | `https://qa10devteam.github.io/betatp/` |
| **PostgreSQL** | `host=localhost dbname=betatp user=postgres password=betatp2024` |
| **Python** | `3.11` — bez venv, używaj `python3` bezpośrednio |
| **Last commit** | `e876a04 deploy: vercel config — frontend/index.html as root` |

---

## 🏆 Model ML — CHAMPION

| Wersja | Holdout AUC | WF AUC | Plik |
|---|---|---|---|
| **v22** ✅ CHAMPION | **0.9171** | **0.9422** | `models/lgbm_v22_20260626_1738.joblib` |
| v14 backup | 0.9031 | 0.9482 | `models/lgbm_v14_20260626_1706.joblib` |

**⚠️ LEAKAGE GUARD:** Używaj TYLKO modeli z `trained_at >= 20260626_1631`.
Wcześniejsze wersje (v5–v13 stary run) = leakage w `h2h_surf_winrate`. Wykluczone.

---

## 🎯 MISJA SESJI 3

**"Stworzyć najbardziej innowacyjne doświadczenie betowania w historii"**

Realizujesz **140 iteracji** w 5 fazach wg metodyki NEXUS Sprint.
Plik jakości kodu: `/home/ubuntu/betatp/.codequality.yml` — obowiązuje wszystkich agentów.
Agenci: `/home/ubuntu/agency-agents/` (237 agentów, 16 dywizji)

---

## 📋 SPEC-OFF 140 ITERACJI

### FAZA A — Assets + Mobile Polish (iter 1–35)
**Agenci:** Frontend Developer + UI Designer (równolegle)

```
Iter 1–7:    Wygeneruj 27 pozostałych assetów AI
             → image_generate() × 27, zapisz URL FAL do index.html
             Kategorie: player_silhouette ×6, court_texture ×4,
             rarity_frame ×4, market_icon ×5, gradient_orb ×4,
             trophy_3d ×2, probability_bg ×2

Iter 8–12:   Embed assetów do HTML
             → podmień src w kartach na FAL URLs
             → każdy asset: lazy loading, explicit width/height

Iter 13–18:  Mobile responsive pass
             → @media (max-width: 480px) dla .deck, .hcard, .slot-wrap
             → touch targets min 44px (Apple HIG)
             → .dbody, .stray: overflow-y: auto z momentum scroll
             → env(safe-area-inset-*) dla iOS notch

Iter 19–24:  Micro-interactions + hover states
             → .mrb hover: scale(1.03) + border-color flash 160ms
             → .pcard hover: subtle translateY(-2px) 200ms ease-out
             → .mktab active: ripple effect 300ms
             → All buttons: :active scale(.96) snap feedback

Iter 25–28:  @media (prefers-reduced-motion: reduce)
             → wszystkie animacje → opacity fade only
             → GLSL shader → static gradient fallback
             → slot machine → instant reveal

Iter 29–35:  Performance pass
             → GLSL canvas: IntersectionObserver → pause gdy hidden
             → GSAP: killTweensOf() przed re-triggerem ceremonii
             → canvas particles: pool zamiast new Array każdy frame
             → AudioContext: suspend() gdy document.hidden
```

**Definition of Done Faza A:**
- [ ] 35/35 assetów osadzonych w HTML
- [ ] Mobile: deck pionowy, slot machine 1-kolumnowy, tap działa
- [ ] 0 console errors na mobile Chrome + Safari
- [ ] `@media (prefers-reduced-motion)` redukuje animacje
- [ ] FCP < 2s na throttled 3G

---

### FAZA B — AI Storytelling / SHAP (iter 36–70)
**Agenci:** AI Engineer + Frontend Developer (równolegle)

```
Iter 36–40:  api/routes/explanations.py
             → endpoint GET /predictions/{pick_id}/explanation
             → response: {top_features: [{name, importance_pct, direction}×5],
                           model_p, market_p, edge_pct,
                           reasoning: [str×3-5], confidence, kelly}
             → LightGBM feature_importance(type='gain') normalizowany do %
             → cache TTL=3600s

Iter 41–46:  SHAP bars na kartach (frontend)
             → 5 poziomych pasków per pick — animowane po flip reveal
             → gsap.to(bar, {width: pct+'%', duration:.95, stagger:.08})
             → kolor: lime (pozytywny) / red (negatywny) wg direction
             → tooltip on hover: pełna nazwa feature

Iter 47–52:  "Jak model doszedł do tej predykcji" journey
             → expand/collapse sekcja "Szczegóły AI" per karta
             → 3 kroki: Dane historyczne → Elo + features → Decyzja modelu
             → progress dots z GSAP morphing

Iter 53–58:  Historical stats embed per pick
             → surface W/R (trawa/clay/hard) ostatnie 24 mies.
             → last 5 matches mini-timeline (W/L kolorowe kropki)
             → H2H summary: X-Y z headlinerem
             → dane z PostgreSQL / statyczne dla demo

Iter 59–63:  Confidence calibration display
             → rarity tier = wizualny język pewności
             → JACKPOT (>28% edge): rainbow border pulsing
             → HIGH (>18%): pink glow
             → VALUE (>8%): blue border
             → COMMON (<8%): grey — nie pojawia się w kuponie

Iter 64–70:  Live odds → real-time probability update
             → The Odds API polling co 90s gdy klucz podany
             → jeśli odds zmienią się o >3%, animate prob bar update
             → gsap.to(bar, {width: newPct+'%', duration:.4, ease:'power2.out'})
             → toast "Kurs zaktualizowany" z nową wartością
```

**Definition of Done Faza B:**
- [ ] GET /predictions/{id}/explanation zwraca poprawny JSON
- [ ] 5 SHAP bars widocznych na każdej karcie po reveal
- [ ] "Szczegóły AI" expand/collapse działa
- [ ] Live odds update animuje się bez page reload
- [ ] 0 console errors

---

### FAZA C — Backend Connect (iter 71–105)
**Agenci:** Backend Architect + DevOps Automator (równolegle)

```
Iter 71–74:  Uruchom API v22 stabilnie
             cd /home/ubuntu/betatp
             uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
             curl http://localhost:8000/health
             → Zweryfikuj: model v22 załadowany, /coupons/daily zwraca picks

Iter 75–79:  Napraw /coupons/daily endpoint
             → wczytaj lgbm_v22_20260626_1738.joblib + feat_cols_v22_*.joblib
             → compute predictions dla 3-5 dzisiejszych meczów ATP
             → filter edge >= 8%
             → response schema: {picks: [{player, opponent, mkt, sel,
               odds, p_model, p_market, edge, reasoning, kelly, rarity}],
               total_odds, ev_pct, generated_at}

Iter 80–84:  Cloudflare tunnel → public URL
             cloudflared tunnel --url http://localhost:8000
             → zapisz public URL do frontend/index.html jako API_BASE_URL
             → const API_BASE = 'https://xxxx.trycloudflare.com'

Iter 85–90:  Podłącz frontend do API
             → zamień demo PICKS na fetch(API_BASE + '/coupons/daily')
             → loading state: btn-gen disabled + spinner podczas fetch
             → error fallback: jeśli fetch fail → użyj DEMO picks + toast info
             → timeout: 4000ms

Iter 91–98:  Daily pipeline cron
             scripts/run_daily_pipeline.py:
             → 7:00 UTC: fetch meczów ATP (The Odds API lub schedule)
             → compute v22 features → predict → filter → save JSON
             → cron: "0 7 * * * cd /home/ubuntu/betatp && python3 scripts/run_daily_pipeline.py"
             → output: /tmp/betatp_daily_coupon.json → serwowany przez /coupons/daily

Iter 99–105: System Builder live
             → /predictions?player_a=X&player_b=Y&surface=grass
             → 3 rynki per mecz: winner/handicap/total z real odds
             → frontend: mrb.odds i mrb.edge z API zamiast MATCHES[]
```

**Definition of Done Faza C:**
- [ ] `curl http://localhost:8000/health` → `{status: ok, model: v22}`
- [ ] `curl http://localhost:8000/coupons/daily` → 3-5 picks z realnym edge
- [ ] Frontend generuje kupon z API (nie demo)
- [ ] Cloudflare tunnel działa — public URL dostępny
- [ ] Daily cron uruchomiony: `crontab -l | grep betatp`

---

### FAZA D — Three.js 3D Court + Gyroscope (iter 106–125)
**Agenci:** Frontend Developer + UI Designer (równolegle)

```
Iter 106–110: Three.js scene setup
              CDN: https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js
              → canvas#court-canvas: position:fixed, z-index:-1 (za .screen)
              → PlaneGeometry(23.77, 10.97) — Wimbledon wymiary
              → texture z asset court-texture
              → LineSegments (linie boiska) kolor #c2ff3d
              → PerspectiveCamera(45) @ [0, 12, 18] → lookAt(0,0,0)
              → slow orbit: GSAP timeline 60s revolution

Iter 111–114: Three.js particles + lighting
              → 800 particles: float + sin wave z-axis
              → AmbientLight(0x0d0d24, 0.6)
              → DirectionalLight(0xc2ff3d, 0.4)
              → UnrealBloomPass: threshold=0.4, strength=0.6
              → IntersectionObserver: pause gdy tab niewidoczny

Iter 115–118: Gyroscope tilt na kartach (.pcard, .hcard)
              → DeviceOrientationEvent.requestPermission() — iOS 13+
              → gamma → rotateY (max ±18deg)
              → beta → rotateX (max ±14deg)
              → lerp factor 0.08 per frame (requestAnimationFrame)
              → fallback: mousemove parallax dla desktop

Iter 119–122: GSAP morphSVG — ikony rynków
              → SVG inline per market icon
              → na tab switch: morph ikona poprzedniego → nowego rynku
              → duration: 420ms ease-in-out

Iter 123–125: "Win streak" achievement system
              → localStorage: betatp_streak, betatp_wins
              → po każdym wygenerowanym kuponie: streak++
              → streak milestones: 3/7/14/30 → fireworks burst + toast
              → mini badge w logo-pill: "🔥 7"
```

**Definition of Done Faza D:**
- [ ] Three.js court widoczny w tle home screen
- [ ] Particles animują się @ 60fps
- [ ] Gyroscope tilt działa na iOS/Android (z permission dialog)
- [ ] Fallback mouse parallax działa na desktop
- [ ] Brak FPS drop poniżej 50fps z Three.js aktywnym

---

### FAZA E — Launch 🚀 (iter 126–140)
**Agenci:** Senior Dev + Evidence Collector + DevOps (Sequential)

```
Iter 126–128: SEO + PWA
              → <title>betatp.io — AI Value Betting ATP | LightGBM v22</title>
              → <meta name="description" content="..."> (max 155 znaków)
              → og:image: FAL-generated 1200×630 hero
              → frontend/manifest.json: PWA standalone, #020208 theme
              → frontend/sw.js: NetworkFirst API + CacheFirst assets

Iter 129–131: vercel.json finalizacja
              → builds: frontend/** → @vercel/static
              → headers: security (nosniff, DENY, XSS) + cache (immutable assets)
              → routes: /* → /frontend/index.html
              → Plik: /home/ubuntu/betatp/vercel.json ← JUŻ NAPISANY ✅

Iter 132–134: render.yaml — API deploy
              → services: web, python, startCommand: uvicorn api.main:app
              → envVars: DATABASE_URL, MODEL_PATH, ODDS_API_KEY
              → healthCheckPath: /health

Iter 135–137: Reality Checker — Evidence Collector agent
              WYMAGANE DOWODY (każdy = curl output lub screenshot):
              ✓ curl /health → {status: ok, model: v22, auc: 0.9171}
              ✓ curl /coupons/daily → 3-5 picks, edge >8% każdy
              ✓ Frontend loads < 2s (DevTools Network → DOMContentLoaded)
              ✓ Ceremonia 5-fazowa: Scan → Found → 3-2-1 → Slots → Flip
              ✓ Slot near-miss overshoot animuje się (overshoots 2.3×IH)
              ✓ Web Audio: ascending 200→800Hz podczas suspense
              ✓ Mobile: deck pionowy, tap na karty działa
              ✓ System Builder: 2 picks → total odds mnożą się
              ✓ Market tabs: click "± Handicap" → tylko handicap karty
              ✓ 0 console errors / 0 CORS errors
              ✓ Wszystkie 8+ FAL assets: HTTP 200

Iter 138–139: Final polish sprint
              → usuń console.log() z JS (prod)
              → sprawdź wc -l frontend/index.html < 2000
              → git status --porcelain = clean

Iter 140: SHIP 🚀
              git checkout gh-pages
              cp frontend/index.html index.html
              git add -A && git commit -m "feat: v1.0 — 140 iterations complete"
              git push origin gh-pages
              git checkout main
```

**Definition of Done Faza E (= Definition of Done projektu):**
- [ ] WSZYSTKIE 11 reality-check boxes zielone
- [ ] `wc -l frontend/index.html` < 2000
- [ ] `git log --oneline | wc -l` ≥ 50 (historia pracy)
- [ ] Live URL działa: https://qa10devteam.github.io/betatp/
- [ ] `vercel.json` + `render.yaml` gotowe do ręcznego deploy

---

## 🤖 NEXUS Sprint — Uruchomienie Batch 1 (natychmiast)

```
BATCH 1 — dispatch równolegle (3 agenty):

Agent 1: Frontend Developer
→ Faza A iter 1–12: wygeneruj 27 assetów + embed do index.html
→ Narzędzia: image_generate, write_file, terminal
→ Kontekst: /home/ubuntu/betatp/frontend/index.html (1426 linii)
→ Quality: /home/ubuntu/betatp/.codequality.yml → phase_a.assets

Agent 2: UI Designer
→ Faza A iter 13–28: mobile responsive + micro-interactions
→ Narzędzia: write_file, browser (visual check)
→ Kontekst: ten sam index.html co Agent 1 — skoordynuj sekcje CSS
→ Quality: phase_a.mobile_polish + phase_a.css_rules

Agent 3: AI Engineer
→ Faza B iter 36–46: api/routes/explanations.py + SHAP bars frontend
→ Narzędzia: terminal, write_file
→ Kontekst: models/lgbm_v22_20260626_1738.joblib, api/routes/
→ Quality: phase_b.shap_approximation

BATCH 2 — po zakończeniu Batch 1:

Agent 4: Backend Architect
→ Faza C iter 71–84: API v22 stable + /coupons/daily + cloudflare tunnel
→ Narzędzia: terminal
→ Kontekst: api/main.py, api/routes/, models/lgbm_v22_*.joblib

Agent 5: DevOps Automator
→ Faza C iter 85–105: daily pipeline cron + system builder live
→ Narzędzia: terminal, write_file
→ Kontekst: scripts/run_daily_pipeline.py, crontab

Agent 6: Evidence Collector (OSTATNI — po Batch 2)
→ Faza E iter 135–137: Reality check — WSZYSTKIE 11 dowodów
→ Narzędzia: terminal, browser
→ Zero tolerance dla "działa" bez curl output / screenshot
```

---

## 🛠️ Komendy startowe (wklej od razu)

```bash
# 1. Stan repo
cd /home/ubuntu/betatp && git log --oneline -3

# 2. Weryfikacja champion modelu
ls models/lgbm_v22_20260626_1738.joblib

# 3. Stan API
curl -s http://localhost:8000/health 2>/dev/null || echo "API offline"

# 4. Stan frontendu
wc -l frontend/index.html

# 5. Sprawdź assetów już wygenerowanych (8/35)
grep -c "fal.media" frontend/index.html
```

---

## 📁 Kluczowe pliki

```
/home/ubuntu/betatp/
├── .codequality.yml              ← SPEC JAKOŚCI — obowiązuje wszystkich agentów
├── frontend/
│   └── index.html                ← FRONTEND (1426 linii, LIVE)
├── api/
│   ├── main.py                   ← FastAPI entry point
│   ├── routes/predictions.py
│   ├── routes/coupons.py
│   └── routes/live.py
├── models/
│   ├── lgbm_v22_20260626_1738.joblib   ← CHAMPION MODEL
│   └── versions_results.json
├── scripts/
│   └── run_daily_pipeline.py
├── vercel.json                   ← Deploy config (napisany ✅)
└── specs/                        ← 22 aksjomaty matematyczne
```

---

## 🎨 Assets wygenerowane (8/35)

| # | Opis | URL |
|---|---|---|
| 1 | Hero background — dark emerald court | `https://v3b.fal.media/files/b/0a9fe175/-RlAtf05yGWN2_a8AI7nL_CN3iRoZE.png` |
| 2 | Market icon set (5 icons) | `https://v3b.fal.media/files/b/0a9fe179/4JPA1-dbvC7GtlqDGGNvB_PYQ20ZpF.png` |
| 3 | Holographic value bet card | `https://v3b.fal.media/files/b/0a9fe17c/5aXGKPrN0YKu8ZD2fKCcS_UD57jLsn.png` |
| 4 | Player silhouette stat card | `https://v3b.fal.media/files/b/0a9fe17f/QP3Dmo9SL4LFd9Yp8D2ar_Jr2RMa5l.png` |
| 5 | Data viz dashboard bg | `https://v3b.fal.media/files/b/0a9fe18b/YFpo2nM4EoM7VMZup3pnH_tNetBUN4.png` |
| 6 | Ceremony overlay bg | `https://v3b.fal.media/files/b/0a9fe185/g84L_hEAvlP19geMTTYGr_jaVBZ7KR.png` |
| 7 | System builder accent | `https://v3b.fal.media/files/b/0a9fe199/Du0tghwLqy4Iok3ECgYmt_9Jud0sAW.png` |
| 8 | Additional court bg | `https://v3b.fal.media/files/b/0a9fe189/2lgVtIxPEOb0lHDTnsBPx_P5m5rzOS.png` |

**Pozostałe 27 assetów = Faza A, iter 1–7**

---

## 🧠 Neuroscience design — zachowaj w kodzie

Komentarze inline WYMAGANE przy każdym mechanizmie:

| Implementacja | Komentarz w kodzie |
|---|---|
| `setTimeout(onDone, 520)` po locku reela | `// Dixon 2019: PRP 520ms — post-reinforcement pause increases perceived reward value` |
| overshoot `finalY - 2.3*IH` | `// Clark 2009 (Neuron, PMC2658737): near-miss overshoot Z=4.30 ventral putamen` |
| `anticipationTone()` 200→800Hz | `// Cherkasova 2018 (JNeurosci): ascending pitch signals reward imminence` |
| animacje suspense 2–8s | `// Jauhar 2021 (45-study fMRI): anticipation > delivery for dopamine activation` |
| `--t-drama: 4000ms` | `// Schultz 2016 (RPE): dopamine ramps during anticipation window` |
| `#61b510` CTA button | `// DraftKings Vida Loca — verified via logotyp.us` |
| CS2 rarity colors grey→blue→pink→gold | `// Barton 2017 (51-study): color hierarchy = engineered dopamine arousal ramp` |

---

*Hermes — 2026-06-26 | Sesja 3 | Model v22 champion | 140 iter spec-off*
