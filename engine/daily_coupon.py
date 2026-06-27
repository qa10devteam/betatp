"""
daily_coupon.py — Assembles the betatp.io daily coupon from raw match predictions.

Typical usage:
    builder = DailyCouponBuilder()
    coupon = builder.build(matches)
    print(builder.to_json())
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from engine.coupon_ranker import CouponRanker
from engine.coupon_system import SystemBetBuilder, SYSTEM_TYPES

_MAX_TOP_SINGLES = 3
_DEFAULT_MIN_EV = 0.02


class DailyCouponBuilder:
    """
    Builds the daily betting coupon for betatp.io.

    Given a list of raw match dicts (each containing predictions),
    produces a structured coupon with:
      - top single bets (max 3)
      - a 2/3 system bet (if enough value selections exist)
      - a 3/4 system bet (if enough value selections exist)
    """

    def __init__(self) -> None:
        self._ranker = CouponRanker()
        self._system_builder = SystemBetBuilder()
        self._last_coupon: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        matches: list[dict[str, Any]],
        min_ev: float = _DEFAULT_MIN_EV,
    ) -> dict[str, Any]:
        """
        Build the daily coupon.

        Parameters
        ----------
        matches : list of match dicts; each may contain a 'predictions'
                  list or top-level prediction fields (odds, ev, p_model …)
        min_ev  : minimum EV threshold for a selection to appear in the coupon

        Returns
        -------
        dict with keys:
            date          : ISO date string (UTC today)
            top_singles   : list of up to 3 ranked single selections
            system_2_3    : dict|None — 2/3 system bet result
            system_3_4    : dict|None — 3/4 system bet result
            generated_at  : ISO datetime string (UTC)
        """
        singles = self._scan_singles(matches, min_ev)
        systems = self._build_systems(singles)

        now_utc = datetime.now(timezone.utc)
        coupon: dict[str, Any] = {
            "date": now_utc.date().isoformat(),
            "top_singles": singles[:_MAX_TOP_SINGLES],
            "system_2_3": systems.get("2/3"),
            "system_3_4": systems.get("3/4"),
            "generated_at": now_utc.isoformat(),
        }
        self._last_coupon = coupon
        return coupon

    def to_json(self) -> str:
        """
        Serialize the most recently built coupon to a JSON string
        suitable for API responses.

        Raises RuntimeError if build() has not been called yet.
        """
        if self._last_coupon is None:
            raise RuntimeError("Call build() before to_json().")
        return json.dumps(self._last_coupon, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Internal pipeline steps
    # ------------------------------------------------------------------

    def _scan_singles(
        self,
        matches: list[dict[str, Any]],
        min_ev: float,
    ) -> list[dict[str, Any]]:
        """
        Extract individual selections from matches, filter by min_ev,
        annotate with score / confidence / reasoning, and return sorted
        by composite score descending.

        A match dict is expected to have either:
          - A 'predictions' key → list of per-selection dicts, OR
          - Top-level keys: player, odds, ev, p_model, kelly
        """
        raw_selections: list[dict[str, Any]] = []

        for match in matches:
            if "predictions" in match and isinstance(match["predictions"], list):
                for pred in match["predictions"]:
                    merged = {**match, **pred}
                    merged.pop("predictions", None)
                    raw_selections.append(merged)
            else:
                raw_selections.append(dict(match))

        # Filter by EV
        filtered = [s for s in raw_selections if s.get("ev", 0.0) >= min_ev]

        # Annotate via ranker (rank_coupons on singles only)
        ranked = self._ranker.rank_coupons(filtered, [])

        # Sort by composite score descending
        ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return ranked

    def _build_systems(
        self,
        singles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Attempt to build 2/3 and 3/4 system bets from the ranked singles.
        Returns a dict with keys '2/3' and '3/4'; values are result dicts
        or None if not enough eligible selections exist.
        """
        results: dict[str, Any] = {}

        for system_type, (min_correct, total_legs) in [
            ("2/3", SYSTEM_TYPES["2/3"]),
            ("3/4", SYSTEM_TYPES["3/4"]),
        ]:
            if len(singles) >= total_legs:
                result = self._system_builder.build_system(
                    singles[:total_legs], system_type
                )
                results[system_type] = result if result["combinations"] else None
            else:
                results[system_type] = None

        return results
