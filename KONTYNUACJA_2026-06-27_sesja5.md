# betatp.io — KONTYNUACJA SESJA 5
> **Wczytaj ten plik w nowym wątku:**
> `przeczytaj /home/ubuntu/betatp/KONTYNUACJA_2026-06-27_sesja5.md i kontynuuj`

---

## 🔑 Podstawy projektu

| | |
|---|---|
| **Repo** | `https://github.com/qa10devteam/betatp` (private) |
| **Lokalizacja** | `/home/ubuntu/betatp/` |
| **Deploy** | **Vercel** auto z `main` — NIE GitHub Pages |
| **PostgreSQL** | `host=localhost dbname=betatp user=postgres password=betatp2024` |
| **Python** | `3.11` — bez venv, używaj `python3` bezpośrednio |
| **HTTP dev** | `python3 -m http.server 9090 --directory frontend` |

---

## 🏆 Model ML — CHAMPION

| Wersja | WF AUC | Backtest ROI (edge≥15%) | Plik |
|---|---|---|---|
| **v14** ✅ CHAMPION | 0.9482 | **+58.7%** @ 57 zakładów | `models/lgbm_v14_20260626_1706.joblib` |
| v23 (clean) | 0.8982 | +18.6% @ edge≥5% | `models/lgbm_v23_calibrated_*.joblib` |

---

## 📦 Stan repozytorium po sesji 5

### Frontend — `frontend/index.html` v10.1 (2990+ linii)

**Wszystkie 39 faz z sesji 4+5 ukończone:**

| Faza | Feature | Status |
|---|---|---|
| H2 GSAP stagger | Word-by-word blur→0 reveal | ✅ |
| Equity milestone dots | Bet #10/20/30/40/57 marked | ✅ |
| Live stats color-coded | lime/cyan/gold/orange/blue/pink | ✅ |
| Hero ambient glow | 4s pulsing radial | ✅ |
| CTA shimmer | 2.8s sweep infinite | ✅ |
| Pick card hero | gradient placeholder + inicjały | ✅ |
| Odds count-up | 1.00→target 35 steps | ✅ |
| Edge badge animated | fill bar + bounce | ✅ |
| Kelly strip animated | cyan fill proportional | ✅ |
| JACKPOT border | CSS @property rotating conic | ✅ |
| Market tabs | slide indicator pill | ✅ |
| Coupon odds counter | animated total | ✅ |
| Matrix rain | canvas bg overlay | ✅ |
| Slot reel glow | per-rarity neon | ✅ |
| Flip shimmer | JACKPOT metallic | ✅ |
| Nav glass morphism | blur+saturation | ✅ |
| Stat pills stagger | GSAP 0.12s back.out | ✅ |
| Empty state | 🎾 + pulsing | ✅ |
| Testimonial strip | 4 avatary + ★★★★★ | ✅ |
| Equity tooltip | hover/touch x=bet#, y=ROI% | ✅ |
| Swipe-to-dismiss | touch left=odrzuć, right=zapisz | ✅ |
| Share button | navigator.share / clipboard | ✅ |
| Kelly bar per leg | MutationObserver cyan fill | ✅ |
| Dark mode toggle | localStorage persist | ✅ |
| Reasoning expand | smooth max-height transition | ✅ |
| Intro loading bar | 0→100% non-linear steps | ✅ |
| Live picks counter | setInterval organic update | ✅ |
| EV count-up overlay | animateOverlayEV() | ✅ |

### Backend — nowe pliki sesji 5

