import re
from pathlib import Path
from app.core.config import settings

def sanitize_path_component(component: str) -> str:
    """
    Sanitizes a path component (like job_id or cert_id) to prevent directory traversal.
    Only allows alphanumeric characters, hyphens, and underscores.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', str(component))
    if not sanitized:
        raise ValueError("Invalid path component after sanitization.")
    return sanitized

def get_certificate_path(job_id: str, certificate_id: str) -> Path:
    """
    Generates a safe storage path for a certificate.
    Format: {storage_dir}/{job_id}/{certificate_id}.pdf
    """
    safe_job = sanitize_path_component(job_id)
    safe_cert = sanitize_path_component(certificate_id)
    
    base_dir = Path(settings.storage_dir).resolve()
    target_path = (base_dir / safe_job / f"{safe_cert}.pdf").resolve()
    
    if not target_path.is_relative_to(base_dir):
        raise ValueError("Path traversal attempt detected")
        
    return target_path
