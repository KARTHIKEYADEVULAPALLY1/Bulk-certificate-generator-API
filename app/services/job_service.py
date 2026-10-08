import re
from sqlalchemy.orm import Session
from app.schemas.job import JobCreateRequest, JobResponse
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import JobStatus, CertificateStatus

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

def validate_recipient(name: str | None, email: str | None):
    name = (name or "").strip()
    email = (email or "").strip()
    
    if not name:
        return False, "Name cannot be empty"
    if len(name) > 100:
        return False, "Name exceeds 100 characters"
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"
    return True, None

def create_job(db: Session, request: JobCreateRequest, base_url: str) -> JobResponse:
    job = Job(
        total=len(request.recipients),
        status=JobStatus.PENDING,
        succeeded=0,
        failed=0
    )
    db.add(job)
    db.flush()

    failed_count = 0

    for recipient in request.recipients:
        is_valid, error_msg = validate_recipient(recipient.name, recipient.email)
        
        cert = Certificate(
            job_id=job.id,
            recipient_name=(recipient.name or "").strip(),
            recipient_email=(recipient.email or "").strip(),
            course_name=request.course_name,
            issue_date=request.issue_date,
            status=CertificateStatus.PENDING if is_valid else CertificateStatus.FAILED,
            error_message=error_msg
        )
        if not is_valid:
            failed_count += 1
            
        db.add(cert)
        
    job.failed = failed_count
    
    if job.failed == job.total:
        job.status = JobStatus.FAILED

    db.commit()

    return JobResponse(
        job_id=job.id,
        total=job.total,
        status_url=f"{base_url}/api/v1/jobs/{job.id}"
    )
