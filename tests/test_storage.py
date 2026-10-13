import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.services.storage import (
    BaseStorageBackend,
    LocalStorageBackend,
    S3StorageBackend,
    get_storage_backend,
)

# -------------------------------------------------------------
# Tests for LocalStorageBackend
# -------------------------------------------------------------

def test_local_storage_upload_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)
        content = b"%PDF-1.4 test certificate content"

        # 1. Upload bytes
        dest_key = "job-1/cert-1.pdf"
        stored_path = backend.upload_file(content, destination_path=dest_key)
        assert stored_path == dest_key
        assert backend.file_exists(dest_key) is True

        # 2. Read bytes
        retrieved = backend.get_file_bytes(dest_key)
        assert retrieved == content

        # 3. Download response
        response = backend.get_download_response(dest_key, filename="cert.pdf")
        assert isinstance(response, FileResponse)
        assert response.filename == "cert.pdf"

        # 4. Delete file
        assert backend.delete_file(dest_key) is True
        assert backend.file_exists(dest_key) is False

def test_local_storage_upload_from_filepath():
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)

        # Create a source file
        src_path = Path(tmpdir) / "source.pdf"
        src_path.write_bytes(b"sample file content")

        # Upload via file path
        dest_key = "subfolder/dest.pdf"
        backend.upload_file(src_path, destination_path=dest_key)
        assert backend.file_exists(dest_key) is True
        assert backend.get_file_bytes(dest_key) == b"sample file content"

def test_local_storage_path_traversal_prevention():
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            backend.upload_file(b"bad", destination_path="../../etc/passwd")

def test_local_storage_missing_file_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(base_dir=tmpdir)
        assert backend.file_exists("nonexistent.pdf") is False
        with pytest.raises(FileNotFoundError):
            backend.get_file_bytes("nonexistent.pdf")
        with pytest.raises(HTTPException) as exc:
            backend.get_download_response("nonexistent.pdf", "file.pdf")
        assert exc.value.status_code == 404

# -------------------------------------------------------------
# Tests for S3StorageBackend
# -------------------------------------------------------------

@pytest.fixture
def s3_backend():
    backend = S3StorageBackend(
        bucket_name="test-bucket",
        region_name="us-east-1",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
    )
    return backend

def test_s3_storage_upload_bytes(s3_backend):
    stubber = Stubber(s3_backend.s3_client)
    dest_key = "job-100/cert-200.pdf"
    content = b"%PDF mock cloud bytes"

    stubber.add_response(
        "put_object",
        {},
        {"Bucket": "test-bucket", "Key": dest_key, "Body": content, "ContentType": "application/pdf"}
    )

    with stubber:
        stored_key = s3_backend.upload_file(content, destination_path=dest_key)
        assert stored_key == dest_key

def test_s3_storage_get_file_bytes(s3_backend):
    stubber = Stubber(s3_backend.s3_client)
    dest_key = "job-100/cert-200.pdf"
    content = b"%PDF retrieved from s3"

    stubber.add_response(
        "get_object",
        {"Body": io.BytesIO(content), "ContentLength": len(content)},
        {"Bucket": "test-bucket", "Key": dest_key}
    )

    with stubber:
        retrieved = s3_backend.get_file_bytes(dest_key)
        assert retrieved == content

def test_s3_storage_file_exists(s3_backend):
    stubber = Stubber(s3_backend.s3_client)

    # 1. Existing object
    stubber.add_response("head_object", {"ContentLength": 100}, {"Bucket": "test-bucket", "Key": "found.pdf"})
    # 2. Missing object
    stubber.add_client_error("head_object", service_error_code="404", expected_params={"Bucket": "test-bucket", "Key": "missing.pdf"})

    with stubber:
        assert s3_backend.file_exists("found.pdf") is True
        assert s3_backend.file_exists("missing.pdf") is False

def test_s3_storage_delete_file(s3_backend):
    stubber = Stubber(s3_backend.s3_client)
    stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": "del.pdf"})

    with stubber:
        assert s3_backend.delete_file("del.pdf") is True

def test_s3_storage_download_response_streaming(s3_backend):
    stubber = Stubber(s3_backend.s3_client)
    content = b"PDF cloud stream data"

    stubber.add_response(
        "get_object",
        {"Body": io.BytesIO(content), "ContentLength": len(content), "ContentType": "application/pdf"},
        {"Bucket": "test-bucket", "Key": "stream.pdf"}
    )

    with stubber:
        response = s3_backend.get_download_response("stream.pdf", filename="download.pdf")
        assert isinstance(response, StreamingResponse)
        assert response.headers["Content-Disposition"] == 'attachment; filename="download.pdf"'
        assert response.headers["Content-Length"] == str(len(content))

def test_s3_storage_presigned_url(s3_backend):
    with patch.object(s3_backend.s3_client, "generate_presigned_url", return_value="https://s3.amazonaws.com/presigned") as mock_url:
        url = s3_backend.get_presigned_url("cert.pdf", expires_in=1800)
        assert url == "https://s3.amazonaws.com/presigned"
        mock_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "cert.pdf"},
            ExpiresIn=1800
        )

# -------------------------------------------------------------
# Tests for Factory Pattern
# -------------------------------------------------------------

def test_get_storage_backend_factory():
    local = get_storage_backend("local")
    assert isinstance(local, LocalStorageBackend)

    s3 = get_storage_backend("s3")
    assert isinstance(s3, S3StorageBackend)

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_storage_backend("unknown_cloud")

# -------------------------------------------------------------
# End-to-end API test with S3 Storage Backend dependency override
# -------------------------------------------------------------

def test_api_download_streamed_from_s3(client, db_session):
    from app.models.job import Job
    from app.models.certificate import Certificate
    from app.models.enums import JobStatus, CertificateStatus
    from app.services.storage import get_storage_backend

    mock_s3 = MagicMock(spec=BaseStorageBackend)
    mock_s3.file_exists.return_value = True
    mock_s3.get_download_response.return_value = StreamingResponse(
        io.BytesIO(b"%PDF-1.4 s3 streamed bytes"),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="Alice_certificate.pdf"'}
    )

    job = Job(id="s3-job-test", total=1, status=JobStatus.COMPLETED, succeeded=1, failed=0)
    cert = Certificate(
        id="s3-cert-test",
        job_id="s3-job-test",
        recipient_name="Alice",
        recipient_email="alice@example.com",
        course_name="Cloud Engineering",
        issue_date="2024-01-01",
        status=CertificateStatus.SUCCESS,
        file_path="s3-job-test/s3-cert-test.pdf",
    )
    db_session.add_all([job, cert])
    db_session.commit()

    from app.main import app
    app.dependency_overrides[get_storage_backend] = lambda: mock_s3
    try:
        response = client.get(f"/api/v1/certificates/{cert.id}/download")
        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 s3 streamed bytes"
        mock_s3.file_exists.assert_called_with("s3-job-test/s3-cert-test.pdf")
        mock_s3.get_download_response.assert_called_once()
    finally:
        del app.dependency_overrides[get_storage_backend]
