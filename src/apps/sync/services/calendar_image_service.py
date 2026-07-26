import logging
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
from django.conf import settings

from integrations.storage.minio import minio_client

logger = logging.getLogger(__name__)


class CalendarImageService:
    FOLDER = "calendar-covers"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": settings.BANGUMI_USER_AGENT},
                timeout=settings.BANGUMI_TIMEOUT,
                follow_redirects=False,
            )
        return self._client

    def cache_cover(
        self,
        *,
        bangumi_id: int,
        images: dict | None,
    ) -> str:
        image_url = self._select_image_url(images)
        if not image_url or not self._is_allowed_url(image_url):
            return ""

        try:
            with self.client.stream("GET", image_url) as response:
                response.raise_for_status()
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                )
                if content_type and not content_type.startswith("image/"):
                    return ""

                content_length = response.headers.get("content-length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > settings.BANGUMI_IMAGE_MAX_BYTES
                ):
                    return ""

                file_obj = BytesIO()
                for chunk in response.iter_bytes():
                    if file_obj.tell() + len(chunk) > settings.BANGUMI_IMAGE_MAX_BYTES:
                        return ""
                    file_obj.write(chunk)

            ext = self._extension_for(image_url=image_url, content_type=content_type)
            file_name = f"{self.FOLDER}/{bangumi_id}{ext}"
            file_obj.name = PurePosixPath(file_name).name
            file_obj.size = file_obj.tell()
            file_obj.seek(0)

            return minio_client.upload_file(
                file_obj,
                file_name=file_name,
                content_type=content_type or "image/jpeg",
                folder=self.FOLDER,
            )
        except Exception:
            logger.warning(
                "Calendar cover caching failed",
                extra={"bangumi_id": bangumi_id, "image_url": image_url},
                exc_info=True,
            )
            return ""

    @staticmethod
    def _is_allowed_url(image_url: str) -> bool:
        parsed = urlparse(image_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not hostname:
            return False

        return any(
            hostname == allowed_host or hostname.endswith(f".{allowed_host}")
            for raw_host in settings.BANGUMI_IMAGE_ALLOWED_HOSTS
            if (allowed_host := raw_host.strip().lower())
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

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
