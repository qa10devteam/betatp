"""
value/clv_tracker.py — Closing Line Value tracker for betatp.io
Tracks bet performance vs Pinnacle closing line as the gold standard.
"""
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Optional
import uuid
import numpy as np
from scipy import stats


@dataclass
class BetRecord:
    bet_id: str
    match_id: str
    player_backed: str
    stake: float
    opening_odds: float
    opening_timestamp: datetime
    closing_odds_pinnacle: Optional[float] = None
    closing_timestamp: Optional[datetime] = None
    actual_result: Optional[int] = None   # 1=win, 0=loss
    clv: Optional[float] = None           # computed: opening/closing - 1
    pnl: Optional[float] = None


class CLVTracker:
    def __init__(self):
        self._bets: list[BetRecord] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_bet(
        self,
        match_id: str,
        player: str,
        stake: float,
        opening_odds: float,
        opening_timestamp: Optional[datetime] = None,
    ) -> str:
        """Dodaj zakład. Zwróć bet_id."""
        bet_id = str(uuid.uuid4())[:12]
        ts = opening_timestamp or datetime.now(tz=timezone.utc)
        record = BetRecord(
            bet_id=bet_id,
            match_id=match_id,
            player_backed=player,
            stake=stake,
            opening_odds=opening_odds,
            opening_timestamp=ts,
        )
        self._bets.append(record)
        return bet_id

    def record_closing(
        self,
        bet_id: str,
        pinnacle_closing_odds: float,
        closing_timestamp: Optional[datetime] = None,
    ) -> None:
        """Zapisz closing line + oblicz CLV."""
        rec = self._get(bet_id)
        rec.closing_odds_pinnacle = pinnacle_closing_odds
        rec.closing_timestamp = closing_timestamp or datetime.now(tz=timezone.utc)
        rec.clv = self.compute_clv(bet_id)

    def record_result(self, bet_id: str, won: bool) -> None:
        """Zapisz wynik i oblicz PnL."""
        rec = self._get(bet_id)
        rec.actual_result = 1 if won else 0
        if won:
            rec.pnl = rec.stake * (rec.opening_odds - 1.0)
        else:
            rec.pnl = -rec.stake

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute_clv(self, bet_id: str) -> float:
        """CLV = opening_odds / closing_odds - 1"""
        rec = self._get(bet_id)
        if rec.closing_odds_pinnacle is None or rec.closing_odds_pinnacle <= 0:
            raise ValueError(f"No closing odds for bet {bet_id}")
        return rec.opening_odds / rec.closing_odds_pinnacle - 1.0

    def rolling_clv(self, window_days: int = 30) -> Optional[float]:
        """Średnie CLV z ostatnich window_days dni (tylko resolved bets z CLV)."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
        clvs = []
        for b in self._bets:
            if b.clv is None:
                continue
            ts = b.closing_timestamp or b.opening_timestamp
            # Make timezone-aware if naive
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                clvs.append(b.clv)
        if not clvs:
            return None
        return float(np.mean(clvs))

    def significance_test(self) -> dict:
        """
        One-sample t-test: H0: mean_CLV = 0
        Returns dict with stats and interpretation.
        """
        clvs = [b.clv for b in self._bets if b.clv is not None]
        n = len(clvs)

        if n < 2:
            return {
                "t_stat": None,
                "p_value": None,
                "reject_h0": False,
                "n_bets": n,
                "mean_clv": float(np.mean(clvs)) if clvs else 0.0,
                "std_clv": 0.0,
                "ci_95_low": None,
                "ci_95_high": None,
                "interpretation": "Za mało danych do testu statystycznego (min. 2 zakładów).",
            }

        arr = np.array(clvs)
        t_stat, p_value = stats.ttest_1samp(arr, popmean=0.0)
        mean_clv = float(arr.mean())
        std_clv = float(arr.std(ddof=1))
        sem = std_clv / math.sqrt(n)
        ci_lo, ci_hi = stats.t.interval(0.95, df=n - 1, loc=mean_clv, scale=sem)

        # For n < 30 we keep a higher bar for significance
        reject_h0 = bool(p_value < 0.05 and n >= 30)

        if reject_h0:
            if mean_clv > 0:
                interpretation = f"Statystycznie istotna przewaga CLV ({mean_clv*100:.2f}%). Model bije rynek."
            else:
                interpretation = f"Statystycznie istotna strata CLV ({mean_clv*100:.2f}%). Model przegrywa z rynkiem."
        else:
            interpretation = (
                f"Brak statystycznie istotnej różnicy od 0 "
                f"(n={n}, p={p_value:.3f}). {'Potrzeba więcej danych (min. 30).' if n < 30 else 'CLV nie różni się od zera.'}"
            )

        return {
            "t_stat": float(t_stat),
            "p_value": float(p_value),
            "reject_h0": reject_h0,
            "n_bets": n,
            "mean_clv": mean_clv,
            "std_clv": std_clv,
            "ci_95_low": float(ci_lo),
            "ci_95_high": float(ci_hi),
            "interpretation": interpretation,
        }

    def performance_tier(self) -> str:
        """
        Elite: CLV > 3%
        Professional: 1.5–3%
        Competent: 0.5–1.5%
        Break-even: -0.5% to 0.5%
        Losing: < -0.5%
        """
        clvs = [b.clv for b in self._bets if b.clv is not None]
        if not clvs:
            return "Break-even"
        mean_clv = float(np.mean(clvs))
        pct = mean_clv * 100.0
        if pct > 3.0:
            return "Elite"
        if pct > 1.5:
            return "Professional"
        if pct > 0.5:
            return "Competent"
        if pct >= -0.5:
            return "Break-even"
        return "Losing"

    def summary(self) -> dict:
        """Zwraca pełny dashboard."""
        bets = self._bets
        n = len(bets)

        resolved = [b for b in bets if b.pnl is not None]
        total_stake = sum(b.stake for b in resolved)
        total_pnl = sum(b.pnl for b in resolved)
        roi = (total_pnl / total_stake) if total_stake > 0 else 0.0

        wins = [b for b in resolved if b.actual_result == 1]
        win_rate = len(wins) / len(resolved) if resolved else 0.0

        clvs_all = [b.clv for b in bets if b.clv is not None]

        # Equity curve
        equity_curve = []
        running = 0.0
        for b in bets:
            if b.pnl is not None:
                running += b.pnl
                equity_curve.append(round(running, 4))

        # Max drawdown
        max_drawdown = self._max_drawdown(equity_curve)

        # Profit factor
        gross_profit = sum(b.pnl for b in resolved if b.pnl is not None and b.pnl > 0)
        gross_loss = abs(sum(b.pnl for b in resolved if b.pnl is not None and b.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        return {
            "n_bets": n,
            "roi": round(roi, 4),
            "clv_7d": self.rolling_clv(7),
            "clv_30d": self.rolling_clv(30),
            "clv_90d": self.rolling_clv(90),
            "clv_alltime": float(np.mean(clvs_all)) if clvs_all else None,
            "significance": self.significance_test(),
            "tier": self.performance_tier(),
            "profit_factor": round(profit_factor, 3),
            "max_drawdown": round(max_drawdown, 4),
            "win_rate": round(win_rate, 4),
            "equity_curve": equity_curve,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, bet_id: str) -> BetRecord:
        for b in self._bets:
            if b.bet_id == bet_id:
                return b
        raise KeyError(f"Bet {bet_id} not found")

    def _max_drawdown(self, equity_curve: list) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd:
                max_dd = dd
        return max_dd


import math  # noqa: E402
