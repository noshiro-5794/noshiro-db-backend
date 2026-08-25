"""Durable orchestration for provider-wide synchronization campaigns.

Provider clients own transport and pagination. Import services own canonical
projection. This module only coordinates the durable campaign/work-item
boundary and the optional evidence-first AI phase.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.index.models import (
    Entity,
    Observation,
    ProviderRecord,
    ProviderRepresentation,
)
from apps.sync.models import SyncCampaign, SyncWorkItem
from apps.sync.providers.anilist import ANILIST_ANIME_NAMESPACE, anilist_client
from apps.sync.providers.contracts import CatalogPage
from apps.sync.providers.exceptions import ProviderAPIError
from apps.sync.providers.vndb import VNDB_VN_NAMESPACE, vndb_client
from apps.sync.services.anilist_service import anilist_import_service
from apps.sync.services.campaign_ai import SyncAIContext, sync_ai_service
from apps.sync.services.campaign_state import SyncCampaignStateMachine
from apps.sync.services.vndb_service import vndb_import_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CampaignProvider:
    slug: str
    namespace_slug: str
    discover: Callable[..., CatalogPage]
    import_item: Callable[[str], Entity]


PROVIDERS: dict[str, CampaignProvider] = {
    "vndb": CampaignProvider(
        slug="vndb",
        namespace_slug=VNDB_VN_NAMESPACE.slug,
        discover=vndb_client.discover_vn_page,
        import_item=lambda external_id: vndb_import_service.import_work(
            vndb_id=external_id, include_related=True
        ),
    ),
    "anilist": CampaignProvider(
        slug="anilist",
        namespace_slug=ANILIST_ANIME_NAMESPACE.slug,
        discover=anilist_client.discover_anime_page,
        import_item=lambda external_id: anilist_import_service.import_media(
            int(external_id)
        ),
    ),
}


class CampaignProviderNotFound(ValueError):
    """Raised when a campaign references an unregistered provider."""


class SyncCampaignService:
    """Create, resume, and execute one durable provider synchronization."""

    DEFAULT_PAGE_SIZE = 100
    DEFAULT_AI_SAMPLE_SIZE = 16
    WORK_ITEM_LEASE_SECONDS = 3600

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
        """Run all unfinished phases; every phase is safe to re-enter."""
        campaign = SyncCampaign.objects.get(pk=campaign.pk)
        if campaign.status == SyncCampaign.Status.FAILED:
            campaign = self.resume(campaign)
        if campaign.status == SyncCampaign.Status.QUEUED and not self._transition(
            campaign, SyncCampaign.Status.DISCOVERING
        ):
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
                self._normalize(campaign)
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.RECONCILING
                )
            if campaign.status == SyncCampaign.Status.RECONCILING:
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.ENRICHING
                )
            if campaign.status == SyncCampaign.Status.ENRICHING:
                campaign = self._transition_required(
                    campaign, SyncCampaign.Status.REVIEWING
                )
            if campaign.status == SyncCampaign.Status.REVIEWING:
                self._write_quality_report(campaign)
                self._transition_required(campaign, SyncCampaign.Status.COMPLETED)
        except Exception as exc:
            logger.exception(
                "Sync campaign failed", extra={"campaign_id": str(campaign.pk)}
            )
            self._fail(campaign, exc)
        return SyncCampaign.objects.get(pk=campaign.pk)

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
        cursor = discovery.get("next_cursor") or "1"
        page_size = self._positive_int(params.get("page_size"), self.DEFAULT_PAGE_SIZE)
        max_pages = params.get("max_pages")
        pages = 0
        while cursor:
            page = provider.discover(cursor=cursor, page_size=page_size)
            page_number = max(1, int(cursor))
            SyncWorkItem.objects.bulk_create(
                [
                    SyncWorkItem(
                        campaign=campaign,
                        shard=page_number,
                        cursor=external_id,
                    )
                    for external_id in page.external_ids
                ],
                ignore_conflicts=True,
            )
            discovery["next_cursor"] = page.next_cursor
            discovery["pages"] = pages + 1
            if page.total_count is not None:
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
            if max_pages is not None and pages >= self._positive_int(max_pages, pages):
                return not cursor
        campaign.total_items = SyncWorkItem.objects.filter(campaign=campaign).count()
        campaign.parameters = params
        campaign.save(update_fields=["parameters", "total_items", "updated_at"])
        return True

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
        queryset = SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.QUEUED
        ).order_by("shard", "id")
        if max_items is not None:
            queryset = queryset[: max(0, max_items)]
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
            try:
                entity = provider.import_item(item.cursor)
            except ProviderAPIError as exc:
                self._fail_item(item, exc)
                continue
            except Exception as exc:
                self._fail_item(item, exc)
                continue
            SyncWorkItem.objects.filter(pk=item.pk).update(
                status=SyncWorkItem.Status.SUCCEEDED,
                result={"entity_id": str(entity.pk), "external_id": item.cursor},
                finished_at=timezone.now(),
                error="",
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
        if campaign.failed_items:
            raise RuntimeError(f"{campaign.failed_items} provider work items failed.")
        return not SyncWorkItem.objects.filter(
            campaign=campaign, status=SyncWorkItem.Status.QUEUED
        ).exists()

    def _normalize(self, campaign: SyncCampaign) -> None:
        if campaign.ai_mode == SyncCampaign.AIMode.OFF:
            return
        sample_size = self._positive_int(
            (campaign.parameters or {}).get("ai_sample_size"),
            self.DEFAULT_AI_SAMPLE_SIZE,
        )
        items = SyncWorkItem.objects.filter(
            campaign=campaign,
            status=SyncWorkItem.Status.SUCCEEDED,
            ai_processed_at__isnull=True,
        ).order_by("shard", "id")[:sample_size]
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
        campaign.quality_report = {
            "total_items": campaign.total_items,
            "succeeded_items": succeeded,
            "failed_items": failed,
            "ai_mode": campaign.ai_mode,
            "evidence_first": True,
        }
        campaign.save(update_fields=["quality_report", "updated_at"])

    @staticmethod
    def _fail_item(item: SyncWorkItem, error: Exception) -> None:
        SyncWorkItem.objects.filter(pk=item.pk).update(
            status=SyncWorkItem.Status.FAILED,
            error=f"{type(error).__name__}: {error}"[:4000],
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
            SyncCampaign.Status.COMPLETED,
            SyncCampaign.Status.CANCELLED,
            SyncCampaign.Status.FAILED,
        }:
            SyncCampaignStateMachine(campaign).advance(SyncCampaign.Status.FAILED)
        SyncCampaign.objects.filter(pk=campaign.pk).update(
            error=f"{type(error).__name__}: {error}"[:4000],
            finished_at=timezone.now(),
        )

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