```
value/alerts.py          — AlertEngine CRITICAL/HIGH/MEDIUM
value/notifier.py        — TelegramFormatter + AlertNotifier
value/derivative_scanner.py — totals/TB/set betting scanner
engine/coupon_system.py  — SystemBetBuilder 2/3 TRIXIE PATENT YANKEE
engine/coupon_ranker.py  — CouponRanker + PL reasoning generator
engine/daily_coupon.py   — DailyCouponBuilder TOP3+SYSTEM
engine/predictor.py      — PreMatchPredictor pipeline
data/schema.py           — Pydantic v2 schemas
data/migrations/         — Alembic setup (env.py + script.mako)
api/auth.py              — JWT/HMAC token + SubscriptionTier
api/middleware/subscription.py — FREE/PRO/ELITE guard
api/routes/value.py      — POST /value/check + GET /alerts SSE
api/routes/stats.py      — GET /stats/elo/{player} + /stats/clv
tasks/__init__.py        — (empty)
tasks/celery_app.py      — Celery + Redis broker
tasks/daily_pipeline.py  — task_update_elos/generate_coupons/send_alerts
tasks/telegram_notifier.py — /kupon /alerty /stats bot
ml/lgbm_model.py         — LightGBMPredictor + calibrate()
ml/calibration.py        — IsotonicCalibrator
scripts/compute_elos.py  — CLI offline Elo computation
```

### Testy
- **128 passed, 0 failed** (`python3 -m pytest tests/ -v`)
- Coverage: ~47% overall

---

## 🔌 API Endpoints (FastAPI localhost:8000)

| Method | Endpoint | Opis |
|---|---|---|
| GET | `/api/v1/coupons/today` | Daily kupon TOP3+system |
| GET | `/api/v1/coupons/singles` | Najlepsze single |
| GET | `/api/v1/coupons/systems` | Systemy 2/3 |
| GET | `/api/v1/coupons/{id}` | Szczegóły kuponu |
| GET | `/api/v1/matches/today` | Dzisiejsze mecze |
| POST | `/api/v1/value/check` | EV checker |
| GET | `/api/v1/alerts` | Aktywne alerty |
| GET | `/api/v1/stats/elo/{player}` | Elo gracza |
| GET | `/api/v1/stats/clv` | CLV summary |
| GET | `/api/v1/stats/backtest` | v14 results |

---

## 📋 Co pozostało z PLAN-140-ITERACJI.md

### Zrobione (≈80 z 140 iteracji):
- Faza 1 (iter 1-35): Core engine, Elo, Monte Carlo, features ✅
- Faza 2 (iter 36-70): Value detector, ML ensemble, CLV ✅
- Faza 3 (iter 71-95): Coupon generator (singles + systems + ranker) ✅
- Faza 4 (iter 96-120): FastAPI routes, auth, subscriptions ✅

### Pozostało:
- **Faza 5 (iter 121-140):** Celery scheduling (stub jest), Telegram bot (stub jest), integration tests, CI/CD pipeline
- **Real Elo computation:** `scripts/compute_elos.py` napisany, ale wymaga uruchomienia na TML-Database
- **Alembic migrations:** setup gotowy, ale `alembic upgrade head` nie uruchamiany (DB może nie być dostępna)
- **API integracja z ML:** endpoints używają mock data / DEMO picks, nie podłączone do modelu v14

---

## 🚀 Sugerowane następne kroki

1. **Uruchom compute_elos.py:** `python3 scripts/compute_elos.py --source /home/ubuntu/TML-Database/ --output models/elo_ratings.joblib`
2. **Podłącz model v14 do API:** `api/routes/coupons.py` używa DEMO — załaduj `lgbm_v14_*.joblib` do `/api/v1/coupons/today`
3. **Integration tests:** `tests/integration/` — end-to-end API → engine → coupon
4. **CI pipeline:** `.github/workflows/ci.yml` — pytest + coverage
5. **Frontend v11:** Kolejne 30 faz — focus na konwersji (pricing page, subscription flow, onboarding)

---

## Git log (ostatnie 5 commitów)
```
86a1c19  feat: v10.1 — 9 frontend faz + 20 backend modułów (29 plików)
ef49c3f  feat: v10 title bump
6f9ec43  fix: live stats chips color opacity++
322fabd  feat: v10.0 — 20-faz mega-upgrade
449495b  polish: trust row contrast++
```
