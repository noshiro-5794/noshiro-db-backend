"""Durable orchestration for provider-wide synchronization campaigns.

Provider clients own transport and pagination. Import services own canonical
projection. This module only coordinates the durable campaign/work-item
boundary and the optional evidence-first AI phase.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.ai.models import AgentRun, AIClaim
from apps.index.models import (
    Entity,
    Observation,
    ProviderRecord,
    ProviderRepresentation,
)
from apps.sync.models import SyncCampaign, SyncWorkItem
from apps.sync.providers.anilist import ANILIST_ANIME_NAMESPACE, anilist_client
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_NAMESPACE, bangumi_client
from apps.sync.providers.contracts import CatalogPage
from apps.sync.providers.exceptions import ProviderAPIError
from apps.sync.providers.vndb import VNDB_VN_NAMESPACE, vndb_client
from apps.sync.services.anilist_service import anilist_import_service
from apps.sync.services.campaign_ai import SyncAIContext, sync_ai_service
from apps.sync.services.campaign_state import SyncCampaignStateMachine
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.vndb_service import vndb_import_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CampaignProvider:
    slug: str
    namespace_slug: str
    discover: Callable[..., CatalogPage]
    import_item: Callable[[str], Entity]
    discover_delta: Callable[..., Any] | None = None
    # True when discovery provably enumerates the whole catalog (stable ordering
    # plus an authoritative terminal page); only then is MISSING reconciliation
    # safe. Bangumi's browse endpoint is an approximate view and defaults to
    # False.
    discovery_complete: bool = True


PROVIDERS: dict[str, CampaignProvider] = {
    "vndb": CampaignProvider(
        slug="vndb",
        namespace_slug=VNDB_VN_NAMESPACE.slug,
        discover=vndb_client.discover_vn_page,
        import_item=lambda external_id: vndb_import_service.import_work(
            vndb_id=external_id, include_related=True
        ),
        discover_delta=vndb_client.discover_vn_delta_page,
    ),
    "bangumi": CampaignProvider(
        slug="bangumi",
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        discover=bangumi_client.discover_subject_page,
        import_item=lambda external_id: _import_bangumi_subject(external_id),
        discover_delta=bangumi_client.discover_subject_delta_page,
        discovery_complete=False,
    ),
    "anilist": CampaignProvider(
        slug="anilist",
        namespace_slug=ANILIST_ANIME_NAMESPACE.slug,
        discover=anilist_client.discover_anime_page,
        import_item=lambda external_id: anilist_import_service.import_media(
            int(external_id)
        ),
        discover_delta=anilist_client.discover_anime_delta_page,
    ),
}


def _import_bangumi_subject(external_id: str) -> Entity:
    result = manual_subject_sync_service.sync_by_bangumi_id(bangumi_id=int(external_id))
    return Entity.objects.get(pk=result["subject_id"])


class CampaignProviderNotFound(ValueError):
    """Raised when a campaign references an unregistered provider."""


class SyncCampaignService:
    """Create, resume, and execute one durable provider synchronization."""

    DEFAULT_PAGE_SIZE = 100
    DEFAULT_DISCOVERY_PAGES_PER_STEP = 1
    DEFAULT_FETCH_BATCH_SIZE = 50
    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_RETRY_BASE_SECONDS = 30
    DEFAULT_AI_BATCH_SIZE = 50
    WORK_ITEM_LEASE_SECONDS = 300
    CAMPAIGN_LEASE_SECONDS = 600

    def provider_for(self, provider_slug: str) -> CampaignProvider:
        try:
            return PROVIDERS[provider_slug]
        except KeyError as exc:
            raise CampaignProviderNotFound(
                f"Unsupported campaign provider: {provider_slug}"
            ) from exc

    @transaction.atomic
    def create_campaign(
        self,
        *,
        provider_slug: str,
        campaign_type: str = "full",
        ai_mode: str = SyncCampaign.AIMode.SHADOW,
        parameters: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> SyncCampaign:
        self.provider_for(provider_slug)
        if ai_mode not in SyncCampaign.AIMode.values:
            raise ValueError(f"Unsupported AI mode: {ai_mode}")
        params = dict(parameters or {})
        key = (idempotency_key or "").strip()[:128]
        if key:
            campaign, _ = SyncCampaign.objects.get_or_create(
                provider_slug=provider_slug,
                campaign_type=campaign_type,
                idempotency_key=key,
                defaults={"ai_mode": ai_mode, "parameters": params},
            )
            return campaign
        return SyncCampaign.objects.create(
            provider_slug=provider_slug,
            campaign_type=campaign_type,
            ai_mode=ai_mode,
            parameters=params,
        )

    def run(
        self, campaign: SyncCampaign, *, max_items: int | None = None
    ) -> SyncCampaign:
        """Run one bounded campaign step; the Celery task schedules the next step."""
        campaign = SyncCampaign.objects.get(pk=campaign.pk)
        if campaign.status in {
            SyncCampaign.Status.PAUSED,
            SyncCampaign.Status.CANCELLED,
            SyncCampaign.Status.COMPLETED,
        }:
            return campaign
        owner = f"campaign:{uuid.uuid4()}"
        now = timezone.now()
        claimed = (
            SyncCampaign.objects.filter(
                pk=campaign.pk,
            )
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=now))
            .exclude(
                status__in=[
                    SyncCampaign.Status.PAUSED,
                    SyncCampaign.Status.CANCELLED,
                    SyncCampaign.Status.COMPLETED,
                ]
            )
            .update(
                lease_owner=owner,
                lease_expires_at=now + timedelta(seconds=self.CAMPAIGN_LEASE_SECONDS),
                heartbeat_at=now,
            )
        )
        if claimed != 1:
            return SyncCampaign.objects.get(pk=campaign.pk)
        campaign.refresh_from_db()
        if campaign.status == SyncCampaign.Status.FAILED:
            campaign = self.resume(campaign)
        if campaign.status == SyncCampaign.Status.QUEUED and not self._transition(
            campaign, SyncCampaign.Status.DISCOVERING
        ):
            SyncCampaign.objects.filter(pk=campaign.pk, lease_owner=owner).update(
                lease_owner="", lease_expires_at=None, heartbeat_at=timezone.now()
            )
            return SyncCampaign.objects.get(pk=campaign.pk)
        try:
            if campaign.status == SyncCampaign.Status.DISCOVERING:
                if not self._discover(campaign):
                    return SyncCampaign.objects.get(pk=campaign.pk)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.FETCHING
                )
            if campaign.status == SyncCampaign.Status.FETCHING:
                if not self._fetch(campaign, max_items=max_items):
                    return SyncCampaign.objects.get(pk=campaign.pk)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.MAPPING
                )
            if campaign.status == SyncCampaign.Status.MAPPING:
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.NORMALIZING
                )
            if campaign.status == SyncCampaign.Status.NORMALIZING:
                if not self._normalize(campaign):
                    return SyncCampaign.objects.get(pk=campaign.pk)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.RECONCILING
                )
            if campaign.status == SyncCampaign.Status.RECONCILING:
                self._reconcile_provider_records(campaign)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.ENRICHING
                )
            if campaign.status == SyncCampaign.Status.ENRICHING:
                if not self._enrich(campaign):
                    return SyncCampaign.objects.get(pk=campaign.pk)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.REVIEWING
                )
            if campaign.status == SyncCampaign.Status.REVIEWING:
                self._write_quality_report(campaign)
                self._promote_watermark(campaign)
                self._mark_agent_run_complete(campaign)
                self._transition_required(campaign, SyncCampaign.Status.COMPLETED)
        except Exception as exc:
            logger.exception(
                "Sync campaign failed", extra={"campaign_id": str(campaign.pk)}
            )
            self._fail(campaign, exc)
        finally:
            SyncCampaign.objects.filter(pk=campaign.pk, lease_owner=owner).update(
                lease_owner="", lease_expires_at=None, heartbeat_at=timezone.now()
            )
        return SyncCampaign.objects.get(pk=campaign.pk)

    @transaction.atomic
    def pause(self, campaign: SyncCampaign) -> SyncCampaign:
        campaign = SyncCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status in {
            SyncCampaign.Status.QUEUED,
            SyncCampaign.Status.DISCOVERING,
            SyncCampaign.Status.FETCHING,
            SyncCampaign.Status.MAPPING,
            SyncCampaign.Status.NORMALIZING,
            SyncCampaign.Status.RECONCILING,
            SyncCampaign.Status.ENRICHING,
            SyncCampaign.Status.REVIEWING,
        }:
            params = dict(campaign.parameters or {})
            params["paused_from"] = campaign.status
            campaign.parameters = params
            campaign.status = SyncCampaign.Status.PAUSED
            campaign.next_run_at = None
            campaign.save(
                update_fields=["parameters", "status", "next_run_at", "updated_at"]
            )
        return campaign

    @transaction.atomic
    def resume_paused(self, campaign: SyncCampaign) -> SyncCampaign:
        campaign = SyncCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != SyncCampaign.Status.PAUSED:
            return campaign
        params = dict(campaign.parameters or {})
        previous = params.pop("paused_from", SyncCampaign.Status.DISCOVERING)
        valid = {
            SyncCampaign.Status.QUEUED,
            SyncCampaign.Status.DISCOVERING,
            SyncCampaign.Status.FETCHING,
            SyncCampaign.Status.MAPPING,
            SyncCampaign.Status.NORMALIZING,
            SyncCampaign.Status.RECONCILING,
            SyncCampaign.Status.ENRICHING,
            SyncCampaign.Status.REVIEWING,
        }
        campaign.status = (
            previous if previous in valid else SyncCampaign.Status.DISCOVERING
        )
        campaign.parameters = params
        campaign.next_run_at = timezone.now()
        campaign.save(
            update_fields=["status", "parameters", "next_run_at", "updated_at"]
        )
        return campaign

    @transaction.atomic
    def cancel(self, campaign: SyncCampaign) -> SyncCampaign:
        campaign = SyncCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status not in {
            SyncCampaign.Status.COMPLETED,
            SyncCampaign.Status.CANCELLED,
        }:
            campaign.status = SyncCampaign.Status.CANCELLED
            campaign.finished_at = timezone.now()
            campaign.next_run_at = None
            campaign.save(
                update_fields=["status", "finished_at", "next_run_at", "updated_at"]
            )
            campaign.work_items.filter(status=SyncWorkItem.Status.RUNNING).update(
                status=SyncWorkItem.Status.QUEUED,
                lease_owner="",
                lease_expires_at=None,
            )
        return campaign

    @transaction.atomic
    def resume(self, campaign: SyncCampaign) -> SyncCampaign:
        """Make failed work retryable while preserving successful work."""
        campaign = SyncCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != SyncCampaign.Status.FAILED:
            return campaign
        SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.FAILED
        ).update(
            status=SyncWorkItem.Status.QUEUED,
            error="",
            lease_owner="",
            lease_expires_at=None,
            finished_at=None,
            next_retry_at=None,
            last_error_code="",
        )
        parameters = campaign.parameters or {}
        discovery = dict(parameters.get("discovery") or {})
        campaign.status = (
            SyncCampaign.Status.DISCOVERING
            if "discovery" not in parameters or discovery.get("next_cursor")
            else SyncCampaign.Status.FETCHING
        )
        campaign.error = ""
        campaign.finished_at = None
        campaign.updated_at = timezone.now()
        campaign.save(update_fields=["status", "error", "finished_at", "updated_at"])
        return campaign

    def _discover(self, campaign: SyncCampaign) -> bool:
        provider = self.provider_for(campaign.provider_slug)
        params = dict(campaign.parameters or {})
        discovery = dict(params.get("discovery") or {})
        default_cursor = self._default_cursor(campaign)
        cursor = discovery.get("next_cursor") or default_cursor
        page_size = self._positive_int(params.get("page_size"), self.DEFAULT_PAGE_SIZE)
        max_pages = params.get("max_pages")
        pages_per_step = self._positive_int(
            params.get("discovery_pages_per_step"),
            self.DEFAULT_DISCOVERY_PAGES_PER_STEP,
        )
        pages = 0
        total_pages = int(discovery.get("pages") or 0)
        while cursor and pages < pages_per_step:
            if campaign.campaign_type == "incremental" and provider.discover_delta:
                watermark = str(params.get("watermark") or "0")
                page = provider.discover_delta(
                    watermark=watermark, cursor=cursor, page_size=page_size
                )
            else:
                page = provider.discover(cursor=cursor, page_size=page_size)
            SyncWorkItem.objects.bulk_create(
                [
                    SyncWorkItem(
                        campaign=campaign,
                        shard=total_pages + 1,
                        cursor=external_id,
                    )
                    for external_id in page.external_ids
                ],
                ignore_conflicts=True,
            )
            discovery["next_cursor"] = page.next_cursor
            total_pages += 1
            discovery["pages"] = total_pages
            if campaign.campaign_type == "incremental":
                pending = self._accumulate_watermark(
                    params.get("pending_watermark"), page
                )
                if pending is not None:
                    params["pending_watermark"] = pending
            if getattr(page, "total_count", None) is not None:
                campaign.total_items = max(campaign.total_items, page.total_count)
            else:
                campaign.total_items = SyncWorkItem.objects.filter(
                    campaign=campaign
                ).count()
            params["discovery"] = discovery
            campaign.parameters = params
            campaign.save(update_fields=["parameters", "total_items", "updated_at"])
            pages += 1
            cursor = page.next_cursor
            if max_pages is not None and total_pages >= self._positive_int(
                max_pages, total_pages
            ):
                discovery["truncated"] = bool(cursor)
                discovery["next_cursor"] = None
                params.pop("pending_watermark", None)
                params["discovery"] = discovery
                campaign.parameters = params
                campaign.save(update_fields=["parameters", "updated_at"])
                return True
        campaign.total_items = SyncWorkItem.objects.filter(campaign=campaign).count()
        if campaign.campaign_type == "incremental" and not cursor:
            params.setdefault("pending_watermark", str(int(time.time())))
        campaign.parameters = params
        campaign.save(update_fields=["parameters", "total_items", "updated_at"])
        return not cursor

    @staticmethod
    def _accumulate_watermark(
        pending: str | None, page: CatalogPage | Any
    ) -> str | None:
        """Merge a delta page's watermark into the campaign's pending watermark.

        Providers with a true update feed (AniList) report the highest
        ``updatedAt`` observed so far; advancing the watermark to that value
        closes the moving-window gap. Pseudo-watermarks from payload
        reconciliation providers are ignored.
        """
        raw = getattr(page, "watermark", None)
        if not isinstance(raw, str) or not raw.isdigit():
            return pending
        candidate = int(raw)
        if pending is None or int(pending) < candidate:
            return str(candidate)
        return pending

    @staticmethod
    def _default_cursor(campaign: SyncCampaign) -> str:
        """Return the starting discovery cursor for a fresh campaign step."""
        if campaign.provider_slug == "bangumi":
            return "0" if campaign.campaign_type == "incremental" else "1:0"
        return "1"

    def _fetch(self, campaign: SyncCampaign, *, max_items: int | None) -> bool:
        provider = self.provider_for(campaign.provider_slug)
        now = timezone.now()
        SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.RUNNING,
            lease_expires_at__lt=now,
        ).update(
            status=SyncWorkItem.Status.QUEUED,
            lease_owner="",
            lease_expires_at=None,
            error="Worker lease expired before completion.",
        )
        lease_owner = f"campaign:{uuid.uuid4()}"
        lease_expires_at = now + timedelta(seconds=self.WORK_ITEM_LEASE_SECONDS)
        queryset = (
            SyncWorkItem.objects.filter(
                campaign=campaign,
                status=SyncWorkItem.Status.QUEUED,
            )
            .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
            .order_by("shard", "id")
        )
        if max_items is not None:
            queryset = queryset[: max(0, max_items)]
        else:
            queryset = queryset[
                : self._positive_int(
                    (campaign.parameters or {}).get("fetch_batch_size"),
                    self.DEFAULT_FETCH_BATCH_SIZE,
                )
            ]
        for item in queryset:
            claimed = SyncWorkItem.objects.filter(
                pk=item.pk, status=SyncWorkItem.Status.QUEUED
            ).update(
                status=SyncWorkItem.Status.RUNNING,
                attempt=F("attempt") + 1,
                started_at=timezone.now(),
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
            )
            if claimed != 1:
                continue
            item.refresh_from_db()
            try:
                entity = provider.import_item(item.cursor)
            except ProviderAPIError as exc:
                if getattr(exc, "is_not_found", False):
                    self._skip_item(campaign, item, exc)
                    continue
                self._fail_item(campaign, item, exc)
                continue
            except Exception as exc:
                self._fail_item(campaign, item, exc)
                continue
            SyncWorkItem.objects.filter(pk=item.pk).update(
                status=SyncWorkItem.Status.SUCCEEDED,
                result={"entity_id": str(entity.pk), "external_id": item.cursor},
                finished_at=timezone.now(),
                error="",
                last_error_code="",
                next_retry_at=None,
                lease_owner="",
                lease_expires_at=None,
            )
            SyncCampaign.objects.filter(pk=campaign.pk).update(
                processed_items=F("processed_items") + 1,
                synced_items=F("synced_items") + 1,
            )
        campaign.refresh_from_db()
        campaign.failed_items = SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.FAILED
        ).count()
        campaign.save(update_fields=["failed_items", "updated_at"])
        queued = (
            SyncWorkItem.objects.filter(
                campaign=campaign,
                status=SyncWorkItem.Status.QUEUED,
            )
            .filter(
                Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=timezone.now())
            )
            .exists()
        )
        running = SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.RUNNING
        ).exists()
        waiting = SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.QUEUED,
            next_retry_at__gt=timezone.now(),
        ).exists()
        if not queued and not waiting and not running and campaign.failed_items:
            raise RuntimeError(
                f"{campaign.failed_items} provider work items exhausted retries."
            )
        return not queued and not waiting and not running

    def _normalize(self, campaign: SyncCampaign) -> bool:
        if campaign.ai_mode == SyncCampaign.AIMode.OFF:
            return True
        parameters = campaign.parameters or {}
        batch_size = self._positive_int(
            parameters.get("ai_batch_size"), self.DEFAULT_AI_BATCH_SIZE
        )
        configured_limit = parameters.get("ai_sample_size")
        processed_ai = SyncWorkItem.objects.filter(
            campaign=campaign, ai_processed_at__isnull=False
        ).count()
        if configured_limit is not None and int(configured_limit) > 0:
            remaining = int(configured_limit) - processed_ai
            if remaining <= 0:
                return True
            batch_size = min(batch_size, remaining)
        items = SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.SUCCEEDED,
            ai_processed_at__isnull=True,
        ).order_by("shard", "id")[:batch_size]
        for item in items:
            claimed = SyncWorkItem.objects.filter(
                pk=item.pk,
                status=SyncWorkItem.Status.SUCCEEDED,
                ai_processed_at__isnull=True,
            ).update(ai_processed_at=timezone.now())
            if claimed == 1:
                try:
                    self._normalize_item(campaign, item)
                except Exception:
                    SyncWorkItem.objects.filter(pk=item.pk).update(ai_processed_at=None)
                    raise
        return not SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.SUCCEEDED,
            ai_processed_at__isnull=True,
        ).exists()

    def _normalize_item(self, campaign: SyncCampaign, item: SyncWorkItem) -> None:
        result = item.result or {}
        entity_id = result.get("entity_id")
        if not entity_id:
            return
        record = (
            ProviderRecord.objects.filter(
                namespace__provider__slug=campaign.provider_slug,
                namespace__slug=self.provider_for(
                    campaign.provider_slug
                ).namespace_slug,
                external_id=item.cursor,
            )
            .select_related("namespace")
            .first()
        )
        entity = Entity.objects.filter(pk=entity_id).first()
        if record is None or entity is None:
            return
        observation = (
            Observation.objects.filter(provider_record=record)
            .order_by("-observed_at")
            .first()
        )
        representation_exists = ProviderRepresentation.objects.filter(
            provider_record=record, entity=entity, is_active=True
        ).exists()
        if observation is None or not representation_exists:
            return
        payload = record.latest_revision.payload if record.latest_revision else {}
        for source_text in self._taxonomy_values(payload):
            sync_ai_service.normalize_field(
                context=SyncAIContext(
                    campaign=campaign,
                    entity=entity,
                    observation=observation,
                ),
                vocabulary="provider-tag",
                source_text=source_text,
                provider_namespace=record.namespace.slug,
                field_context={"provider": campaign.provider_slug},
            )

    def _enrich(self, campaign: SyncCampaign) -> bool:
        """Run one bounded AI enrichment step for a sampled subset of items."""
        if campaign.ai_mode == SyncCampaign.AIMode.OFF:
            return True
        params = dict(campaign.parameters or {})
        batch_size = self._positive_int(
            params.get("ai_batch_size"), self.DEFAULT_AI_BATCH_SIZE
        )
        sample = params.get("enrich_sample_size")
        if sample is None:
            sample = settings.AI_ENRICH_SAMPLE_SIZE
        sample = int(sample)
        processed = SyncWorkItem.objects.filter(
            campaign=campaign, ai_enriched_at__isnull=False
        ).count()
        if sample > 0:
            remaining = sample - processed
            if remaining <= 0:
                return True
            batch_size = min(batch_size, remaining)
        items = SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.SUCCEEDED,
            ai_enriched_at__isnull=True,
        ).order_by("shard", "id")[:batch_size]
        stats = dict(
            params.get("enrichment")
            or {"claims": 0, "applied": 0, "abstained": 0, "skipped": 0}
        )
        apply = bool(params.get("enrich_apply", settings.AI_ENRICH_APPLY))
        min_confidence = float(
            params.get("enrich_min_confidence", settings.AI_ENRICH_MIN_CONFIDENCE)
        )
        languages = tuple(
            params.get("enrich_languages") or settings.AI_ENRICH_LANGUAGES
        )
        for item in items:
            claimed = SyncWorkItem.objects.filter(
                pk=item.pk,
                status=SyncWorkItem.Status.SUCCEEDED,
                ai_enriched_at__isnull=True,
            ).update(ai_enriched_at=timezone.now())
            if claimed != 1:
                continue
            try:
                result = self._enrich_item(
                    campaign,
                    item,
                    apply=apply,
                    min_confidence=min_confidence,
                    languages=languages,
                )
            except Exception:
                SyncWorkItem.objects.filter(pk=item.pk).update(ai_enriched_at=None)
                raise
            for key in ("claims", "applied", "abstained", "skipped"):
                stats[key] = stats.get(key, 0) + int(result.get(key, 0))
            params["enrichment"] = stats
            campaign.parameters = params
            campaign.save(update_fields=["parameters", "updated_at"])
        if sample > 0:
            processed_now = SyncWorkItem.objects.filter(
                campaign=campaign, ai_enriched_at__isnull=False
            ).count()
            if processed_now >= sample:
                return True
        return not SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.SUCCEEDED,
            ai_enriched_at__isnull=True,
        ).exists()

    def _enrich_item(
        self,
        campaign: SyncCampaign,
        item: SyncWorkItem,
        *,
        apply: bool,
        min_confidence: float,
        languages: tuple[str, ...],
    ) -> dict:
        result = item.result or {}
        entity_id = result.get("entity_id")
        if not entity_id:
            return {"claims": 0, "applied": 0, "abstained": 0, "skipped": 1}
        record = (
            ProviderRecord.objects.filter(
                namespace__provider__slug=campaign.provider_slug,
                namespace__slug=self.provider_for(
                    campaign.provider_slug
                ).namespace_slug,
                external_id=item.cursor,
            )
            .select_related("namespace")
            .first()
        )
        entity = Entity.objects.filter(pk=entity_id).first()
        if record is None or entity is None:
            return {"claims": 0, "applied": 0, "abstained": 0, "skipped": 1}
        observation = (
            Observation.objects.filter(provider_record=record)
            .order_by("-observed_at")
            .first()
        )
        representation_exists = ProviderRepresentation.objects.filter(
            provider_record=record, entity=entity, is_active=True
        ).exists()
        if observation is None or not representation_exists:
            return {"claims": 0, "applied": 0, "abstained": 0, "skipped": 1}
        return sync_ai_service.enrich_entity(
            context=SyncAIContext(
                campaign=campaign,
                entity=entity,
                observation=observation,
            ),
            apply=apply,
            min_confidence=min_confidence,
            target_languages=languages,
        )

    @staticmethod
    def _reconcile_provider_records(campaign: SyncCampaign) -> None:
        """Mark records absent from a completed full catalog as missing."""
        if not SyncCampaignService._can_mark_missing(campaign):
            return
        namespace_slug = PROVIDERS[campaign.provider_slug].namespace_slug
        seen = SyncWorkItem.objects.filter(campaign=campaign).values("cursor")
        ProviderRecord.objects.filter(
            namespace__provider__slug=campaign.provider_slug,
            namespace__slug=namespace_slug,
            status=ProviderRecord.Status.ACTIVE,
        ).exclude(external_id__in=seen).update(status=ProviderRecord.Status.MISSING)

    @staticmethod
    def _can_mark_missing(campaign: SyncCampaign) -> bool:
        """MISSING marking is only safe after a provably complete full catalog."""
        if campaign.campaign_type != "full":
            return False
        discovery = dict((campaign.parameters or {}).get("discovery") or {})
        if discovery.get("next_cursor") or discovery.get("truncated"):
            return False
        provider = PROVIDERS[campaign.provider_slug]
        return bool(
            (campaign.parameters or {}).get(
                "reconcile_missing", provider.discovery_complete
            )
        )

    @staticmethod
    def _taxonomy_values(payload: dict[str, Any]) -> tuple[str, ...]:
        values: list[str] = []
        for value in payload.get("genres") or []:
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        for item in payload.get("tags") or []:
            value = item.get("name") if isinstance(item, dict) else item
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _write_quality_report(campaign: SyncCampaign) -> None:
        succeeded = SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.SUCCEEDED
        ).count()
        failed = SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.FAILED
        ).count()
        params = campaign.parameters or {}
        pending_claims = 0
        if campaign.agent_run_id:
            pending_claims = AIClaim.objects.filter(
                step__run_id=campaign.agent_run_id,
                status=AIClaim.Status.PROPOSED,
            ).count()
        campaign.quality_report = {
            "total_items": campaign.total_items,
            "succeeded_items": succeeded,
            "failed_items": failed,
            "skipped_items": campaign.skipped_items,
            "ai_mode": campaign.ai_mode,
            "evidence_first": True,
            "ai_enrichment": params.get("enrichment")
            or {"claims": 0, "applied": 0, "abstained": 0, "skipped": 0},
            "ai_claims_pending_review": pending_claims,
            "discovery_truncated": bool(
                (campaign.parameters or {}).get("discovery", {}).get("truncated")
            ),
        }
        campaign.save(update_fields=["quality_report", "updated_at"])

    @staticmethod
    def _promote_watermark(campaign: SyncCampaign) -> None:
        """Advance the incremental watermark only after a fully successful campaign."""
        if campaign.campaign_type != "incremental":
            return
        parameters = dict(campaign.parameters or {})
        if dict(parameters.get("discovery") or {}).get("truncated"):
            return
        pending = parameters.pop("pending_watermark", None)
        if pending is None:
            return
        parameters["watermark"] = pending
        campaign.parameters = parameters
        campaign.save(update_fields=["parameters", "updated_at"])

    @staticmethod
    def _mark_agent_run_complete(campaign: SyncCampaign) -> None:
        """Close the campaign's agent run when direct skill calls finish."""
        if campaign.agent_run_id is None:
            return
        AgentRun.objects.filter(
            pk=campaign.agent_run_id,
            status__in={AgentRun.Status.QUEUED, AgentRun.Status.RUNNING},
        ).update(status=AgentRun.Status.SUCCEEDED, finished_at=timezone.now())

    @staticmethod
    def _skip_item(
        campaign: SyncCampaign, item: SyncWorkItem, error: Exception
    ) -> None:
        SyncWorkItem.objects.filter(pk=item.pk).update(
            status=SyncWorkItem.Status.SKIPPED,
            error=f"{type(error).__name__}: {error}"[:4000],
            last_error_code="not_found",
            next_retry_at=None,
            finished_at=timezone.now(),
            lease_owner="",
            lease_expires_at=None,
        )
        SyncCampaign.objects.filter(pk=campaign.pk).update(
            processed_items=F("processed_items") + 1,
            skipped_items=F("skipped_items") + 1,
        )

    @staticmethod
    def _fail_item(
        campaign: SyncCampaign, item: SyncWorkItem, error: Exception
    ) -> None:
        retryable = bool(getattr(error, "retryable", False))
        max_attempts = SyncCampaignService._positive_int(
            (campaign.parameters or {}).get("max_attempts"),
            SyncCampaignService.DEFAULT_MAX_ATTEMPTS,
        )
        message = f"{type(error).__name__}: {error}"[:4000]
        if retryable and item.attempt < max_attempts:
            retry_after = getattr(error, "retry_after", None)
            delay = retry_after or SyncCampaignService.DEFAULT_RETRY_BASE_SECONDS * (
                2 ** max(0, item.attempt - 1)
            )
            SyncWorkItem.objects.filter(pk=item.pk).update(
                status=SyncWorkItem.Status.QUEUED,
                error=message,
                last_error_code=type(error).__name__.lower(),
                next_retry_at=timezone.now() + timedelta(seconds=min(delay, 3600)),
                lease_owner="",
                lease_expires_at=None,
            )
            return
        SyncWorkItem.objects.filter(pk=item.pk).update(
            status=SyncWorkItem.Status.FAILED,
            error=message,
            last_error_code=type(error).__name__.lower(),
            next_retry_at=None,
            finished_at=timezone.now(),
            lease_owner="",
            lease_expires_at=None,
        )
        SyncCampaign.objects.filter(pk=item.campaign_id).update(
            processed_items=F("processed_items") + 1,
            failed_items=F("failed_items") + 1,
        )

    @staticmethod
    def _fail(campaign: SyncCampaign, error: Exception) -> None:
        campaign.refresh_from_db()
        if campaign.status not in {
            SyncCampaign.Status.PAUSED,
            SyncCampaign.Status.COMPLETED,
            SyncCampaign.Status.CANCELLED,
            SyncCampaign.Status.FAILED,
        }:
            SyncCampaignStateMachine(campaign).advance(SyncCampaign.Status.FAILED)
        updates = {"error": f"{type(error).__name__}: {error}"[:4000]}
        if campaign.status != SyncCampaign.Status.PAUSED:
            updates["finished_at"] = timezone.now()
        SyncCampaign.objects.filter(pk=campaign.pk).update(**updates)

    @staticmethod
    def _transition(campaign: SyncCampaign, next_status: str) -> bool:
        return SyncCampaignStateMachine(campaign).advance(next_status)

    @classmethod
    def _transition_required(
        cls, campaign: SyncCampaign, next_status: str
    ) -> SyncCampaign:
        if not cls._transition(campaign, next_status):
            raise RuntimeError(f"Invalid campaign transition to {next_status}.")
        campaign.refresh_from_db()
        return campaign

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default


sync_campaign_service = SyncCampaignService()


def campaign_idempotency_key(
    *, provider_slug: str, campaign_type: str, parameters: dict[str, Any]
) -> str:
    payload = json.dumps(
        {"provider": provider_slug, "type": campaign_type, "parameters": parameters},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"{provider_slug}:{campaign_type}:{hashlib.sha256(payload).hexdigest()[:32]}"
