import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss
import lightgbm as lgb
import xgboost as xgb
import joblib
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

LGBM_PARAMS = {
    "n_estimators": 1000,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_lambda": 1.0,
    "objective": "binary",
    "metric": "binary_logloss",
    "verbosity": -1,
}

XGB_PARAMS = {
    "n_estimators": 800,
    "max_depth": 5,
    "learning_rate": 0.05,
    "min_child_weight": 10,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_lambda": 1.0,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "verbosity": 0,
}


@dataclass
class EnsembleWeights:
    lgbm: float = 0.35
    xgb: float = 0.25
    lr: float = 0.10
    elo: float = 0.30


class BetaTPEnsemble:
    """Level-1 stacking ensemble: LGBM + XGB + LR + Elo"""

    def __init__(self, models_dir: str = "/home/ubuntu/betatp/models"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True, parents=True)
        self.lgbm = None
        self.xgb_model = None
        self.lr = LogisticRegression(C=1.0, max_iter=1000)
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.weights = EnsembleWeights()
        self._is_fitted = False
        self._meta_lr = LogisticRegression(C=1.0, max_iter=1000)

    def _cold_start_weights(self, n_matches: int) -> EnsembleWeights:
        """Gdy n_matches < 10: elo weight = 0.90, reszta proporcjonalnie"""
        if n_matches < 10:
            # elo = 0.90, remaining 0.10 split proportionally among others
            # original non-elo weights: lgbm=0.35, xgb=0.25, lr=0.10 -> sum=0.70
            remaining = 0.10
            orig_non_elo = {"lgbm": 0.35, "xgb": 0.25, "lr": 0.10}
            orig_sum = sum(orig_non_elo.values())
            return EnsembleWeights(
                lgbm=remaining * orig_non_elo["lgbm"] / orig_sum,
                xgb=remaining * orig_non_elo["xgb"] / orig_sum,
                lr=remaining * orig_non_elo["lr"] / orig_sum,
                elo=0.90,
            )
        return EnsembleWeights()  # default weights

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        elo_probs_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
        elo_probs_val: np.ndarray | None = None,
    ) -> dict:
        """
        Steps:
        1. Train LGBM z early stopping na X_val
        2. Train XGBoost z early stopping
        3. Train LR na X_train
        4. OOF predictions dla Level-1 (3-fold cross-val)
        5. Train meta-learner na OOF stack
        6. Calibrate z IsotonicRegression
        Returns: {"lgbm_auc": ..., "xgb_auc": ..., "ensemble_brier": ...}
        """
        has_val = X_val is not None and y_val is not None

        # 1. Train LGBM
        lgbm_params = {k: v for k, v in LGBM_PARAMS.items()}
        if has_val:
            self.lgbm = lgb.LGBMClassifier(
                **lgbm_params,
                early_stopping_rounds=50,
            )
            self.lgbm.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
            )
        else:
            lgbm_params_no_es = {k: v for k, v in lgbm_params.items()}
            lgbm_params_no_es["n_estimators"] = 300
            self.lgbm = lgb.LGBMClassifier(**lgbm_params_no_es)
            self.lgbm.fit(X_train, y_train)

        # 2. Train XGBoost
        xgb_params = {k: v for k, v in XGB_PARAMS.items()}
        if has_val:
            self.xgb_model = xgb.XGBClassifier(
                **xgb_params,
                early_stopping_rounds=50,
            )
            self.xgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
        else:
            xgb_params_no_es = {k: v for k, v in xgb_params.items()}
            xgb_params_no_es["n_estimators"] = 300
            self.xgb_model = xgb.XGBClassifier(**xgb_params_no_es)
            self.xgb_model.fit(X_train, y_train, verbose=False)

        # 3. Train LR
        self.lr.fit(X_train, y_train)

        # 4. OOF predictions (3-fold)
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

        lgbm_oof = cross_val_predict(
            lgb.LGBMClassifier(n_estimators=300, verbosity=-1),
            X_train, y_train, cv=cv, method="predict_proba"
        )[:, 1]
        xgb_oof = cross_val_predict(
            xgb.XGBClassifier(n_estimators=300, verbosity=0),
            X_train, y_train, cv=cv, method="predict_proba"
        )[:, 1]
        lr_oof = cross_val_predict(
            LogisticRegression(C=1.0, max_iter=1000),
            X_train, y_train, cv=cv, method="predict_proba"
        )[:, 1]

        # Stack OOF + elo
        oof_stack = np.column_stack([lgbm_oof, xgb_oof, lr_oof, elo_probs_train])

        # 5. Train meta-learner
        self._meta_lr.fit(oof_stack, y_train)

        # 6. Calibrate
        meta_train_preds = self._meta_lr.predict_proba(oof_stack)[:, 1]
        self.calibrator.fit(meta_train_preds, y_train)

        # Compute metrics
        lgbm_train_preds = self.lgbm.predict_proba(X_train)[:, 1]
        xgb_train_preds = self.xgb_model.predict_proba(X_train)[:, 1]

        metrics = {}
        try:
            metrics["lgbm_auc"] = roc_auc_score(y_train, lgbm_train_preds)
        except Exception:
            metrics["lgbm_auc"] = float("nan")
        try:
            metrics["xgb_auc"] = roc_auc_score(y_train, xgb_train_preds)
        except Exception:
            metrics["xgb_auc"] = float("nan")

        # Ensemble brier on train
        ensemble_preds = self.predict_proba(X_train, elo_probs_train)
        metrics["ensemble_brier"] = brier_score_loss(y_train, ensemble_preds)

        self._is_fitted = True
        return metrics

    def predict_proba(self, X: np.ndarray, elo_probs: np.ndarray, n_matches: int = 100) -> np.ndarray:
        """
        Zwraca P(A wins) dla każdego wiersza X.
        Weights zależą od n_matches (cold start rule).
        """
        weights = self._cold_start_weights(n_matches)

        if self._is_fitted and self.lgbm is not None:
            lgbm_preds = self.lgbm.predict_proba(X)[:, 1]
            xgb_preds = self.xgb_model.predict_proba(X)[:, 1]
            lr_preds = self.lr.predict_proba(X)[:, 1]
        else:
            # Not fitted — fall back to elo only
            n = len(X) if hasattr(X, '__len__') else X.shape[0]
            lgbm_preds = np.full(n, 0.5)
            xgb_preds = np.full(n, 0.5)
            lr_preds = np.full(n, 0.5)
            weights = EnsembleWeights(lgbm=0.0, xgb=0.0, lr=0.0, elo=1.0)

        # Weighted ensemble
        ensemble = (
            weights.lgbm * lgbm_preds
            + weights.xgb * xgb_preds
            + weights.lr * lr_preds
            + weights.elo * elo_probs
        )

        # Calibrate if fitted
        if self._is_fitted:
            ensemble = self.calibrator.predict(ensemble)

        return np.clip(ensemble, 0.0, 1.0)

    def save(self, path: str | None = None) -> str:
        """Zapisz model do models/ensemble_v{timestamp}.joblib"""
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(self.models_dir / f"ensemble_v{ts}.joblib")
        joblib.dump(self, path)
        return path

    def load(self, path: str) -> None:
        """Wczytaj model z pliku"""
        loaded = joblib.load(path)
        self.__dict__.update(loaded.__dict__)
