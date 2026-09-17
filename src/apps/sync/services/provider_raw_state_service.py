"""Classify and repair provider raw-payload completeness."""

from __future__ import annotations

from typing import Any

from django.db import connection

from apps.index.models import ProviderRecord
from apps.sync.services.provider_raw_policy import (
    SLIM_NAMESPACES,
)


class ProviderRawStateService:
    def report(self) -> dict[str, Any]:
        rows = ProviderRecord.objects.values(
            "namespace__provider__slug",
            "raw_state",
        ).order_by()
        summary: dict[str, dict[str, int]] = {}
        for row in rows:
            provider = row["namespace__provider__slug"]
            summary.setdefault(provider, {})
            summary[provider][row["raw_state"]] = (
                summary[provider].get(row["raw_state"], 0) + 1
            )
        return summary

    def classify(self, *, apply: bool = False) -> dict[str, Any]:
        slim_pairs = " OR ".join(
            f"(p.slug = '{provider}' AND pn.slug = '{namespace}')"
            for provider, namespace in sorted(SLIM_NAMESPACES)
        )
        namespace_subquery = (
            "SELECT pn.id FROM provider_namespace pn "
            "JOIN provider p ON p.id = pn.provider_id "
        )
        rules = [
            (
                "bangumi_no_payload",
                ProviderRecord.RawState.LEGACY,
                "pr.namespace_id IN ("
                + namespace_subquery
                + "WHERE p.slug = 'bangumi') AND pr.latest_revision_id IS NULL "
                "AND pr.raw_state <> 'legacy'",
            ),
            (
                "non_bangumi_no_payload",
                ProviderRecord.RawState.STUB,
                "pr.namespace_id IN ("
                + namespace_subquery
                + "WHERE p.slug <> 'bangumi') AND pr.latest_revision_id IS NULL "
                "AND pr.raw_state <> 'stub'",
            ),
            (
                "slim_payload",
                ProviderRecord.RawState.SLIM,
                "pr.latest_revision_id IS NOT NULL AND pr.raw_state <> 'slim' "
                "AND pr.namespace_id IN ("
                + namespace_subquery
                + f"WHERE {slim_pairs})",
            ),
            (
                "raw_payload",
                ProviderRecord.RawState.RAW,
                "pr.latest_revision_id IS NOT NULL "
                "AND pr.raw_state NOT IN ('slim', 'raw')",
            ),
        ]
        result: dict[str, Any] = {"rules": {}, "updated": 0}
        with connection.cursor() as cursor:
            for label, state, condition in rules:
                cursor.execute(
                    f"SELECT count(*) FROM provider_record pr WHERE {condition}"
                )
                count = cursor.fetchone()[0]
                result["rules"][label] = {"state": state, "count": count}
                if apply and count:
                    cursor.execute(
                        f"UPDATE provider_record pr SET raw_state = %s "
                        f"WHERE {condition}",
                        [state],
                    )
                    result["updated"] += cursor.rowcount
        return result

    def repair_mal_legacy(self, *, apply: bool = False) -> dict[str, Any]:
        queryset = ProviderRecord.objects.filter(
            namespace__provider__slug="mal",
            latest_revision__schema_version="jikan-v4",
        )
        records = list(queryset.values("id", "namespace__slug", "external_id"))
        result = {"count": len(records), "records": records, "updated": 0}
        if apply and records:
            result["updated"] = queryset.update(
                status=ProviderRecord.Status.MISSING,
                raw_state=ProviderRecord.RawState.LEGACY,
            )
        return result

    @staticmethod
    def repair_superseded_anilist_seasons(*, apply: bool = False) -> dict[str, Any]:
        """Retire the season snapshot produced by the old month-mapping bug."""
        queryset = ProviderRecord.objects.filter(
            namespace__provider__slug="anilist",
            namespace__slug="season",
            external_id="season:fall:2026",
        )
        count = queryset.count()
        if apply and count:
            queryset.update(status=ProviderRecord.Status.MISSING)
        return {"count": count, "updated": count if apply else 0}


provider_raw_state_service = ProviderRawStateService()
