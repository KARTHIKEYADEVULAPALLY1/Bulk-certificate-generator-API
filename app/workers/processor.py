import time
import uuid
from pathlib import Path
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import CertificateGenerationError
from app.core.logging import get_logger, bind_contextvars, clear_contextvars
from app.core.utils import get_certificate_path
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, JobStatus
from app.models.job import Job
from app.services.certificate_generator import generate_certificate
from app.services.email_service import send_certificate_email
from app.services.storage import get_storage_backend

logger = get_logger(__name__)

def generate_certificate_with_backoff(
    recipient_name: str,
    course_name: str,
    issue_date: str,
    output_path: Path,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> Path:
    """
    Generates a certificate PDF with exponential backoff retry for transient errors
    (such as CertificateGenerationError, OSError, IOError).
    """
    retries = max_retries if max_retries is not None else settings.cert_max_retries
    delay_base = base_delay if base_delay is not None else settings.cert_retry_backoff_base

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return generate_certificate(
                recipient_name=recipient_name,
                course_name=course_name,
                issue_date=issue_date,
                output_path=output_path,
            )
        except (CertificateGenerationError, OSError, IOError) as exc:
            last_error = exc
            if attempt < retries - 1:
                delay = delay_base * (2 ** attempt)
                logger.warning(
                    "Transient failure generating certificate",
                    recipient=recipient_name,
                    attempt=attempt + 1,
                    max_retries=retries,
                    delay_seconds=round(delay, 2),
                    error=str(exc),
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Exhausted retries generating certificate",
                    recipient=recipient_name,
                    retries=retries,
                    error=str(exc),
                )
                raise
        except Exception:
            # Non-transient errors (e.g. ValueError, bad inputs) fail immediately
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Unexpected end of retry loop without return or exception")

@celery_app.task(
    bind=True,
    name="app.workers.processor.process_job",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    autoretry_for=(SQLAlchemyError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_job(self, job_id: str, correlation_id: str | None = None):
    effective_corr_id = (
        correlation_id
        or getattr(getattr(self, "request", None), "correlation_id", None)
        or str(uuid.uuid4())
    )
    clear_contextvars()
    bind_contextvars(correlation_id=effective_corr_id, job_id=job_id)

    try:
        logger.info("Starting processing for job", job_id=job_id, correlation_id=effective_corr_id)

        with SessionLocal() as db:
            # 1. Atomic Job Claim: Support claiming PENDING jobs or resuming PROCESSING jobs on worker restart
            stmt = (
                update(Job)
                .where(Job.id == job_id, Job.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]))
                .values(status=JobStatus.PROCESSING)
            )
            result = db.execute(stmt)
            db.commit()

            if result.rowcount == 0:
                logger.info("Job could not be claimed: already completed or missing", job_id=job_id)
                return

            # Refetch job to have attributes in memory
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.error("Job not found in database after claim", job_id=job_id)
                return

            pending_certs = db.query(Certificate).filter(
                Certificate.job_id == job_id,
                Certificate.status == CertificateStatus.PENDING
            ).all()

            storage = get_storage_backend()

            for cert in pending_certs:
                dest_key = f"{job_id}/{cert.id}.pdf"
                try:
                    output_path = get_certificate_path(job_id, cert.id)
                    final_path = generate_certificate_with_backoff(
                        recipient_name=cert.recipient_name,
                        course_name=cert.course_name,
                        issue_date=cert.issue_date,
                        output_path=output_path,
                    )
                    if Path(final_path).exists():
                        stored_ref = storage.upload_file(
                            final_path, destination_path=dest_key, content_type="application/pdf"
                        )
                        if settings.storage_type.lower() == "s3" and Path(final_path).is_file():
                            try:
                                Path(final_path).unlink()
                            except Exception:
                                pass
                    else:
                        stored_ref = str(final_path)

                    cert.status = CertificateStatus.SUCCESS
                    cert.file_path = stored_ref

                    # 2. Atomic counter increment
                    db.execute(update(Job).where(Job.id == job_id).values(succeeded=Job.succeeded + 1))
                    logger.info(
                        "Certificate generated successfully",
                        certificate_id=cert.id,
                        recipient=cert.recipient_name,
                        storage_path=stored_ref,
                    )

                    # 3. Trigger email dispatch with PDF attached
                    if settings.email_enabled:
                        try:
                            pdf_payload = None
                            if Path(final_path).is_file():
                                with open(final_path, "rb") as pf:
                                    pdf_payload = pf.read()
                            elif stored_ref and storage.file_exists(stored_ref):
                                pdf_payload = storage.get_file_bytes(stored_ref)
                            else:
                                pdf_payload = final_path

                            send_certificate_email(
                                recipient_name=cert.recipient_name,
                                recipient_email=cert.recipient_email,
                                course_name=cert.course_name,
                                pdf_content=pdf_payload,
                                issue_date=cert.issue_date,
                            )
                        except Exception as email_err:
                            logger.warning(
                                "Email dispatch failed for certificate",
                                certificate_id=cert.id,
                                recipient=cert.recipient_email,
                                error=str(email_err),
                            )

                except Exception as e:
                    logger.error(
                        "Failed to generate certificate",
                        certificate_id=cert.id,
                        recipient=cert.recipient_name,
                        error=str(e),
                    )
                    cert.status = CertificateStatus.FAILED
                    cert.error_message = str(e)

                    # 2. Atomic counter increment
                    db.execute(update(Job).where(Job.id == job_id).values(failed=Job.failed + 1))

                # 3. Robust Commit Wrapping per certificate
                try:
                    db.commit()
                except SQLAlchemyError as db_err:
                    db.rollback()
                    logger.error(
                        "Database error committing certificate",
                        certificate_id=cert.id,
                        error=str(db_err),
                    )
                    try:
                        db.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.FAILED))
                        db.commit()
                        logger.error("Marked Job as FAILED due to unrecoverable database error", job_id=job_id)
                    except SQLAlchemyError:
                        db.rollback()
                    return  # Stop processing the job

            # Refetch job to accurately determine final status
            db.refresh(job)

            if job.succeeded == job.total:
                job.status = JobStatus.COMPLETED
            elif job.succeeded == 0:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.COMPLETED_WITH_ERRORS

            try:
                db.commit()
                logger.info(
                    "Finished processing job",
                    job_id=job_id,
                    status=str(job.status),
                    succeeded=job.succeeded,
                    failed=job.failed,
                    total=job.total,
                )
            except SQLAlchemyError as db_err:
                db.rollback()
                logger.error("Failed to commit final status for job", job_id=job_id, error=str(db_err))
                raise
    finally:
        clear_contextvars()

