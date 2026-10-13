import pytest
from app.core.config import settings
from app.models.job import Job
from app.models.enums import JobStatus

def test_missing_api_key(unauthenticated_client):
    response = unauthenticated_client.post("/api/v1/jobs/", json={
        "course_name": "Test Course",
        "issue_date": "2024-01-01",
        "recipients": [{"name": "Alice", "email": "alice@example.com"}]
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API Key header"

def test_empty_api_key(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/v1/jobs/",
        headers={settings.api_key_name: ""},
        json={
            "course_name": "Test Course",
            "issue_date": "2024-01-01",
            "recipients": [{"name": "Alice", "email": "alice@example.com"}]
        }
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API Key header"

def test_invalid_api_key(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/v1/jobs/",
        headers={settings.api_key_name: "invalid-secret-key"},
        json={
            "course_name": "Test Course",
            "issue_date": "2024-01-01",
            "recipients": [{"name": "Alice", "email": "alice@example.com"}]
        }
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

def test_valid_api_key_succeeds(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/v1/jobs/",
        headers={settings.api_key_name: settings.api_key},
        json={
            "course_name": "Test Course",
            "issue_date": "2024-01-01",
            "recipients": [{"name": "Alice", "email": "alice@example.com"}]
        }
    )
    assert response.status_code == 202

def test_protected_get_job_without_key(unauthenticated_client, db_session):
    job = Job(id="test-job-auth", total=1, status=JobStatus.COMPLETED, succeeded=1, failed=0)
    db_session.add(job)
    db_session.commit()

    response = unauthenticated_client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == 401

def test_protected_certificates_endpoint_without_key(unauthenticated_client):
    response = unauthenticated_client.get("/api/v1/certificates/some-id/download")
    assert response.status_code == 401

def test_health_check_does_not_require_api_key(unauthenticated_client):
    response = unauthenticated_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_openapi_spec_includes_api_key_security(unauthenticated_client):
    response = unauthenticated_client.get("/openapi.json")
    assert response.status_code == 200
    openapi = response.json()
    assert "components" in openapi
    assert "securitySchemes" in openapi["components"]
    assert "APIKeyHeader" in openapi["components"]["securitySchemes"]
    scheme = openapi["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme["type"] == "apiKey"
    assert scheme["name"] == settings.api_key_name
    assert scheme["in"] == "header"
