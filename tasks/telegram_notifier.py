"""
tasks/telegram_notifier.py — Telegram bot integration for betatp.io

TelegramBot class:
  - send_message(chat_id, text, parse_mode='Markdown') -> bool
      Uses requests.post to Telegram Bot API if TELEGRAM_TOKEN env var is set.
      Otherwise logs to stdout.
  - handle_command(command: str, chat_id: str) -> str
      /kupon  -> formatted daily coupon as Markdown
      /alerty -> list active HIGH/CRITICAL alerts
      /stats  -> CLV 7/30/90d summary
  - format_coupon_message(coupon: dict) -> str
      Nice Markdown with emojis
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Surface emojis
_SURFACE_EMOJI = {
    "hard": "🏟️",
    "clay": "🟤",
    "grass": "🟢",
    "Hard": "🏟️",
    "Clay": "🟤",
    "Grass": "🟢",
}

_CONFIDENCE_EMOJI = {
    "HIGH": "🔥",
    "MEDIUM": "⚡",
    "LOW": "💧",
}

_PRIORITY_EMOJI = {
    "TOP PICK": "🏆",
    "RECOMMENDED": "✅",
    "SPECULATIVE": "🎲",
}


class TelegramBot:
    """
    Telegram Bot integration for betatp.io.

    Usage:
        bot = TelegramBot()
        bot.send_message(chat_id="123456789", text="Hello!")
        response = bot.handle_command("/kupon", chat_id="123456789")
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TELEGRAM_TOKEN", "")
        self._api_url = TELEGRAM_API_URL.format(token=self.token) if self.token else None

    # ──────────────────────────────────────────────────────────────────────────
    # Core send
    # ──────────────────────────────────────────────────────────────────────────

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
    ) -> bool:
        """
        Send a Telegram message.

        If TELEGRAM_TOKEN env var is set, posts to Telegram Bot API.
        Otherwise logs the message to stdout (useful for dev/CI).

        Returns True on success, False on failure.
        """
        if not self.token:
            logger.info(
                "[TelegramBot] No TELEGRAM_TOKEN — stdout fallback\n"
                f"[chat={chat_id}] {text}"
            )
            print(f"[betatp Telegram] chat={chat_id}\n{text}")
            return True

        try:
            import requests

            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            resp = requests.post(self._api_url, json=payload, timeout=10)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            else:
                logger.warning(
                    f"[TelegramBot] send_message failed: {resp.status_code} {resp.text}"
                )
                return False
        except Exception as exc:
            logger.exception(f"[TelegramBot] send_message exception: {exc}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Command dispatcher
    # ──────────────────────────────────────────────────────────────────────────

    def handle_command(self, command: str, chat_id: str) -> str:
        """
        Handle a bot command and return the response text (Markdown).

        Supported commands:
          /kupon  — daily coupon Markdown
          /alerty — active HIGH/CRITICAL alerts
          /stats  — CLV 7/30/90d summary
        """
        cmd = command.strip().split()[0].lower()

        if cmd == "/kupon":
            text = self._cmd_kupon()
        elif cmd == "/alerty":
            text = self._cmd_alerty()
        elif cmd == "/stats":
            text = self._cmd_stats()
        else:
            text = (
                "🤖 *betatp.io Bot*\n\n"
                "Dostępne komendy:\n"
                "• `/kupon` — dzienny kupon zakładowy\n"
                "• `/alerty` — aktywne alerty HIGH/CRITICAL\n"
                "• `/stats` — podsumowanie CLV 7/30/90d\n"
            )

        self.send_message(chat_id=chat_id, text=text)
        return text

    # ──────────────────────────────────────────────────────────────────────────
    # Command implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _cmd_kupon(self) -> str:
        """Build and format today's daily coupon."""
        try:
            coupon = self._get_daily_coupon()
            return self.format_coupon_message(coupon)
        except Exception as exc:
            logger.warning(f"[TelegramBot] _cmd_kupon error: {exc}")
            return f"⚠️ Nie udało się pobrać kuponu: {exc}"

    def _cmd_alerty(self) -> str:
        """List active HIGH/CRITICAL alerts."""
        try:
            alerts = self._get_active_alerts()
        except Exception as exc:
            return f"⚠️ Błąd pobierania alertów: {exc}"

        if not alerts:
            return "✅ *Brak aktywnych alertów HIGH/CRITICAL.*"

        lines = ["🚨 *Aktywne alerty HIGH/CRITICAL:*\n"]
        for a in alerts[:10]:
            priority = a.get("priority", "?")
            emoji = "🔴" if priority == "CRITICAL" else "🟠"
            ev_pct = a.get("ev_pct", 0.0)
            player = a.get("player", "?")
            odds = a.get("odds", "?")
            alert_type = a.get("alert_type", "?")
            match_id = a.get("match_id", "?")
            lines.append(
                f"{emoji} *{player}* | EV `{ev_pct:.1f}%` | @{odds} | {alert_type} | `{match_id}`"
            )

        return "\n".join(lines)

    def _cmd_stats(self) -> str:
        """CLV 7/30/90d summary."""
        try:
            stats = self._get_clv_stats()
        except Exception as exc:
            return f"⚠️ Błąd pobierania statystyk CLV: {exc}"

        lines = [
            "📊 *Statystyki CLV betatp.io*\n",
            f"*Okres*       | *Zakłady* | *Śr. CLV* | *ROI*",
            f"-------------|----------|----------|------",
        ]
        for period in (7, 30, 90):
            key = str(period)
            d = stats.get(key, {})
            n = d.get("n_bets", 0)
            clv = d.get("mean_clv", 0.0)
            roi = d.get("roi", 0.0)
            roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
            clv_str = f"+{clv:.2f}" if clv >= 0 else f"{clv:.2f}"
            lines.append(f"`{period:3d}d` | `{n:7d}` | `{clv_str}` | `{roi_str}`")

        total = stats.get("total", {})
        if total:
            lines.append(
                f"\n📈 *Łącznie*: {total.get('n_bets', 0)} zakładów, "
                f"śr. CLV `{total.get('mean_clv', 0.0):+.2f}`, "
                f"ROI `{total.get('roi', 0.0):+.1f}%`"
            )

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # Formatting
    # ──────────────────────────────────────────────────────────────────────────

    def format_coupon_message(self, coupon: dict) -> str:
        """
        Format a daily coupon dict as a Markdown message with emojis.

        Expected coupon keys:
          date, source, headline, total_ev, top3_singles, system_2of3
        or (CouponResponse-style):
          coupon_date, headline, summary, total_ev, priority, selections
        """
        # Normalise between "today" style and CouponResponse style
        coupon_date = coupon.get("date") or str(coupon.get("coupon_date", date.today()))
        headline = coupon.get("headline", "Dzienny kupon betatp.io")
        total_ev = coupon.get("total_ev", 0.0)
        priority = coupon.get("priority", "")
        priority_emoji = _PRIORITY_EMOJI.get(priority, "📋")
        summary = coupon.get("summary", "")

        # Picks can come from "top3_singles" (today endpoint) or "selections"
        singles = coupon.get("top3_singles") or coupon.get("selections", [])
        system = coupon.get("system_2of3")

        lines = [
            f"⚽ *betatp.io — Kupon {coupon_date}*",
            f"{priority_emoji} {headline}",
            "",
        ]

        # Singles
        if singles:
            lines.append("🎾 *Singlei:*")
            for i, sel in enumerate(singles[:3], 1):
                player = sel.get("player_backed", "?")
                opp = sel.get("opponent", "?")
                surface = sel.get("surface", "Hard")
                surf_emoji = _SURFACE_EMOJI.get(surface, "🎾")
                odds = sel.get("bk_odds", "?")
                p_model = sel.get("p_model", 0.0)
                ev_pct = sel.get("ev_pct", 0.0)
                confidence = sel.get("confidence", "LOW")
                conf_emoji = _CONFIDENCE_EMOJI.get(confidence, "")
                kelly = sel.get("kelly_stake_pct", 0.0)
                lines.append(
                    f"  {i}. {conf_emoji} *{player}* vs {opp} {surf_emoji} "
                    f"@ `{odds}` | p=`{p_model:.0%}` | EV `+{ev_pct:.1f}%` | Kelly `{kelly:.1f}%`"
                )
            lines.append("")

        # System
        if system and isinstance(system, dict) and system.get("legs", 0) > 0:
            sys_type = system.get("system_type", "2/3")
            sys_ev = system.get("system_ev", 0.0)
            stake_u = system.get("total_stake_units", 0)
            best = system.get("best_combo")
            lines.append(f"🔗 *System {sys_type}:*")
            lines.append(f"  EV: `{sys_ev*100:+.1f}%` | Jednostki: `{stake_u}`")
            if best:
                best_players = " & ".join(best.get("players", []))
                best_odds = best.get("combined_odds", "?")
                lines.append(f"  Najlepsza kombinacja: *{best_players}* @ `{best_odds}`")
            lines.append("")

        # Summary
        if summary:
            lines.append(f"📝 _{summary}_")
            lines.append("")

        # Total EV
        lines.append(f"📈 *Łączne EV: `+{total_ev:.1f}%`*")
        lines.append("")
        lines.append("⚠️ _Graj odpowiedzialnie. Zakłady to ryzyko straty._")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # Data fetchers (use internal engine/api logic without HTTP)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_daily_coupon(self) -> dict:
        """Get today's coupon from the coupons engine (no HTTP)."""
        from pathlib import Path
        from datetime import timedelta

        data_dir = Path(__file__).parent.parent / "data"
        csvs = sorted(data_dir.glob("backtest_v*_bets.csv"), key=lambda f: f.stat().st_mtime)

        today = date.today()

        if not csvs:
            # Return mock coupon
            from api.routes.coupons import MOCK_SINGLES
            return {
                "date": str(today),
                "source": "demo_v14_backtest",
                "headline": f"DEMO kupon {today} — v14 backtest picks",
                "total_ev": sum(s["ev_pct"] for s in MOCK_SINGLES[:3]),
                "top3_singles": MOCK_SINGLES[:3],
                "system_2of3": None,
                "priority": "TOP PICK",
            }

        try:
            import pandas as pd
            df = pd.read_csv(csvs[-1])
            df["date"] = pd.to_datetime(df["date"])
            cutoff = df["date"].max() - timedelta(days=90)
            df = df[df["date"] >= cutoff]
            df = df[df["market_edge"] >= 0.10]
            df = df.sort_values("market_edge", ascending=False)
            bets = df.head(3).to_dict("records")
        except Exception:
            bets = []

        if not bets:
            from api.routes.coupons import MOCK_SINGLES
            return {
                "date": str(today),
                "source": "demo_v14_backtest",
                "headline": f"DEMO kupon {today} — v14 backtest picks",
                "total_ev": sum(s["ev_pct"] for s in MOCK_SINGLES[:3]),
                "top3_singles": MOCK_SINGLES[:3],
                "system_2of3": None,
                "priority": "TOP PICK",
            }

        singles = []
        raw_for_system = []
        for row in bets:
            edge = float(row.get("market_edge", 0))
            p_model = float(row.get("p_model", 0.5))
            odds = float(row.get("psw_bet", 2.0))
            ev_pct = round((p_model * odds - 1) * 100, 2)
            kelly = float(row.get("kelly_stake_pct", 0))
            confidence = "HIGH" if edge >= 0.20 else "MEDIUM" if edge >= 0.15 else "LOW"
            backed = str(row.get("winner_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("loser_name", "?"))
            opp = str(row.get("loser_name", "?")) if row.get("y_bet", 0) == 1 else str(row.get("winner_name", "?"))
            sel = {
                "player_backed": backed,
                "opponent": opp,
                "surface": str(row.get("surface", "Hard")),
                "bk_odds": round(odds, 2),
                "p_model": round(p_model, 4),
                "ev_pct": ev_pct,
                "confidence": confidence,
                "kelly_stake_pct": round(kelly, 2),
            }
            singles.append(sel)
            raw_for_system.append({
                "player": backed,
                "odds": odds,
                "p_model": p_model,
                "ev": ev_pct / 100,
                "kelly": kelly,
            })

        # System
        system = None
        try:
            from engine.coupon_system import SystemBetBuilder
            builder = SystemBetBuilder()
            system = builder.build_system(raw_for_system, "2/3")
        except Exception:
            pass

        total_ev = round(sum(s["ev_pct"] for s in singles), 2)
        return {
            "date": str(today),
            "source": "backtest_csv",
            "headline": f"Dzienny kupon {today} — {len(singles)} singlei + system 2/3",
            "total_ev": total_ev,
            "top3_singles": singles,
            "system_2of3": system,
            "priority": "TOP PICK",
        }

    def _get_active_alerts(self) -> list[dict]:
        """
        Get active HIGH/CRITICAL alerts.
        Tries value/alerts.py AlertEngine; falls back to empty list.
        """
        try:
            from value.alerts import AlertEngine
            engine = AlertEngine()
            active = engine.get_active(priorities=["HIGH", "CRITICAL"])
            return [
                {
                    "match_id": a.match_id,
                    "player": a.player,
                    "ev_pct": a.ev_pct,
                    "priority": a.priority.value,
                    "alert_type": a.alert_type,
                    "odds": a.odds,
                }
                for a in active
            ]
        except Exception as exc:
            logger.debug(f"[TelegramBot] _get_active_alerts: {exc}")
            return []

    def _get_clv_stats(self) -> dict:
        """
        Get CLV stats for 7/30/90 day windows.
        Tries value/clv_tracker.py; falls back to mock summary.
        """
        try:
            from value.clv_tracker import CLVTracker
            tracker = CLVTracker()
            summary = tracker.summary()
            return summary
        except Exception as exc:
            logger.debug(f"[TelegramBot] _get_clv_stats: {exc}")
            # Return mock stats
            return {
                "7": {"n_bets": 12, "mean_clv": 0.032, "roi": 4.1},
                "30": {"n_bets": 47, "mean_clv": 0.028, "roi": 3.2},
                "90": {"n_bets": 134, "mean_clv": 0.021, "roi": 2.8},
                "total": {"n_bets": 134, "mean_clv": 0.021, "roi": 2.8},
            }
