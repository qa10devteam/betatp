"""
api/main.py — FastAPI application entry point dla atpbet.io
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes.coupons import router as coupons_router
from api.routes.predictions import router as predictions_router
from api.routes.live import router as live_router
from api.schemas import HealthResponse

# ── Optional routers ────────────────────────────────────────────────────────
try:
    from api.routes.value import router as value_router
except Exception:
    value_router = None  # type: ignore[assignment]

try:
    from api.routes.stats import router as stats_router
except Exception:
    stats_router = None  # type: ignore[assignment]

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="atpbet.io API",
    description="ATP Tennis Betting Intelligence",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware)

# ── TierLimitMiddleware ────────────────────────────────────────────────────────
try:
    from api.middleware.subscription import TierLimitMiddleware
    app.add_middleware(TierLimitMiddleware)
except Exception:
    pass

# ── Include routers under /api/v1/ ────────────────────────────────────────────
app.include_router(coupons_router, prefix="/api/v1/coupons", tags=["coupons"])
app.include_router(predictions_router, prefix="/api/v1/predictions", tags=["predictions"])
app.include_router(live_router, prefix="/api/v1/live", tags=["live"])

# Legacy paths (keep for backwards compat)
app.include_router(coupons_router, prefix="/coupons", tags=["coupons-legacy"], include_in_schema=False)
app.include_router(predictions_router, prefix="/predictions", tags=["predictions-legacy"], include_in_schema=False)

if value_router is not None:
    app.include_router(value_router)

if stats_router is not None:
    app.include_router(stats_router)


# ── Startup event ──────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    print("[ATPBet] API starting up...")
    print("[ATPBet] Health:     http://localhost:8000/health")
    print("[ATPBet] Dashboard:  http://localhost:8000/")
    print("[ATPBet] Docs:       http://localhost:8000/docs")


# ── Frontend ───────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serves główny dashboard (frontend/index.html)."""
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index, media_type="text/html")


# ── Static data files ──────────────────────────────────────────────────────────
@app.get("/data/{filename}", include_in_schema=False)
async def serve_data(filename: str):
    """Serves pliki danych (JSON / CSV) z katalogu data/."""
    # Path traversal protection
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not (filename.endswith(".json") or filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Only .json and .csv files are served")

    # Obsługa v12 → fallback do v4 gdy brak v12
    if filename == "backtest_v12.json":
        f = DATA_DIR / "backtest_v12.json"
        if not f.exists():
            f = DATA_DIR / "backtest_v4.json"
    else:
        f = DATA_DIR / filename

    if not f.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")

    media = "application/json" if filename.endswith(".json") else "text/csv"
    return FileResponse(f, media_type=media)


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — lekki, NIE triggeruje ładowania modelu ML."""
    return {"status": "ok", "version": "v10.1"}

