import pytest
from app.core.config import settings
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus

def test_create_job_success(client):
    response = client.post("/api/v1/jobs/", json={
        "course_name": "Course A",
        "issue_date": "2024-01-01",
        "recipients": [
            {"name": "Valid Name", "email": "valid@example.com"}
        ]
    })
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["total"] == 1
    assert data["status_url"].endswith(f"/api/v1/jobs/{data['job_id']}")

def test_create_job_empty_list(client):
    response = client.post("/api/v1/jobs/", json={
        "course_name": "Course A",
        "issue_date": "2024-01-01",
        "recipients": []
    })
    assert response.status_code == 422

def test_create_job_oversized_batch(client):
    response = client.post("/api/v1/jobs/", json={
        "course_name": "Course A",
        "issue_date": "2024-01-01",
        "recipients": [{"name": "A", "email": "a@example.com"}] * (settings.max_batch_size + 1)
    })
    assert response.status_code == 422

def test_create_job_missing_fields(client):
    response = client.post("/api/v1/jobs/", json={
        "issue_date": "2024-01-01",
        "recipients": [{"name": "A", "email": "a@example.com"}]
    })
    assert response.status_code == 422

def test_create_job_mix_valid_invalid(client, db_session):
    response = client.post("/api/v1/jobs/", json={
        "course_name": "Course A",
        "issue_date": "2024-01-01",
        "recipients": [
            {"name": "Valid Name", "email": "valid@example.com"},
            {"name": "", "email": "valid@example.com"},
            {"name": "Valid Name", "email": "invalid"},
            {"name": "A" * 101, "email": "valid@example.com"}
        ]
    })
    assert response.status_code == 202
    data = response.json()
    job_id = data["job_id"]
    
    job = db_session.query(Job).filter(Job.id == job_id).first()
    assert job.total == 4
    assert job.failed == 3
    
    certs = db_session.query(Certificate).filter(Certificate.job_id == job_id).all()
    failed_certs = [c for c in certs if c.status == CertificateStatus.FAILED]
    success_certs = [c for c in certs if c.status == CertificateStatus.PENDING]
    
    assert len(failed_certs) == 3
    assert len(success_certs) == 1
    
    error_msgs = [c.error_message for c in failed_certs]
    assert "Name cannot be empty" in error_msgs
    assert "Invalid email format" in error_msgs
    assert "Name exceeds 100 characters" in error_msgs
