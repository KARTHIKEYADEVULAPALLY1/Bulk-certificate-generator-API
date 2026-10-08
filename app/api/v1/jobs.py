import os
import io
import zipfile
import tempfile
from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.job import JobCreateRequest, JobResponse, JobStatusResponse, PaginatedCertificatesResponse, CertificateResponse
from app.services.job_service import create_job
from app.workers.processor import process_job
from app.models.job import Job
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=202)
def submit_job(request: Request, payload: JobCreateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip("/")
    job_response = create_job(db, payload, base_url)
    background_tasks.add_task(process_job, job_response.job_id)
    return job_response

@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    progress = 0.0
    if job.total > 0:
        progress = ((job.succeeded + job.failed) / job.total) * 100.0
        
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
        raise HTTPException(status_code=404, detail="Job not found")
        
    query = db.query(Certificate).filter(Certificate.job_id == job_id)
    if status:
        query = query.filter(Certificate.status == status)
        
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
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
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    successful_certs = db.query(Certificate).filter(
        Certificate.job_id == job_id,
        Certificate.status == CertificateStatus.SUCCESS
    ).all()
    
    if not successful_certs:
        raise HTTPException(status_code=409, detail="No successful certificates available for this job")
        
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for cert in successful_certs:
            if cert.file_path and os.path.exists(cert.file_path):
                # Ensure a safe filename in ZIP
                safe_name = "".join([c if c.isalnum() else "_" for c in cert.recipient_name])
                zip_file.write(cert.file_path, arcname=f"{safe_name}_{cert.id}.pdf")
                
    tmp.close()
    
    return FileResponse(
        path=tmp.name,
        media_type="application/zip",
        filename=f"job_{job_id}.zip",
        background=BackgroundTask(os.unlink, tmp.name)
    )
