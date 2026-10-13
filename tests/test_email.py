import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, JobStatus
from app.models.job import Job
from app.services.email_service import sanitize_filename, send_certificate_email
from app.workers.processor import process_job


def test_sanitize_filename():
    assert sanitize_filename("Python 101: Intro!") == "Python_101__Intro_"
    assert sanitize_filename("Advanced-Rust_Programming") == "Advanced-Rust_Programming"


def test_send_certificate_email_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", False)
    result = send_certificate_email(
        recipient_name="Alice Smith",
        recipient_email="alice@example.com",
        course_name="Cloud Computing",
        pdf_content=b"%PDF-1.4 mock",
    )
    assert result is False


def test_send_certificate_email_invalid_email(monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    assert not send_certificate_email(
        recipient_name="Alice",
        recipient_email="invalid-email-string",
        course_name="Course",
        pdf_content=b"%PDF-1.4",
        raise_on_error=False,
    )

    with pytest.raises(ValueError):
        send_certificate_email(
            recipient_name="Alice",
            recipient_email="",
            course_name="Course",
            pdf_content=b"%PDF-1.4",
            raise_on_error=True,
        )


def test_send_certificate_email_file_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "email_enabled", True)
    non_existent = tmp_path / "non_existent.pdf"

    assert not send_certificate_email(
        recipient_name="Alice",
        recipient_email="alice@example.com",
        course_name="Course",
        pdf_content=non_existent,
        raise_on_error=False,
    )

    with pytest.raises(FileNotFoundError):
        send_certificate_email(
            recipient_name="Alice",
            recipient_email="alice@example.com",
            course_name="Course",
            pdf_content=non_existent,
            raise_on_error=True,
        )


@patch("smtplib.SMTP")
def test_send_certificate_email_smtp_tls_success(mock_smtp_cls, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "apikey")
    monkeypatch.setattr(settings, "smtp_password", "SG.test_secret")
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "email_from", "noreply@certifyflow.io")
    monkeypatch.setattr(settings, "email_from_name", "CertifyFlow Dispatcher")

    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    pdf_data = b"%PDF-1.4 simulated binary data"
    success = send_certificate_email(
        recipient_name="Jane Doe",
        recipient_email="jane.doe@example.com",
        course_name="Distributed Architecture",
        pdf_content=pdf_data,
        issue_date="2026-10-13",
    )

    assert success is True
    mock_smtp_cls.assert_called_once_with("smtp.sendgrid.net", 587, timeout=15)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("apikey", "SG.test_secret")
    mock_server.send_message.assert_called_once()

    # Inspect transmitted message
    sent_msg = mock_server.send_message.call_args[0][0]
    assert sent_msg["To"] == "jane.doe@example.com"
    assert "CertifyFlow Dispatcher" in sent_msg["From"]
    assert "Distributed Architecture" in sent_msg["Subject"]

    # Verify attachment is present
    attachments = [part for part in sent_msg.walk() if part.get_content_maintype() == "application"]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "Distributed_Architecture_Certificate.pdf"
    assert attachments[0].get_payload(decode=True) == pdf_data


@patch("smtplib.SMTP_SSL")
def test_send_certificate_email_smtp_ssl_success(mock_smtp_ssl_cls, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_user", "bot@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password-123")
    monkeypatch.setattr(settings, "smtp_use_ssl", True)

    mock_server = MagicMock()
    mock_smtp_ssl_cls.return_value.__enter__.return_value = mock_server

    success = send_certificate_email(
        recipient_name="Bob Jones",
        recipient_email="bob@example.com",
        course_name="DevOps Mastery",
        pdf_content=b"%PDF-1.4 test",
    )

    assert success is True
    mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
    mock_server.login.assert_called_once_with("bot@gmail.com", "app-password-123")
    mock_server.send_message.assert_called_once()


@patch("smtplib.SMTP")
def test_send_certificate_email_smtp_exception(mock_smtp_cls, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    mock_server = MagicMock()
    mock_server.send_message.side_effect = smtplib.SMTPException("Mail server rejected")
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    # Without raise_on_error
    result = send_certificate_email(
        recipient_name="Charlie",
        recipient_email="charlie@example.com",
        course_name="Kubernetes",
        pdf_content=b"%PDF-1.4",
        raise_on_error=False,
    )
    assert result is False

    # With raise_on_error
    with pytest.raises(smtplib.SMTPException):
        send_certificate_email(
            recipient_name="Charlie",
            recipient_email="charlie@example.com",
            course_name="Kubernetes",
            pdf_content=b"%PDF-1.4",
            raise_on_error=True,
        )


@patch("app.workers.processor.generate_certificate")
@patch("app.workers.processor.send_certificate_email")
def test_process_job_triggers_email_dispatch_when_enabled(
    mock_send_email,
    mock_generate,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "email_enabled", True)
    mock_generate.return_value = "dummy_cert.pdf"

    # Create job in database
    job = Job(id="job-email-test", total=1, status=JobStatus.PENDING, succeeded=0, failed=0)
    cert = Certificate(
        id="cert-email-test",
        job_id="job-email-test",
        recipient_name="Grace Hopper",
        recipient_email="grace@navy.mil",
        course_name="Compiler Architecture",
        issue_date="2026-10-13",
        status=CertificateStatus.PENDING,
    )
    db_session.add_all([job, cert])
    db_session.commit()

    with patch("app.workers.processor.SessionLocal") as mock_session_local:
        mock_session_local.return_value.__enter__.return_value = db_session
        process_job("job-email-test")

    db_session.refresh(job)
    db_session.refresh(cert)

    assert job.status == JobStatus.COMPLETED
    assert cert.status == CertificateStatus.SUCCESS

    # Verify email dispatch was triggered with the expected recipient information
    mock_send_email.assert_called_once()
    call_kwargs = mock_send_email.call_args[1]
    assert call_kwargs["recipient_name"] == "Grace Hopper"
    assert call_kwargs["recipient_email"] == "grace@navy.mil"
    assert call_kwargs["course_name"] == "Compiler Architecture"
    assert call_kwargs["issue_date"] == "2026-10-13"
