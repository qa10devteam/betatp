# betatp.io — KONTYNUACJA (sesja 3, 2026-06-26)
> Wczytaj ten plik na początku nowego wątku: `/home/ubuntu/betatp/KONTYNUACJA_2026-06-26_sesja3.md`

---

## 🔑 Podstawowe info

| Klucz | Wartość |
|---|---|
| Repo | `https://github.com/qa10devteam/betatp` (private, org: qa10devteam) |
| Lokalizacja | `/home/ubuntu/betatp/` |
| GitHub Pages | `https://qa10devteam.github.io/betatp/` ← LIVE |
| PostgreSQL | `host=localhost dbname=betatp user=postgres password=betatp2024` |
| Python | `3.11`, venv w systemie (brak venv — używaj `python3` bezpośrednio) |
| Last commit main | `529ae85 chore: add model metas v5-v22, training logs, plan files, misc artifacts` |

---

## 🏆 Stan modeli ML (LEAKAGE-CLEAN — tylko trained_at >= 20260626_1631)

| Wersja | Holdout AUC | WF AUC | Plik modelu | Status |
|---|---|---|---|---|
| **v22** | **0.9171** | **0.9422** | `lgbm_v22_20260626_1738.joblib` | ✅ BEST CHAMPION |
| v14 | 0.9031 | 0.9482 | `lgbm_v14_20260626_1706.joblib` | ✅ backup |
| v17 | 0.8844 | 0.9205 | `lgbm_v17_20260626_1725.joblib` | ok |
| v16 | 0.8828 | 0.9204 | `lgbm_v16_20260626_1717.joblib` | ok |

**LEAKAGE GUARD:** `versions_results.json` — TYLKO modele `trained_at >= 20260626_1631` są czyste.
Nie używaj v5-v13 (stary training run, leakage w h2h_surf_winrate).

**CURRENT CHAMPION: v22** (holdout_auc=0.9171, wf_auc=0.9422, 57 features, 71,872 train samples)

Top features v22: winner_age_b, winner_rank_b, winner_rank_a, winner_age_a, pw_heat_edge, rank_inv_b, draw_diff_b, h2h_wins_delta_3_a

Pełen model_meta: `/home/ubuntu/betatp/models/model_meta_v22_20260626_1738.json`

---

## 🐛 Historia bugów i napraw (do wglądu, nie wznawiać)

| Bug | Status | Opis |
|---|---|---|
| Bug #1 | ✅ NAPRAWIONY | b365/max/avg odds shared (col,col) — Fix: dodano `_l` kolumny |
| Bug #2 | ⚠️ SUSPECT | v6 pw_heat_wr (AUC=0.9866) — version pomijana, nie używamy |
| Bug #3 | ✅ NAPRAWIONY | h2h delta features winner-oriented — Fix: _w/_l split |
| Bug #4 | ✅ OBSERWOWANY | v9 AUC=0.9975 — h2h_surf_winrate_a leakage. v9 wyłączony z użycia |

---

## 🎯 GŁÓWNA MISJA SESJI 3 (niezrealizowane)

### Cel nadrzędny
**Stworzyć najbardziej innowacyjne doświadczenie betowania w historii** — platforma betatp.io z:
1. WOW-level frontend (Three.js + GSAP + GLSL + Web Audio)
2. Pełna przezroczystość AI — storytelling skąd bierze się predykcja
3. 5 rynków: Winner / Handicap / Total Sets / First Set / Correct Score
4. 35 iteracji własnych assetów (AI-generated + konwersja)
5. Backend v22 live połączony z frontendem

### Spec-off: 140 iteracji (niezrealizowane przed końcem sesji)
Pełny plan w: `/home/ubuntu/betatp/PLAN-140-ITERACJI.md`

---

## 🏗️ Stan infrastruktury

