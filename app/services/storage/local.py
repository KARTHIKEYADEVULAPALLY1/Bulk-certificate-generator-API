import os
import shutil
from pathlib import Path
from typing import BinaryIO
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from app.core.config import settings
from app.services.storage.base import BaseStorageBackend

class LocalStorageBackend(BaseStorageBackend):
    """
    Storage backend implementation using the local filesystem.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.storage_dir).resolve()
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_path(self, storage_path: str) -> Path:
        """
        Resolves a storage path safely, handling relative paths within base_dir
        as well as existing absolute paths (e.g., from test environments).
        Prevents directory traversal attacks.
        """
        p = Path(storage_path)
        if p.is_absolute() and p.exists():
            return p.resolve()

        # Sanitize and resolve relative to base_dir
        normalized = storage_path.replace("\\", "/").lstrip("/")
        target = (self.base_dir / normalized).resolve()
        if not target.is_relative_to(self.base_dir):
            raise ValueError(f"Path traversal attempt detected: {storage_path}")
        return target

    def upload_file(
        self,
        source: str | Path | bytes | BinaryIO,
        destination_path: str,
        content_type: str = "application/pdf",
    ) -> str:
        target_path = self._resolve_path(destination_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(source, (str, Path)):
            src_path = Path(source).resolve()
            if src_path != target_path.resolve():
                shutil.copyfile(src_path, target_path)
        elif isinstance(source, bytes):
            with open(target_path, "wb") as f:
                f.write(source)
        elif hasattr(source, "read"):
            with open(target_path, "wb") as f:
                shutil.copyfileobj(source, f)
        else:
            raise TypeError(f"Unsupported source type for upload_file: {type(source)}")

        try:
            return str(target_path.relative_to(self.base_dir)).replace("\\", "/")
        except ValueError:
            return str(target_path).replace("\\", "/")

    def get_file_bytes(self, storage_path: str) -> bytes:
        target_path = self._resolve_path(storage_path)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {storage_path}")
        with open(target_path, "rb") as f:
            return f.read()

    def file_exists(self, storage_path: str) -> bool:
        try:
            target_path = self._resolve_path(storage_path)
            return target_path.is_file()
        except Exception:
            return False

    def delete_file(self, storage_path: str) -> bool:
        try:
            target_path = self._resolve_path(storage_path)
            if target_path.exists():
                target_path.unlink()
                return True
            return False
        except Exception:
            return False

    def get_download_response(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/pdf",
    ) -> Response:
        target_path = self._resolve_path(storage_path)
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File not found in storage")
        return FileResponse(
            path=str(target_path),
            filename=filename,
            media_type=media_type,
        )

    def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        target_path = self._resolve_path(storage_path)
        return str(target_path)

    def check_health(self) -> tuple[bool, str | None]:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            probe = self.base_dir / ".healthz_probe"
            probe.write_bytes(b"healthz")
            if probe.exists():
                probe.unlink()
            return True, None
        except Exception as e:
            return False, str(e)

