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
        ai_context=None,
    ) -> str:
        original = name.strip()
        if not original:
            return ""
        if ai_context is not None and ai_context.enabled:
            from apps.sync.services.campaign_ai import sync_ai_service

            result = sync_ai_service.normalize_field(
                context=ai_context,
                vocabulary=vocabulary,
                source_text=original,
                provider_namespace=ai_context.campaign.provider_slug,
                language=language,
            )
            if result.action in {"map_existing", "propose_new"}:
                return result.preferred_term[:256]
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
            is_reviewed=True,
        )
        if provider_namespace_id is None:
            aliases = aliases.filter(provider_namespace__isnull=True)
        else:
            aliases = aliases.filter(provider_namespace_id=provider_namespace_id)
        alias = aliases.only("preferred_term").order_by("-confidence", "id").first()
        preferred_term = alias.preferred_term if alias is not None else original
        cache.set(cache_key, preferred_term, timeout=self.CACHE_TTL_SECONDS)
        return preferred_term

    @staticmethod
    def normalize_key(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).strip().lower()
        return re.sub(r"\s+", " ", value)


name_normalizer = NameNormalizer()
