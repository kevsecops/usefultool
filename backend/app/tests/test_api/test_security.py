"""Tests for security middleware and startup checks."""

from app.core.config import get_settings


def test_security_headers_on_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_weak_admin_token_detection(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    get_settings.cache_clear()
    assert get_settings().is_weak_admin_token() is True

    monkeypatch.setenv("ADMIN_TOKEN", "a" * 32)
    get_settings.cache_clear()
    assert get_settings().is_weak_admin_token() is False
