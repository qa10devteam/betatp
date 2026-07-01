# atpbet — 140-Phase Complete Product Plan

> **Project rename:** betatp → **atpbet** | Language: **English throughout**
> **Deploy:** Vercel auto from `main` branch | Local: `/home/ubuntu/betatp/`

**Goal:** Ship a production-ready, commercially viable ATP tennis betting intelligence platform — complete with ML prediction engine (champion stack v70/v80), real-time value detection, polished English UI, subscription paywall, and automated daily coupon delivery.

**Architecture:** FastAPI backend + PostgreSQL (197k matches) + LightGBM champion models (AUC 0.836–0.935) + React-free single-file frontend (vanilla JS + GSAP + Three.js) + Vercel static + Celery/Redis for scheduled jobs.

**Champion Models Available:**
- `lgbm_v70_is_straight` — AUC 0.935 (P straight sets)
- `lgbm_v54_ou39.5_full` — AUC 0.928 (O/U 39.5 games)
- `lgbm_v31_fatigue_5sets` — AUC 0.920 (P 5 sets)
- `lgbm_v23_ou36.5` — AUC 0.892 (O/U 36.5 games)
- `lgbm_v80_hcp_9` — AUC 0.836 (HCP >9.5 games)
- `lgbm_v39_cross_over33` — AUC 0.833 (O/U 33.5 games)

---

## PHASE A — Rename & Foundation (Phases 1–10)

### Phase 1: Rename project to atpbet
**Files:** `api/main.py`, `frontend/index.html`, `README.md`, `render.yaml`
- Replace all occurrences of "betatp", "betatp.io", "Betatp" with "atpbet", "atpbet.io", "ATPBet"
- Update `api/main.py` title: `"atpbet.io API"`, version `"1.0"`
- Update `api/main.py` description: `"ATP Tennis Betting Intelligence"`
- `git commit -m "chore: rename betatp → atpbet"`

### Phase 2: English-only API responses
**Files:** `api/main.py`, `api/schemas.py`, `api/routes/*.py`
- Replace all Polish strings in API responses with English equivalents
- Polish→English glossary: "Brak" → "No", "mecz" → "match", "kurs" → "odds", "zakład" → "bet", "wartość" → "value", "stawka" → "stake"
- Update FastAPI description fields, error messages, response models
- `git commit -m "feat: English-only API layer"`

### Phase 3: PostgreSQL password config
**Files:** `api/main.py`, `.env.example`, new `config.py`
- Create `config.py`: `PG_DSN = "host=localhost dbname=betatp user=postgres password=betatp2026"`
- All DB connections import from `config.py`
- Note: `sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'betatp2026';"` already done
- `git commit -m "chore: centralise DB config"`

### Phase 4: Champion model registry
**File:** `ml/champion_stack.py` (new)
```python
CHAMPION_MODELS = {
    "straight": "lgbm_v70_is_straight_20260701_0806.joblib",
    "fatigue5": "lgbm_v31_fatigue_5sets_20260629_1957.joblib",
    "ou39":     "lgbm_v54_ou39.5_full_20260630_1705.joblib",
    "ou36":     "lgbm_v23_ou36.5_20260629_1938.joblib",
    "hcp9":     "lgbm_v80_hcp_9_20260701_1118.joblib",
    "ou33":     "lgbm_v39_cross_over33_20260629_2010.joblib",
}
# Market descriptions for UI
MARKET_LABELS = {
    "straight": "Straight Sets (2:0)",
    "fatigue5": "Full Distance (3 Sets)",
    "ou39":     "Over/Under 39.5 Games",
    "ou36":     "Over/Under 36.5 Games",
    "hcp9":     "Game Handicap >9.5",
    "ou33":     "Over/Under 33.5 Games",
}
```
- `git commit -m "feat: champion model registry"`

### Phase 5: Feature builder refactor (EN)
**File:** `engine/feature_builder.py` (new, extracted from `scripts/generate_coupons.py`)
- Extract `build_features_full()` into standalone module
- All 103 features documented with English comments
- `get_player_stats(conn, player_name)` → returns rolling stats dict
- Unit test: `tests/test_feature_builder.py` — mock PG, assert 103 keys
- `git commit -m "refactor: extract feature builder module"`

### Phase 6: Prediction service
**File:** `engine/prediction_service.py` (new)
```python
class PredictionService:
    def predict_match(self, player_a, player_b, surface, round_num, odds_a, odds_b) -> dict
    # Returns: {market: {prob, edge, ev, implied_prob}} for all 6 markets
```
- Loads champion stack once at startup (lazy singleton)
- `tests/test_prediction_service.py` — test with Sinner vs Medvedev
- `git commit -m "feat: prediction service with champion stack"`

### Phase 7: Value bet detector
**File:** `engine/value_detector.py` (new)
```python
class ValueDetector:
    def scan(self, predictions: dict, sts_odds: dict) -> list[ValueBet]
    # ValueBet: match, market, model_prob, sts_odds, edge, ev, kelly_pct, stake_usd
    # Threshold: edge > 0.04 (4%)
    # Kelly: half-Kelly capped at 0.05 (5% bankroll)
```
- `tests/test_value_detector.py`
- `git commit -m "feat: value bet detector with Kelly sizing"`

### Phase 8: ATP schedule fetcher
**File:** `engine/schedule.py` (new)
```python
def fetch_today_matches(surface_filter=None) -> list[MatchSlot]
# Sources: ATP Tour JSON feed → fallback hardcoded for current tournament
# MatchSlot: player_a, player_b, tournament, surface, round, start_time, odds_a, odds_b
```
- ATP schedule URL: `https://www.atptour.com/en/scores/current/{tournament}/results`
- Fallback: last known schedule stored in `data/schedule_cache.json`
- `git commit -m "feat: ATP schedule fetcher with cache fallback"`

### Phase 9: Daily coupon pipeline
**File:** `engine/daily_pipeline.py` (refactored)
```python
def run_daily_pipeline() -> list[Coupon]:
    matches = fetch_today_matches()
    predictions = [PredictionService().predict_match(m) for m in matches]
    value_bets = ValueDetector().scan(predictions)
    coupons = CouponBuilder(budget=15.0, n_coupons=3).build(value_bets)
    return coupons
```
- Output saved to `coupons/daily.json`
- `git commit -m "feat: daily coupon pipeline refactor"`

