"""
tests/integration/test_api_integration.py — FastAPI integration tests (h8)
============================================================================
Tests:
  1. test_health_check    — GET /health -> 200
  2. test_coupons_today   — GET /api/v1/coupons/today -> 200 + 'top_singles' key
  3. test_value_check     — POST /api/v1/value/check -> 200 + 'ev_pct'
  4. test_stats_backtest  — GET /api/v1/stats/backtest -> 200 + roi=58.7
  5. test_alerts_list     — GET /api/v1/alerts -> 200 + list
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---------------------------------------------------------------------------
# App fixture (shared TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Create FastAPI TestClient with the betatp app."""
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Test 1: Health check
# ---------------------------------------------------------------------------

def test_health_check(client):
    """GET /health -> 200 with status='ok'."""
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "status" in data, f"Missing 'status' key in response: {data}"
    assert data["status"] == "ok", f"Expected status='ok', got {data['status']}"


def test_health_check_version(client):
    """GET /health response must include 'version'."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data


# ---------------------------------------------------------------------------
# Test 2: GET /api/v1/coupons/today
# ---------------------------------------------------------------------------

def test_coupons_today(client):
    """GET /api/v1/coupons/today -> 200 + has 'top_singles' key."""
    response = client.get("/api/v1/coupons/today")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:500]}"
    )
    data = response.json()
    assert "top_singles" in data, (
        f"Response must have 'top_singles' key, got keys: {list(data.keys())}"
    )
    assert isinstance(data["top_singles"], list), "'top_singles' must be a list"


def test_coupons_today_has_date(client):
    """GET /api/v1/coupons/today response must include 'date'."""
    response = client.get("/api/v1/coupons/today")
    assert response.status_code == 200
    data = response.json()
    assert "date" in data, f"Missing 'date' key, got: {list(data.keys())}"


# ---------------------------------------------------------------------------
# Test 3: POST /api/v1/value/check
# ---------------------------------------------------------------------------

def test_value_check(client):
    """POST /api/v1/value/check -> 200 + has 'ev_pct'."""
    payload = {
        "player_a": "Carlos Alcaraz",
        "player_b": "Holger Rune",
        "p_model": 0.72,
        "decimal_odds_a": 1.62,
        "decimal_odds_b": 2.45,
    }
    response = client.post("/api/v1/value/check", json=payload)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:500]}"
    )
    data = response.json()
    assert "ev_pct" in data, f"Missing 'ev_pct' in response: {data}"
    assert isinstance(data["ev_pct"], (int, float)), f"ev_pct must be numeric, got {type(data['ev_pct'])}"


def test_value_check_positive_ev(client):
    """POST /api/v1/value/check with p_model > market implied -> ev_pct > 0."""
    payload = {
        "player_a": "Strong Player",
        "player_b": "Weak Player",
        "p_model": 0.80,         # model: 80%
        "decimal_odds_a": 1.50,  # market implied: 66.7% → big value
        "decimal_odds_b": 2.75,
    }
    response = client.post("/api/v1/value/check", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ev_pct"] > 0, f"Expected positive EV, got {data['ev_pct']}"


def test_value_check_required_fields(client):
    """POST /api/v1/value/check response has all required fields."""
    payload = {
        "player_a": "Sinner",
        "player_b": "Zverev",
        "p_model": 0.65,
        "decimal_odds_a": 1.75,
        "decimal_odds_b": 2.15,
    }
    response = client.post("/api/v1/value/check", json=payload)
    assert response.status_code == 200
    data = response.json()
    required_keys = ["ev_pct", "kelly_stake", "devigged_p", "recommendation", "confidence"]
    for key in required_keys:
        assert key in data, f"Missing required key '{key}' in response: {list(data.keys())}"


# ---------------------------------------------------------------------------
# Test 4: GET /api/v1/stats/backtest
# ---------------------------------------------------------------------------

def test_stats_backtest(client):
    """GET /api/v1/stats/backtest -> 200 + roi=58.7."""
    response = client.get("/api/v1/stats/backtest")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:500]}"
    )
    data = response.json()
    assert "roi" in data, f"Missing 'roi' key in response: {data}"
    assert abs(data["roi"] - 58.7) < 0.01, f"Expected roi=58.7, got {data['roi']}"


def test_stats_backtest_has_required_fields(client):
    """GET /api/v1/stats/backtest response has all required fields."""
    response = client.get("/api/v1/stats/backtest")
    assert response.status_code == 200
    data = response.json()
    for key in ["roi", "win_rate", "n_bets", "version"]:
        assert key in data, f"Missing '{key}' in backtest response: {list(data.keys())}"


def test_stats_backtest_v14(client):
    """GET /api/v1/stats/backtest should return v14 results."""
    response = client.get("/api/v1/stats/backtest")
    assert response.status_code == 200
    data = response.json()
    assert data.get("version") == "v14", f"Expected v14, got {data.get('version')}"


# ---------------------------------------------------------------------------
# Test 5: GET /api/v1/alerts
# ---------------------------------------------------------------------------

def test_alerts_list(client):
    """GET /api/v1/alerts -> 200 + list."""
    response = client.get("/api/v1/alerts")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:500]}"
    )
    data = response.json()
    assert isinstance(data, list), f"Expected a list, got {type(data)}: {data}"


def test_alerts_list_empty_or_items(client):
    """GET /api/v1/alerts returns list (may be empty, no crash)."""
    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    data = response.json()
    # Valid: empty list or list of alert dicts
    assert isinstance(data, list)
    for item in data:
        assert isinstance(item, dict), f"Each alert must be a dict, got {type(item)}"


# ---------------------------------------------------------------------------
# Test 6: Additional endpoints sanity checks
# ---------------------------------------------------------------------------

def test_coupons_singles(client):
    """GET /coupons/singles -> 200."""
    response = client.get("/coupons/singles")
    assert response.status_code == 200


def test_stats_clv(client):
    """GET /api/v1/stats/clv -> 200 with CLV data."""
    response = client.get("/api/v1/stats/clv")
    assert response.status_code == 200
    data = response.json()
    assert "avg_clv_30d" in data or "total_bets" in data


def test_openapi_available(client):
    """OpenAPI JSON schema is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
