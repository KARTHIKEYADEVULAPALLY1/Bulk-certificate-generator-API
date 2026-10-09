import os
from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.jobs import router as jobs_router
from app.api.v1.certificates import router as certificates_router
from app.core.database import engine, Base, SessionLocal
from app.models.job import Job
from app.models.enums import JobStatus
from sqlalchemy import update
from datetime import datetime, timedelta
import app.models  # Ensures models are registered
from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.storage_dir, exist_ok=True)
    
    # Startup recovery: mark stuck PROCESSING jobs as FAILED.
    # I chose to mark them as FAILED rather than re-queueing them because without strong idempotency 
    # guarantees on the PDF generation (or partial file cleanup checks), automatically retrying could 
    # result in corrupted state, duplicate partial files, or infinite crash loops.
    with SessionLocal() as db:
        timeout = datetime.utcnow() - timedelta(minutes=60)
        stmt = (
            update(Job)
            .where(Job.status == JobStatus.PROCESSING, Job.updated_at < timeout)
            .values(status=JobStatus.FAILED)
        )
        db.execute(stmt)
        db.commit()
    yield

app = FastAPI(title="Bulk Certificate Generator API", lifespan=lifespan)
app.include_router(jobs_router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(certificates_router, prefix="/api/v1/certificates", tags=["certificates"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")
