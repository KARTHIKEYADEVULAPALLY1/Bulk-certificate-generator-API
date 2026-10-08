import logging
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import SessionLocal
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import JobStatus, CertificateStatus
from app.services.certificate_generator import generate_certificate
from app.core.utils import get_certificate_path

logger = logging.getLogger(__name__)

def process_job(job_id: str):
    logger.info(f"Starting processing for job_id: {job_id}")
    
    with SessionLocal() as db:
        # 1. Atomic Job Claim
        stmt = (
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.PENDING)
            .values(status=JobStatus.PROCESSING)
        )
        result = db.execute(stmt)
        db.commit()
        
        if result.rowcount == 0:
            logger.info(f"Job {job_id} could not be claimed. Already processing, completed, or missing.")
            return

        # Refetch to have job attributes in memory to calculate total later
        job = db.query(Job).filter(Job.id == job_id).first()

        pending_certs = db.query(Certificate).filter(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.PENDING
        ).all()

        for cert in pending_certs:
            try:
                output_path = get_certificate_path(job_id, cert.id)
                final_path = generate_certificate(
                    recipient_name=cert.recipient_name,
                    course_name=cert.course_name,
                    issue_date=cert.issue_date,
                    output_path=output_path
                )
                cert.status = CertificateStatus.SUCCESS
                cert.file_path = str(final_path)
                
                # 2. Atomic counter increment
                db.execute(update(Job).where(Job.id == job_id).values(succeeded=Job.succeeded + 1))
                logger.info(f"Job {job_id}: Certificate {cert.id} generated successfully.")
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to generate certificate {cert.id}. Error: {str(e)}")
                cert.status = CertificateStatus.FAILED
                cert.error_message = str(e)
                
                # 2. Atomic counter increment
                db.execute(update(Job).where(Job.id == job_id).values(failed=Job.failed + 1))
            
            # 3. Robust Commit Wrapping
            try:
                db.commit()
            except SQLAlchemyError as db_err:
                db.rollback()
                logger.error(f"Database error committing cert {cert.id} for job {job_id}: {db_err}")
                try:
                    db.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.FAILED))
                    db.commit()
                    logger.error(f"Marked Job {job_id} as FAILED due to unrecoverable database error.")
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
            logger.info(f"Finished processing job_id: {job_id} with status {job.status}")
        except SQLAlchemyError as db_err:
            db.rollback()
            logger.error(f"Failed to commit final status for job {job_id}: {db_err}")
