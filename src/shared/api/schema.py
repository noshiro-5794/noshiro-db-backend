import re

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.openapi import AutoSchema


class ContextJWTScheme(SimpleJWTScheme):
    target_class = "shared.api.authentication.ContextJWTAuthentication"


class NoshiroAutoSchema(AutoSchema):
    """Project schema defaults for APIViews and stable generated operation IDs."""

    def get_operation_id(self) -> str:
        path = self.path.strip("/") or "root"
        path = re.sub(r"\{([^}]+)\}", r"by_\1", path)
        path = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
        return f"{self.method.lower()}_{path}"
