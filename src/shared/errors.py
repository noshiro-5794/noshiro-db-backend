class ApplicationError(Exception):
    default_code = 10000
    default_message = "business error"

    def __init__(
        self,
        message: str | None = None,
        code: int | None = None,
    ) -> None:
        self.message = self.default_message if message is None else message
        self.code = self.default_code if code is None else code
        super().__init__(self.message)
