"""
config.py — Centralised configuration for atpbet.io
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
COUPONS_DIR = BASE_DIR / "coupons"
LOGS_DIR = BASE_DIR / "logs"

# ── Database ───────────────────────────────────────────────────────────────────
PG_DSN = os.getenv(
    "DATABASE_URL",
    "host=localhost dbname=betatp user=postgres password=betatp2026"
)

# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Notifications ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

# ── App ────────────────────────────────────────────────────────────────────────
APP_VERSION = "1.0.0"
APP_NAME = "atpbet.io"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

# ── Model thresholds ───────────────────────────────────────────────────────────
DEFAULT_EDGE_THRESHOLD = 0.04   # 4% minimum edge to flag as value bet
MAX_KELLY_FRACTION = 0.05       # 5% max bankroll per bet (half-Kelly cap)
COUPON_BUDGET_DEFAULT = 15.0    # Default coupon budget in USD
N_COUPONS = 3                   # Number of coupons to generate daily

# ── Champion model registry ────────────────────────────────────────────────────
CHAMPION_MODELS = {
    "straight": "lgbm_v70_is_straight_20260701_0806.joblib",
    "fatigue5": "lgbm_v31_fatigue_5sets_20260629_1957.joblib",
    "ou39":     "lgbm_v54_ou39.5_full_20260630_1705.joblib",
    "ou36":     "lgbm_v23_ou36.5_20260629_1938.joblib",
    "hcp9":     "lgbm_v80_hcp_9_20260701_1118.joblib",
    "ou33":     "lgbm_v39_cross_over33_20260629_2010.joblib",
}

MARKET_LABELS = {
    "straight": "Straight Sets (2:0 or 3:0)",
    "fatigue5": "Full Distance (5 Sets)",
    "ou39":     "Over/Under 39.5 Games",
    "ou36":     "Over/Under 36.5 Games",
    "hcp9":     "Game Handicap >9.5",
    "ou33":     "Over/Under 33.5 Games",
}

MARKET_AUCS = {
    "straight": 0.9354,
    "fatigue5": 0.9195,
    "ou39":     0.9276,
    "ou36":     0.8925,
    "hcp9":     0.8360,
    "ou33":     0.8326,
}

MARKET_DESCRIPTIONS = {
    "straight": "P(match ends in minimum sets: 2:0 or 3:0). Best model in stack.",
    "fatigue5": "P(match goes full distance: 5 sets). Key for Grand Slams.",
    "ou39":     "Total games over/under 39.5. High volume market.",
    "ou36":     "Total games over/under 36.5. Moderate dominance required.",
    "hcp9":     "Winner wins by more than 9.5 games. Dominance indicator.",
    "ou33":     "Total games over/under 33.5. Fastest matches only.",
}