### Phase 10: API endpoint /coupons/today
**File:** `api/routes/coupons.py`
```python
GET /coupons/today → { coupons: [...], generated_at: ISO, surface: str, n_value_bets: int }
GET /coupons/markets → { markets: [{id, label, auc, description}] }
POST /coupons/custom → { matches: [...], budget: float } → custom coupon
```
- Response fully in English
- `tests/integration/test_coupon_flow.py` updated
- `git commit -m "feat: /coupons/today and /coupons/markets endpoints"`

---

## PHASE B — Backtest & Model Validation (Phases 11–20)

### Phase 11: Champion stack backtest
**File:** `scripts/backtest_champion.py` (new)
- Walk-forward backtest of all 6 champion models on 2024 holdout (1,904 matches)
- Metrics: AUC, Brier score, ROI at various edge thresholds (3%, 5%, 8%, 10%, 15%)
- Output: `data/backtest_champion.json`
- Run: `python scripts/backtest_champion.py`
- `git commit -m "feat: champion stack backtest 2024 holdout"`

### Phase 12: ROI curves by market
**File:** `data/backtest_champion.json`
- Structure: `{market: {edge_threshold: {bets, win_rate, roi, max_dd, kelly_roi}}}`
- Used by frontend to show "backtested ROI" per market
- `git commit -m "data: champion stack ROI curves"`

### Phase 13: Calibration check
**File:** `scripts/calibrate_champions.py`
- Reliability diagrams for each champion model (10 probability bins)
- Expected calibration error (ECE) per model
- Flag if ECE > 0.05 (needs recalibration)
- Output: `data/calibration_report.json`
- `git commit -m "feat: calibration report for champion stack"`

### Phase 14: CLV (Closing Line Value) tracker
**File:** `value/clv_tracker.py` (refactored, EN)
- Track opening odds vs closing odds for predicted value bets
- CLV = log(closing_odds / opening_odds) — positive means market moved in our direction
- 30-day rolling CLV chart data
- `git commit -m "feat: CLV tracker with 30-day history"`

### Phase 15: Win rate by tournament/surface
**File:** `engine/surface_stats.py` (new)
- Query PG: win rates by surface, round, tournament level for each player
- Cache 24h in `data/surface_stats_cache.json`
- API endpoint: `GET /predictions/player-stats?name=Sinner`
- `git commit -m "feat: player surface stats endpoint"`

### Phase 16: Model confidence indicator
**File:** `engine/confidence.py` (new)
- Aggregate 6 champion model predictions → consensus confidence score
- High confidence: ≥4 models agree with |edge| > 6%
- Medium: 2–3 models agree
- Low: <2 models agree
- Returns: `{confidence: "HIGH"|"MEDIUM"|"LOW", n_agreeing: int, avg_edge: float}`
- `git commit -m "feat: multi-model consensus confidence"`

### Phase 17: Value history endpoint
**File:** `api/routes/value.py` (refactored)
```python
GET /value/history?days=30 → last N days of detected value bets with outcome
GET /value/stats → { total_bets, win_rate, roi, avg_edge, avg_odds }
GET /value/leaderboard → top 10 picks by EV (last 30 days)
```
- `git commit -m "feat: value history and stats endpoints"`

### Phase 18: Odds scraper integration
**File:** `engine/odds_scraper.py` (new)
- Scrape Pinnacle/STS odds for current tournament matches
- Store in `data/live_odds_cache.json` (TTL 15min)
- Fallback to B365 from PG `odds` table
- `git commit -m "feat: live odds scraper with cache"`

### Phase 19: Edge threshold optimizer
**File:** `scripts/optimize_threshold.py` (new)
- Grid search: edge threshold ∈ [2%, 20%] step 1%
- Optimize for Kelly ROI on 2023–2024 test set
- Output optimal threshold per market to `data/optimal_thresholds.json`
- `git commit -m "feat: edge threshold optimizer"`

### Phase 20: Model performance dashboard data
**File:** `data/model_performance.json` (new)
```json
{
  "straight": {"auc": 0.9354, "brier": 0.0624, "roi_5pct": 0.38, "roi_10pct": 0.52, "n_bets_2024": 87},
  "ou39": {...}, ...
}
```
- Consumed by frontend Model Performance section
- Auto-regenerated after each backtest run
- `git commit -m "data: model performance summary JSON"`

---

## PHASE C — Frontend Complete Rebuild (Phases 21–50)

### Phase 21: New index.html scaffold — atpbet branding
**File:** `frontend/index.html` (full rebuild)
- Replace all Polish text with English
- Brand: "atpbet" (lowercase) + tagline "ATP Intelligence. Real Edge."
- Color scheme: keep `#c2ff3d` lime accent, dark bg `#0a0a0f`
- Nav: logo pill + "Dashboard" / "Today's Picks" / "Markets" / "Performance" / "Subscribe"
- `git commit -m "feat: atpbet frontend EN scaffold"`

### Phase 22: Hero section — "Beat the Market"
**File:** `frontend/index.html` → `#hero`
```html
<section id="hero">
  <h1 class="hero-tag">ATP Intelligence</h1>
  <h2 class="hero-headline">Beat the Market,<br>Every Tournament.</h2>
  <p class="hero-sub">6-model ensemble. 197,000 matches. Real edge vs Pinnacle.</p>
  <div class="hero-stats">...</div>  <!-- 3 stat pills -->
  <canvas id="equity-curve"></canvas>
  <button class="cta-primary">Get Today's Picks →</button>
</section>
```
- Equity curve canvas: animated draw, final +58.7% ROI label
- `git commit -m "feat: hero section EN"`

### Phase 23: Stat pills — real metrics
- Pill 1: `+58.7% ROI` (v14 backtest)
- Pill 2: `0.935 AUC` (best model)  
- Pill 3: `197K matches`
- GSAP stagger reveal 0.12s, back.out(1.4)
- `git commit -m "feat: hero stat pills with real metrics"`

