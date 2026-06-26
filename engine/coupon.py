"""
engine/coupon.py — CouponGenerator B2C core for betatp.io
Generates singles, system bets, and daily coupons for subscribers.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
import json
import hashlib
import math
from itertools import combinations


@dataclass
class BetSelection:
    """Jedna selekcja (jeden mecz) w kuponie."""
    match_id: str
    player_backed: str  # np. "Carlos Alcaraz"
    opponent: str
    surface: str
    tourney_name: str
    tourney_level: str  # G/M/500/250
    match_date: date

    # Prawdopodobieństwo i wartość
    p_model: float       # nasz model
    bk_odds: float       # kurs bukmachera
    p_fair: float        # devigged probability
    ev_pct: float        # Expected Value %
    kelly_stake_pct: float        # Half Kelly jako % bankrolla
    recommended_stake_units: float  # w jednostkach (np. 1.5 units)

    # Confidence i uzasadnienie
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    ev_source: Literal["elo", "ml_ensemble", "both"] = "elo"

    # Uzasadnienie PL (wygenerowany tekst)
    reasoning: str = ""

    # Statystyki wspierające reasoning
    elo_diff: float = 0.0
    surface_elo_diff: float = 0.0
    form_last5: str = ""       # np. "WWLWW"
    fatigue_flag: bool = False
    h2h_summary: str = ""      # np. "12-8 (surface: 6-3)"
    model_edge: float = 0.0    # p_model - p_fair


@dataclass
class Coupon:
    """Kupon dla subskrybenta."""
    coupon_id: str
    coupon_date: date
    coupon_type: Literal["single", "2/3", "3/4", "3/5", "trixie", "patent", "yankee"]
    selections: list

    total_ev: float           # średnie EV selekcji
    combined_odds: float      # iloczyn kursów (dla systemów)
    recommended_total_stake: float  # w % bankrolla

    priority: Literal["TOP PICK", "RECOMMENDED", "SPECULATIVE"]
    headline: str             # np. "Alcaraz dominuje na Hard — EV +8.3%"
    summary: str              # 2-3 zdania PL


class CouponGenerator:
    def __init__(
        self,
        min_ev: float = 0.02,
        min_odds: float = 1.30,
        max_odds: float = 5.00,
        max_kelly: float = 0.05,
        max_selections_per_day: int = 8,
    ):
        self.min_ev = min_ev
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.max_kelly = max_kelly
        self.max_selections = max_selections_per_day

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_singles(self, match_predictions: list) -> list:
        """
        Input: lista dict {match_id, player_a, player_b, surface, tourney,
                          tourney_level, match_date, p_model, bk_odds_a,
                          bk_odds_b, elo_diff, form_a, form_b, fatigue_a,
                          fatigue_b, h2h, n_matches_a, n_matches_b}
        """
        selections = []

        for md in match_predictions:
            # --- Pick the side with value ---
            bk_odds_a = md.get("bk_odds_a", 2.0)
            bk_odds_b = md.get("bk_odds_b", 2.0)
            p_model_a = md.get("p_model", 0.5)
            p_model_b = 1.0 - p_model_a

            # Devig (power method — two-outcome)
            p_fair_a, p_fair_b = self._devig_two(bk_odds_a, bk_odds_b)

            # EV for both sides
            ev_a = p_model_a * bk_odds_a - 1.0
            ev_b = p_model_b * bk_odds_b - 1.0

            # Choose the better-valued side
            if ev_a >= ev_b:
                player = md.get("player_a", "Player A")
                opponent = md.get("player_b", "Player B")
                bk_odds = bk_odds_a
                p_model = p_model_a
                p_fair = p_fair_a
                ev = ev_a
                form_last5 = md.get("form_a", "")
                fatigue = bool(md.get("fatigue_a", False))
            else:
                player = md.get("player_b", "Player B")
                opponent = md.get("player_a", "Player A")
                bk_odds = bk_odds_b
                p_model = p_model_b
                p_fair = p_fair_b
                ev = ev_b
                form_last5 = md.get("form_b", "")
                fatigue = bool(md.get("fatigue_b", False))

            # Filter
            if ev < self.min_ev:
                continue
            if bk_odds < self.min_odds or bk_odds > self.max_odds:
                continue

            model_edge = p_model - p_fair

            # Half Kelly stake
            kelly = self._half_kelly(p_model, bk_odds)
            kelly = min(kelly, self.max_kelly)

            confidence = self._confidence_level(ev, p_model, model_edge)

            match_date = md.get("match_date", date.today())
            if isinstance(match_date, str):
                match_date = date.fromisoformat(match_date)

            sel = BetSelection(
                match_id=md.get("match_id", ""),
                player_backed=player,
                opponent=opponent,
                surface=md.get("surface", "Hard"),
                tourney_name=md.get("tourney", ""),
                tourney_level=md.get("tourney_level", "250"),
                match_date=match_date,
                p_model=round(p_model, 4),
                bk_odds=round(bk_odds, 2),
                p_fair=round(p_fair, 4),
                ev_pct=round(ev, 4),
                kelly_stake_pct=round(kelly, 4),
                recommended_stake_units=round(kelly * 20, 2),  # scale to units
                confidence=confidence,
                ev_source=md.get("ev_source", "elo"),
                elo_diff=md.get("elo_diff", 0.0),
                surface_elo_diff=md.get("surface_elo_diff", 0.0),
                form_last5=form_last5,
                fatigue_flag=fatigue,
                h2h_summary=md.get("h2h", ""),
                model_edge=round(model_edge, 4),
            )
            sel.reasoning = self._generate_reasoning(sel, md)
            selections.append(sel)

        # Sort EV desc, take top max_selections
        selections.sort(key=lambda s: s.ev_pct, reverse=True)
        return selections[: self.max_selections]

    def _devig_two(self, odds_a: float, odds_b: float):
        """Power devig for two-outcome market."""
        if odds_a <= 1.0 or odds_b <= 1.0:
            return 0.5, 0.5
        raw_a = 1.0 / odds_a
        raw_b = 1.0 / odds_b
        total = raw_a + raw_b
        return raw_a / total, raw_b / total

    def _half_kelly(self, p: float, odds: float) -> float:
        """Half Kelly criterion stake as fraction of bankroll."""
        b = odds - 1.0
        if b <= 0 or p <= 0 or p >= 1:
            return 0.0
        q = 1.0 - p
        kelly = (b * p - q) / b
        return max(0.0, kelly / 2.0)

    def _generate_reasoning(self, sel: BetSelection, match_data: dict) -> str:
        """
        Generuj uzasadnienie po POLSKU z minimum 3 zdaniami (faktami).
        """
        lines = []

        # Fact 1: Player form + Elo
        elo_info = ""
        if sel.elo_diff != 0.0:
            direction = "wyższe" if sel.elo_diff > 0 else "niższe"
            elo_info = f" Elo {direction} o {abs(sel.elo_diff):.0f} pkt vs przeciwnik."
        form_info = f" Forma ostatnich 5 meczy: {sel.form_last5}." if sel.form_last5 else ""
        lines.append(
            f"{sel.player_backed} vs {sel.opponent} na {sel.surface} ({sel.tourney_name}).{elo_info}{form_info}"
        )

        # Fact 2: Model probability vs market
        lines.append(
            f"Model wycenia szanse na {sel.p_model*100:.1f}% vs rynek {sel.p_fair*100:.1f}% "
            f"(EV +{sel.ev_pct*100:.1f}%, przewaga modelu: +{sel.model_edge*100:.1f}%)."
        )

        # Fact 3: Odds + stake recommendation
        lines.append(
            f"Kurs bukmachera: {sel.bk_odds:.2f}. "
            f"Zalecana stawka: {sel.kelly_stake_pct*100:.1f}% bankrolla "
            f"({sel.recommended_stake_units:.1f} jednostek). "
            f"Poziom pewności: {sel.confidence}."
        )

        # Fact 4 (optional): fatigue / h2h
        extras = []
        if sel.fatigue_flag:
            extras.append(f"{sel.player_backed} może być zmęczony — flaga zmęczenia aktywna.")
        if sel.h2h_summary:
            extras.append(f"H2H: {sel.h2h_summary}.")
        if sel.surface_elo_diff != 0.0:
            extras.append(
                f"Elo nawierzchniowe ({sel.surface}): różnica {sel.surface_elo_diff:+.0f} pkt."
            )
        if extras:
            lines.append(" ".join(extras))

        return " ".join(lines)

    def _confidence_level(self, ev: float, p_model: float, model_edge: float) -> str:
        """
        HIGH: EV > 0.05 AND model_edge > 0.07
        MEDIUM: EV > 0.03 OR model_edge > 0.05
        LOW: EV > 0.02
        """
        if ev > 0.05 and model_edge > 0.07:
            return "HIGH"
        if ev > 0.03 or model_edge > 0.05:
            return "MEDIUM"
        return "LOW"

    def build_system_bet(self, selections: list, system_type: str) -> "Coupon | None":
        """
        Build system coupon from a list of BetSelections.
        system_type: "2/3", "3/4", "3/5", "trixie", "patent", "yankee"
        Only selections with EV > 1.5% enter the system.
        """
        # Filter by minimum EV for system
        eligible = [s for s in selections if s.ev_pct > 0.015]

        # Determine required number of selections
        min_sel_map = {
            "2/3": 3, "3/4": 4, "3/5": 5,
            "trixie": 3, "patent": 3, "yankee": 4,
        }
        min_required = min_sel_map.get(system_type, 3)

        if len(eligible) < min_required:
            return None

        # Trim to required
        working = eligible[:min_required] if system_type in ("2/3", "3/4", "3/5") else eligible[:min_required]

        # For yankee we need exactly 4
        if system_type == "yankee":
            working = eligible[:4]
            if len(working) < 4:
                return None

        # Combined odds = product of all odds
        combined_odds = 1.0
        for s in working:
            combined_odds *= s.bk_odds

        total_ev = sum(s.ev_pct for s in working) / len(working)

        # Stake: sum of Kelly stakes
        recommended_stake = sum(s.kelly_stake_pct for s in working)

        # Build coupon_id
        ids = "_".join(s.match_id for s in working)
        coupon_id = hashlib.md5(f"{system_type}_{ids}".encode()).hexdigest()[:12]

        # Priority
        if total_ev > 0.05:
            priority = "TOP PICK"
        elif total_ev > 0.03:
            priority = "RECOMMENDED"
        else:
            priority = "SPECULATIVE"

        headline = self._system_headline(working, system_type, total_ev)
        summary = self._system_summary(working, system_type, combined_odds, total_ev)

        return Coupon(
            coupon_id=coupon_id,
            coupon_date=working[0].match_date,
            coupon_type=system_type,  # type: ignore[arg-type]
            selections=working,
            total_ev=round(total_ev, 4),
            combined_odds=round(combined_odds, 3),
            recommended_total_stake=round(recommended_stake, 4),
            priority=priority,  # type: ignore[arg-type]
            headline=headline,
            summary=summary,
        )

    def _system_headline(self, selections: list, system_type: str, total_ev: float) -> str:
        names = " + ".join(s.player_backed.split()[-1] for s in selections[:3])
        return f"System {system_type.upper()}: {names} — śr. EV +{total_ev*100:.1f}%"

    def _system_summary(
        self, selections: list, system_type: str, combined_odds: float, total_ev: float
    ) -> str:
        n = len(selections)
        names = ", ".join(s.player_backed for s in selections)
        return (
            f"Kupon systemowy {system_type} złożony z {n} selekcji: {names}. "
            f"Łączny kurs: {combined_odds:.2f}. "
            f"Średnie EV: +{total_ev*100:.1f}%."
        )

    def generate_daily_coupons(self, match_predictions: list, coupon_date: date) -> dict:
        """
        Główna funkcja generująca kupony na dany dzień.
        """
        singles = self.generate_singles(match_predictions)
        top5_singles = singles[:5]

        system_2of3 = None
        trixie = None
        yankee = None

        if len(singles) >= 3:
            system_2of3 = self.build_system_bet(singles[:3], "2/3")

        if len(singles) >= 3:
            trixie = self.build_system_bet(singles[:3], "trixie")

        if len(singles) >= 4:
            yankee = self.build_system_bet(singles[:4], "yankee")

        top_pick = singles[0] if singles else None

        # Daily summary
        if singles:
            summary = (
                f"Dzisiaj {len(singles)} selekcji z wartością EV > {self.min_ev*100:.0f}%. "
                f"Najlepsza selekcja: {top_pick.player_backed} (EV +{top_pick.ev_pct*100:.1f}%). "
                f"Łącznie {['brak systemów', 'system 2/3', 'system 2/3 + Trixie'][min(2, (1 if system_2of3 else 0) + (1 if trixie else 0))]} dostępnych."
            )
        else:
            summary = "Brak selekcji spełniających kryteria wartości na dziś."

        return {
            "date": coupon_date,
            "singles": top5_singles,
            "system_2of3": system_2of3,
            "trixie": trixie,
            "yankee": yankee,
            "top_pick": top_pick,
            "summary": summary,
        }


class DailyCouponBuilder:
    """Orkiestrator — integruje EloEngine + MonteCarloEngine + CouponGenerator"""

    def __init__(self, elo_engine=None, mc_engine=None, coupon_gen=None):
        self.elo = elo_engine
        self.mc = mc_engine
        self.gen = coupon_gen or CouponGenerator()

    def process_day(self, matches: list, coupon_date: date) -> dict:
        """End-to-end: lista meczów -> gotowe kupony."""
        # If engines are available, enrich predictions; otherwise pass through
        predictions = []
        for m in matches:
            pred = dict(m)
            if self.elo is not None:
                try:
                    elo_pred = self.elo.predict(m.get("player_a"), m.get("player_b"), m.get("surface", "Hard"))
                    pred.update(elo_pred)
                except Exception:
                    pass
            predictions.append(pred)

        return self.gen.generate_daily_coupons(predictions, coupon_date)
