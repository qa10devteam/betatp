"""
tests/test_notifier.py — Coverage tests for value/notifier.py
"""
import pytest
from datetime import datetime, timezone

from value.notifier import TelegramFormatter, AlertNotifier
from value.alerts import Alert, Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_alert(ev_pct: float = 6.5, priority: Priority = Priority.HIGH) -> Alert:
    return Alert(
        id="test-uuid-001",
        match_id="wim-2025-001",
        player="Carlos Alcaraz",
        ev_pct=ev_pct,
        priority=priority,
        alert_type="moneyline",
        odds=1.95,
        p_model=0.62,
        created_at=datetime(2025, 7, 7, 10, 30, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. test_telegram_formatter_coupon — returns str with emoji
# ---------------------------------------------------------------------------

def test_telegram_formatter_coupon():
    """format_coupon must return a non-empty string containing at least one emoji."""
    fmt = TelegramFormatter()
    coupon_data = {
        "match": "Alcaraz vs Djokovic",
        "market": "Match Winner",
        "selection": "Alcaraz",
        "odds": 1.85,
        "stake": 2.0,
        "ev_pct": 7.5,
        "kelly_fraction": 0.035,
        "tournament": "Wimbledon 2025",
        "surface": "Grass",
        "match_time": "2025-07-07T14:00:00",
    }
    result = fmt.format_coupon(coupon_data)
    assert isinstance(result, str)
    assert len(result) > 20
    # Must contain at least one emoji character
    assert any(ord(ch) > 127 for ch in result), "Expected at least one non-ASCII (emoji) character"
    # Must mention the match
    assert "Alcaraz" in result


# ---------------------------------------------------------------------------
# 2. test_telegram_formatter_alert — contains EV
# ---------------------------------------------------------------------------

def test_telegram_formatter_alert():
    """format_alert must contain EV information."""
    fmt = TelegramFormatter()
    alert = make_alert(ev_pct=6.5)
    result = fmt.format_alert(alert)
    assert isinstance(result, str)
    # Must contain EV string
    assert "EV" in result or "ev" in result.lower() or "6.50" in result or "+6.50" in result
    # Must contain player name
    assert "Alcaraz" in result


# ---------------------------------------------------------------------------
# 3. test_telegram_formatter_stats — contains CLV
# ---------------------------------------------------------------------------

def test_telegram_formatter_stats():
    """format_stats must contain CLV (avg_clv) information."""
    fmt = TelegramFormatter()
    stats_data = {
        "period": "2025-W27",
        "bets_total": 42,
        "bets_won": 24,
        "win_rate": 0.571,
        "avg_odds": 1.92,
        "avg_clv": 3.4,
        "total_stake": 84.0,
        "total_profit": 12.5,
        "roi": 14.88,
        "yield_pct": 14.88,
    }
    result = fmt.format_stats(stats_data)
    assert isinstance(result, str)
    # Must contain CLV-related keyword
    assert "CLV" in result or "clv" in result.lower() or "3.40" in result or "+3.40" in result
    # Must contain ROI or profit info
    assert "ROI" in result or "P&L" in result or "Profit" in result


# ---------------------------------------------------------------------------
# 4. test_alert_notifier_log_channel — no exceptions
# ---------------------------------------------------------------------------

def test_alert_notifier_log_channel():
    """AlertNotifier.notify on 'log' channel must not raise exceptions."""
    notifier = AlertNotifier()
    alert = make_alert(ev_pct=5.2, priority=Priority.HIGH)
    result = notifier.notify(alert, channel="log")
    assert result is True


def test_alert_notifier_coupon_log():
    """AlertNotifier.notify_coupon on 'log' channel must not raise."""
    notifier = AlertNotifier()
    coupon_data = {
        "match": "Sinner vs Rune",
        "market": "Match Winner",
        "selection": "Sinner",
        "odds": 1.60,
        "stake": 3.0,
        "ev_pct": 4.2,
    }
    result = notifier.notify_coupon(coupon_data, channel="log")
    assert result is True


def test_alert_notifier_stats_log():
    """AlertNotifier.notify_stats on 'log' channel must not raise."""
    notifier = AlertNotifier()
    stats = {
        "period": "2025-W27",
        "bets_total": 10,
        "bets_won": 6,
        "avg_clv": 2.8,
        "roi": 9.5,
    }
    result = notifier.notify_stats(stats, channel="log")
    assert result is True


def test_alert_notifier_unknown_channel_returns_log():
    """Unknown channel falls back to log (returns True, no exception)."""
    notifier = AlertNotifier()
    alert = make_alert()
    result = notifier.notify(alert, channel="unknown_channel")
    assert result is True  # falls back to log
