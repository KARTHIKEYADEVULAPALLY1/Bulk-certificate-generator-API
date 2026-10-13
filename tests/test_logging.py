import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.core.logging import setup_logging, get_logger, bind_contextvars, clear_contextvars
from app.core.middleware import CorrelationIdMiddleware
from app.main import app
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import JobStatus, CertificateStatus
from app.services.storage.local import LocalStorageBackend
from app.services.storage.s3 import S3StorageBackend
from app.workers.processor import process_job

client = TestClient(app)

@pytest.fixture
def sample_job(db_session):
    job = Job(id="job-log-1", total=1, status=JobStatus.PENDING, succeeded=0, failed=0)
    db_session.add(job)
    cert = Certificate(
        id="cert-log-1",
        job_id="job-log-1",
        recipient_name="Test User",
        recipient_email="test@example.com",
        course_name="Course",
        issue_date="2024-01-01",
        status=CertificateStatus.PENDING
    )
    db_session.add(cert)
    db_session.commit()
    return job

def test_local_storage_check_health_success():
    """Verify LocalStorageBackend.check_health returns True and cleans up probe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)
        healthy, err = backend.check_health()
        assert healthy is True
        assert err is None
        probe = Path(tmpdir) / ".healthz_probe"
        assert not probe.exists()

def test_local_storage_check_health_failure():
    """Verify LocalStorageBackend.check_health returns False and error on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)
        with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
            healthy, err = backend.check_health()
            assert healthy is False
            assert "Permission denied" in str(err)

def test_s3_storage_check_health_success():
    """Verify S3StorageBackend.check_health calls head_bucket and returns True."""
    backend = S3StorageBackend(
        bucket_name="test-bucket",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )
    with patch.object(backend.s3_client, "head_bucket") as mock_head:
        mock_head.return_value = {}
        healthy, err = backend.check_health()
        assert healthy is True
        assert err is None
        mock_head.assert_called_once_with(Bucket="test-bucket")

def test_s3_storage_check_health_failure():
    """Verify S3StorageBackend.check_health returns False when head_bucket fails."""
    backend = S3StorageBackend(
        bucket_name="test-bucket",
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
    )
    with patch.object(backend.s3_client, "head_bucket") as mock_head:
        mock_head.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}},
            "HeadBucket"
        )
        healthy, err = backend.check_health()
        assert healthy is False
        assert "Forbidden" in str(err)

def test_correlation_id_auto_generated():
    """Verify X-Correlation-ID and X-Request-ID are generated and returned when not supplied."""
    response = client.get("/health")
    assert response.status_code == 200
    corr_id = response.headers.get("x-correlation-id")
    req_id = response.headers.get("x-request-id")
    assert corr_id is not None
    assert len(corr_id) == 36  # UUID length
    assert corr_id == req_id

def test_correlation_id_propagated_from_x_request_id():
    """Verify incoming X-Request-ID is used if X-Correlation-ID is not provided."""
    custom_req_id = "trace-request-header-xyz-987"
    response = client.get("/health", headers={"X-Request-ID": custom_req_id})
    assert response.status_code == 200
    assert response.headers.get("x-correlation-id") == custom_req_id
    assert response.headers.get("x-request-id") == custom_req_id

def test_worker_process_job_binds_correlation_id(sample_job):
    """Verify process_job task binds provided correlation_id and job_id to structlog context."""
    from structlog.contextvars import get_contextvars

    bound_contexts = []

    def mock_info(event, **kwargs):
        ctx = get_contextvars()
        bound_contexts.append((event, ctx.copy(), kwargs))

    with patch("app.workers.processor.logger.info", side_effect=mock_info):
        process_job(sample_job.id, correlation_id="worker-corr-12345")

    # Context should be cleared after execution
    assert "correlation_id" not in get_contextvars()
    assert len(bound_contexts) > 0
    # First logged event should have correlation_id and job_id bound
    event, ctx, kwargs = bound_contexts[0]
    assert ctx.get("correlation_id") == "worker-corr-12345"
    assert ctx.get("job_id") == sample_job.id

def test_structlog_json_formatting(capsys):
    """Verify structlog outputs valid JSON format containing required fields."""
    setup_logging(log_level="DEBUG")
    clear_contextvars()
    bind_contextvars(correlation_id="json-test-trace-id")

    logger = get_logger("test.structured")
    logger.info("testing json structured output", custom_field="val123")

    captured = capsys.readouterr()
    log_line = captured.out.strip()
    
    # Must parse as valid JSON
    parsed = json.loads(log_line)
    assert parsed["event"] == "testing json structured output"
    assert parsed["correlation_id"] == "json-test-trace-id"
    assert parsed["logger"] == "test.structured"
    assert parsed["level"] == "info"
    assert parsed["custom_field"] == "val123"
    assert "timestamp" in parsed