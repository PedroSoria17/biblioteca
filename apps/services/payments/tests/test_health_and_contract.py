from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from conftest import DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD
from services import status


ORDERS_STATUS = Path(__file__).resolve().parents[2] / "orders" / "services" / "status.py"


def _assert_no_secrets(text: str) -> None:
    for secret in (DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD):
        assert secret not in text


def test_health_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "service": "payments",
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }


def test_health_unavailable_without_redis(client, fake_redis):
    fake_redis.down = True

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["redis"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_health_unavailable_without_database(client, pay_db):
    pay_db.down = True

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["database"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_database_down_on_an_endpoint_is_503(client, admin_headers, pay_db):
    pay_db.down = True

    response = client.get("/payments", headers=admin_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"
    _assert_no_secrets(response.get_data(as_text=True))


def test_wildcard_cors_rejected_in_production(env, monkeypatch, gateway):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ConfigurationError):
        create_app(redis_gateway=gateway)


@pytest.mark.parametrize("name", ["JWT_SECRET_KEY", "REDIS_URL", "DB_PASSWORD"])
def test_missing_required_configuration_fails_fast(env, monkeypatch, gateway, name):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.delenv(name)

    with pytest.raises(ConfigurationError):
        create_app(redis_gateway=gateway)


def test_default_port_is_5005(env, monkeypatch):
    from config import get_settings

    monkeypatch.delenv("FLASK_PORT", raising=False)

    assert get_settings().flask_port == 5005


# ---------------------------------------------------------------------------
# Contract with Orders (apps/services/orders/services/status.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def orders_status():
    if not ORDERS_STATUS.exists():
        pytest.skip("orders service not found")
    spec = importlib.util.spec_from_file_location("orders_status_contract", ORDERS_STATUS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_payments_performs_exactly_the_transitions_orders_delegates(orders_status):
    delegated = orders_status.ORDER_TRANSITIONS - orders_status.ORDERS_SERVICE_TRANSITIONS
    assert status.ORDER_TRANSITIONS_BY_PAYMENTS == delegated
    assert not (status.ORDER_TRANSITIONS_BY_PAYMENTS & orders_status.ORDERS_SERVICE_TRANSITIONS)


def test_order_state_names_match_orders(orders_status):
    assert (status.ORDER_PENDING, status.ORDER_PAID, status.ORDER_COMPLETED, status.ORDER_CANCELLED) == orders_status.STATUSES


def test_refund_restores_stock_according_to_orders_rule(orders_status):
    assert orders_status.restores_stock(status.ORDER_PAID, status.ORDER_CANCELLED)


def test_payment_states_and_methods_match_the_schema():
    assert status.PAYMENT_STATUSES == ("pending", "approved", "rejected", "refunded")
    assert status.PAYMENT_METHODS == ("credit_card", "debit_card", "bank_transfer", "cash")
