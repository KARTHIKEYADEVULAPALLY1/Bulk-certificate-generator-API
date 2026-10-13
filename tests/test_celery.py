import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.exceptions import CertificateGenerationError
from app.workers.processor import process_job, generate_certificate_with_backoff

def test_celery_task_registration():
    """Verify process_job is registered in Celery and has persistence attributes."""
    assert "app.workers.processor.process_job" in celery_app.tasks
    task = celery_app.tasks["app.workers.processor.process_job"]
    assert task.acks_late is True
    assert task.reject_on_worker_lost is True
    assert task.max_retries == 3

def test_celery_app_persistence_configuration():
    """Verify Celery app has persistence and reliability settings enabled."""
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.broker_connection_retry_on_startup is True
    assert celery_app.conf.worker_prefetch_multiplier == 1

def test_submit_job_dispatches_celery_delay(client):
    """Verify submit_job endpoint dispatches process_job via Celery delay()."""
    with patch("app.api.v1.jobs.process_job.delay") as mock_delay:
        response = client.post("/api/v1/jobs/", json={
            "course_name": "Celery Test Course",
            "issue_date": "2024-01-01",
            "recipients": [{"name": "Celery User", "email": "celery@example.com"}]
        })
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert mock_delay.call_count == 1
        args, kwargs = mock_delay.call_args
        assert args[0] == job_id
        assert "correlation_id" in kwargs


def test_generate_certificate_with_backoff_success_first_try():
    """Verify generate_certificate_with_backoff returns immediately when successful."""
    with patch("app.workers.processor.generate_certificate") as mock_gen:
        mock_gen.return_value = Path("/tmp/cert.pdf")
        result = generate_certificate_with_backoff(
            recipient_name="Alice",
            course_name="Course",
            issue_date="2024-01-01",
            output_path=Path("/tmp/cert.pdf"),
            max_retries=3,
            base_delay=0.001,
        )
        assert result == Path("/tmp/cert.pdf")
        assert mock_gen.call_count == 1

def test_generate_certificate_with_backoff_transient_retry():
    """Verify exponential backoff occurs and succeeds on subsequent try."""
    with patch("app.workers.processor.generate_certificate") as mock_gen:
        # Fails first two calls with transient OSError, succeeds on 3rd
        mock_gen.side_effect = [
            OSError("Disk write timeout"),
            CertificateGenerationError("Font lock timeout"),
            Path("/tmp/cert.pdf")
        ]
        start_time = time.time()
        result = generate_certificate_with_backoff(
            recipient_name="Bob",
            course_name="Course",
            issue_date="2024-01-01",
            output_path=Path("/tmp/cert.pdf"),
            max_retries=3,
            base_delay=0.01,
        )
        elapsed = time.time() - start_time
        assert result == Path("/tmp/cert.pdf")
        assert mock_gen.call_count == 3
        # 1st retry delay: 0.01 * 1 = 0.01s, 2nd retry delay: 0.01 * 2 = 0.02s => total >= 0.03s
        assert elapsed >= 0.025

def test_generate_certificate_with_backoff_exhausts_retries():
    """Verify exhausted retries raise the transient exception."""
    with patch("app.workers.processor.generate_certificate") as mock_gen:
        mock_gen.side_effect = OSError("Persistent I/O failure")
        with pytest.raises(OSError, match="Persistent I/O failure"):
            generate_certificate_with_backoff(
                recipient_name="Charlie",
                course_name="Course",
                issue_date="2024-01-01",
                output_path=Path("/tmp/cert.pdf"),
                max_retries=3,
                base_delay=0.001,
            )
        assert mock_gen.call_count == 3