### Phase 24: Today's Picks section
**Section:** `#picks`
- Header: "Today's Value Picks" + date + surface badge
- Pick cards: player names (EN), market label (EN), odds, edge %, confidence badge
- Empty state: "No picks today — check back at 08:00 UTC"
- Fetch from `/coupons/today` with AbortSignal.timeout(5000)
- Fallback DEMO picks if API offline
- `git commit -m "feat: today's picks section EN"`

### Phase 25: Pick card design
Each card:
```
[PLAYER A] vs [PLAYER B]     [surface badge]
[Market: Over/Under 39.5 Games]
Model prob: 71.4%   Pinnacle: 54.1%   Edge: +17.3%   EV: +32.0%
Suggested odds: 1.85   Kelly stake: 3.2% bankroll
[confidence: HIGH ●●●]
```
- Confidence: 3 dots, lime=agreeing models
- `git commit -m "feat: pick card redesign EN"`

### Phase 26: Market selector tabs
- Tabs: All · Straight Sets · O/U Games · Handicap · 5-Set Matches
- Active tab: lime underline + glow
- Filter picks by market type
- Count badge per tab
- `git commit -m "feat: market filter tabs"`

### Phase 27: Coupon builder UI
**Section:** `#coupon`
- Show 3 pre-built coupons (MAX VALUE AKO / STRUCTURAL 3-FOLD / DIVERSIFIED 3-FOLD)
- Each coupon: picks list, total odds, potential win, budget input
- Budget input: slider 5–50 USD/GBP/EUR (currency switcher)
- "Copy to clipboard" button per coupon
- `git commit -m "feat: coupon builder UI EN"`

### Phase 28: Markets overview section
**Section:** `#markets`
- 6 market cards (one per champion model)
- Each: market name, AUC badge, backtested ROI at 5% edge, sample size
- Expandable: shows reliability diagram (canvas, 10 bins)
- `git commit -m "feat: markets overview section EN"`

### Phase 29: Performance dashboard section
**Section:** `#performance`
- Equity curve (full 2024 backtest, animated canvas)
- Monthly ROI bar chart (canvas, last 12 months)
- Win rate donut (CSS conic-gradient)
- Key stats: total bets, win rate, avg odds, max drawdown
- Data from `/value/stats` endpoint
- `git commit -m "feat: performance dashboard section"`

### Phase 30: Subscription / Pricing section
**Section:** `#subscribe`
- 3 tiers: Free (3 picks/day) · Pro ($19/mo, all picks + coupons) · Elite ($49/mo, API access + alerts)
- Most popular: Pro tier highlighted
- CTA: "Start Free Trial" → email capture modal
- `git commit -m "feat: pricing section EN"`

### Phase 31: Email capture modal
- Triggered by CTA buttons
- Fields: Email + Plan selector
- Submit → POST `/subscribe` (stub, returns {status: "waitlist", position: N})
- Success state: "You're on the list! 🎾 We'll notify you at launch."
- `git commit -m "feat: email capture modal"`

### Phase 32: Match detail drawer
- Click any pick card → slide-up bottom sheet
- Content: full prediction breakdown, all 6 model probabilities, feature importance (top 5)
- Kelly stake calculator: input bankroll → shows stake in USD
- Close on swipe-down / ESC / backdrop click
- `git commit -m "feat: match detail drawer"`

### Phase 33: Tennis court neural canvas
- Three.js neural network (existing v7 code, EN comments)
- Switch: replace Polish labels on Three.js intro sequence
- "Analyzing 197,000 matches..." / "Calibrating edge detection..." / "Ready."
- `git commit -m "feat: Three.js intro EN"`

### Phase 34: Live score ticker
- `#score-ticker` horizontal scroll strip
- Shows 4 mock ATP live scores in progress
- Format: "Djokovic 6-4 3-2* Sinner — On Serve (2R, Wimbledon)"
- Auto-scrolls, pauses on hover
- `git commit -m "feat: live score ticker EN"`

### Phase 35: Testimonials section
- 4 testimonials from "beta users" (realistic EN names + countries)
- Format: star rating + quote + "Pro member since..."
- Rotating carousel (CSS scroll snap)
- `git commit -m "feat: testimonials section EN"`

### Phase 36: FAQ section
**Section:** `#faq`
- 8 Q&As in English:
  1. How does the model work?
  2. What is "edge" in betting?
  3. What does AUC 0.935 mean?
  4. Which bookmakers are supported?
  5. How many picks per day?
  6. What tournaments are covered?
  7. Is this guaranteed profit?
  8. How do I use Kelly criterion?
- Accordion expand/collapse
- `git commit -m "feat: FAQ section EN"`

### Phase 37: Footer
- Logo + tagline
- Links: About · Privacy · Terms · Contact
- "Powered by LightGBM · 197K ATP matches · Real-time Pinnacle odds"
- Social: Twitter/X · Telegram channel
- Disclaimer: "For entertainment purposes. Please gamble responsibly."
- `git commit -m "feat: footer EN"`

### Phase 38: Mobile responsiveness — picks grid
- Picks: 1-column on mobile, 2-col on tablet, 3-col on desktop
- Breakpoints: 480px / 768px / 1200px
- Touch gestures: swipe pick card left to dismiss, right to add to coupon
- `git commit -m "feat: mobile picks grid"`

### Phase 39: Mobile responsiveness — nav
- Hamburger menu on mobile
- Bottom nav bar: Dashboard · Picks · Markets · Performance
- Active state: lime dot
- `git commit -m "feat: mobile nav"`

### Phase 40: Mobile responsiveness — coupon builder
- Full-screen coupon modal on mobile
- Sticky CTA at bottom: "Place Bets at STS →"
- `git commit -m "feat: mobile coupon builder"`

### Phase 41: Dark/light mode toggle
- Default: dark (`#0a0a0f` bg)
- Light: `#f8f9fa` bg, dark text
- CSS `prefers-color-scheme` + manual toggle
- Persist in localStorage
- `git commit -m "feat: dark/light mode toggle"`

