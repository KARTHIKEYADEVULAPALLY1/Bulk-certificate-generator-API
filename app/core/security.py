import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

api_key_header = APIKeyHeader(
    name=settings.api_key_name,
    auto_error=False,
    description="API Key authentication header",
)

def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Validates the API key from request headers using constant-time comparison.
    Raises HTTP 401 Unauthorized if the key is missing or invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key header",
        )
    if not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return api_key
