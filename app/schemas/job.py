from pydantic import BaseModel, Field
from typing import List, Optional
from app.core.config import settings
from app.models.enums import JobStatus, CertificateStatus
from datetime import datetime

class RecipientInput(BaseModel):
    name: str | None = None
    email: str | None = None

class JobCreateRequest(BaseModel):
    course_name: str = Field(..., min_length=1)
    issue_date: str = Field(..., min_length=1)
    recipients: List[RecipientInput] = Field(..., min_length=1, max_length=settings.max_batch_size)

class JobResponse(BaseModel):
    job_id: str
    total: int
    status_url: str

class JobStatusResponse(BaseModel):
    id: str
    status: JobStatus
    total: int
    succeeded: int
    failed: int
    progress_percent: float

class CertificateResponse(BaseModel):
    id: str
    recipient_name: str
    recipient_email: str
    status: CertificateStatus
    error_message: str | None
    created_at: datetime

class PaginatedCertificatesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CertificateResponse]