### Phase 42: Loading skeleton states
- Pick cards: skeleton shimmer while fetching
- Canvas charts: "Loading data..." placeholder
- Coupon section: spinner with "Analyzing today's matches..."
- `git commit -m "feat: loading skeleton states"`

### Phase 43: Error states & fallbacks
- API offline → show DEMO picks with "⚡ Demo mode — Live predictions start at 08:00 UTC"
- Rate limit hit → "Too many requests — Try again in 60 seconds"
- No picks today → "Market closed — Next picks tomorrow" + countdown timer
- `git commit -m "feat: error states and fallbacks"`

### Phase 44: Pick card animations
- Card reveal: staggered slide-up from below (0.08s per card)
- Odds count-up: 1.00 → final value, 300ms, ease-out
- Edge bar: animated fill left-to-right
- Confidence dots: sequential light-up
- `git commit -m "feat: pick card reveal animations"`

### Phase 45: Equity curve canvas (production)
- Full 2024 backtest data from `/value/history`
- Animated: line draws left-to-right over 1.5s
- Milestone dots at +10%, +30%, +50%
- Drawdown shading (red below watermark)
- Hover tooltip: date + cumulative ROI
- `git commit -m "feat: equity curve canvas production"`

### Phase 46: Monthly ROI bar chart
- 12 bars for last 12 months
- Color: lime if positive, red if negative
- Hover: month + ROI%
- Animate: bars grow from bottom 0.6s stagger
- `git commit -m "feat: monthly ROI bar chart"`

### Phase 47: Reliability diagram canvas
- 10 probability bins (0.0–0.1, ..., 0.9–1.0)
- Dots: observed frequency vs predicted probability
- Perfect calibration line (dashed)
- ECE displayed in corner
- `git commit -m "feat: reliability diagram canvas per market"`

### Phase 48: Bankroll calculator
- Input: bankroll amount + currency
- Shows: stake for each pick (Kelly %)
- Running total if all 3 coupons placed
- Expected value in currency
- `git commit -m "feat: bankroll calculator modal"`

### Phase 49: Surface filter (All/Hard/Clay/Grass)
- Filter picks + performance stats by surface
- Grass icon 🌿, Clay icon 🟤, Hard icon 🔵
- Champion model has different AUC per surface (display)
- `git commit -m "feat: surface filter"`

### Phase 50: PWA manifest + service worker (EN)
**Files:** `frontend/manifest.json`, `frontend/sw.js`
- App name: "ATPBet — Tennis Intelligence"
- Icons: 192px + 512px (generate placeholder)
- SW: cache-first for static, network-first for /api/ and /coupons/
- `git commit -m "feat: PWA manifest and service worker EN"`

---

## PHASE D — API Production Hardening (Phases 51–70)

### Phase 51: /predictions/match endpoint
```python
POST /predictions/match
Body: {player_a, player_b, surface, round, odds_a, odds_b}
Response: {
  match: str,
  surface: str,
  predictions: {
    straight: {prob: float, edge: float, ev: float, model: "v70", auc: 0.9354},
    ou39: {...},
    ...
  },
  top_value: {market, edge, ev, stake_pct},
  confidence: "HIGH"|"MEDIUM"|"LOW"
}
```
- `git commit -m "feat: /predictions/match full response"`

### Phase 52: /predictions/tournament endpoint
```python
GET /predictions/tournament?name=wimbledon&round=R2
Response: { matches: [{...}], surface, total_value_bets, best_edge }
```
- `git commit -m "feat: /predictions/tournament endpoint"`

### Phase 53: /schedule/today endpoint
```python
GET /schedule/today
Response: { matches: [{player_a, player_b, start_time_utc, tournament, surface, round}], fetched_at }
```
- `git commit -m "feat: /schedule/today endpoint"`

### Phase 54: Authentication stub (JWT)
**File:** `api/auth.py` (refactored)
- `POST /auth/register` → create user (email + password hash)
- `POST /auth/login` → return JWT
- `GET /auth/me` → user info + tier
- Free tier: 3 picks/day | Pro: unlimited | Elite: API access
- `git commit -m "feat: JWT authentication stub"`

### Phase 55: Subscription tier middleware
**File:** `api/middleware/subscription.py` (refactored)
- Free: allow `/coupons/today?limit=3`
- Pro: full access
- Elite: `GET /predictions/raw` (raw model probabilities)
- Rate limit: 60 req/min free, 300 req/min pro
- `git commit -m "feat: subscription tier middleware"`

### Phase 56: /coupons/today — real pipeline
**File:** `api/routes/coupons.py`
- Replace mock with real `run_daily_pipeline()` call
- Cache result 30min (avoid re-running expensive prediction)
- Response includes: `{coupons, generated_at, total_value_bets, top_edge, surface}`
- `git commit -m "feat: /coupons/today real pipeline"`

### Phase 57: /health endpoint enhanced
```python
GET /health → {
  status: "ok",
  models_loaded: 6,
  db_connected: true,
  last_coupon_run: ISO,
  today_n_picks: int,
  version: "1.0.0"
}
```
- `git commit -m "feat: enhanced /health endpoint"`

### Phase 58: Request logging middleware
**File:** `api/middleware/logging.py` (new)
- Log: timestamp + method + path + status + latency_ms
- Output to `logs/api.log` (rotating, max 50MB)
- `git commit -m "feat: request logging middleware"`

### Phase 59: Database connection pool
**File:** `config.py` refactored
- Use `psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10)`
- Context manager: `with get_conn() as conn:`
- `git commit -m "feat: DB connection pool"`

### Phase 60: Async prediction endpoint
**File:** `api/routes/predictions.py`
- Use `asyncio.run_in_executor` for LightGBM inference (CPU-bound)
- Ensure no event loop blocking
- `git commit -m "feat: async prediction endpoint"`

### Phase 61: /coupons/archive endpoint
```python
GET /coupons/archive?from=2026-01-01&to=2026-07-01
Response: { coupons: [{date, picks, outcome, roi}], total_roi, win_rate }
```
- Reads from `data/coupon_history.json`
- `git commit -m "feat: coupon archive endpoint"`

