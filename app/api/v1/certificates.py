import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus

router = APIRouter()

@router.get("/{certificate_id}/download")
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
        
    if cert.status == CertificateStatus.PENDING:
        raise HTTPException(status_code=409, detail="Certificate is still pending")
        
    if cert.status == CertificateStatus.FAILED:
        raise HTTPException(status_code=409, detail="Certificate generation failed")
        
    if not cert.file_path or not os.path.exists(cert.file_path):
        raise HTTPException(status_code=404, detail="Certificate file not found on disk")
        
    return FileResponse(
        cert.file_path,
        media_type="application/pdf",
        filename=f"{cert.recipient_name}_certificate.pdf"
    )
