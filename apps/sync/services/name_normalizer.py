from cachetools import TTLCache
from django.db import IntegrityError, transaction

from apps.sync.models import NameMapping
from apps.sync.providers.ai import ai_client


class NameNormalizer:

    def __init__(self):

        self.cache = TTLCache(maxsize=1000, ttl=172800)

    def normalize_name(self, name: str) -> str:
        if not name:
            return ""

        if name in self.cache:
            return self.cache[name]

        mapping = (
            NameMapping.objects.filter(external_name=name).only("internal_name").first()
        )
        if mapping:
            self.cache[name] = mapping.internal_name
            return mapping.internal_name

        try:
            normalized_name = ai_client.normalize_name(name)
        except Exception as exc:
            normalized_name = name.strip()
            print(
                f"[name-normalizer] fallback to original name={name!r}: {exc}",
                flush=True,
            )
            return normalized_name

        if not normalized_name:
            raise RuntimeError("Failed to normalize name")

        try:
            with transaction.atomic():
                obj, _ = NameMapping.objects.get_or_create(
                    external_name=name, defaults={"internal_name": normalized_name}
                )
                final_name = obj.internal_name
        except IntegrityError:
            obj = NameMapping.objects.get(external_name=name)
            final_name = obj.internal_name

        self.cache[name] = final_name

        return final_name


name_normalizer = NameNormalizer()
