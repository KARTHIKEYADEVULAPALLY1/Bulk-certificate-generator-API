import io
from pathlib import Path
from typing import BinaryIO, Iterator
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response
from app.core.config import settings
from app.services.storage.base import BaseStorageBackend

class S3StorageBackend(BaseStorageBackend):
    """
    Storage backend implementation for AWS S3 and S3-compatible cloud object stores (e.g. MinIO).
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        s3_client=None,
    ):
        self.bucket_name = bucket_name or settings.s3_bucket_name
        self.endpoint_url = endpoint_url or settings.s3_endpoint_url
        self.aws_access_key_id = aws_access_key_id or settings.s3_access_key
        self.aws_secret_access_key = aws_secret_access_key or settings.s3_secret_key
        self.region_name = region_name or settings.s3_region

        if s3_client is not None:
            self.s3_client = s3_client
        else:
            client_kwargs = {
                "region_name": self.region_name,
            }
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
            if self.aws_access_key_id and self.aws_secret_access_key:
                client_kwargs["aws_access_key_id"] = self.aws_access_key_id
                client_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

            self.s3_client = boto3.client("s3", **client_kwargs)

    def _normalize_key(self, storage_path: str) -> str:
        return storage_path.replace("\\", "/").lstrip("/")

    def upload_file(
        self,
        source: str | Path | bytes | BinaryIO,
        destination_path: str,
        content_type: str = "application/pdf",
    ) -> str:
        key = self._normalize_key(destination_path)
        extra_args = {"ContentType": content_type}

        if isinstance(source, (str, Path)):
            src_path = str(source)
            self.s3_client.upload_file(
                Filename=src_path,
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs=extra_args,
            )
        elif isinstance(source, bytes):
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=source,
                ContentType=content_type,
            )
        elif hasattr(source, "read"):
            self.s3_client.upload_fileobj(
                Fileobj=source,
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs=extra_args,
            )
        else:
            raise TypeError(f"Unsupported source type for S3 upload: {type(source)}")

        return key

    def get_file_bytes(self, storage_path: str) -> bytes:
        key = self._normalize_key(storage_path)
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"Object not found in S3 bucket {self.bucket_name}: {key}") from e
            raise

    def file_exists(self, storage_path: str) -> bool:
        key = self._normalize_key(storage_path)
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False

    def delete_file(self, storage_path: str) -> bool:
        key = self._normalize_key(storage_path)
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False

    def get_download_response(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/pdf",
    ) -> Response:
        key = self._normalize_key(storage_path)
        try:
            s3_obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("NoSuchKey", "404"):
                raise HTTPException(status_code=404, detail="File not found in storage") from e
            raise HTTPException(status_code=500, detail=f"S3 storage error: {str(e)}") from e

        content_length = s3_obj.get("ContentLength")
        body = s3_obj["Body"]

        def iterfile() -> Iterator[bytes]:
            for chunk in body.iter_chunks(chunk_size=65536):
                yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length is not None:
            headers["Content-Length"] = str(content_length)

        return StreamingResponse(
            content=iterfile(),
            media_type=media_type,
            headers=headers,
        )

    def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        key = self._normalize_key(storage_path)
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )

    def check_health(self) -> tuple[bool, str | None]:
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True, None
        except Exception as e:
            return False, str(e)

