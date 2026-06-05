import os
import uuid

from django.conf import settings
from minio import Minio
from minio.error import S3Error


class MinioClient:

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_HTTPS,
        )
        self.bucket = settings.MINIO_BUCKET
        self._bucket_ready = False

    def _ensure_bucket(self):
        if self._bucket_ready:
            return
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._bucket_ready = True
        except S3Error as e:
            raise RuntimeError(f"MinIO bucket init failed: {e}")

    def upload_file(
        self,
        file_obj,
        file_name=None,
        content_type=None,
        folder="uploads",
    ):
        try:
            original_name = getattr(file_obj, "name", "")
            ext = os.path.splitext(original_name)[-1].lower() or ".jpg"
            folder = folder.strip("/")
            file_name = file_name or f"{folder}/{uuid.uuid4().hex}{ext}"
            content_type = content_type or getattr(
                file_obj, "content_type", "application/octet-stream"
            )
            self._ensure_bucket()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            self.client.put_object(
                self.bucket,
                file_name,
                file_obj,
                length=getattr(file_obj, "size", -1),
                content_type=content_type,
            )
            return self.get_file_url(file_name)
        except S3Error as e:
            raise RuntimeError(f"MinIO upload failed: {e}")

    def get_file_url(self, file_name: str) -> str:
        base = settings.MINIO_PUBLIC_URL.rstrip("/")
        return f"{base}/{self.bucket}/{file_name}"


minio_client = MinioClient()
