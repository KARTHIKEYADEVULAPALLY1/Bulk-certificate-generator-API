from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_root_redirect():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"

def test_healthz_all_healthy():
    """Verify /healthz actively checks DB and storage and returns HTTP 200 when healthy."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"]["status"] == "up"
    assert data["checks"]["storage"]["status"] == "up"
    assert "backend" in data["checks"]["storage"]
    assert "x-correlation-id" in response.headers

def test_healthz_public_without_api_key():
    """Verify /healthz is unauthenticated and can be reached without X-API-Key."""
    response = client.get("/healthz")
    assert response.status_code == 200

def test_healthz_preserves_custom_correlation_id():
    """Verify /healthz preserves client-supplied X-Correlation-ID and X-Request-ID."""
    custom_id = "trace-custom-correlation-98765"
    response = client.get("/healthz", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == custom_id
    assert response.headers["x-request-id"] == custom_id

def test_healthz_database_failure():
    """Verify /healthz returns HTTP 503 degraded status when database is unreachable."""
    with patch("app.main.SessionLocal") as mock_session_local:
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_session
        mock_session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("Database connection failed"))
        mock_session_local.return_value = mock_session

        response = client.get("/healthz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "down"
        assert "Database connection failed" in data["checks"]["database"]["error"]

def test_healthz_storage_failure():
    """Verify /healthz returns HTTP 503 degraded status when storage backend probe fails."""
    with patch("app.main.get_storage_backend") as mock_storage_factory:
        mock_backend = MagicMock()
        mock_backend.check_health.return_value = (False, "Storage directory not writable")
        mock_storage_factory.return_value = mock_backend

        response = client.get("/healthz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["storage"]["status"] == "down"
        assert "Storage directory not writable" in data["checks"]["storage"]["error"]