### Phase 62: Outcome tracker (auto-update)
**File:** `engine/outcome_tracker.py` (new)
- After match played: fetch result from ATP, compare with prediction
- Update `data/prediction_outcomes.json` with win/loss per pick
- Schedule: runs at 23:00 UTC daily
- `git commit -m "feat: outcome tracker"`

### Phase 63: CLV endpoint
```python
GET /value/clv?days=30
Response: { avg_clv: float, picks: [{match, opening, closing, clv_pct}], chart_data: [...] }
```
- `git commit -m "feat: CLV endpoint"`

### Phase 64: Player stats endpoint
```python
GET /predictions/player?name=Djokovic&surface=Grass
Response: {
  full_name, rank, age, elo, surface_elo,
  grass_form_last10: [{date, result, opp}],
  serve_stats: {ace_rate, hold_pct, 1stWon_pct},
  model_features: {key features used}
}
```
- `git commit -m "feat: player stats endpoint"`

### Phase 65: OpenAPI schema cleanup
- All endpoints: proper English descriptions
- Request/response schemas: Pydantic models with EN docstrings
- Remove all Polish from API docs
- `GET /docs` → Swagger UI showing clean EN schema
- `git commit -m "docs: clean OpenAPI schema EN"`

### Phase 66: Rate limiting with Redis
**File:** `api/middleware/rate_limit.py` (new)
- Use Redis `INCR + EXPIRE` for rate counting
- Free: 60/min, Pro: 300/min, Elite: 1000/min
- Fallback: in-memory if Redis unavailable
- `git commit -m "feat: Redis rate limiting"`

### Phase 67: /markets endpoint
```python
GET /markets
Response: {
  markets: [{
    id, label, description, auc, brier_score,
    best_surface, n_bets_2024, roi_at_5pct_edge
  }]
}
```
- Reads from `data/model_performance.json`
- `git commit -m "feat: /markets endpoint"`

### Phase 68: /tournaments/active endpoint
```python
GET /tournaments/active
Response: {tournaments: [{name, surface, round, start_date, end_date, draw_size}]}
```
- Scrapes ATP calendar or uses cached list
- `git commit -m "feat: /tournaments/active endpoint"`

### Phase 69: CORS + security headers
**File:** `api/main.py`
- Restrict CORS to `atpbet.io` in production (env var)
- Add `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- `git commit -m "security: CORS and security headers"`

### Phase 70: API versioning
- Prefix all routes with `/api/v1/`
- Keep `/` → frontend, `/health` unversioned
- Update frontend fetch URLs to `/api/v1/...`
- `git commit -m "feat: API versioning /api/v1/"`

---

## PHASE E — Data Pipeline & Automation (Phases 71–85)

### Phase 71: Automated daily schedule fetch
**File:** `tasks/daily_pipeline.py` (refactored)
- 07:30 UTC: fetch today's ATP schedule
- 08:00 UTC: run prediction pipeline → generate coupons
- 08:05 UTC: save to `coupons/daily.json` + notify subscribers
- Celery beat schedule in `tasks/celery_app.py`
- `git commit -m "feat: automated daily schedule at 07:30+08:00 UTC"`

### Phase 72: Telegram bot integration
**File:** `tasks/telegram_notifier.py` (refactored, EN)
- Message format (EN): "🎾 Today's Value Picks | Wimbledon R3\n\n..."
- Coupon format: market + odds + edge + EV
- Send to channel on new coupons
- Config: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_ID` env vars
- `git commit -m "feat: Telegram notifier EN"`

### Phase 73: Email notifier
**File:** `tasks/email_notifier.py` (new)
- SendGrid integration (or SMTP fallback)
- Daily picks email template (HTML, EN)
- Subscriber list from `data/subscribers.json`
- `git commit -m "feat: email notifier with HTML template"`

### Phase 74: Odds auto-fetch
**File:** `engine/odds_scraper.py` (Phase 18 continued)
- Cron: every 30min during active tournaments
- Fetch Pinnacle API (if available) or scrape STS
- Store: `data/live_odds_{date}.json`
- Alert if odds move >5% from opening (potential edge change)
- `git commit -m "feat: odds auto-fetch cron"`

### Phase 75: Match result scraper
**File:** `engine/results_scraper.py` (new)
- ATP Tour results page → parse completed matches
- Store in `data/results_{date}.json`
- Trigger outcome_tracker after match completes
- `git commit -m "feat: match result scraper"`

### Phase 76: Player ELO update pipeline
**File:** `scripts/update_elos.py` (new)
- After each completed match: update ELO for both players in PG
- Surfaces separately: Global ELO, Grass ELO, Clay ELO, Hard ELO
- Use `player_ratings` table
- `git commit -m "feat: ELO update pipeline"`

### Phase 77: Serve stats update pipeline
**File:** `scripts/update_serve_stats.py` (new)
- After match: parse serve stats from ATP result
- Update rolling 40-match window in `player_ratings` or separate cache table
- `git commit -m "feat: serve stats update pipeline"`

### Phase 78: Tournament season calendar
**File:** `data/atp_calendar_2026.json` (new)
```json
[
  {"name": "Wimbledon", "surface": "Grass", "start": "2026-06-29", "end": "2026-07-12", "draw_size": 128, "level": "GrandSlam"},
  {"name": "US Open", "surface": "Hard", "start": "2026-08-31", "end": "2026-09-13", "draw_size": 128, "level": "GrandSlam"},
  ...
]
```
- Full 2026 ATP calendar (all Masters + Grand Slams + 500s)
- Used by schedule fetcher + frontend
- `git commit -m "data: ATP calendar 2026"`

### Phase 79: Backfill outcomes 2024
**File:** `scripts/backfill_outcomes_2024.py` (new)
- For all 1,904 holdout matches: compute what prediction would have been
- Store in `data/prediction_outcomes_2024.json`
- Used for: backtested ROI curve, monthly performance, win rate display
- `git commit -m "data: backfill prediction outcomes 2024"`

### Phase 80: Data quality monitoring
**File:** `data/quality.py` (refactored)
- Check daily: missing match data, stale odds, ELO drift
- Alert via Telegram if quality check fails
- Log: `logs/data_quality.log`
- `git commit -m "feat: data quality monitoring"`

