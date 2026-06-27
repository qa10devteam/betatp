"""
tests/test_api.py — 10 pytest tests for betatp.io REST API
Iter 129-131
"""
import time
import pytest
from datetime import date

from fastapi.testclient import TestClient
from api.main import app
from api.schemas import CouponResponse

client = TestClient(app)


# ── Test 1: GET /health -> 200 ─────────────────────────────────────────────────

def test_health_200():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ── Test 2: GET /coupons/daily -> 200 + list ───────────────────────────────────

def test_coupons_daily_200():
    response = client.get("/coupons/daily")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


# ── Test 3: GET /coupons/daily: response has required fields ───────────────────

def test_coupons_daily_required_fields():
    response = client.get("/coupons/daily")
    assert response.status_code == 200
    coupons = response.json()
    required_fields = {
        "coupon_id", "coupon_date", "coupon_type", "priority",
        "headline", "summary", "total_ev", "recommended_total_stake", "selections"
    }
    for coupon in coupons:
        for field in required_fields:
            assert field in coupon, f"Missing field: {field}"


# ── Test 4: POST /predictions/match -> 200 + p_win_a + p_win_b ≈ 1.0 ──────────

def test_predict_match_probabilities_sum_to_one():
    payload = {
        "player_a_name": "Novak Djokovic",
        "player_b_name": "Carlos Alcaraz",
        "surface": "grass",
        "tourney_level": "G",
        "best_of": 5,
        "odds_a": 1.75,
        "odds_b": 2.10,
    }
    response = client.post("/predictions/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "p_win_a" in data
    assert "p_win_b" in data
    total = data["p_win_a"] + data["p_win_b"]
    assert abs(total - 1.0) < 1e-4, f"p_win_a + p_win_b = {total} (expected ~1.0)"


# ── Test 5: GET /predictions/player/{id}/elo -> 200 ───────────────────────────

def test_player_elo_200():
    response = client.get("/predictions/player/1/elo")
    assert response.status_code == 200
    data = response.json()
    assert "elo" in data
    assert "player_id" in data
    assert data["player_id"] == 1


# ── Test 6: GET /coupons/history -> 200 ───────────────────────────────────────

def test_coupon_history_200():
    response = client.get("/coupons/history")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ── Test 7: GET /coupons/{invalid_id} -> 404 ──────────────────────────────────

def test_coupon_invalid_id_404():
    response = client.get("/coupons/nonexistent-coupon-id-12345")
    assert response.status_code == 404


# ── Test 8: Prediction latency < 200ms ────────────────────────────────────────

def test_predict_match_latency():
    payload = {
        "player_a_name": "Jannik Sinner",
        "player_b_name": "Daniil Medvedev",
        "surface": "hard",
        "tourney_level": "M",
        "best_of": 3,
        "odds_a": 1.65,
        "odds_b": 2.30,
    }
    t0 = time.perf_counter()
    response = client.post("/predictions/match", json=payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 200.0, f"Prediction latency {elapsed_ms:.1f}ms exceeded 200ms"


# ── Test 9: CouponResponse validates Pydantic schema ──────────────────────────

def test_coupon_response_pydantic_schema():
    response = client.get("/coupons/daily")
    assert response.status_code == 200
    coupons_data = response.json()
    # Validate each coupon with Pydantic
    for raw in coupons_data:
        coupon = CouponResponse(**raw)
        assert coupon.coupon_id
        assert coupon.coupon_date
        assert isinstance(coupon.selections, list)
        assert coupon.total_ev is not None
        assert coupon.priority in ("TOP PICK", "RECOMMENDED", "SPECULATIVE")


# ── Test 10: /health returns version ──────────────────────────────────────────

def test_health_returns_version():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] == "v10.1"
