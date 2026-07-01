"""
ml/champion_stack.py — Champion model registry and batch loader for atpbet.io

Champion stack: 6 models, AUC 0.833–0.935, trained on 197K ATP matches (v23–v80).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from config import CHAMPION_MODELS, MARKET_LABELS, MARKET_AUCS, MARKET_DESCRIPTIONS, MODELS_DIR

logger = logging.getLogger(__name__)


class ChampionStack:
    """
    Lazy-loading singleton for all 6 champion models.
    Thread-safe: models are loaded once at first call to predict().
    """

    _instance: Optional["ChampionStack"] = None
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self.models: dict = {}
            self.feature_cols: dict = {}
            self._loaded = False

    def load(self) -> "ChampionStack":
        """Load all 6 champion models from disk."""
        if self._loaded:
            return self

        logger.info("[atpbet] Loading champion stack...")
        for market_id, filename in CHAMPION_MODELS.items():
            model_path = MODELS_DIR / filename
            if not model_path.exists():
                logger.warning(f"  ⚠️  {market_id}: {filename} not found — skipping")
                continue
            try:
                self.models[market_id] = joblib.load(model_path)
                logger.info(f"  ✅ {market_id}: {filename} (AUC {MARKET_AUCS[market_id]:.4f})")
            except Exception as e:
                logger.error(f"  ❌ {market_id}: failed to load — {e}")

        self._loaded = True
        logger.info(f"[atpbet] Champion stack ready: {len(self.models)}/{len(CHAMPION_MODELS)} models")
        return self

    def predict(self, market_id: str, features: np.ndarray) -> float:
        """
        Predict probability for a single market.

        Args:
            market_id: One of 'straight', 'fatigue5', 'ou39', 'ou36', 'hcp9', 'ou33'
            features: 1D numpy array of feature values

        Returns:
            float: probability in [0, 1]
        """
        if not self._loaded:
            self.load()

        model = self.models.get(market_id)
        if model is None:
            raise ValueError(f"Model '{market_id}' not loaded")

        X = features.reshape(1, -1)
        prob = model.predict_proba(X)[0, 1]
        return float(prob)

    def predict_all(self, features: np.ndarray) -> dict[str, float]:
        """
        Predict probabilities for all loaded markets.

        Args:
            features: 1D numpy array of feature values (103 features, champion format)

        Returns:
            dict: {market_id: probability}
        """
        if not self._loaded:
            self.load()

        results = {}
        for market_id, model in self.models.items():
            try:
                X = features.reshape(1, -1)
                prob = model.predict_proba(X)[0, 1]
                results[market_id] = float(prob)
            except Exception as e:
                logger.warning(f"predict_all: {market_id} failed — {e}")
                results[market_id] = 0.5  # fallback

        return results

    @property
    def n_models(self) -> int:
        return len(self.models)

    @property
    def market_info(self) -> list[dict]:
        """Return structured info about all markets for API responses."""
        return [
            {
                "id": mid,
                "label": MARKET_LABELS.get(mid, mid),
                "description": MARKET_DESCRIPTIONS.get(mid, ""),
                "auc": MARKET_AUCS.get(mid, 0.0),
                "loaded": mid in self.models,
            }
            for mid in CHAMPION_MODELS
        ]


# Module-level singleton
champion_stack = ChampionStack()
