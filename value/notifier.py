"""
notifier.py — Telegram formatting & alert notification for betatp.io
"""

from __future__ import annotations

import logging
import os
from datetime import timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .alerts import Alert

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import requests as _requests_lib  # type: ignore
    _REQUESTS_AVAILABLE = True
except ImportError:
    _requests_lib = None            # type: ignore[assignment]
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# TelegramFormatter
# ---------------------------------------------------------------------------

class TelegramFormatter:
    """Produces Markdown-formatted messages suitable for Telegram Bot API."""

    # Priority → emoji mapping
    _PRIORITY_EMOJI = {
        "CRITICAL": "🚨",
        "HIGH":     "🔴",
        "MEDIUM":   "🟡",
    }

    # ---------------------------------------------------------------------------
    # format_coupon
    # ---------------------------------------------------------------------------

    def format_coupon(self, coupon_data: dict) -> str:
        """
        Format a betting coupon summary.

        Expected keys in *coupon_data* (all optional with sensible defaults):
            match, market, selection, odds, stake, ev_pct, kelly_fraction,
            tournament, surface, match_time (ISO string or datetime)
        """
        match       = coupon_data.get("match", "Unknown vs Unknown")
        market      = coupon_data.get("market", "—")
        selection   = coupon_data.get("selection", "—")
        odds        = coupon_data.get("odds", 0.0)
        stake       = coupon_data.get("stake", 0.0)
        ev_pct      = coupon_data.get("ev_pct", 0.0)
        kelly       = coupon_data.get("kelly_fraction", None)
        tournament  = coupon_data.get("tournament", "")
        surface     = coupon_data.get("surface", "")
        match_time  = coupon_data.get("match_time", "")

        # Format optional fields
        tournament_line = f"🏆 *Tournament:* {self._esc(tournament)}\n" if tournament else ""
        surface_line    = f"🎾 *Surface:* {self._esc(surface)}\n"    if surface    else ""
        time_line       = f"🕐 *Match time:* {self._esc(str(match_time))}\n" if match_time else ""
        kelly_line      = f"📐 *Kelly fraction:* {kelly:.2%}\n"              if kelly is not None else ""

        ev_emoji = "🟢" if ev_pct >= 5 else "🟡"

        lines = [
            "🎯 *BETTING COUPON*",
            "━━━━━━━━━━━━━━━━━━━━",
            f"⚽ *Match:* {self._esc(match)}",
        ]
        if tournament_line:
            lines.append(tournament_line.rstrip())
        if surface_line:
            lines.append(surface_line.rstrip())
        if time_line:
            lines.append(time_line.rstrip())
        lines += [
            f"📊 *Market:* {self._esc(market)}",
            f"✅ *Selection:* {self._esc(selection)}",
            f"💰 *Odds:* `{odds:.2f}`",
            f"💵 *Stake:* `{stake:.2f}u`",
            f"{ev_emoji} *EV:* `{ev_pct:+.2f}%`",
        ]
        if kelly_line:
            lines.append(kelly_line.rstrip())
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    # ---------------------------------------------------------------------------
    # format_alert
    # ---------------------------------------------------------------------------

    def format_alert(self, alert: "Alert") -> str:
        """Format a single Alert as a Markdown string."""
        priority_str = getattr(alert.priority, "value", str(alert.priority))
        emoji = self._PRIORITY_EMOJI.get(priority_str, "ℹ️")
        ev_sign = "+" if alert.ev_pct >= 0 else ""

        # created_at might be naive or aware
        created_at = alert.created_at
        if hasattr(created_at, "astimezone"):
            created_str = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            created_str = str(created_at)

        lines = [
            f"{emoji} *{priority_str} ALERT*",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎾 *Player:* {self._esc(alert.player)}",
            f"🔑 *Match ID:* `{self._esc(str(alert.match_id))}`",
            f"📊 *Market:* {self._esc(alert.alert_type)}",
            f"💰 *Odds:* `{alert.odds:.2f}`",
            f"🧮 *Model P:* `{alert.p_model:.4f}` ({alert.p_model:.2%})",
            f"📈 *EV:* `{ev_sign}{alert.ev_pct:.2f}%`",
            f"🕐 *Created:* {created_str}",
            f"🆔 `{alert.id}`",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)

    # ---------------------------------------------------------------------------
    # format_stats
    # ---------------------------------------------------------------------------

    def format_stats(self, clv_data: dict) -> str:
        """
        Format a CLV / performance stats summary.

        Expected keys (all optional):
            period, bets_total, bets_won, win_rate, avg_odds, avg_clv,
            total_stake, total_profit, roi, yield_pct
        """
        period       = clv_data.get("period", "—")
        bets_total   = clv_data.get("bets_total", 0)
        bets_won     = clv_data.get("bets_won", 0)
        win_rate     = clv_data.get("win_rate", None)
        avg_odds     = clv_data.get("avg_odds", None)
        avg_clv      = clv_data.get("avg_clv", None)
        total_stake  = clv_data.get("total_stake", None)
        total_profit = clv_data.get("total_profit", None)
        roi          = clv_data.get("roi", None)
        yield_pct    = clv_data.get("yield_pct", None)

        # Derived win rate
        if win_rate is None and bets_total > 0:
            win_rate = bets_won / bets_total

        profit_emoji = "🟢" if (total_profit or 0) >= 0 else "🔴"
        roi_emoji    = "📈" if (roi or 0) >= 0 else "📉"

        lines = [
            "📊 *PERFORMANCE STATS*",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📅 *Period:* {self._esc(str(period))}",
            f"📋 *Bets:* {bets_total} total / {bets_won} won",
        ]
        if win_rate is not None:
            lines.append(f"🎯 *Win rate:* `{win_rate:.2%}`")
        if avg_odds is not None:
            lines.append(f"💰 *Avg odds:* `{avg_odds:.3f}`")
        if avg_clv is not None:
            clv_sign = "+" if avg_clv >= 0 else ""
            lines.append(f"📐 *Avg CLV:* `{clv_sign}{avg_clv:.2f}%`")
        if total_stake is not None:
            lines.append(f"💵 *Total staked:* `{total_stake:.2f}u`")
        if total_profit is not None:
            profit_sign = "+" if total_profit >= 0 else ""
            lines.append(f"{profit_emoji} *P&L:* `{profit_sign}{total_profit:.2f}u`")
        if roi is not None:
            roi_sign = "+" if roi >= 0 else ""
            lines.append(f"{roi_emoji} *ROI:* `{roi_sign}{roi:.2f}%`")
        if yield_pct is not None:
            yield_sign = "+" if yield_pct >= 0 else ""
            lines.append(f"📊 *Yield:* `{yield_sign}{yield_pct:.2f}%`")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _esc(text: str) -> str:
        """Escape Markdown special characters for Telegram MarkdownV1."""
        # In MarkdownV1 only *, _, `, [ need escaping with backslash
        for ch in ("_", "*", "`", "["):
            text = text.replace(ch, f"\\{ch}")
        return text


