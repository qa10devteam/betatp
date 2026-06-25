import numpy as np
import pandas as pd
from typing import List, Tuple, Optional


class WalkForwardDataset:
    """
    Walk-Forward splits — jedyny dozwolony protokół walidacji.
    NIGDY nie używaj przyszłych danych.
    """

    FORBIDDEN_COLUMNS = [
        # Kolumny które nie mogą być features:
        "score", "winner_rank", "loser_rank",  # post-match
        "w_ace", "w_df", "w_svpt", "w_1stIn",  # post-match stats
        "w_1stWon", "w_2ndWon", "w_SvGms",
        "w_bpSaved", "w_bpFaced",
        "l_ace", "l_df", "l_svpt", "l_1stIn",
        "l_1stWon", "l_2ndWon", "l_SvGms",
        "l_bpSaved", "l_bpFaced",
    ]

    SPLITS = [
        # (train_end_year, val_start_year, val_end_year)
        (2002, 2003, 2004),
        (2004, 2005, 2007),
        (2007, 2008, 2011),
        (2011, 2012, 2016),
        (2016, 2017, 2020),
    ]

    HOLDOUT = (2021, 2025)  # NIGDY nie używaj do train/val

    def build_split(
        self,
        matches_df: pd.DataFrame,
        features_df: pd.DataFrame,
        train_end: int,
        val_start: int,
        val_end: int,
    ) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """
        Returns (X_train, y_train, X_val, y_val)
        KRYTYCZNE: Elo dla każdego meczu = Elo PRZED tym meczem
        (nie po). Zabezpiecz przed leakage.
        """
        # Ensure year column exists — try to derive from tourney_date if needed
        df = matches_df.copy()
        if "year" not in df.columns:
            if "tourney_date" in df.columns:
                df["year"] = pd.to_datetime(df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce").dt.year
            else:
                raise ValueError("matches_df must have 'year' or 'tourney_date' column")

        # Split by year
        train_mask = df["year"] <= train_end
        val_mask = (df["year"] >= val_start) & (df["year"] <= val_end)

        # Validate no leakage: val must start after train ends
        assert val_start > train_end, f"Leakage! val_start={val_start} <= train_end={train_end}"

        # Get indices
        train_idx = df[train_mask].index
        val_idx = df[val_mask].index

        # Merge features
        feat_cols = [c for c in features_df.columns if c not in self.FORBIDDEN_COLUMNS]
        feat_df = features_df[feat_cols]

        # Align features with matches
        X_train = feat_df.loc[feat_df.index.isin(train_idx)] if len(train_idx) > 0 else feat_df.iloc[:0]
        X_val = feat_df.loc[feat_df.index.isin(val_idx)] if len(val_idx) > 0 else feat_df.iloc[:0]

        # Target: 1 = player_a wins (winner_id == player_a_id), or use 'y' column
        if "y" in df.columns:
            y_train = df.loc[train_idx, "y"] if len(train_idx) > 0 else pd.Series(dtype=int)
            y_val = df.loc[val_idx, "y"] if len(val_idx) > 0 else pd.Series(dtype=int)
        else:
            # Default: all 1s (winner is always first in standard tennis datasets)
            y_train = pd.Series(np.ones(len(train_idx), dtype=int), index=train_idx)
            y_val = pd.Series(np.ones(len(val_idx), dtype=int), index=val_idx)

        return X_train, y_train, X_val, y_val

    def get_all_splits(
        self, matches_df: pd.DataFrame, features_df: pd.DataFrame
    ) -> List[Tuple]:
        """Zwraca listę (X_train, y_train, X_val, y_val) dla 5 splitów"""
        results = []
        for train_end, val_start, val_end in self.SPLITS:
            # Verify we don't use holdout data
            assert val_end < self.HOLDOUT[0], (
                f"Split val_end={val_end} overlaps with HOLDOUT start={self.HOLDOUT[0]}"
            )
            split = self.build_split(matches_df, features_df, train_end, val_start, val_end)
            results.append(split)
        return results

    def check_leakage(self, X: pd.DataFrame) -> List[str]:
        """Sprawdź czy X nie zawiera zakazanych kolumn. Zwraca listę naruszeń."""
        violations = [col for col in self.FORBIDDEN_COLUMNS if col in X.columns]
        return violations
