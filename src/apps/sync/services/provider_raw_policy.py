"""Provider raw-payload completeness policy.

Not every provider record is backed by a replayable API payload. This module
centralizes the classification so ingestion and maintenance commands agree on
what ``raw`` / ``slim`` / ``stub`` / ``legacy`` mean.
"""

from __future__ import annotations

from apps.index.models import ProviderRecord

# Namespaces whose stored payload intentionally contains a bounded projection
# (cards, schedule nodes, list pages) rather than the provider's full object.
SLIM_NAMESPACES: frozenset[tuple[str, str]] = frozenset(
    {
        ("anilist", "anime"),
        ("anilist", "episode"),
        ("anilist", "season-item"),
        ("anilist", "calendar"),
        ("anilist", "season"),
        ("mal", "schedule-item"),
        ("mal", "season"),
        ("bangumi", "calendar"),
        ("vndb", "vn-related"),
    }
)


def raw_state_for_namespace(
    *,
    provider_slug: str,
    namespace_slug: str,
) -> str:
    """Return the state for a record that owns a revision payload."""
    key = (provider_slug, namespace_slug)
    if key in SLIM_NAMESPACES:
        return ProviderRecord.RawState.SLIM
    return ProviderRecord.RawState.RAW


def stub_state_for_namespace(*, provider_slug: str) -> str:
    """Return the state for a record created without any payload."""
    if provider_slug == "bangumi":
        return ProviderRecord.RawState.LEGACY
    return ProviderRecord.RawState.STUB
