from __future__ import annotations

from pathlib import Path
import logging
import os
import shutil
from typing import Protocol
from uuid import uuid4

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class DocumentStorage(Protocol):
    def put_file(self, source: Path, key: str, content_type: str) -> None: ...

    def read_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def delete_legacy_path(self, path: str) -> None: ...


class LocalDocumentStorage:
    def __init__(self, settings: Settings):
        self.root = Path(settings.document_storage_path).resolve()
        self.legacy_root = Path(settings.storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        candidate = Path(key)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise StorageError("Invalid document storage key.")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise StorageError("Invalid document storage key.")
        return resolved

    def put_file(self, source: Path, key: str, content_type: str) -> None:
        del content_type  # Local storage does not need MIME metadata.
        destination = self._safe_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with source.open("rb") as source_file, temporary.open("wb") as destination_file:
                shutil.copyfileobj(source_file, destination_file, length=1024 * 1024)
            os.replace(temporary, destination)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary document object.")
            raise StorageError("The document could not be stored.") from exc

    def read_bytes(self, key: str) -> bytes:
        path = self._safe_path(key)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError("The stored document could not be read.") from exc

    def delete(self, key: str) -> None:
        path = self._safe_path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The stored document could not be deleted.") from exc

    def delete_legacy_path(self, path: str) -> None:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if candidate != self.legacy_root and self.legacy_root not in candidate.parents:
            raise StorageError("Invalid legacy document storage path.")
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The stored document could not be deleted.") from exc


class S3DocumentStorage:
    def __init__(self, settings: Settings):
        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET is required when document storage uses S3.")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - dependency is installed in production.
            raise StorageError("The boto3 package is required for S3 document storage.") from exc

        client_kwargs: dict[str, str] = {}
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_region:
            client_kwargs["region_name"] = settings.s3_region
        if settings.s3_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
        if settings.s3_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        self.client = boto3.client("s3", **client_kwargs)
        self.bucket = settings.s3_bucket

    def put_file(self, source: Path, key: str, content_type: str) -> None:
        try:
            with source.open("rb") as source_file:
                self.client.upload_fileobj(
                    source_file,
                    self.bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
        except Exception as exc:
            raise StorageError("The document could not be stored.") from exc

    def read_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise StorageError("The stored document could not be read.") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError("The stored document could not be deleted.") from exc

    def delete_legacy_path(self, path: str) -> None:
        del path
        raise StorageError("A legacy local storage object cannot be deleted from an S3 backend.")


def get_document_storage(settings: Settings | None = None) -> DocumentStorage:
    settings = settings or get_settings()
    if settings.document_storage_backend == "s3":
        return S3DocumentStorage(settings)
    if settings.environment.lower() == "production":
        raise StorageError("Local document storage is not allowed in production.")
    return LocalDocumentStorage(settings)