### Phase 81: Parquet export for frontend
**File:** `scripts/export_frontend_data.py` (new)
- Export PG → `data/frontend_stats.json` (pre-aggregated for UI)
- Monthly ROI, total bets, win rates, CLV history
- Run daily at 07:00 UTC
- `git commit -m "feat: pre-aggregated frontend data export"`

### Phase 82: Redis caching layer
**File:** `api/cache.py` (new)
- Cache keys: `coupons:today`, `schedule:today`, `markets:performance`
- TTL: coupons=4h, schedule=2h, markets=24h
- Fallback to file cache if Redis unavailable
- `git commit -m "feat: Redis caching for hot endpoints"`

### Phase 83: DB backup cron
- Daily at 02:00 UTC: `pg_dump betatp > backups/betatp_{date}.sql.gz`
- Retain last 7 days
- `git commit -m "ops: daily DB backup cron"`

### Phase 84: Monitoring & alerting
**File:** `tasks/monitoring.py` (new)
- Health check every 5min: ping `/health`
- Alert on: API down, model load failure, pipeline timeout
- Uptime tracker: `data/uptime.json`
- `git commit -m "feat: monitoring and alerting"`

### Phase 85: Docker Compose production config
**File:** `docker-compose.prod.yml` (new)
```yaml
services:
  api: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
  worker: celery -A tasks.celery_app worker
  beat: celery -A tasks.celery_app beat
  redis: redis:7-alpine
  nginx: nginx proxy with SSL
```
- `git commit -m "ops: docker-compose prod config"`

---

## PHASE F — Frontend Polish & Advanced Features (Phases 86–115)

### Phase 86: Onboarding wizard (EN)
- 3-step: "What's your bankroll?" / "Preferred surface?" / "Alert preference?"
- localStorage persist
- Progress dots indicator
- `git commit -m "feat: onboarding wizard EN"`

### Phase 87: Push notifications (EN)
- Permission prompt after onboarding step 3
- Notification on new picks: "🎾 3 value picks available for Wimbledon QF"
- Service Worker push handler
- `git commit -m "feat: push notifications EN"`

### Phase 88: Keyboard shortcuts
- `P` → go to Picks, `M` → Markets, `D` → Dashboard, `Esc` → close modal
- Tooltip hint bar: "Press P for Picks · M for Markets"
- `git commit -m "feat: keyboard shortcuts"`

### Phase 89: Share pick button
- "Share" button on each pick card
- Generates: "🎾 {Player A} vs {Player B} | Over 36.5 Games @ 1.85 | Edge +17% | atpbet.io"
- Native share API → fallback copy to clipboard
- `git commit -m "feat: share pick button"`

### Phase 90: Bet slip (add to coupon)
- "+" button on pick card → adds to custom coupon builder
- Coupon builder shows running total odds, potential win
- Max 5 picks per coupon
- "Clear All" + "Build Coupon" CTA
- `git commit -m "feat: bet slip coupon builder"`

### Phase 91: Model explainability overlay
- Click "Why?" on any pick → shows top 5 features contributing to prediction
- Feature importance bars (horizontal)
- EN labels: "Serve Dominance", "Elo Differential", "Surface Form", "Opening Odds", "Age Factor"
- `git commit -m "feat: model explainability overlay"`

### Phase 92: Tournament bracket viewer
- Visual bracket for current tournament (Wimbledon R3 example)
- Click player → shows their prediction profile
- Win probability overlay on bracket
- `git commit -m "feat: tournament bracket viewer"`

### Phase 93: Odds movement chart
- Shows opening vs current odds for each pick
- Arrow indicator: ↑ odds drifted up (value decreasing) / ↓ shorter (sharp action)
- CLV indicator if match completed
- `git commit -m "feat: odds movement chart"`

### Phase 94: Leaderboard / top picks
**Section:** `#leaderboard`
- Top 10 picks by EV this month
- Each: match, market, edge, actual result (✅/❌)
- Filter: surface, month
- `git commit -m "feat: leaderboard section"`

### Phase 95: Surface performance deep-dive
**Section:** `#surface-performance`
- AUC by surface per model (6×3 grid)
- ROI by surface chart
- "Best surface: Grass (v70 AUC 0.951)"
- `git commit -m "feat: surface performance section"`

### Phase 96: Draw analysis widget
- Shows tournament draw difficulty for top seeds
- "Sinner's path to final: difficulty score 7.2/10"
- Based on ELO of potential opponents per round
- `git commit -m "feat: draw analysis widget"`

### Phase 97: Player head-to-head card
- On match detail drawer: H2H last 5 meetings
- Surface-specific H2H
- "Djokovic leads H2H 27-23 (Grass: 4-2)"
- `git commit -m "feat: H2H card in match detail"`

### Phase 98: Alert settings panel
- Threshold alerts: "Notify me when edge > X%"
- Surface filter: Grass / Clay / Hard / All
- Market filter: checkboxes for 6 markets
- Stores in localStorage
- `git commit -m "feat: alert settings panel"`

### Phase 99: Currency selector
- USD / EUR / GBP / PLN
- All stake calculations converted
- Exchange rates from Open Exchange Rates API (fallback: fixed)
- `git commit -m "feat: currency selector"`

### Phase 100: Historical performance browser
**Section:** `#history`
- Browse picks by week/month
- Filter: won/lost/pending
- Sort: by edge, EV, odds
- `git commit -m "feat: historical performance browser"`

### Phase 101: Compare picks mode
- Select 2 picks → side-by-side comparison
- Metrics: edge, EV, model confidence, surface form
- `git commit -m "feat: compare picks mode"`

### Phase 102: Match countdown timer
- On pick card: "Starts in 2h 43m"
- Lime color when <1h
- Red flash when live (in-play)
- `git commit -m "feat: match countdown timer"`

### Phase 103: Live in-play indicator
- Real-time score fetch (mock for now, ready for ATP API)
- Pick card turns amber if match is live: "🔴 LIVE 6-4 2-3*"
- Auto-dismiss completed picks
- `git commit -m "feat: live in-play indicator"`

