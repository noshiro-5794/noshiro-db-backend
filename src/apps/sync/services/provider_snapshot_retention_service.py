"""Retention policies for provider snapshots.

Current-state snapshots (for example the MAL/AniList season listing) only need
their latest revision to drive projections. Entity records and evidence
observations are never touched here; this service only compacts revisions that
belong to an explicitly classified snapshot namespace and refuses to delete
anything still referenced by protected evidence.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.index.models import (
    MappingRun,
    Observation,
    ProviderRecord,
    ProviderRevision,
)

CURRENT_ONLY: frozenset[tuple[str, str]] = frozenset(
    {
        ("mal", "season"),
        ("anilist", "season"),
    }
)


class ProviderSnapshotRetentionService:
    def policies(self) -> dict[str, Any]:
        return {
            "current_only": [
                {"provider": provider, "namespace": namespace}
                for provider, namespace in sorted(CURRENT_ONLY)
            ]
        }

    def report(self) -> dict[str, Any]:
        records = ProviderRecord.objects.filter(
            latest_revision__isnull=False,
            namespace__provider__slug__in=sorted(
                {provider for provider, _ in CURRENT_ONLY}
            ),
        )
        rows = []
        for record in records:
            key = (
                record.namespace.provider.slug,
                record.namespace.slug,
            )
            if key not in CURRENT_ONLY:
                continue
            revisions = ProviderRevision.objects.filter(record=record)
            rows.append(
                {
                    "record_id": str(record.pk),
                    "provider": key[0],
                    "namespace": key[1],
                    "external_id": record.external_id,
                    "revisions": revisions.count(),
                    "retained": 1,
                    "compactable": max(0, revisions.count() - 1),
                }
            )
        return {
            "records": len(rows),
            "compactable_revisions": sum(row["compactable"] for row in rows),
            "details": rows,
        }

    def retain_current(self, record: ProviderRecord) -> dict[str, int]:
        """Keep only the latest revision/observation for one snapshot record."""
        latest = record.latest_revision
        if latest is None:
            return {"deleted_revisions": 0, "deleted_observations": 0}
        deleted_revisions = 0
        deleted_observations = 0
        old_revisions = ProviderRevision.objects.filter(record=record).exclude(
            pk=latest.pk
        )
        for revision in old_revisions:
            observations = list(
                Observation.objects.filter(mapping_run__revision=revision)
            )
            deleted = True
            for observation in observations:
                try:
                    with transaction.atomic():
                        observation.delete()
                    deleted_observations += 1
                except ProtectedError:
                    deleted = False
                    break
            if not deleted:
                continue
            MappingRun.objects.filter(revision=revision).delete()
            ProviderRevision.objects.filter(pk=revision.pk).delete()
            deleted_revisions += 1
        return {
            "deleted_revisions": deleted_revisions,
            "deleted_observations": deleted_observations,
        }

    def compact(self, *, apply: bool = False) -> dict[str, Any]:
        report = self.report()
        if not apply:
            return report
        totals = {"deleted_revisions": 0, "deleted_observations": 0}
        for row in report["details"]:
            record = ProviderRecord.objects.get(pk=row["record_id"])
            result = self.retain_current(record)
            totals["deleted_revisions"] += result["deleted_revisions"]
            totals["deleted_observations"] += result["deleted_observations"]
        report["applied"] = totals
        return report


provider_snapshot_retention_service = ProviderSnapshotRetentionService()
