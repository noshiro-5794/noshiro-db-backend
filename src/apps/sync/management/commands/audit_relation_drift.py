"""Read-only relation drift audit across recently synced relation records."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.index.models import ProviderRecord
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_RELATIONS_NAMESPACE
from apps.sync.services.relation_drift_service import relation_drift_service


class Command(BaseCommand):
    help = (
        "Compare latest relation observations with stored relations and report "
        "provider-removed relations. Never writes or deletes anything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument(
            "--details",
            action="store_true",
            help="Print each drifted relation row.",
        )

    def handle(self, *args, **options):
        records = list(
            ProviderRecord.objects.filter(
                namespace__provider__slug="bangumi",
                namespace__slug=BANGUMI_SUBJECT_RELATIONS_NAMESPACE.slug,
                status=ProviderRecord.Status.ACTIVE,
            )
            .order_by("-updated_at")
            .only("id", "external_id", "updated_at")[: max(1, options["limit"])]
        )
        total_drift = 0
        affected = 0
        for record in records:
            drift = relation_drift_service.audit_record(record=record)
            if not drift:
                continue
            affected += 1
            total_drift += len(drift)
            if options["details"]:
                for row in drift:
                    self.stdout.write(
                        f"  {record.external_id}: ->{row.target_external_id or '?'} "
                        f"{row.relation_type} ({row.raw_relation}) "
                        f"last_seen={row.last_seen_at}"
                    )
        self.stdout.write(
            f"audited={len(records)} affected={affected} drift={total_drift}"
        )
