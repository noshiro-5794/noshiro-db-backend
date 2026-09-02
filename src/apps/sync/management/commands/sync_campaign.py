from django.core.management.base import BaseCommand, CommandError

from apps.sync.models import SyncCampaign
from apps.sync.services.campaign_service import (
    campaign_idempotency_key,
    sync_campaign_service,
)


class Command(BaseCommand):
    help = "Run a durable provider-wide sync campaign."

    def add_arguments(self, parser):
        parser.add_argument("provider", choices=("vndb", "anilist", "bangumi"))
        parser.add_argument(
            "--campaign-type",
            choices=("full", "incremental"),
            default="full",
        )
        parser.add_argument(
            "--ai-mode",
            choices=[value for value, _ in SyncCampaign.AIMode.choices],
            default=SyncCampaign.AIMode.SHADOW,
        )
        parser.add_argument("--idempotency-key", default="")
        parser.add_argument("--page-size", type=int, default=100)
        parser.add_argument(
            "--ai-sample-size",
            type=int,
            default=0,
            help="Optional cap for AI processing; zero processes every successful item.",
        )
        parser.add_argument("--max-items", type=int)

    def handle(self, *args, **options):
        provider = options["provider"]
        campaign_type = options["campaign_type"]
        parameters = {
            "page_size": options["page_size"],
            "ai_sample_size": options["ai_sample_size"],
        }
        key = options["idempotency_key"] or campaign_idempotency_key(
            provider_slug=provider,
            campaign_type=campaign_type,
            parameters=parameters,
        )
        try:
            campaign = sync_campaign_service.create_campaign(
                provider_slug=provider,
                campaign_type=campaign_type,
                ai_mode=options["ai_mode"],
                parameters=parameters,
                idempotency_key=key,
            )
            campaign = sync_campaign_service.run(
                campaign, max_items=options.get("max_items")
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Campaign {campaign.pk} {campaign.provider_slug}: {campaign.status}"
            )
        )
