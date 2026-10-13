import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.job import Job
from app.models.enums import JobStatus

@pytest.fixture
def rate_limit_payload():
    return {
        "course_name": "Rate Limit Test Course",
        "issue_date": "2024-01-01",
        "recipients": [{"name": "Rate Test User", "email": "ratetest@example.com"}]
    }

def test_post_jobs_rate_limit_exceeded(rate_limit_payload, db_session):
    client_ip_1 = TestClient(
        app,
        client=("192.168.1.10", 50000),
        headers={settings.api_key_name: settings.api_key}
    )

    # First 5 requests within a minute must succeed (202 Accepted)
    for i in range(5):
        response = client_ip_1.post("/api/v1/jobs/", json=rate_limit_payload)
        assert response.status_code == 202, f"Request {i+1} failed with status {response.status_code}"

    # 6th request from the same IP must be rejected with 429 Too Many Requests
    blocked_response = client_ip_1.post("/api/v1/jobs/", json=rate_limit_payload)
    assert blocked_response.status_code == 429
    data = blocked_response.json()
    assert "error" in data
    assert "Rate limit exceeded" in data["error"]

def test_rate_limit_isolated_per_ip(rate_limit_payload, db_session):
    client_ip_1 = TestClient(
        app,
        client=("10.0.0.1", 50000),
        headers={settings.api_key_name: settings.api_key}
    )
    client_ip_2 = TestClient(
        app,
        client=("10.0.0.2", 50000),
        headers={settings.api_key_name: settings.api_key}
    )

    # Exhaust limit for IP 1
    for _ in range(5):
        res = client_ip_1.post("/api/v1/jobs/", json=rate_limit_payload)
        assert res.status_code == 202

    # IP 1 is blocked
    assert client_ip_1.post("/api/v1/jobs/", json=rate_limit_payload).status_code == 429

    # IP 2 should still be allowed to make requests
    res_ip2 = client_ip_2.post("/api/v1/jobs/", json=rate_limit_payload)
    assert res_ip2.status_code == 202

def test_rate_limit_does_not_block_get_job(rate_limit_payload, db_session):
    client = TestClient(
        app,
        client=("192.168.1.50", 50000),
        headers={settings.api_key_name: settings.api_key}
    )

    # Exhaust rate limit on POST /api/v1/jobs/
    last_job_id = None
    for _ in range(5):
        res = client.post("/api/v1/jobs/", json=rate_limit_payload)
        assert res.status_code == 202
        last_job_id = res.json()["job_id"]

    assert client.post("/api/v1/jobs/", json=rate_limit_payload).status_code == 429

    # GET /api/v1/jobs/{job_id} must still be accessible
    get_res = client.get(f"/api/v1/jobs/{last_job_id}")
    assert get_res.status_code == 200

def test_rate_limiter_reset(rate_limit_payload, db_session):
    client = TestClient(
        app,
        client=("192.168.1.99", 50000),
        headers={settings.api_key_name: settings.api_key}
    )

    for _ in range(5):
        assert client.post("/api/v1/jobs/", json=rate_limit_payload).status_code == 202

    assert client.post("/api/v1/jobs/", json=rate_limit_payload).status_code == 429

    # Reset limiter
    limiter.reset()

    # After reset, the same IP can submit jobs again
    assert client.post("/api/v1/jobs/", json=rate_limit_payload).status_code == 202