### Phase 104: GSAP animation polish pass
- Audit all transitions: smooth 60fps on mobile
- Remove jank: replace `setInterval` with GSAP ticker
- Intro sequence: tune timing (logo 0.4s → tagline 0.6s → stats 0.8s → picks 1.0s)
- `git commit -m "perf: GSAP animation polish"`

### Phase 105: Canvas performance optimization
- `requestAnimationFrame` throttling for equity curve (60fps cap)
- Offscreen canvas for heavy neural background
- Resize observer for responsive canvas
- `git commit -m "perf: canvas performance optimisation"`

### Phase 106: Font & typography system
- Import: `Inter` (UI) + `JetBrains Mono` (numbers/odds)
- Type scale: 12/14/16/20/28/40/56px
- All monetary values: JetBrains Mono, tabular nums
- `git commit -m "style: typography system"`

### Phase 107: Icon system (SVG sprites)
- Custom SVG icons: tennis ball, racquet, trophy, chart, lock, bolt
- Inline SVG sprite in `<head>`, referenced via `<use>`
- Replace all emoji icons with SVG
- `git commit -m "style: SVG icon system"`

### Phase 108: Micro-interactions
- Button press: scale(0.97) + shadow reduction
- Card hover: translateY(-2px) + shadow
- Odds change: flash animation (lime pulse)
- `git commit -m "style: micro-interactions"`

### Phase 109: Accessibility (WCAG AA)
- Keyboard navigation: all interactive elements focusable
- ARIA labels on all icons, canvas elements
- Color contrast: all text ≥4.5:1
- Screen reader: picks readable as table
- `git commit -m "a11y: WCAG AA compliance"`

### Phase 110: SEO meta tags
```html
<title>ATPBet — ATP Tennis Betting Intelligence</title>
<meta name="description" content="AI-powered ATP tennis value betting. 0.935 AUC. +58.7% ROI backtested. Real edge vs Pinnacle.">
<meta property="og:image" content="/og-image.png">
<link rel="canonical" href="https://atpbet.io/">
```
- `git commit -m "seo: meta tags and og image"`

### Phase 111: Performance optimization
- Inline critical CSS (above-fold styles)
- Defer Three.js load (not needed on initial paint)
- `font-display: swap` for Google Fonts
- Target: Lighthouse Performance > 85
- `git commit -m "perf: critical CSS and deferred loading"`

### Phase 112: Cross-browser testing
- Chrome + Safari + Firefox + Edge
- Fix: Safari `backdrop-filter` prefix
- Fix: Firefox canvas anti-aliasing
- `git commit -m "compat: cross-browser fixes"`

### Phase 113: Error boundary + retry
- API fetch retry: 3 attempts with exponential backoff (500ms, 1s, 2s)
- Show: "Retrying... (2/3)" in pick card skeleton
- On final failure: show cached last picks with "⚡ Showing yesterday's analysis"
- `git commit -m "feat: API retry with backoff and stale cache"`

### Phase 114: Analytics stub
- `gtag()` events: page_view, pick_card_click, coupon_view, subscribe_click
- Privacy-first: no PII, no cookies without consent
- Consent banner (EN, GDPR-compliant)
- `git commit -m "feat: analytics stub with consent banner"`

### Phase 115: Print / PDF export
- "Download Coupons" button → print-optimized CSS
- Coupon format: A5, black/white compatible
- `git commit -m "feat: print/PDF export for coupons"`

---

## PHASE G — Testing, Docs & Launch (Phases 116–130)

### Phase 116: Full test suite update (EN)
- All test strings → English
- `tests/test_prediction_service.py` — 15 tests
- `tests/test_value_detector.py` — 10 tests
- `tests/test_champion_stack.py` — 6 model loads + inference
- `tests/test_feature_builder.py` — 20 tests
- Target: 200 passing tests
- `git commit -m "test: full test suite EN, 200 passing"`

### Phase 117: Integration test — full pipeline
- `tests/integration/test_full_pipeline.py`
- Test: fetch schedule → build features → predict → detect value → build coupons
- Assert: at least 1 value bet on typical Wimbledon day (mocked data)
- `git commit -m "test: full pipeline integration test"`

### Phase 118: Load test
- `locust -f tests/load/locustfile.py`
- Target: 100 concurrent users, p95 latency < 500ms on `/coupons/today`
- `git commit -m "test: load test with locust"`

### Phase 119: API documentation
**File:** `docs/API.md` (full EN rewrite)
- All endpoints: description, request/response examples
- Authentication guide
- Rate limits
- Error codes
- `git commit -m "docs: API documentation EN"`

### Phase 120: User guide
**File:** `docs/USER_GUIDE.md` (new EN)
- What is ATPBet?
- How to read a pick card
- How edge and EV work
- How to use Kelly criterion
- Which markets are best for your strategy
- `git commit -m "docs: user guide EN"`

### Phase 121: Developer setup guide
**File:** `README.md` (full EN rewrite)
- Quick start: `git clone → pip install → uvicorn`
- Model training: champion stack
- DB setup
- `git commit -m "docs: README.md full EN rewrite"`

### Phase 122: CHANGELOG
**File:** `CHANGELOG.md` (new)
- v1.0.0 (2026-07-01): initial release
- 6 champion models, 197K matches, automated daily coupons
- `git commit -m "docs: CHANGELOG v1.0.0"`

### Phase 123: Vercel config
**File:** `vercel.json` (review + update)
```json
{
  "buildCommand": "",
  "outputDirectory": "frontend",
  "framework": null,
  "routes": [{"handle": "filesystem"}, {"src": "/(.*)", "dest": "/index.html"}]
}
```
- Ensure SPA routing works (all paths → index.html)
- `git commit -m "ops: Vercel config SPA routing"`

### Phase 124: Environment variables
**File:** `.env.example` (EN update)
```
DATABASE_URL=postgresql://postgres:betatp2026@localhost/betatp
REDIS_URL=redis://localhost:6379/0
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
JWT_SECRET=
CORS_ORIGINS=https://atpbet.io,https://atpbet.vercel.app
```
- `git commit -m "ops: env vars documentation"`

