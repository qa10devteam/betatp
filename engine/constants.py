"""
engine/constants.py — Wszystkie stałe matematyczne silnika betatp.io
Źródło: specs/ (68 dokumentów) — Elo, Kelly, Monte Carlo, surface blend
"""

# ─── Elo K-Factors per tournament level ───────────────────────────────────────
# G=Grand Slam, M=Masters 1000, 500=ATP 500, 250=ATP 250, D=Davis Cup, F=Finals
K_FACTORS: dict[str, float] = {
    "G": 48,
    "M": 36,
    "500": 28,
    "250": 24,
    "D": 16,
    "F": 40,
}

# ─── Surface Elo delta adjustments ────────────────────────────────────────────
# Additive correction to overall Elo for surface-specific rating
SURFACE_DELTAS: dict[str, float] = {
    "Hard": 0.0,
    "Clay": -0.034,
    "Grass": 0.015,
    "Indoor Hard": 0.008,
}

# ─── Elo baseline parameters ──────────────────────────────────────────────────
ELO_MEAN: float = 1500.0          # Starting/mean Elo for new players
ELO_FLOOR: float = 1000.0         # Minimum possible Elo rating
ELO_CEILING: float = 2800.0       # Maximum possible Elo rating
ELO_HALFLIFE_DAYS: int = 365      # Inactivity decay half-life (days)
ELO_INITIAL_SCALE: int = 400      # Logistic scale denominator (σ)

# ─── Monte Carlo simulation ────────────────────────────────────────────────────
MC_N_SIMULATIONS: int = 100_000   # Number of MC iterations per prediction

# ─── Kelly staking ────────────────────────────────────────────────────────────
KELLY_FRACTION: float = 0.5       # Fractional Kelly (half-Kelly) multiplier

# ─── EV / odds filters ────────────────────────────────────────────────────────
MIN_EV_THRESHOLD: float = 0.02    # Minimum expected value % to flag a bet (+2%)
MIN_ODDS: float = 1.30            # Minimum decimal odds accepted
MAX_ODDS: float = 5.00            # Maximum decimal odds accepted

# ─── Surface blend / Bayesian shrinkage ───────────────────────────────────────
SURFACE_BLEND_N0: int = 30        # Prior weight (matches) for surface blend
EWMA_ALPHA: float = 0.15          # Exponential weighted moving average alpha

# ─── Head-to-head Bayesian prior ──────────────────────────────────────────────
H2H_PRIOR_ALPHA: int = 3          # Beta-Binomial prior α (pseudo wins)
H2H_PRIOR_BETA: int = 3           # Beta-Binomial prior β (pseudo losses)

# ─── Serve / return stat validation ranges ────────────────────────────────────
SERVE_WIN_PCT_MIN: float = 0.30
SERVE_WIN_PCT_MAX: float = 0.95
ACE_PCT_MIN: float = 0.00
ACE_PCT_MAX: float = 0.30

# ─── Tournament level mapping ─────────────────────────────────────────────────
TOURNEY_LEVEL_MAP: dict[str, str] = {
    "G": "G",   # Grand Slam
    "M": "M",   # Masters 1000
    "A": "250", # ATP 250/500 (legacy)
    "D": "D",   # Davis Cup
    "F": "F",   # ATP Finals
    "C": "250", # Challenger (mapped to 250 bucket)
    "S": "500", # ATP 500 series (legacy S code)
    "500": "500",
    "250": "250",
}

# ─── Surface normalisation map ────────────────────────────────────────────────
SURFACE_NORM_MAP: dict[str, str] = {
    "Hard": "Hard",
    "hard": "Hard",
    "HARD": "Hard",
    "Clay": "Clay",
    "clay": "Clay",
    "CLAY": "Clay",
    "Grass": "Grass",
    "grass": "Grass",
    "GRASS": "Grass",
    "Carpet": "Hard",   # treat Carpet as Hard (legacy surface)
    "carpet": "Hard",
    "Indoor Hard": "Hard",
    "indoor hard": "Hard",
}

# ─── Minimum matches threshold ────────────────────────────────────────────────
MIN_MATCHES_THRESHOLD: int = 10   # Players with fewer matches flagged as outliers

# ─── Round ordering (for bracket logic) ───────────────────────────────────────
ROUND_ORDER: dict[str, int] = {
    "R128": 1, "R64": 2, "R32": 3, "R16": 4,
    "QF": 5, "SF": 6, "F": 7, "RR": 3,  # RR = round-robin ~ R32 level
    "BR": 6,  # Bronze/3rd place
}
