import logging

from cachetools import TTLCache

from apps.sync.models import NameMapping
from apps.sync.providers.ai import AIProviderError, ai_client

logger = logging.getLogger(__name__)


class NameNormalizer:
    def __init__(self):
        self.cache = TTLCache(maxsize=1000, ttl=172800)

    def normalize_name(self, name: str) -> str:
        external_name = name.strip()
        if not external_name:
            return ""

        if external_name in self.cache:
            return self.cache[external_name]

        mapping = (
            NameMapping.objects.filter(external_name=external_name)
            .only("internal_name")
            .first()
        )
        if mapping:
            self.cache[external_name] = mapping.internal_name
            return mapping.internal_name

        try:
            normalized_name = ai_client.normalize_name(external_name)[:256]
        except AIProviderError:
            logger.warning(
                "Name normalization failed; using the original value",
                extra={"external_name": external_name},
                exc_info=True,
            )
            return external_name

        if len(external_name) > 256:
            return normalized_name

        obj, _ = NameMapping.objects.get_or_create(
            external_name=external_name,
            defaults={"internal_name": normalized_name},
        )
        final_name = obj.internal_name

        self.cache[external_name] = final_name

        return final_name


name_normalizer = NameNormalizer()
