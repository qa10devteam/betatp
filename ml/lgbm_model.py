"""
ml/lgbm_model.py — LightGBMPredictor for betatp.io

Standalone LightGBM classifier with isotonic calibration,
save/load, and feature importance helpers.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss

import lightgbm as lgb

logger = logging.getLogger(__name__)

_DEFAULT_PARAMS: dict = {
    "n_estimators": 1000,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "binary",
    "metric": "binary_logloss",
    "verbosity": -1,
    "n_jobs": -1,
}


class LightGBMPredictor:
    """
    Wraps lightgbm.LGBMClassifier with optional isotonic calibration.

    Usage
    -----
    pred = LightGBMPredictor()
    metrics = pred.train(X_train, y_train, X_val, y_val)
    pred.calibrate(X_cal, y_cal)
    proba = pred.predict_proba(X_test)   # shape (N, 2)
    pred.save("models/lgbm_v1.joblib")
    pred2 = LightGBMPredictor.load("models/lgbm_v1.joblib")
    """

    def __init__(self, params: Optional[dict] = None):
        merged = {**_DEFAULT_PARAMS}
        if params:
            merged.update(params)
        self.params = merged
        self._model: Optional[lgb.LGBMClassifier] = None
        self._calibrator = None          # IsotonicCalibrator or None
        self._feature_names: Optional[list] = None
        self._is_fitted: bool = False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        X_train,
        y_train,
        X_val=None,
        y_val=None,
    ) -> dict:
        """
        Train the LightGBM model.

        Parameters
        ----------
        X_train : array-like or pd.DataFrame
        y_train : array-like, binary labels
        X_val   : optional validation features
        X_val   : optional validation labels (enables early stopping)

        Returns
        -------
        dict with keys: auc, log_loss  (computed on training set, or val if provided)
        """
        params = {k: v for k, v in self.params.items()}
        has_val = X_val is not None and y_val is not None

        if has_val:
            self._model = lgb.LGBMClassifier(**params)
            self._model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[
                    lgb.early_stopping(stopping_rounds=50, verbose=False),
                    lgb.log_evaluation(-1),
                ],
            )
        else:
            # No validation — cap estimators at 300 to avoid overfit
            no_es_params = {**params, "n_estimators": min(params.get("n_estimators", 300), 300)}
            self._model = lgb.LGBMClassifier(**no_es_params)
            self._model.fit(X_train, y_train)

        # Store feature names if DataFrame
        if hasattr(X_train, "columns"):
            self._feature_names = list(X_train.columns)

        self._is_fitted = True

        # Compute metrics on val (if available) else train
        eval_X = X_val if has_val else X_train
        eval_y = y_val if has_val else y_train

        proba = self._model.predict_proba(eval_X)[:, 1]
        metrics: dict = {}
        try:
            metrics["auc"] = float(roc_auc_score(eval_y, proba))
        except Exception:
            metrics["auc"] = float("nan")
        try:
            metrics["log_loss"] = float(log_loss(eval_y, proba))
        except Exception:
            metrics["log_loss"] = float("nan")

        split = "val" if has_val else "train"
        logger.info(
            "LightGBMPredictor trained — %s AUC=%.4f  log_loss=%.4f",
            split,
            metrics["auc"],
            metrics["log_loss"],
        )
        return metrics

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_proba(self, X) -> np.ndarray:
        """
        Return probability estimates of shape (N, 2).
        Column 0: P(class=0), Column 1: P(class=1).
        If calibrator is fitted, probabilities in column 1 are calibrated.
        """
        self._check_fitted()
        raw_proba = self._model.predict_proba(X)  # (N, 2)

        if self._calibrator is not None:
            cal = self._calibrator.transform(raw_proba[:, 1])
            raw_proba = np.column_stack([1.0 - cal, cal])

        return raw_proba

    def predict(self, X) -> np.ndarray:
        """Return binary predictions (threshold 0.5)."""
        proba = self.predict_proba(X)[:, 1]
        return (proba >= 0.5).astype(int)

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def calibrate(self, X_cal, y_cal) -> None:
        """
        Fit an IsotonicCalibrator on calibration data.
        After this call, predict_proba() returns calibrated probabilities.
        """
        self._check_fitted()
        from ml.calibration import IsotonicCalibrator  # local import to avoid circular

        raw_proba = self._model.predict_proba(X_cal)[:, 1]
        self._calibrator = IsotonicCalibrator()
        self._calibrator.fit(raw_proba, np.asarray(y_cal))
        logger.info("LightGBMPredictor: isotonic calibrator fitted on %d samples.", len(y_cal))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize the predictor (model + calibrator) to *path* via joblib."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("LightGBMPredictor saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "LightGBMPredictor":
        """Deserialize a previously saved LightGBMPredictor from *path*."""
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected LightGBMPredictor, got {type(obj)}")
        logger.info("LightGBMPredictor loaded from %s", path)
        return obj

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def feature_importance(self) -> pd.Series:
        """
        Return feature importances as a pd.Series sorted descending.
        Uses LightGBM's built-in 'gain' importance.
        """
        self._check_fitted()
        importances = self._model.feature_importances_

        if self._feature_names and len(self._feature_names) == len(importances):
            index = self._feature_names
        else:
            index = [f"f{i}" for i in range(len(importances))]

        return pd.Series(importances, index=index, name="importance").sort_values(ascending=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_fitted(self) -> None:
        if not self._is_fitted or self._model is None:
            raise RuntimeError("LightGBMPredictor is not fitted yet. Call train() first.")

    def __repr__(self) -> str:
        status = "fitted" if self._is_fitted else "unfitted"
        cal = "calibrated" if self._calibrator is not None else "uncalibrated"
        return f"LightGBMPredictor({status}, {cal})"
