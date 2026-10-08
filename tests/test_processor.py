import pytest
from unittest.mock import patch
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import JobStatus, CertificateStatus
from app.workers.processor import process_job

@pytest.fixture
def sample_job(db_session):
    job = Job(id="job-1", total=3, status=JobStatus.PENDING, succeeded=0, failed=0)
    db_session.add(job)
    for i in range(3):
        cert = Certificate(
            id=f"cert-{i}",
            job_id="job-1",
            recipient_name=f"User {i}",
            recipient_email=f"user{i}@example.com",
            course_name="Course",
            issue_date="2024-01-01",
            status=CertificateStatus.PENDING
        )
        db_session.add(cert)
    db_session.commit()
    return job

# Instead of passing Session to process_job, process_job uses SessionLocal().
# We need to mock SessionLocal to yield our db_session so it doesn't try to connect to the main db.
@pytest.fixture(autouse=True)
def mock_session_local(db_session):
    with patch("app.workers.processor.SessionLocal") as mock:
        mock.return_value.__enter__.return_value = db_session
        yield mock

@patch("app.workers.processor.generate_certificate")
def test_process_job_all_succeed(mock_generate, db_session, sample_job):
    mock_generate.return_value = "path/to/cert.pdf"
    
    process_job(sample_job.id)
    
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.COMPLETED
    assert sample_job.succeeded == 3
    assert sample_job.failed == 0
    
    certs = db_session.query(Certificate).filter(Certificate.job_id == sample_job.id).all()
    for cert in certs:
        assert cert.status == CertificateStatus.SUCCESS
        assert "path/to/cert.pdf" in cert.file_path

@patch("app.workers.processor.generate_certificate")
def test_process_job_one_fails(mock_generate, db_session, sample_job):
    # Make the second generation fail
    def side_effect(*args, **kwargs):
        if "User 1" in kwargs.get("recipient_name", ""):
            raise Exception("Mock failure")
        return "path/to/cert.pdf"
    mock_generate.side_effect = side_effect
    
    process_job(sample_job.id)
    
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert sample_job.succeeded == 2
    assert sample_job.failed == 1
    
    certs = db_session.query(Certificate).filter(Certificate.job_id == sample_job.id).order_by(Certificate.id).all()
    assert certs[0].status == CertificateStatus.SUCCESS
    assert certs[1].status == CertificateStatus.FAILED
    assert "Mock failure" in certs[1].error_message
    assert certs[2].status == CertificateStatus.SUCCESS

@patch("app.workers.processor.generate_certificate")
def test_process_job_all_fail(mock_generate, db_session, sample_job):
    mock_generate.side_effect = Exception("System down")
    
    process_job(sample_job.id)
    
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.FAILED
    assert sample_job.succeeded == 0
    assert sample_job.failed == 3
    
    certs = db_session.query(Certificate).filter(Certificate.job_id == sample_job.id).all()
    for cert in certs:
        assert cert.status == CertificateStatus.FAILED
        assert "System down" in cert.error_message
