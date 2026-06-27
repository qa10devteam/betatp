"""
coupon_system.py — System bet builder for betatp.io
Supports: 2/3, 2/4, 3/4, 3/5, TRIXIE, PATENT, YANKEE
Only selections with ev > 0.015 enter a system.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from functools import reduce
from typing import Any

# ---------------------------------------------------------------------------
# System type registry
# Each entry: (min_correct_to_profit, total_legs_in_system)
# For named systems the leg breakdown is handled separately.
# ---------------------------------------------------------------------------
SYSTEM_TYPES: dict[str, tuple[int, int]] = {
    "2/3":    (2, 3),
    "2/4":    (2, 4),
    "3/4":    (3, 4),
    "3/5":    (3, 5),
    "TRIXIE": (2, 3),   # 3 doubles → need 2 correct to get return
    "PATENT": (1, 3),   # 3 singles + 3 doubles + 1 treble → singles pay from 1
    "YANKEE": (2, 4),   # 6 doubles + 4 trebles + 1 fourfold → need 2 correct
}

# Named system bet structures: list of combo-sizes that form the system
_NAMED_SYSTEM_COMBOS: dict[str, list[int]] = {
    "TRIXIE": [2, 2, 2],                         # 3 doubles
    "PATENT": [1, 1, 1, 2, 2, 2, 3],             # 3 singles, 3 doubles, 1 treble
    "YANKEE": [2]*6 + [3]*4 + [4]*1,             # 6 doubles, 4 trebles, 1 fourfold
}

_MIN_EV_THRESHOLD = 0.015


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def combined_probability(p_list: list[float]) -> float:
    """Return the joint probability (product) of independent events."""
    return reduce(lambda a, b: a * b, p_list, 1.0)


def combined_odds(odds_list: list[float]) -> float:
    """Return the combined decimal odds (product) of a multi-leg bet."""
    return reduce(lambda a, b: a * b, odds_list, 1.0)


def _ev_for_combo(odds_product: float, prob_product: float) -> float:
    """EV per unit stake for a single combination."""
    return odds_product * prob_product - 1.0


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

@dataclass
class SystemBetBuilder:
    """Builds system bets from a list of value selections."""

    ev_threshold: float = _MIN_EV_THRESHOLD

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_system(
        self,
        selections: list[dict[str, Any]],
        system_type: str,
    ) -> dict[str, Any]:
        """
        Build a system bet.

        Parameters
        ----------
        selections : list of dicts with keys: player, odds, ev, p_model, kelly
        system_type : one of SYSTEM_TYPES keys

        Returns
        -------
        dict with keys:
            system_type, legs, combinations, total_stake_units,
            system_ev, best_combo
        """
        if system_type not in SYSTEM_TYPES:
            raise ValueError(
                f"Unknown system_type '{system_type}'. "
                f"Valid types: {list(SYSTEM_TYPES)}"
            )

        # Filter to only value selections
        eligible = [s for s in selections if s.get("ev", 0.0) > self.ev_threshold]

        if not eligible:
            return self._empty_result(system_type)

        min_correct, total_legs = SYSTEM_TYPES[system_type]

        # Trim eligible list to total_legs requirement
        eligible_sorted = sorted(eligible, key=lambda s: s.get("ev", 0.0), reverse=True)
        pool = eligible_sorted[:total_legs]

        if len(pool) < min_correct:
            return self._empty_result(system_type)

        # Build combinations
        combinations = self._build_combinations(pool, system_type)

        if not combinations:
            return self._empty_result(system_type)

        total_stake_units = len(combinations)  # 1 unit per combination
        system_ev = self.system_expected_return(pool, system_type)
        best_combo = max(combinations, key=lambda c: c["ev"])

        return {
            "system_type": system_type,
            "legs": len(pool),
            "combinations": combinations,
            "total_stake_units": total_stake_units,
            "system_ev": round(system_ev, 6),
            "best_combo": best_combo,
        }

    def system_expected_return(
        self,
        selections: list[dict[str, Any]],
        system_type: str,
    ) -> float:
        """
        Compute the average EV across all combinations in the system.
        Only value selections (ev > threshold) are used.
        """
        eligible = [s for s in selections if s.get("ev", 0.0) > self.ev_threshold]
        if not eligible:
            return 0.0

        min_correct, total_legs = SYSTEM_TYPES[system_type]
        pool = sorted(eligible, key=lambda s: s.get("ev", 0.0), reverse=True)[:total_legs]

        combinations = self._build_combinations(pool, system_type)
        if not combinations:
            return 0.0

        return sum(c["ev"] for c in combinations) / len(combinations)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_combinations(
        self,
        pool: list[dict[str, Any]],
        system_type: str,
    ) -> list[dict[str, Any]]:
        """Generate all bet combinations for the given system type."""

        if system_type in _NAMED_SYSTEM_COMBOS:
            return self._build_named_combinations(pool, system_type)
        else:
            # e.g. '2/3' → all C(3,2) doubles from pool of 3
            min_correct, total_legs = SYSTEM_TYPES[system_type]
            return self._build_nk_combinations(pool, min_correct)

    def _build_named_combinations(
        self,
        pool: list[dict[str, Any]],
        system_type: str,
    ) -> list[dict[str, Any]]:
        """
        For named systems (TRIXIE, PATENT, YANKEE) build the exact
        combination structure defined in _NAMED_SYSTEM_COMBOS.
        """
        combo_sizes = _NAMED_SYSTEM_COMBOS[system_type]
        results: list[dict[str, Any]] = []

        # For each required combo size, generate all C(n, size) combos
        # But the named system specifies a fixed sequence — we iterate
        # through unique sizes and pick the right number of each.
        size_counts: dict[int, int] = {}
        for s in combo_sizes:
            size_counts[s] = size_counts.get(s, 0) + 1

        for size, expected_count in sorted(size_counts.items()):
            combos = list(itertools.combinations(pool, size))
            for combo in combos:
                results.append(self._combo_dict(list(combo)))

        return results

    def _build_nk_combinations(
        self,
        pool: list[dict[str, Any]],
        k: int,
    ) -> list[dict[str, Any]]:
        """All C(len(pool), k) combinations of size k."""
        results: list[dict[str, Any]] = []
        for combo in itertools.combinations(pool, k):
            results.append(self._combo_dict(list(combo)))
        return results

    @staticmethod
    def _combo_dict(legs: list[dict[str, Any]]) -> dict[str, Any]:
        """Turn a list of selections into a combination descriptor."""
        odds_list = [s.get("odds", 1.0) for s in legs]
        p_list = [s.get("p_model", 0.5) for s in legs]

        combo_odds = combined_odds(odds_list)
        combo_prob = combined_probability(p_list)
        ev = _ev_for_combo(combo_odds, combo_prob)

        return {
            "players": [s.get("player", "?") for s in legs],
            "odds": [round(o, 3) for o in odds_list],
            "combined_odds": round(combo_odds, 4),
            "combined_probability": round(combo_prob, 6),
            "ev": round(ev, 6),
            "legs": len(legs),
        }

    @staticmethod
    def _empty_result(system_type: str) -> dict[str, Any]:
        return {
            "system_type": system_type,
            "legs": 0,
            "combinations": [],
            "total_stake_units": 0,
            "system_ev": 0.0,
            "best_combo": None,
        }