### Frontend (LIVE)
- **URL:** https://qa10devteam.github.io/betatp/
- **Plik:** `/home/ubuntu/betatp/frontend/index.html` (1426 linii)
- **Stack:** Pure HTML + GSAP 3.12.5 CDN + WebGL GLSL aurora shader + Web Audio API
- **Co działa:**
  - ✅ GLSL aurora background (5-oktawowy FBM noise, mouse parallax)
  - ✅ 5-fazowa ceremonia generowania kuponu (Scan → Found → Suspense 3-2-1 → Slots → Flip)
  - ✅ CS:GO slot machine z near-miss overshoot (Clark 2009)
  - ✅ FIFA UT pack flip cards (rotateY 180° + light flash)
  - ✅ 5 rynków: Winner / First Set / Handicap / Total Sets / Score
  - ✅ Market filter tabs + System Builder (8 picks, 3 markets/match)
  - ✅ Storytelling na kartach: "Dlaczego model typuje to?" + prob bars + Kelly
  - ✅ Social proof ticker (backtest stats)
  - ✅ Web Audio: ascending 200→800Hz anticipation (Cherkasova 2018)
  - ✅ Particle system (canvas, square particles, burst + rain)
  - ✅ The Odds API integration (the-odds-api.com, klucz w localStorage)
  - ✅ DraftKings #61B510 CTA button, CS2 rarity color hierarchy
  - ✅ 8 custom AI-generated assets (FAL images)
- **Co NIE działa / do zrobienia:**
  - ❌ Backend API połączony z frontendem (frontend używa demo PICKS)
  - ❌ Cloudflare tunnel do API (FastAPI port 8000)
  - ❌ Pozostałe 27/35 assetów
  - ❌ Real v22 predictions w frontend (mock data)

### Backend API (FastAPI)
- **Plik startowy:** `cd /home/ubuntu/betatp && uvicorn api.main:app --host 0.0.0.0 --port 8000`
- **Status:** Prawdopodobnie nie działa (sprawdź: `curl http://localhost:8000/health`)
- **Endpointy:** `/health`, `/predictions`, `/coupons`, `/live`
- **Model:** Do załadowania: `models/lgbm_v22_20260626_1738.joblib` + `models/feat_cols_v22_*.joblib`

### Deploy
- **GitHub Pages:** Branch `gh-pages`, auto-deploy z `frontend/index.html` → `index.html`
- **Render.com:** `render.yaml` + `Procfile` w repo (FastAPI backend)

---

## 📋 SPEC-OFF 140 ITERACJI (do realizacji w sesji 3+)

### NEXUS Metodyka
Aktywuj zespoły agenturalne: `/home/ubuntu/agency-agents/`
Skill: `agency-nexus-orchestrator`

### Faza A: FRONTEND EXCELLENCE (iter 1–35) — ASSETS + POLISH
```
Iter 1–7:   Dokończ 27 pozostałych assetów AI (image_generate → local PNG/SVG)
            Asset types: player silhouettes, court textures, trophy icons,
            rarity frames, gradient orbs, UI icons (x35 total)
Iter 8–14:  Embed assets do HTML (base64 lub GitHub raw URLs)
Iter 15–21: Animacje detale — hover states, micro-interactions, haptics
Iter 22–28: Mobile responsive — touch events, scroll UX, viewport fixes
Iter 29–35: Performance pass — lazy loading, canvas optimizations, FPS profiling
```

### Faza B: AI STORYTELLING ENGINE (iter 36–70)
```
Iter 36–42: SHAP-style explanations — top 5 features per pick, visual bars
Iter 43–49: "Jak model doszedł do predykcji" — journey UI (Schultz RPE flow)
Iter 50–56: Historical stats embed — surface W/R, H2H, last 5 matches
Iter 57–63: Confidence calibration display — reliability diagram per rarity tier
Iter 64–70: Live odds integration — Odds API → real-time prob update animation
```

