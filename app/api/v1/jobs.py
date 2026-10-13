import os
import io
import zipfile
import tempfile
from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.job import JobCreateRequest, JobResponse, JobStatusResponse, PaginatedCertificatesResponse, CertificateResponse
from app.services.job_service import create_job
from app.workers.processor import process_job
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus
from app.services.storage import BaseStorageBackend, get_storage_backend

logger = get_logger(__name__)

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
def submit_job(request: Request, payload: JobCreateRequest, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip("/")
    correlation_id = getattr(request.state, "correlation_id", None)
    job_response = create_job(db, payload, base_url)
    logger.info("Job created", job_id=job_response.job_id, recipient_count=len(payload.recipients))
    process_job.delay(job_response.job_id, correlation_id=correlation_id)
    logger.info("Dispatched job to worker", job_id=job_response.job_id, correlation_id=correlation_id)
    return job_response



@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.warning("Job status check failed: job not found", job_id=job_id)
        raise HTTPException(status_code=404, detail="Job not found")
        
    progress = 0.0
    if job.total > 0:
        progress = ((job.succeeded + job.failed) / job.total) * 100.0
        
    logger.debug("Job status retrieved", job_id=job_id, status=str(job.status), progress=progress)
    return JobStatusResponse(
        id=job.id,
        status=job.status,
        total=job.total,
        succeeded=job.succeeded,
        failed=job.failed,
        progress_percent=round(progress, 2)
    )

@router.get("/{job_id}/certificates", response_model=PaginatedCertificatesResponse)
def get_job_certificates(
    job_id: str, 
    status: CertificateStatus | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.warning("Certificates listing failed: job not found", job_id=job_id)
        raise HTTPException(status_code=404, detail="Job not found")
        
    query = db.query(Certificate).filter(Certificate.job_id == job_id)
    if status:
        query = query.filter(Certificate.status == status)
        
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    logger.debug("Certificates listed", job_id=job_id, total=total, page=page, page_size=page_size)
    return PaginatedCertificatesResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            CertificateResponse(
                id=c.id,
                recipient_name=c.recipient_name,
                recipient_email=c.recipient_email,
                status=c.status,
                error_message=c.error_message,
                created_at=c.created_at
            ) for c in items
        ]
    )

@router.get("/{job_id}/download")
def download_job_zip(
    job_id: str,
    db: Session = Depends(get_db),
    storage: BaseStorageBackend = Depends(get_storage_backend),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.warning("Job ZIP download failed: job not found", job_id=job_id)
        raise HTTPException(status_code=404, detail="Job not found")
        
    successful_certs = db.query(Certificate).filter(
        Certificate.job_id == job_id,
        Certificate.status == CertificateStatus.SUCCESS
    ).all()
    
    if not successful_certs:
        logger.warning("Job ZIP download failed: no successful certificates", job_id=job_id)
        raise HTTPException(status_code=409, detail="No successful certificates available for this job")
        
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for cert in successful_certs:
            if cert.file_path and storage.file_exists(cert.file_path):
                safe_name = "".join([c if c.isalnum() else "_" for c in cert.recipient_name])
                cert_bytes = storage.get_file_bytes(cert.file_path)
                zip_file.writestr(f"{safe_name}_{cert.id}.pdf", cert_bytes)
                
    tmp.close()

    zip_key = f"zips/job_{job_id}.zip"
    storage.upload_file(tmp.name, destination_path=zip_key, content_type="application/zip")
    try:
        os.unlink(tmp.name)
    except Exception:
        pass

    logger.info("Serving job ZIP archive", job_id=job_id, cert_count=len(successful_certs), zip_key=zip_key)
    return storage.get_download_response(
        zip_key,
        filename=f"job_{job_id}.zip",
        media_type="application/zip",
    )