# ---------------------------------------------------------------------------
# AlertNotifier
# ---------------------------------------------------------------------------

class AlertNotifier:
    """
    Dispatches alerts to one or more channels.

    Channels
    --------
    ``'log'``      — Python logging only (default, always available)
    ``'telegram'`` — Telegram Bot API (requires TELEGRAM_TOKEN +
                     TELEGRAM_CHAT_ID env vars and the *requests* library)
    """

    _TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, formatter: Optional[TelegramFormatter] = None):
        self.formatter = formatter or TelegramFormatter()
        self._token   = os.environ.get("TELEGRAM_TOKEN", "").strip()
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify(self, alert: "Alert", channel: str = "log") -> bool:
        """
        Dispatch *alert* to the chosen channel.

        Parameters
        ----------
        alert   : Alert  — the alert to send
        channel : str    — ``'log'`` or ``'telegram'``

        Returns True on success, False on failure.
        """
        channel = channel.lower().strip()

        if channel == "log":
            return self._send_log(alert)
        if channel == "telegram":
            return self._send_telegram(alert)

        logger.warning("Unknown notification channel: %r — falling back to log", channel)
        return self._send_log(alert)

    # ------------------------------------------------------------------
    # Channel implementations
    # ------------------------------------------------------------------

    def _send_log(self, alert: "Alert") -> bool:
        priority_str = getattr(alert.priority, "value", str(alert.priority))
        logger.info(
            "[ALERT][%s] match=%s player=%s type=%s EV=%.2f%% odds=%.2f",
            priority_str,
            alert.match_id,
            alert.player,
            alert.alert_type,
            alert.ev_pct,
            alert.odds,
        )
        return True

    def _send_telegram(self, alert: "Alert") -> bool:
        """Send a formatted alert via the Telegram Bot API."""
        if not _REQUESTS_AVAILABLE:
            logger.error(
                "Telegram channel requested but 'requests' is not installed. "
                "Install it with: pip install requests"
            )
            return False

        if not self._token:
            logger.error("TELEGRAM_TOKEN env var is not set — cannot send Telegram message.")
            return False
        if not self._chat_id:
            logger.error("TELEGRAM_CHAT_ID env var is not set — cannot send Telegram message.")
            return False

        text = self.formatter.format_alert(alert)
        url  = self._TELEGRAM_API.format(token=self._token)
        payload = {
            "chat_id":    self._chat_id,
            "text":       text,
            "parse_mode": "Markdown",
        }

        try:
            resp = _requests_lib.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram alert sent for alert_id=%s", alert.id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send Telegram alert: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def notify_coupon(self, coupon_data: dict, channel: str = "log") -> bool:
        """Format and dispatch a coupon message."""
        text = self.formatter.format_coupon(coupon_data)
        return self._dispatch_text(text, channel, label="COUPON")

    def notify_stats(self, clv_data: dict, channel: str = "log") -> bool:
        """Format and dispatch a stats message."""
        text = self.formatter.format_stats(clv_data)
        return self._dispatch_text(text, channel, label="STATS")

    def _dispatch_text(self, text: str, channel: str, label: str = "") -> bool:
        channel = channel.lower().strip()
        if channel == "log":
            logger.info("[%s]\n%s", label, text)
            return True
        if channel == "telegram":
            if not _REQUESTS_AVAILABLE or not self._token or not self._chat_id:
                logger.error(
                    "Telegram not configured for %s dispatch. "
                    "Need requests lib + TELEGRAM_TOKEN + TELEGRAM_CHAT_ID",
                    label,
                )
                return False
            url = self._TELEGRAM_API.format(token=self._token)
            payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"}
            try:
                resp = _requests_lib.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram dispatch failed (%s): %s", label, exc)
                return False
        logger.warning("Unknown channel %r for %s dispatch", channel, label)
        return False
