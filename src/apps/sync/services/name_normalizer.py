from cachetools import TTLCache

from apps.sync.models import NameMapping


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

        # Source vocabulary remains unchanged until a reviewed taxonomy mapping exists.
        self.cache[external_name] = external_name
        return external_name


name_normalizer = NameNormalizer()
