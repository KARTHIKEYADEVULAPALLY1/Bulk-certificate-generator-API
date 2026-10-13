import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.rate_limit import limiter

@pytest.fixture(autouse=True)
def reset_limiter():
    limiter.reset()
    yield
    limiter.reset()

@pytest.fixture
def rate_limit_payload():
    return {
        "course_name": "Rate Limit Test Course",
        "issue_date": "2024-01-01",
        "recipients": [
            {"name": "Rate Test User", "email": "ratetest@example.com"}
        ]
    }

def test_post_jobs_rate_limit_exceeded(rate_limit_payload, db_session):
    client = TestClient(app, headers={settings.api_key_name: settings.api_key})
    
    for i in range(5):
        response = client.post(
            "/api/v1/jobs/", 
            json=rate_limit_payload,
            headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.10"}
        )
        assert response.status_code == 202, f"Request {i+1} failed with {response.status_code}"

    response = client.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.10"}
    )
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json().get("error", "")

def test_rate_limit_isolated_per_ip(rate_limit_payload, db_session):
    limiter.reset()
    client_ip1 = TestClient(
        app,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "10.0.0.1"}
    )
    
    for _ in range(5):
        client_ip1.post(
            "/api/v1/jobs/", 
            json=rate_limit_payload,
        )
        
    res_ip1 = client_ip1.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
    )
    assert res_ip1.status_code == 429

    client_ip2 = TestClient(
        app,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "10.0.0.2"}
    )
    res_ip2 = client_ip2.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
    )
    assert res_ip2.status_code == 202


def test_rate_limit_does_not_block_get_job(rate_limit_payload, db_session):
    client = TestClient(app, headers={settings.api_key_name: settings.api_key})
    
    for _ in range(5):
        client.post(
            "/api/v1/jobs/", 
            json=rate_limit_payload,
            headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.50"}
        )
        
    res_post = client.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.50"}
    )
    assert res_post.status_code == 429

    res_get = client.get(
        "/api/v1/jobs/nonexistent",
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.50"}
    )
    assert res_get.status_code == 404

def test_rate_limiter_reset(rate_limit_payload, db_session):
    client = TestClient(app, headers={settings.api_key_name: settings.api_key})
    
    for _ in range(5):
        client.post(
            "/api/v1/jobs/", 
            json=rate_limit_payload,
            headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.99"}
        )
        
    assert client.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.99"}
    ).status_code == 429

    limiter.reset()

    res = client.post(
        "/api/v1/jobs/", 
        json=rate_limit_payload,
        headers={settings.api_key_name: settings.api_key, "X-Forwarded-For": "192.168.1.99"}
    )
    assert res.status_code == 202

