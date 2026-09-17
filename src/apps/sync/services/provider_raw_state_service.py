"""Classify and repair provider raw-payload completeness."""

from __future__ import annotations

from typing import Any

from django.db.models import Q

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
        slim_condition = Q()
        for provider_slug, namespace_slug in SLIM_NAMESPACES:
            slim_condition |= Q(
                namespace__provider__slug=provider_slug,
                namespace__slug=namespace_slug,
            )
        rules = [
            (
                "bangumi_no_payload",
                ProviderRecord.RawState.LEGACY,
                Q(namespace__provider__slug="bangumi", latest_revision__isnull=True),
            ),
            (
                "non_bangumi_no_payload",
                ProviderRecord.RawState.STUB,
                Q(latest_revision__isnull=True)
                & ~Q(namespace__provider__slug="bangumi"),
            ),
            (
                "slim_payload",
                ProviderRecord.RawState.SLIM,
                Q(latest_revision__isnull=False) & slim_condition,
            ),
        ]
        result: dict[str, Any] = {"rules": {}, "updated": 0}
        for label, state, condition in rules:
            queryset = ProviderRecord.objects.filter(condition).exclude(raw_state=state)
            count = queryset.count()
            result["rules"][label] = {"state": state, "count": count}
            if apply and count:
                result["updated"] += queryset.update(raw_state=state)

        # Everything with a payload that is not explicitly slim stays raw.
        raw_queryset = ProviderRecord.objects.filter(
            latest_revision__isnull=False
        ).exclude(raw_state=ProviderRecord.RawState.SLIM)
        raw_count = raw_queryset.exclude(raw_state=ProviderRecord.RawState.RAW).count()
        result["rules"]["raw_payload"] = {
            "state": ProviderRecord.RawState.RAW,
            "count": raw_count,
        }
        if apply and raw_count:
            result["updated"] += raw_queryset.exclude(
                raw_state=ProviderRecord.RawState.RAW
            ).update(raw_state=ProviderRecord.RawState.RAW)
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


provider_raw_state_service = ProviderRawStateService()
