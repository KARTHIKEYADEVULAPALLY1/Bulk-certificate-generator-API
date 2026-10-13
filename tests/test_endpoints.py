import os
import io
import zipfile
import tempfile
import pytest
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import JobStatus, CertificateStatus

@pytest.fixture
def mock_data(db_session):
    job = Job(id="job-multi", total=2, status=JobStatus.COMPLETED_WITH_ERRORS, succeeded=1, failed=1)
    db_session.add(job)
    
    # Create a temp PDF file
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "cert.pdf")
    with open(file_path, "wb") as f:
        f.write(b"%PDF-1.4 mock pdf")
        
    cert1 = Certificate(
        id="cert-success",
        job_id="job-multi",
        recipient_name="Alice",
        recipient_email="alice@example.com",
        course_name="Course",
        issue_date="2024-01-01",
        status=CertificateStatus.SUCCESS,
        file_path=file_path
    )
    cert2 = Certificate(
        id="cert-fail",
        job_id="job-multi",
        recipient_name="Bob",
        recipient_email="bob@example.com",
        course_name="Course",
        issue_date="2024-01-01",
        status=CertificateStatus.FAILED,
        error_message="Bad email"
    )
    cert3 = Certificate(
        id="cert-pending",
        job_id="job-multi", 
        recipient_name="Charlie",
        recipient_email="charlie@example.com",
        course_name="Course",
        issue_date="2024-01-01",
        status=CertificateStatus.PENDING,
    )
    
    db_session.add_all([cert1, cert2, cert3])
    db_session.commit()
    return {"job_id": "job-multi", "c_success": "cert-success", "c_fail": "cert-fail", "c_pending": "cert-pending"}

def test_get_job_status(client, mock_data):
    response = client.get(f"/api/v1/jobs/{mock_data['job_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["progress_percent"] == 100.0  # (1+1)/2 * 100

def test_get_job_status_not_found(client):
    response = client.get("/api/v1/jobs/nonexistent")
    assert response.status_code == 404

def test_get_job_certificates(client, mock_data):
    response = client.get(f"/api/v1/jobs/{mock_data['job_id']}/certificates")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    
    # Filter by status
    response = client.get(f"/api/v1/jobs/{mock_data['job_id']}/certificates?status=FAILED")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["error_message"] == "Bad email"

def test_download_certificate_success(client, mock_data):
    response = client.get(f"/api/v1/certificates/{mock_data['c_success']}/download")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 mock pdf"

def test_download_certificate_failed_or_pending(client, mock_data):
    response = client.get(f"/api/v1/certificates/{mock_data['c_fail']}/download")
    assert response.status_code == 409
    
    response = client.get(f"/api/v1/certificates/{mock_data['c_pending']}/download")
    assert response.status_code == 409

def test_download_certificate_not_found(client):
    response = client.get("/api/v1/certificates/nonexistent/download")
    assert response.status_code == 404

def test_download_job_zip(client, mock_data):
    response = client.get(f"/api/v1/jobs/{mock_data['job_id']}/download")
    assert response.status_code == 200
    
    # Verify the ZIP contents
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        names = z.namelist()
        assert len(names) == 1
        assert "Alice" in names[0]
        with z.open(names[0]) as f:
            assert f.read() == b"%PDF-1.4 mock pdf"

def test_download_job_zip_no_success(client, db_session, mock_data):
    # Alter the successful cert to be FAILED to test the 409 error
    cert = db_session.query(Certificate).filter(Certificate.id == mock_data["c_success"]).first()
    cert.status = CertificateStatus.FAILED
    db_session.commit()
    
    response = client.get(f"/api/v1/jobs/{mock_data['job_id']}/download")
    assert response.status_code == 409
