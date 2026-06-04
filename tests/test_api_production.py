"""Tests de integración contra la API REST **en producción** (Render).

Pegan a la URL viva — requieren red. Se marcan con @pytest.mark.integration y se
saltan automáticamente si el servicio no responde (p. ej. sin internet).

URL configurable con la env var API_URL; por defecto el deploy de Render.
Correr solo estos:   pytest -m integration
Saltarlos:           pytest -m "not integration"
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("API_URL", "https://risk-profiling-api.onrender.com").rstrip("/")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def base_url() -> str:
    """Despierta el servicio (Render free duerme tras 15 min) y devuelve la URL.
    Si no responde tras varios intentos, saltea los tests de integración."""
    last = None
    for _ in range(6):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=60)
            if r.status_code == 200:
                return BASE_URL
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:  # noqa: PERF203
            last = str(exc)
    pytest.skip(f"API no disponible en {BASE_URL} ({last})")


def test_health(base_url):
    r = requests.get(f"{base_url}/health", timeout=30)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_user_risk_known_very_high(base_url):
    r = requests.get(f"{base_url}/users/USR0010/risk", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "USR0010"
    assert body["category"] == "VERY_HIGH"
    assert body["score"] >= 80
    assert isinstance(body["top_signals"], list) and body["top_signals"]


def test_user_risk_not_found_returns_404(base_url):
    r = requests.get(f"{base_url}/users/NO_EXISTE_999/risk", timeout=30)
    assert r.status_code == 404


def test_list_by_category_sorted_desc(base_url):
    r = requests.get(f"{base_url}/users", params={"category": "VERY_HIGH", "limit": 5}, timeout=30)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) <= 5
    assert all(u["category"] == "VERY_HIGH" for u in items)
    scores = [u["score"] for u in items]
    assert scores == sorted(scores, reverse=True)  # ordenado por score desc


def test_list_invalid_category_returns_422(base_url):
    r = requests.get(f"{base_url}/users", params={"category": "FOO"}, timeout=30)
    assert r.status_code == 422


def test_list_respects_limit(base_url):
    r = requests.get(f"{base_url}/users", params={"limit": 3}, timeout=30)
    assert r.status_code == 200
    assert len(r.json()) <= 3
