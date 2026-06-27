"""
ml/calibration.py — IsotonicCalibrator for betatp.io

Wraps sklearn's IsotonicRegression with clipping, reliability curves,
and joblib-based persistence.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

logger = logging.getLogger(__name__)


class IsotonicCalibrator:
    """
    Calibrates raw model probabilities using isotonic regression.

    Usage
    -----
    cal = IsotonicCalibrator()
    cal.fit(raw_proba, y_true)
    cal_proba = cal.transform(new_raw_proba)   # clipped to [0.01, 0.99]

    # or in one shot:
    cal_proba = cal.fit_transform(raw_proba, y_true)

    # reliability diagnostics:
    diag = cal.reliability_curve(raw_proba, y_true, n_bins=10)
    """

    def __init__(self) -> None:
        self._iso: Optional[IsotonicRegression] = None
        self._is_fitted: bool = False

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def fit(self, y_proba: np.ndarray, y_true: np.ndarray) -> "IsotonicCalibrator":
        """
        Fit isotonic regression on raw probabilities.

        Parameters
        ----------
        y_proba : 1-D array of raw model probabilities (P(class=1))
        y_true  : 1-D array of binary ground-truth labels

        Returns
        -------
        self
        """
        y_proba = np.asarray(y_proba, dtype=float).ravel()
        y_true = np.asarray(y_true, dtype=float).ravel()

        self._iso = IsotonicRegression(out_of_bounds="clip")
        self._iso.fit(y_proba, y_true)
        self._is_fitted = True
        logger.info("IsotonicCalibrator fitted on %d samples.", len(y_true))
        return self

    def transform(self, y_proba: np.ndarray) -> np.ndarray:
        """
        Calibrate probabilities and clip to [0.01, 0.99].

        Parameters
        ----------
        y_proba : 1-D array of raw model probabilities

        Returns
        -------
        np.ndarray, same shape as y_proba, values in [0.01, 0.99]
        """
        self._check_fitted()
        y_proba = np.asarray(y_proba, dtype=float).ravel()
        calibrated = self._iso.predict(y_proba)
        return np.clip(calibrated, 0.01, 0.99)

    def fit_transform(self, y_proba: np.ndarray, y_true: np.ndarray) -> np.ndarray:
        """Fit and immediately transform in one call."""
        self.fit(y_proba, y_true)
        return self.transform(y_proba)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def reliability_curve(
        self,
        y_proba: np.ndarray,
        y_true: np.ndarray,
        n_bins: int = 10,
    ) -> dict:
        """
        Compute reliability (calibration) curve data.

        Parameters
        ----------
        y_proba : raw (uncalibrated) probability array, shape (N,)
        y_true  : binary label array, shape (N,)
        n_bins  : number of equal-width bins

        Returns
        -------
        dict with keys:
            mean_pred     : np.ndarray (n_bins,) — mean predicted prob per bin
            fraction_pos  : np.ndarray (n_bins,) — empirical fraction of positives
            brier_score   : float                — overall Brier score
        """
        y_proba = np.asarray(y_proba, dtype=float).ravel()
        y_true = np.asarray(y_true, dtype=float).ravel()

        bins = np.linspace(0.0, 1.0, n_bins + 1)
        mean_pred = np.zeros(n_bins)
        fraction_pos = np.zeros(n_bins)

        for i in range(n_bins):
            lo, hi = bins[i], bins[i + 1]
            if i == n_bins - 1:
                mask = (y_proba >= lo) & (y_proba <= hi)
            else:
                mask = (y_proba >= lo) & (y_proba < hi)

            if mask.sum() == 0:
                mean_pred[i] = (lo + hi) / 2.0
                fraction_pos[i] = float("nan")
            else:
                mean_pred[i] = float(y_proba[mask].mean())
                fraction_pos[i] = float(y_true[mask].mean())

        brier = float(brier_score_loss(y_true, y_proba))

        return {
            "mean_pred": mean_pred,
            "fraction_pos": fraction_pos,
            "brier_score": brier,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize calibrator to *path* via joblib."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("IsotonicCalibrator saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "IsotonicCalibrator":
        """Deserialize from *path*."""
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected IsotonicCalibrator, got {type(obj)}")
        logger.info("IsotonicCalibrator loaded from %s", path)
        return obj

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_fitted(self) -> None:
        if not self._is_fitted or self._iso is None:
            raise RuntimeError("IsotonicCalibrator is not fitted yet. Call fit() first.")

    def __repr__(self) -> str:
        status = "fitted" if self._is_fitted else "unfitted"
        return f"IsotonicCalibrator({status})"
