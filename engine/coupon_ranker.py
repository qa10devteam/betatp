"""
coupon_ranker.py — Ranks singles and system bets for betatp.io daily coupon.
Provides Polish-language reasoning strings for each selection.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Confidence label thresholds
# ---------------------------------------------------------------------------
_EV_HIGH = 0.08
_EV_MED = 0.04


class CouponRanker:
    """
    Ranks and annotates bet selections with composite scores and
    Polish-language reasoning strings.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank_coupons(
        self,
        singles: list[dict[str, Any]],
        systems: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge singles and system summaries into a single ranked list,
        sorted by EV descending.

        Each item is annotated with:
            - score     : composite score
            - confidence: WYSOKA / ŚREDNIA / NISKA
            - reasoning : Polish text string
        """
        annotated: list[dict[str, Any]] = []

        for sel in singles:
            enriched = dict(sel)
            ev = sel.get("ev", 0.0)
            enriched["score"] = self.score_selection(sel)
            enriched["confidence"] = self.confidence_label(ev)
            enriched["reasoning"] = self.generate_reasoning(sel)
            enriched.setdefault("type", "single")
            annotated.append(enriched)

        for sys_bet in systems:
            enriched = dict(sys_bet)
            ev = sys_bet.get("system_ev", sys_bet.get("ev", 0.0))
            enriched["ev"] = ev  # normalise key for sorting
            enriched["score"] = self.score_selection(
                {"ev": ev, "kelly": sys_bet.get("kelly", 0.0),
                 "confidence": self._ev_to_confidence_float(ev)}
            )
            enriched["confidence"] = self.confidence_label(ev)
            enriched["reasoning"] = self.generate_reasoning(enriched)
            enriched.setdefault("type", "system")
            annotated.append(enriched)

        annotated.sort(key=lambda x: x.get("ev", 0.0), reverse=True)
        return annotated

    def generate_reasoning(self, selection: dict[str, Any]) -> str:
        """
        Build a Polish reasoning string for a selection.

        Base template:
            'Model daje {p_model:.1%} vs rynek {p_mkt:.1%} → EV {ev:+.1%}'

        Optional appended clauses (when data is present):
            - surface info
            - recent form
            - H2H record
        """
        p_model: float = selection.get("p_model", 0.0)
        # p_mkt is derived from odds if not provided directly
        odds: float = selection.get("odds", 0.0)
        p_mkt: float = selection.get("p_mkt", (1.0 / odds) if odds > 0 else 0.0)
        ev: float = selection.get("ev", 0.0)

        parts: list[str] = [
            f"Model daje {p_model:.1%} vs rynek {p_mkt:.1%} → EV {ev:+.1%}"
        ]

        # Surface (tennis / clay / grass / hard)
        surface: str | None = selection.get("surface")
        if surface:
            parts.append(f"Nawierzchnia: {surface}")

        # Recent form — expects a short string like "W W L W W" or "5/5"
        recent_form: str | None = selection.get("recent_form") or selection.get("form")
        if recent_form:
            parts.append(f"Ostatnia forma: {recent_form}")

        # Head-to-head record
        h2h: str | None = selection.get("h2h") or selection.get("head_to_head")
        if h2h:
            parts.append(f"H2H: {h2h}")

        return " | ".join(parts)

    def score_selection(self, sel: dict[str, Any]) -> float:
        """
        Composite score for ranking:
            0.5 * ev  +  0.3 * kelly  +  0.2 * confidence_float

        confidence_float is mapped from the 'confidence' field if present,
        otherwise derived from ev.
        """
        ev: float = sel.get("ev", 0.0)
        kelly: float = sel.get("kelly", 0.0)

        # Accept a pre-computed numeric confidence or derive it from ev
        raw_conf = sel.get("confidence")
        if isinstance(raw_conf, (int, float)):
            conf_float = float(raw_conf)
        else:
            conf_float = self._ev_to_confidence_float(ev)

        return 0.5 * ev + 0.3 * kelly + 0.2 * conf_float

    @staticmethod
    def confidence_label(ev: float) -> str:
        """
        Return a Polish confidence label based on EV.

        ev > 0.08  → 'WYSOKA'
        ev > 0.04  → 'ŚREDNIA'
        else       → 'NISKA'
        """
        if ev > _EV_HIGH:
            return "WYSOKA"
        if ev > _EV_MED:
            return "ŚREDNIA"
        return "NISKA"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ev_to_confidence_float(ev: float) -> float:
        """Map EV to a [0, 1] confidence float for scoring purposes."""
        if ev > _EV_HIGH:
            return 1.0
        if ev > _EV_MED:
            return 0.5
        return 0.2
