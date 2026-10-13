from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus
from app.services.storage import BaseStorageBackend, get_storage_backend

logger = get_logger(__name__)

router = APIRouter()

@router.get("/{certificate_id}/download")
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
    storage: BaseStorageBackend = Depends(get_storage_backend),
):
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        logger.warning("Certificate download failed: not found", certificate_id=certificate_id)
        raise HTTPException(status_code=404, detail="Certificate not found")
        
    if cert.status == CertificateStatus.PENDING:
        logger.warning("Certificate download rejected: still pending", certificate_id=certificate_id)
        raise HTTPException(status_code=409, detail="Certificate is still pending")
        
    if cert.status == CertificateStatus.FAILED:
        logger.warning("Certificate download rejected: generation failed", certificate_id=certificate_id)
        raise HTTPException(status_code=409, detail="Certificate generation failed")
        
    if not cert.file_path or not storage.file_exists(cert.file_path):
        logger.error("Certificate file missing from storage backend", certificate_id=certificate_id, file_path=cert.file_path)
        raise HTTPException(status_code=404, detail="Certificate file not found in storage")
        
    logger.info("Serving certificate download", certificate_id=certificate_id, file_path=cert.file_path)
    return storage.get_download_response(
        cert.file_path,
        filename=f"{cert.recipient_name}_certificate.pdf",
        media_type="application/pdf"
    )

