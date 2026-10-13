from app.core.config import settings
from app.services.storage.base import BaseStorageBackend
from app.services.storage.local import LocalStorageBackend
from app.services.storage.s3 import S3StorageBackend

def get_storage_backend(storage_type: str | None = None) -> BaseStorageBackend:
    """
    Factory function returning the appropriate storage backend based on configuration or argument.
    """
    backend_name = (storage_type or settings.storage_type).lower().strip()
    if backend_name == "s3":
        return S3StorageBackend()
    elif backend_name == "local":
        return LocalStorageBackend()
    else:
        raise ValueError(
            f"Unsupported storage backend '{backend_name}'. Supported backends are 'local' and 's3'."
        )

__all__ = [
    "BaseStorageBackend",
    "LocalStorageBackend",
    "S3StorageBackend",
    "get_storage_backend",
]