### Phase 125: CI/CD pipeline
**File:** `.github/workflows/ci.yml` (update)
- On PR: pytest + lint (ruff) + type check (mypy)
- On push to main: deploy to Vercel (auto)
- Notify Telegram on failed CI
- `git commit -m "ops: CI/CD pipeline update"`

### Phase 126: Pre-launch checklist
Create `docs/LAUNCH_CHECKLIST.md`:
- [ ] All API endpoints return EN responses
- [ ] Frontend has zero Polish text
- [ ] Champion models load in <5s
- [ ] `/coupons/today` returns valid data
- [ ] Mobile: picks readable on 375px iPhone SE
- [ ] Lighthouse: Performance >85, Accessibility >90
- [ ] Test on Safari iOS
- [ ] DB backup verified
- [ ] Telegram notifications working
- `git commit -m "docs: launch checklist"`

### Phase 127: Smoke test production
- Deploy to Vercel from `main`
- Run: `curl https://atpbet.vercel.app/health`
- Run: `curl https://atpbet.vercel.app/api/v1/coupons/today`
- Visual check: picks section, equity curve, mobile nav
- `git commit -m "test: production smoke test PASS"`

### Phase 128: Beta user invite flow
- Email template: "You're invited to ATPBet Early Access"
- Landing page `/waitlist` → email form
- POST `/auth/waitlist` → store email in PG `waitlist` table
- `git commit -m "feat: beta invite flow"`

### Phase 129: Analytics dashboard (internal)
**File:** `frontend/admin.html` (new, password-protected)
- Shows: DAU, API calls/day, top picks by click, subscription signups
- Powered by `/api/v1/admin/stats` (JWT admin only)
- `git commit -m "feat: internal analytics dashboard"`

### Phase 130: Soft launch
- Announce on Twitter/X: "🎾 ATPBet is live. AI-powered ATP value betting. 0.935 AUC. Free picks daily."
- Telegram channel first post
- Product Hunt draft
- `git commit -m "launch: v1.0.0 soft launch"`

---

## PHASE H — Post-Launch & Monetization (Phases 131–140)

### Phase 131: Stripe subscription integration
**File:** `api/routes/billing.py` (new)
- `POST /billing/create-checkout` → Stripe checkout session
- `POST /billing/webhook` → handle subscription events
- Tiers: Free / Pro ($19/mo) / Elite ($49/mo)
- `git commit -m "feat: Stripe billing integration"`

### Phase 132: Pro member features unlock
- After payment: JWT updated with `tier: "pro"`
- Unlock: all 6 champion markets, full coupon builder, CLV tracker
- `git commit -m "feat: pro tier unlock"`

### Phase 133: Elite API access
- Elite tier: generate API key
- `/api/v1/raw-predictions` — raw model probabilities (all 6 models)
- Rate: 1000 req/min
- `git commit -m "feat: elite API access tier"`

### Phase 134: Daily picks email campaign
- Automated: send picks email at 08:10 UTC to Pro subscribers
- Template: 3 picks, odds, edge, recommended stake
- Unsubscribe link
- `git commit -m "feat: automated daily picks email"`

### Phase 135: Affiliate link tracking
- Each pick shows: "Place at [Pinnacle] [STS] [Bet365]"
- Affiliate UTM params per bookmaker
- Click tracking in `data/affiliate_clicks.json`
- `git commit -m "feat: bookmaker affiliate link tracking"`

### Phase 136: Referral program
- Refer a friend → 1 month Pro free
- Unique referral link: `atpbet.io/?ref=ABC123`
- Track conversions in PG
- `git commit -m "feat: referral program"`

### Phase 137: Next tournament preparation
- After Wimbledon ends: auto-detect next tournament (US Open hardcourt)
- Update `data/atp_calendar_2026.json` with results
- Switch model surface bias: Grass → Hard
- Test: at least 1 value bet in US Open Week 1 simulation
- `git commit -m "feat: next tournament auto-preparation"`

### Phase 138: Model retraining pipeline
**File:** `scripts/retrain_champions.py` (new)
- Monthly: add new matches to PG (from season)
- Retrain v70/v80 champion models with latest data
- Compare AUC: if degraded >2% → alert + skip deploy
- Auto-backup old models before overwrite
- `git commit -m "feat: monthly model retraining pipeline"`

### Phase 139: Feature request tracker
**File:** `docs/ROADMAP.md` (new)
- Q3 2026: In-play predictions, WTA coverage, Court speed analysis
- Q4 2026: Options-style multi-leg parlays, DraftKings integration
- 2027: Global tennis (Challenger), Tennis Abstract integration
- `git commit -m "docs: product roadmap"`

### Phase 140: v2.0 architecture planning
- WTA model training (mirrored v41–v80 pipeline for women's tour)
- Live odds API integration (Betfair Exchange)
- Real-time ELO updates (not batch)
- GraphQL API layer
- Mobile native app (React Native) with push picks
- `git commit -m "docs: v2.0 architecture plan"`

---

## EXECUTION ORDER

| Phase Group | Phases | Priority | Est. Time |
|-------------|--------|----------|-----------|
| A — Foundation | 1–10 | 🔴 CRITICAL | 4h |
| B — Validation | 11–20 | 🔴 CRITICAL | 3h |
| C — Frontend | 21–50 | 🔴 CRITICAL | 8h |
| D — API Hardening | 51–70 | 🟡 HIGH | 6h |
| E — Data Pipeline | 71–85 | 🟡 HIGH | 4h |
| F — Polish | 86–115 | 🟢 MEDIUM | 6h |
| G — Testing/Docs | 116–130 | 🔴 CRITICAL | 4h |
| H — Monetization | 131–140 | 🟢 MEDIUM | 4h |

**TOTAL: ~39h of focused work**

## START IMMEDIATELY

Execute phases in order: **A (1–10) → B (11–20) → C (21–50) → G (116–130 smoke test) → D (51–70) → E (71–85) → F (86–115) → H (131–140)**

Deploy to Vercel is automatic on every push to `main`.

---

*Plan saved: 2026-07-01 | atpbet v1.0.0 | 140 phases | English-only*
