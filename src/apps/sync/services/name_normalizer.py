import re
import unicodedata

from django.core.cache import cache

from apps.index.models import TermAlias


class NameNormalizer:
    CACHE_TTL_SECONDS = 60 * 60 * 24

    def normalize_name(
        self,
        name: str,
        *,
        vocabulary: str = "legacy",
        provider_namespace_id=None,
        language: str = "",
    ) -> str:
        original = name.strip()
        if not original:
            return ""
        normalized_key = self.normalize_key(original)
        cache_key = (
            f"noshiro:term-alias:{vocabulary}:"
            f"{provider_namespace_id or ''}:{language}:{normalized_key}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        aliases = TermAlias.objects.filter(
            vocabulary=vocabulary,
            normalized_key=normalized_key,
            language=language,
        )
        if provider_namespace_id is None:
            aliases = aliases.filter(provider_namespace__isnull=True)
        else:
            aliases = aliases.filter(provider_namespace_id=provider_namespace_id)
        alias = aliases.only("preferred_term").order_by("-is_reviewed", "id").first()
        preferred_term = alias.preferred_term if alias is not None else original
        cache.set(cache_key, preferred_term, timeout=self.CACHE_TTL_SECONDS)
        return preferred_term

    @staticmethod
    def normalize_key(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).strip().lower()
        return re.sub(r"\s+", " ", value)


name_normalizer = NameNormalizer()
