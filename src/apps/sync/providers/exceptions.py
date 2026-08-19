class ProviderAPIError(RuntimeError):
    """Base exception for external catalog provider failures."""


class BangumiAPIError(ProviderAPIError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404


class VNDBAPIError(ProviderAPIError):
    pass


__all__ = ["BangumiAPIError", "ProviderAPIError", "VNDBAPIError"]
