"""Local appliance mode: the credential-free session endpoint stays sealed
unless LOCAL_MODE is explicitly enabled."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_local_session_is_disabled_by_default() -> None:
    assert Settings().local_mode is False
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/session")
    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_local_session_route_is_documented() -> None:
    assert "/api/v1/auth/session" in app.openapi()["paths"]


def test_local_mode_settings_exist_with_safe_defaults() -> None:
    settings = Settings()
    assert settings.local_operator_email == "operator@terralens.app"
    assert settings.learning_enabled is True
    assert settings.imagery_enabled is True
    assert settings.imagery_max_captures_per_source > 0
    assert settings.learning_retention_days >= settings.learning_baseline_window_days
