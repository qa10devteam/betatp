"""
tests/test_api.py — API smoke tests for atpbet.io (FastAPI TestClient)

Run: pytest tests/test_api.py -v
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


# ── Coupons ────────────────────────────────────────────────────────────────────

def test_coupons_today_demo():
    r = client.get("/api/v1/coupons/today?demo=true")
    assert r.status_code == 200
    data = r.json()
    assert data["is_demo"] is True
    assert data["n_value_bets"] == 4
    assert len(data["coupons"]) == 3


def test_coupons_markets():
    r = client.get("/api/v1/coupons/markets")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 6
    aucs = {m["id"]: m["auc"] for m in data["markets"]}
    assert aucs["straight"] == pytest.approx(0.9354, abs=0.001)


def test_coupons_archive():
    r = client.get("/api/v1/coupons/archive?days=7")
    assert r.status_code == 200
    data = r.json()
    assert "total_coupons" in data


# ── Predictions ────────────────────────────────────────────────────────────────

def test_prediction_markets():
    r = client.get("/api/v1/predictions/markets")
    assert r.status_code == 200
    data = r.json()
    assert data["n_loaded"] == 6
    ids = {m["id"] for m in data["markets"]}
    assert ids == {"straight", "fatigue5", "ou39", "ou36", "hcp9", "ou33"}


def test_model_info():
    r = client.get("/api/v1/predictions/model/info")
    assert r.status_code == 200
    data = r.json()
    assert data["n_models"] == 6
    assert data["training_matches"] == 197495
    assert data["backtest"]["win_rate"] == pytest.approx(0.596, abs=0.01)


def test_predict_match():
    payload = {
        "player_a": "Djokovic N.",
        "player_b": "Tsitsipas S.",
        "surface": "Grass",
        "tournament": "Wimbledon",
        "round_num": "QF",
        "odds_a": 1.40,
        "odds_b": 2.80,
    }
    r = client.post("/api/v1/predictions/match", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["player_a"] == "Djokovic N."
    assert data["player_b"] == "Tsitsipas S."
    assert "markets" in data
    assert set(data["markets"].keys()) == {"straight", "fatigue5", "ou39", "ou36", "hcp9", "ou33"}
    for mid, m in data["markets"].items():
        assert "model_prob" in m
        assert "edge" in m
        assert "is_value" in m


def test_predict_match_defaults():
    """Prediction with minimal fields uses defaults."""
    payload = {"player_a": "Alcaraz C.", "player_b": "Ruud C.", "odds_a": 1.60, "odds_b": 2.30}
    r = client.post("/api/v1/predictions/match", json=payload)
    assert r.status_code == 200


# ── Legacy routes still work ───────────────────────────────────────────────────

def test_legacy_coupons():
    r = client.get("/coupons/today?demo=true")
    assert r.status_code == 200


def test_legacy_predictions():
    r = client.get("/predictions/markets")
    assert r.status_code == 200
