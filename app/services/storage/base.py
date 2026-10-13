from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO
from fastapi.responses import Response

class BaseStorageBackend(ABC):
    """
    Abstract interface for storage backends (Local filesystem, AWS S3, MinIO, etc.).
    """

    @abstractmethod
    def upload_file(
        self,
        source: str | Path | bytes | BinaryIO,
        destination_path: str,
        content_type: str = "application/pdf",
    ) -> str:
        """
        Uploads or saves a file to the storage backend.
        Returns the stored storage path / key identifier.
        """
        pass

    @abstractmethod
    def get_file_bytes(self, storage_path: str) -> bytes:
        """
        Retrieves the raw bytes of a file from storage.
        """
        pass

    @abstractmethod
    def file_exists(self, storage_path: str) -> bool:
        """
        Checks whether a file exists in the storage backend.
        """
        pass

    @abstractmethod
    def delete_file(self, storage_path: str) -> bool:
        """
        Deletes a file from the storage backend. Returns True if deleted or did not exist.
        """
        pass

    @abstractmethod
    def get_download_response(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/pdf",
    ) -> Response:
        """
        Returns a FastAPI Response (FileResponse for local or StreamingResponse for S3)
        to download or stream the file.
        """
        pass

    @abstractmethod
    def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """
        Generates a secure pre-signed download URL (or local path/URL).
        """
        pass

    @abstractmethod
    def check_health(self) -> tuple[bool, str | None]:
        """
        Actively checks the health and accessibility of the storage backend.
        Returns (True, None) if healthy, or (False, error_message) if unhealthy.
        """
        pass
