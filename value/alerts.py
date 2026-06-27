"""
alerts.py — AlertEngine for betatp.io
Manages creation, deduplication, prioritisation, and lifecycle of value alerts.
"""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    CRITICAL = "CRITICAL"   # EV > 8 %
    HIGH     = "HIGH"       # 5 % – 8 %
    MEDIUM   = "MEDIUM"     # 2 % – 5 %

    @classmethod
    def from_ev(cls, ev_pct: float) -> "Priority":
        """Derive priority from EV expressed as a percentage (e.g. 6.5 for 6.5 %)."""
        if ev_pct > 8.0:
            return cls.CRITICAL
        if ev_pct > 5.0:
            return cls.HIGH
        return cls.MEDIUM


# ---------------------------------------------------------------------------
# Alert dataclass
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    id:         str
    match_id:   str
    player:     str
    ev_pct:     float          # e.g. 6.5 means 6.5 %
    priority:   Priority
    alert_type: str            # e.g. "moneyline", "total_games", "tiebreak"
    odds:       float
    p_model:    float          # model's implied probability (0–1)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent:       bool = False


# ---------------------------------------------------------------------------
# AlertEngine
# ---------------------------------------------------------------------------

class AlertEngine:
    """
    Manages alerts in memory.  Redis is used as an optional secondary
    deduplication / persistence layer when a client is supplied.
    """

    # Minimum EV to create an alert at all (below MEDIUM threshold is noise)
    MIN_EV_PCT: float = 2.0

    def __init__(self, redis_client=None):
        """
        Parameters
        ----------
        redis_client : optional
            Any object exposing ``set(key, value, ex=seconds)`` and
            ``exists(key) -> int``.  Pass ``None`` (default) for pure
            in-memory operation.
        """
        self._alerts: Dict[str, Alert] = {}          # id -> Alert
        self._seen:   Dict[str, datetime] = {}        # dedup key -> first-seen
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_alert(
        self,
        match_id:   str,
        player:     str,
        ev_pct:     float,
        odds:       float,
        p_model:    float,
        alert_type: str,
    ) -> Optional[Alert]:
        """
        Create and store an Alert if EV is above the minimum threshold.

        Returns the Alert on success or ``None`` if EV is too low.
        """
        if ev_pct < self.MIN_EV_PCT:
            logger.debug(
                "Alert skipped (EV %.2f%% < %.2f%%): %s / %s",
                ev_pct, self.MIN_EV_PCT, match_id, player,
            )
            return None

        priority = Priority.from_ev(ev_pct)
        alert = Alert(
            id=str(uuid.uuid4()),
            match_id=match_id,
            player=player,
            ev_pct=round(ev_pct, 4),
            priority=priority,
            alert_type=alert_type,
            odds=odds,
            p_model=round(p_model, 6),
        )
        self._alerts[alert.id] = alert
        logger.info(
            "Alert created [%s] %s | %s | EV=%.2f%% | odds=%.2f",
            priority.value, match_id, player, ev_pct, odds,
        )
        return alert

    def deduplicate(self, alert: Alert) -> bool:
        """
        Return ``True`` if this alert is a duplicate (already seen recently).

        The dedup key is ``{match_id}:{player}:{alert_type}``.
        Window is 6 hours in memory; Redis TTL mirrors this when available.

        Side-effect: registers the alert as seen when it is *not* a duplicate.
        """
        key = f"{alert.match_id}:{alert.player}:{alert.alert_type}"
        ttl_seconds = 6 * 3600

        # --- Redis path -------------------------------------------------------
        if self._redis is not None:
            try:
                redis_key = f"alert_dedup:{key}"
                if self._redis.exists(redis_key):
                    logger.debug("Duplicate (Redis): %s", key)
                    return True
                self._redis.set(redis_key, "1", ex=ttl_seconds)
                return False
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis dedup error (%s), falling back to memory", exc)

        # --- In-memory path ---------------------------------------------------
        now = datetime.now(timezone.utc)
        if key in self._seen:
            age = (now - self._seen[key]).total_seconds()
            if age < ttl_seconds:
                logger.debug("Duplicate (memory): %s (age %.0fs)", key, age)
                return True

        self._seen[key] = now
        return False

    def get_active_alerts(self, priority: Optional[Priority] = None) -> List[Alert]:
        """
        Return all active (not expired, not yet sent) alerts.

        Parameters
        ----------
        priority : Priority, optional
            If given, filter to only alerts matching this priority level.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        results = [
            a for a in self._alerts.values()
            if a.created_at >= cutoff
        ]
        if priority is not None:
            results = [a for a in results if a.priority == priority]
        # Most critical / newest first
        results.sort(key=lambda a: (list(Priority).index(a.priority), -a.created_at.timestamp()))
        return results

    def mark_sent(self, alert_id: str) -> bool:
        """Mark an alert as sent.  Returns True if the alert was found."""
        if alert_id in self._alerts:
            self._alerts[alert_id].sent = True
            return True
        return False

    def clear_old(self, hours: float = 6) -> int:
        """
        Remove alerts older than *hours* from the in-memory store.

        Returns the number of alerts removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stale = [aid for aid, a in self._alerts.items() if a.created_at < cutoff]
        for aid in stale:
            del self._alerts[aid]
        # Also clean dedup seen-dict
        stale_keys = [k for k, ts in self._seen.items() if (datetime.now(timezone.utc) - ts).total_seconds() > hours * 3600]
        for k in stale_keys:
            del self._seen[k]
        if stale:
            logger.info("Cleared %d stale alert(s) (older than %.1fh)", len(stale), hours)
        return len(stale)

    # ------------------------------------------------------------------
    # Helpers / properties
    # ------------------------------------------------------------------

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AlertEngine alerts={self.alert_count}>"
