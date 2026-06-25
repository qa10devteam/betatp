"""
data/models.py — SQLAlchemy 2.0 ORM models for betatp.io
All tables use Mapped[] / mapped_column() declarative style.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ─── Players ──────────────────────────────────────────────────────────────────

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # player_id from TML-DB
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    dob: Mapped[Optional[date]] = mapped_column(nullable=True)
    hand: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)   # R / L / U
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # cm
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    elo_history: Mapped[list["EloHistory"]] = relationship(
        "EloHistory", back_populates="player", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Player id={self.id} name={self.name!r}>"


# ─── Matches ──────────────────────────────────────────────────────────────────

class Match(Base):
    __tablename__ = "matches"

    # PK: {year}_{tourney_id}_{round}_{winner_id}_{loser_id}
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tourney_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tourney_name: Mapped[str] = mapped_column(String(100), nullable=False)
    surface: Mapped[str] = mapped_column(String(10), nullable=False)          # Hard/Clay/Grass/Carpet
    tourney_level: Mapped[str] = mapped_column(String(5), nullable=False)     # G/M/500/250/D/F
    tourney_date: Mapped[date] = mapped_column(index=True, nullable=False)
    best_of: Mapped[int] = mapped_column(Integer, nullable=False)             # 3 or 5
    round: Mapped[str] = mapped_column(String(10), nullable=False)
    winner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), index=True, nullable=False
    )
    loser_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), index=True, nullable=False
    )
    score: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Winner serve stats ──
    w_ace: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_df: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_svpt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_1stIn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_1stWon: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_2ndWon: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_SvGms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_bpSaved: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_bpFaced: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Loser serve stats ──
    l_ace: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_df: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_svpt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_1stIn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_1stWon: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_2ndWon: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_SvGms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_bpSaved: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    l_bpFaced: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Rankings ──
    winner_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    loser_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Environment flags ──
    is_indoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_high_altitude: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="match", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Match id={self.id!r} date={self.tourney_date}>"


# ─── Elo History ──────────────────────────────────────────────────────────────

class EloHistory(Base):
    __tablename__ = "elo_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), index=True, nullable=False
    )
    match_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("matches.id"), nullable=False
    )
    match_date: Mapped[date] = mapped_column(index=True, nullable=False)

    # ── Multi-surface Elo ratings ──
    overall_elo: Mapped[float] = mapped_column(Float, nullable=False)
    hard_elo: Mapped[float] = mapped_column(Float, nullable=False)
    clay_elo: Mapped[float] = mapped_column(Float, nullable=False)
    grass_elo: Mapped[float] = mapped_column(Float, nullable=False)
    serve_elo: Mapped[float] = mapped_column(Float, nullable=False)
    return_elo: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Match counts (for blend weight) ──
    n_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_hard: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_clay: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_grass: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    player: Mapped["Player"] = relationship("Player", back_populates="elo_history")

    def __repr__(self) -> str:
        return (
            f"<EloHistory player={self.player_id} date={self.match_date} "
            f"elo={self.overall_elo:.1f}>"
        )


# ─── Coupons ──────────────────────────────────────────────────────────────────

class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # {date}_{type}_{hash8}
    date: Mapped[date] = mapped_column(index=True, nullable=False)
    coupon_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # single/2of3/3of4/trixie/yankee
    selections_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of BetSelection
    total_ev: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_stake_units: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending/won/lost/void
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Coupon id={self.id!r} type={self.coupon_type} ev={self.total_ev:.4f}>"


# ─── Subscriptions ────────────────────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    tier: Mapped[str] = mapped_column(String(10), nullable=False)  # FREE/PRO/ELITE
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription user={self.user_id} tier={self.tier!r} expires={self.expires_at}>"


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("matches.id"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # pre_match/in_play/derivative
    market: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # moneyline/total_games/tiebreak/set_betting
    ev_pct: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)  # MEDIUM/HIGH/CRITICAL
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship("Match", back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<Alert id={self.id} match={self.match_id!r} "
            f"priority={self.priority!r} ev={self.ev_pct:.4f}>"
        )
