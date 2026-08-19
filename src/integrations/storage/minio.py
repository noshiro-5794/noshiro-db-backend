import os
import uuid
from typing import BinaryIO
from urllib.parse import quote, unquote, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from minio import Minio
from minio.error import S3Error

from integrations.storage.exceptions import ObjectStorageError


class MinioClient:
    def __init__(self, client: Minio | None = None) -> None:
        self._client = client
        self._bucket_ready = False

    @staticmethod
    def _required_setting(name: str) -> str:
        value = getattr(settings, name, None)
        if not value:
            raise ImproperlyConfigured(f"{name} must be configured to use MinIO.")
        return value

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                self._required_setting("MINIO_ENDPOINT"),
                access_key=self._required_setting("MINIO_ACCESS_KEY"),
                secret_key=self._required_setting("MINIO_SECRET_KEY"),
                secure=getattr(settings, "MINIO_USE_HTTPS", False),
            )
        return self._client

    @property
    def bucket(self) -> str:
        return self._required_setting("MINIO_BUCKET")

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._bucket_ready = True
        except S3Error as exc:
            if exc.code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                self._bucket_ready = True
                return
            raise ObjectStorageError("MinIO bucket initialization failed.") from exc

    @staticmethod
    def _normalize_object_name(value: str) -> str:
        object_name = value.strip().replace("\\", "/").strip("/")
        parts = object_name.split("/")
        if not object_name or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Object name must be a non-empty relative path.")
        return object_name

    def upload_file(
        self,
        file_obj: BinaryIO,
        file_name: str | None = None,
        content_type: str | None = None,
        folder: str = "uploads",
    ) -> str:
        try:
            original_name = getattr(file_obj, "name", "")
            ext = os.path.splitext(original_name)[-1].lower() or ".jpg"
            folder = self._normalize_object_name(folder)
            object_name = self._normalize_object_name(
                file_name or f"{folder}/{uuid.uuid4().hex}{ext}"
            )
            content_type = content_type or getattr(
                file_obj, "content_type", "application/octet-stream"
            )
            self._ensure_bucket()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            self.client.put_object(
                self.bucket,
                object_name,
                file_obj,
                length=getattr(file_obj, "size", -1),
                content_type=content_type,
            )
            return self.get_file_url(object_name)
        except S3Error as exc:
            raise ObjectStorageError("MinIO upload failed.") from exc

    def get_file_url(self, file_name: str) -> str:
        base = self._required_setting("MINIO_PUBLIC_URL").rstrip("/")
        object_name = self._normalize_object_name(file_name)
        return f"{base}/{quote(self.bucket)}/{quote(object_name, safe='/')}"

    def _object_name_from_public_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        parts = path.split("/", 1)
        if len(parts) != 2 or unquote(parts[0]) != self.bucket:
            return None
        return unquote(parts[1])

    def delete_public_url(self, url: str) -> bool:
        object_name = self._object_name_from_public_url(url)
        if not object_name:
            return False
        try:
            self._ensure_bucket()
            self.client.remove_object(self.bucket, object_name)
        except S3Error as exc:
            raise ObjectStorageError("MinIO object deletion failed.") from exc
        return True


minio_client = MinioClient()
