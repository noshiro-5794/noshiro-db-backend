from apps.sync.providers.exceptions import AniListAPIError, VNDBAPIError
from apps.sync.services.relation_types import canonical_relation_type


def test_provider_http_errors_expose_retry_policy() -> None:
    rate_limited = VNDBAPIError("busy", status_code=429, retry_after=4)
    permanent = AniListAPIError("invalid", status_code=400)

    assert rate_limited.retryable is True
    assert rate_limited.retry_after == 4
    assert rate_limited.error_code == "http_429"
    assert permanent.retryable is False


def test_relation_vocabularies_share_canonical_slugs() -> None:
    assert canonical_relation_type("vndb", "seq") == "sequel"
    assert canonical_relation_type("anilist", "SEQUEL") == "sequel"
    assert canonical_relation_type("bangumi", "续作") == "sequel"


def test_unknown_relation_keeps_a_stable_slug() -> None:
    assert canonical_relation_type("custom", "Official Remake") == "official-remake"
