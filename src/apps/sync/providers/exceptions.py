class ProviderAPIError(RuntimeError):
    """Base exception for external catalog provider failures."""

    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        error_code: str = "provider_error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.error_code = error_code


class BangumiAPIError(ProviderAPIError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            retry_after=retry_after,
            error_code=f"http_{status_code}" if status_code else "request_error",
        )
        self.retryable = status_code == 429 or status_code is None or status_code >= 500

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404


class VNDBAPIError(ProviderAPIError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            retry_after=retry_after,
            error_code=f"http_{status_code}" if status_code else "request_error",
        )
        self.retryable = status_code == 429 or status_code is None or status_code >= 500


class AniListAPIError(ProviderAPIError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            retry_after=retry_after,
            error_code=f"http_{status_code}" if status_code else "request_error",
        )
        self.retryable = status_code == 429 or status_code is None or status_code >= 500


__all__ = [
    "AniListAPIError",
    "BangumiAPIError",
    "ProviderAPIError",
    "VNDBAPIError",
]
