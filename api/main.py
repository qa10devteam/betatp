"""
api/main.py — FastAPI application entry point dla betatp.io
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routes.coupons import router as coupons_router
from api.routes.predictions import router as predictions_router
from api.routes.live import router as live_router
from api.schemas import HealthResponse

app = FastAPI(
    title="betatp.io API",
    description="Profesjonalne kupony tenisowe ATP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware)

app.include_router(coupons_router, prefix="/coupons", tags=["coupons"])
app.include_router(predictions_router, prefix="/predictions", tags=["predictions"])
app.include_router(live_router, prefix="/live", tags=["live"])


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
