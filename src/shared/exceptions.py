from http import HTTPStatus
from urllib.parse import quote


class ApplicationError(Exception):
    PROBLEM_BASE_URI = "https://noshiro.moe/problems/"
    default_code = "application_error"
    default_message = "The request could not be completed."
    default_status = HTTPStatus.BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status: int | HTTPStatus | None = None,
    ) -> None:
        self.message = self.default_message if message is None else message
        self.code = self.default_code if code is None else code
        self.status = int(self.default_status if status is None else status)
        super().__init__(self.message)

    @property
    def problem_type(self) -> str:
        """Stable public problem type URI for RFC 9457 responses."""
        return f"{self.PROBLEM_BASE_URI}{quote(self.code, safe='._-')}"
