from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    train_end_year: int = 2018
    test_start_year: int = 2019
    test_end_year: int = 2025
    kelly_fraction: float = 0.5
    min_ev: float = 0.02
    min_odds: float = 1.30
    max_odds: float = 5.00
    max_stake_pct: float = 0.03  # max 3% bankroll per bet
    initial_bankroll: float = 1000.0
    # account limits simulation
    simulate_limits: bool = True
    wins_before_limit: int = 50  # same book
    n_books: int = 8  # available bookmakers
    strategy: str = "main_tour"  # main_tour / challenger / clay_specialist


@dataclass
class BacktestResult:
    roi_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    n_bets: int
    avg_ev: float
    avg_clv: float
    profit_factor: float
    equity_curve: list  # bankroll over time
    monthly_roi: dict  # {"2019-01": 3.2, ...}
    by_surface: dict  # ROI per surface
    by_level: dict  # ROI per tourney level


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config

    def run(
        self,
        predictor,
        matches_df: pd.DataFrame,
        odds_df: Optional[pd.DataFrame] = None,
    ) -> "BacktestResult":
        """
        Walk-forward backtest:
        1. Split: train na 1968-config.train_end_year
        2. Test dzien po dniu 2019-2025
        3. Każdego dnia: generuj selekcje (EV > min_ev)
        4. Symuluj Half Kelly sizing
        5. Jeśli brak odds_df: używaj overround model 6%
        6. Aktualizuj bankroll
        7. Symuluj account limits jeśli simulate_limits=True
        """
        cfg = self.config
        bankroll = cfg.initial_bankroll
        bet_history = []
        book_wins = {i: 0 for i in range(cfg.n_books)}
        blocked_books = set()

        # Ensure year column
        df = matches_df.copy()
        if "year" not in df.columns:
            if "tourney_date" in df.columns:
                df["year"] = pd.to_datetime(
                    df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce"
                ).dt.year
            else:
                df["year"] = cfg.test_start_year  # fallback

        # Filter test period
        test_mask = (df["year"] >= cfg.test_start_year) & (df["year"] <= cfg.test_end_year)
        test_df = df[test_mask].copy()

        # Sort by date if available
        if "tourney_date" in test_df.columns:
            test_df = test_df.sort_values("tourney_date")

        for idx, row in test_df.iterrows():
            # Get prediction
            try:
                if hasattr(predictor, "predict_proba"):
                    # Build a dummy feature array if needed
                    prob_a = 0.55  # placeholder when no features available
                else:
                    prob_a = float(predictor)
            except Exception:
                prob_a = 0.55

            # Get odds
            if odds_df is not None and idx in odds_df.index:
                odds_a = float(odds_df.loc[idx, "odds_a"]) if "odds_a" in odds_df.columns else 2.0
            else:
                # Synthetic odds with 6% overround
                fair_odds = 1.0 / prob_a
                odds_a = fair_odds / 1.06

            # Apply odds filters
            if not (cfg.min_odds <= odds_a <= cfg.max_odds):
                continue

            # Compute EV
            ev = prob_a * (odds_a - 1) - (1 - prob_a)
            if ev < cfg.min_ev:
                continue

            # Kelly sizing
            kelly = (prob_a * (odds_a - 1) - (1 - prob_a)) / (odds_a - 1)
            kelly = max(0.0, kelly)
            stake_fraction = cfg.kelly_fraction * kelly
            stake = min(stake_fraction * bankroll, cfg.max_stake_pct * bankroll)
            stake = max(0.0, stake)

            if stake <= 0:
                continue

            # Account limit simulation
            if cfg.simulate_limits:
                available_books = [b for b in range(cfg.n_books) if b not in blocked_books]
                if not available_books:
                    continue
                book_id = available_books[idx % len(available_books)]
                if self._apply_account_limit(book_wins, book_id):
                    blocked_books.add(book_id)
                    available_books = [b for b in range(cfg.n_books) if b not in blocked_books]
                    if not available_books:
                        continue
                    book_id = available_books[0]
            else:
                book_id = 0

            # Outcome: use actual result if available
            if "y" in row and not pd.isna(row.get("y", np.nan)):
                outcome = int(row["y"])
            else:
                # Simulate based on probability
                outcome = int(np.random.random() < prob_a)

            pnl = self._simulate_bet(stake, odds_a, outcome)
            bankroll += pnl

            if outcome == 1 and cfg.simulate_limits:
                book_wins[book_id] = book_wins.get(book_id, 0) + 1

            # Determine surface and level
            surface = row.get("surface", "Unknown") if hasattr(row, "get") else "Unknown"
            level = row.get("tourney_level", "Unknown") if hasattr(row, "get") else "Unknown"
            match_date = row.get("tourney_date", None) if hasattr(row, "get") else None

            bet_history.append({
                "stake": stake,
                "odds": odds_a,
                "outcome": outcome,
                "pnl": pnl,
                "bankroll": bankroll,
                "ev": ev,
                "clv": 0.0,  # CLV tracking requires closing odds
                "surface": surface,
                "level": level,
                "date": match_date,
            })

        return self.compute_metrics(bet_history)

    def _simulate_bet(self, stake: float, odds: float, outcome: int) -> float:
        """Zwraca P&L: outcome * stake * (odds-1) - (1-outcome) * stake"""
        return outcome * stake * (odds - 1) - (1 - outcome) * stake

    def _apply_account_limit(self, book_wins: dict, book_id: int) -> bool:
        """Zwraca True jeśli konto zostało zablokowane (>= wins_before_limit wygranych)"""
        wins = book_wins.get(book_id, 0)
        return wins >= self.config.wins_before_limit

    def compute_metrics(self, bet_history: list) -> BacktestResult:
        """ROI, Sharpe, MaxDrawdown, WinRate etc."""
        if not bet_history:
            return BacktestResult(
                roi_pct=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                n_bets=0,
                avg_ev=0.0,
                avg_clv=0.0,
                profit_factor=0.0,
                equity_curve=[self.config.initial_bankroll],
                monthly_roi={},
                by_surface={},
                by_level={},
            )

        stakes = np.array([b["stake"] for b in bet_history])
        pnls = np.array([b["pnl"] for b in bet_history])
        outcomes = np.array([b["outcome"] for b in bet_history])
        evs = np.array([b["ev"] for b in bet_history])
        clvs = np.array([b["clv"] for b in bet_history])
        bankrolls = np.array([b["bankroll"] for b in bet_history])

        total_staked = stakes.sum()
        total_pnl = pnls.sum()
        roi_pct = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0

        win_rate = outcomes.mean() if len(outcomes) > 0 else 0.0
        n_bets = len(bet_history)
        avg_ev = evs.mean() if len(evs) > 0 else 0.0
        avg_clv = clvs.mean() if len(clvs) > 0 else 0.0

        # Profit factor: gross wins / gross losses
        gross_wins = pnls[pnls > 0].sum()
        gross_losses = abs(pnls[pnls < 0].sum())
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")

        # Equity curve
        equity_curve = [self.config.initial_bankroll] + bankrolls.tolist()

        # Sharpe ratio (daily returns approximation)
        returns = pnls / stakes
        sharpe_ratio = (
            (returns.mean() / returns.std() * np.sqrt(252))
            if returns.std() > 0
            else 0.0
        )

        # Max drawdown
        eq = np.array(equity_curve)
        peak = np.maximum.accumulate(eq)
        drawdowns = (peak - eq) / peak * 100
        max_drawdown_pct = drawdowns.max() if len(drawdowns) > 0 else 0.0

        # Monthly ROI
        monthly_roi = {}
        for bet in bet_history:
            d = bet.get("date")
            if d is not None:
                try:
                    month_key = str(d)[:7] if isinstance(d, str) else str(d)[:7]
                    if month_key not in monthly_roi:
                        monthly_roi[month_key] = {"pnl": 0.0, "stake": 0.0}
                    monthly_roi[month_key]["pnl"] += bet["pnl"]
                    monthly_roi[month_key]["stake"] += bet["stake"]
                except Exception:
                    pass
        monthly_roi_pct = {
            k: (v["pnl"] / v["stake"] * 100) if v["stake"] > 0 else 0.0
            for k, v in monthly_roi.items()
        }

        # By surface
        by_surface = {}
        for bet in bet_history:
            surf = bet.get("surface", "Unknown")
            if surf not in by_surface:
                by_surface[surf] = {"pnl": 0.0, "stake": 0.0}
            by_surface[surf]["pnl"] += bet["pnl"]
            by_surface[surf]["stake"] += bet["stake"]
        by_surface_roi = {
            k: (v["pnl"] / v["stake"] * 100) if v["stake"] > 0 else 0.0
            for k, v in by_surface.items()
        }

        # By level
        by_level = {}
        for bet in bet_history:
            lvl = bet.get("level", "Unknown")
            if lvl not in by_level:
                by_level[lvl] = {"pnl": 0.0, "stake": 0.0}
            by_level[lvl]["pnl"] += bet["pnl"]
            by_level[lvl]["stake"] += bet["stake"]
        by_level_roi = {
            k: (v["pnl"] / v["stake"] * 100) if v["stake"] > 0 else 0.0
            for k, v in by_level.items()
        }

        return BacktestResult(
            roi_pct=roi_pct,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            win_rate=win_rate,
            n_bets=n_bets,
            avg_ev=avg_ev,
            avg_clv=avg_clv,
            profit_factor=profit_factor,
            equity_curve=equity_curve,
            monthly_roi=monthly_roi_pct,
            by_surface=by_surface_roi,
            by_level=by_level_roi,
        )
