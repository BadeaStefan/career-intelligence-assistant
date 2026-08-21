"""The upload limit must be published, not duplicated in the client.

The web app cannot enforce or even describe a limit it has no way to learn, so
the empty state hardcoded "max 5 MB" -- a number that stayed put while
MAX_UPLOAD_BYTES changed underneath it. This endpoint is the single source.
"""

from fastapi.testclient import TestClient

from career_intel.api.app import create_app
from career_intel.config import Settings, get_settings


def test_config_reports_the_configured_upload_limit() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=12345)

    response = TestClient(app).get("/config")

    assert response.status_code == 200
    assert response.json() == {"max_upload_bytes": 12345}


def test_config_never_leaks_the_api_key() -> None:
    """The payload reaches the browser, so it carries only what the browser needs."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-secret", database_url="postgresql+asyncpg://u:pw@h/db"
    )

    body = TestClient(app).get("/config").text

    assert "sk-secret" not in body
    assert "pw" not in body
