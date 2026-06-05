from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
from django.conf import settings

from apps.core.storage.minio_client import minio_client


class CalendarImageService:

    FOLDER = "calendar-covers"

    @classmethod
    def cache_cover(cls, *, bangumi_id: int, images: dict | None) -> str:
        image_url = cls._select_image_url(images)
        if not image_url:
            return ""

        try:
            response = httpx.get(
                image_url,
                timeout=settings.BANGUMI_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                return ""

            ext = cls._extension_for(image_url=image_url, content_type=content_type)
            file_name = f"{cls.FOLDER}/{bangumi_id}{ext}"
            file_obj = BytesIO(response.content)
            file_obj.name = PurePosixPath(file_name).name
            file_obj.size = len(response.content)

            return minio_client.upload_file(
                file_obj,
                file_name=file_name,
                content_type=content_type or "image/jpeg",
                folder=cls.FOLDER,
            )
        except Exception:
            return ""

    @staticmethod
    def _select_image_url(images: dict | None) -> str:
        if not isinstance(images, dict):
            return ""
        for key in ("large", "common", "medium", "grid", "small"):
            value = images.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _extension_for(*, image_url: str, content_type: str) -> str:
        by_content_type = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        if content_type in by_content_type:
            return by_content_type[content_type]
        suffix = PurePosixPath(urlparse(image_url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
        return ".jpg"


calendar_image_service = CalendarImageService()