### Faza C: BACKEND CONNECT (iter 71–105)
```
Iter 71–77: Uruchom API v22 stabilnie (uvicorn + supervisord)
Iter 78–84: Cloudflare tunnel → public URL → podłącz do frontend fetch()
Iter 85–91: Daily pipeline cron — o 7:00 pobierz mecze ATP, compute predictions
Iter 92–98: Coupon endpoint — /coupons/daily → JSON → frontend renders live
Iter 99–105: System builder live — /predictions?match_id=X → odds + edges
```

### Faza D: WOW EXPERIENCE ESCALATION (iter 106–125)
```
Iter 106–110: Three.js 3D tennis court — rotating court z particle trails
Iter 111–115: GSAP morphSVG — ikony zmieniają kształt między rynkami
Iter 116–120: Tilt.js holographic card tilt per device gyroscope
Iter 121–125: "Win streak" achievement system — local storage, fireworks
```

### Faza E: LAUNCH (iter 126–140)
```
Iter 126–130: SEO meta, OG image, PWA manifest, service worker
Iter 131–134: Render.com deploy — API live na public URL
Iter 135–137: Reality Checker — end-to-end test wszystkich flows
Iter 138–139: Final polish sprint
Iter 140:     Ship 🚀 — finalne commit + gh-pages deploy + announcement
```

---

## 🤖 ZESPOŁY AGENTURALNE (NEXUS-Sprint)

### Batch 1 — równolegle (FRONTEND)
```
Agent: engineering-frontend-developer.md
Cel: Iter 1–14 (assets embed + mobile responsive)

Agent: design-ui-designer.md
Cel: Iter 15–28 (micro-interactions, hover, touch UX)

Agent: engineering-ai-engineer.md
Cel: Iter 36–49 (SHAP explanations, storytelling engine)
```

### Batch 2 — równolegle (BACKEND)
```
Agent: engineering-backend-architect.md
Cel: Iter 71–84 (API v22 + Cloudflare tunnel)

Agent: engineering-devops-automator.md
Cel: Iter 85–98 (daily pipeline cron + deploy)

Agent: testing-evidence-collector.md
Cel: Reality check po każdym batchu
```

---

## 🛠️ Komendy startowe (wklej natychmiast)

```bash
# Sprawdź stan repo
cd /home/ubuntu/betatp && git log --oneline -3

# Sprawdź model v22
ls models/lgbm_v22_20260626_1738.joblib

# Uruchom API
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
sleep 2 && curl -s http://localhost:8000/health | python3 -m json.tool

# Sprawdź frontend
wc -l frontend/index.html
```

---

## 📁 Kluczowe pliki

```
/home/ubuntu/betatp/
├── frontend/index.html          ← GŁÓWNY FRONTEND (1426 linii, LIVE)
├── api/
│   ├── main.py                  ← FastAPI entry point
│   ├── routes/predictions.py   ← /predictions endpoint
│   ├── routes/coupons.py       ← /coupons endpoint
│   └── routes/live.py          ← /live endpoint
├── models/
│   ├── lgbm_v22_20260626_1738.joblib  ← CHAMPION MODEL
│   ├── feat_cols_v22_*.joblib          ← Feature columns
│   └── versions_results.json           ← Wszystkie wersje
├── scripts/
│   ├── train_versions.py        ← Training script
│   ├── run_backtest.py          ← Backtest
│   └── run_daily_pipeline.py   ← Daily cron
├── PLAN-140-ITERACJI.md         ← Szczegółowy plan
├── KONTYNUACJA_2026-06-26_sesja2.md  ← Poprzednia sesja
└── specs/                       ← 22 aksjomaty matematyczne
```

---

## 🎨 Frontend — custom assets wygenerowane (8/35)

| # | Opis | URL FAL |
|---|---|---|
| 1 | Hero background (dark emerald tennis court) | `https://v3b.fal.media/files/b/0a9fe175/-RlAtf05yGWN2_a8AI7nL_CN3iRoZE.png` |
| 2 | Market icon set (5 icons) | `https://v3b.fal.media/files/b/0a9fe179/4JPA1-dbvC7GtlqDGGNvB_PYQ20ZpF.png` |
| 3 | Holographic value bet card | `https://v3b.fal.media/files/b/0a9fe17c/5aXGKPrN0YKu8ZD2fKCcS_UD57jLsn.png` |
| 4 | Player silhouette stat card | `https://v3b.fal.media/files/b/0a9fe17f/QP3Dmo9SL4LFd9Yp8D2ar_Jr2RMa5l.png` |
| 5 | Data viz dashboard background | `https://v3b.fal.media/files/b/0a9fe18b/YFpo2nM4EoM7VMZup3pnH_tNetBUN4.png` |
| 6 | JACKPOT rarity card (CS:GO rainbow) | (w index.html) |
| 7 | Dark overlay background (ceremony) | `https://v3b.fal.media/files/b/0a9fe185/g84L_hEAvlP19geMTTYGr_jaVBZ7KR.png` |
| 8 | System builder accent | `https://v3b.fal.media/files/b/0a9fe199/Du0tghwLqy4Iok3ECgYmt_9Jud0sAW.png` |

Pozostałe 27 assetów: DO WYGENEROWANIA (iter 1–7 sesji 3)

---

## 🧠 Neuroscience design decisions (zachowaj w kodzie)

| Mechanizm | Implementacja | Źródło |
|---|---|---|
| Dopamine peakuje w anticipation, nie po reveal | 4-fazowe okno suspense przed reveal | Schultz 2016 (RPE) |
| Near-miss overshoot | reel → overshoot 2.3×IH → PRP 520ms → settle | Clark 2009 (Neuron, Z=4.30) |
| ~50% uncertainty = max DA | Pick odds celowo między 1.5–3.0 | Jauhar 2021 (n=2000+) |
| Ascending pitch 200→800Hz | `anticipationTone()` WebAudio | Cherkasova 2018 (JNeurosci) |
| PRP 520ms po każdym locku | `setTimeout(onDone, 520)` | Dixon 2019 |
| CS2 rarity color hierarchy | grey→blue→pink→gold | Barton 2017 |
| AV sync | sound+visual burst synchronized | Presti 2021 |
| Social proof ticker | real backtest stats w DOM | Cialdini 1984 |
| DraftKings #61B510 CTA | `background: #61b510` | DraftKings brand |

---

## 🚀 WYTYCZNA DLA SESJI 3

Hasło misji: **"Najbardziej innowacyjne doświadczenie betowania w historii"**

Priorytet 1 (natychmiast po wczytaniu):
1. Sprawdź stan API (`curl localhost:8000/health`)
2. Wygeneruj 10 kolejnych assetów (iter 1–3 assetów, image_generate)
3. Uruchom NEXUS Batch 1 — 3 agenty równolegle (frontend+design+AI)

Priorytet 2:
4. Połącz frontend z API v22 (real predictions, nie demo)
5. Deploy Cloudflare tunnel → public API URL

Priorytet 3:
6. Three.js 3D tennis court scene
7. SHAP feature importance bars na kartach
8. Daily pipeline cron (o 7:00 UTC)

---

## 📊 Wyniki backtest (referenyjne)

Model v22 (champion, clean):
- Holdout AUC: **0.9171**
- WF AUC: **0.9422** (4 spity 2014→2024)
- Train samples: 71,872 | Holdout: 6,150
- Features: 57 (top: age, rank, pw_heat_edge, draw_diff)

Model v14 (backup, clean):
- Holdout AUC: 0.9031 | WF AUC: 0.9482
- Backtest Kelly: ROI +42.1%, 57 betów (zatwierdzony)

---

*Wygenerowano automatycznie przez Hermes 2026-06-26. Plik do wczytania w nowym wątku.*
