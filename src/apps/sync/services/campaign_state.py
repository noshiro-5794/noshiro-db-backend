"""Durable state transitions for provider synchronization campaigns."""

import logging
from dataclasses import dataclass

from django.utils import timezone

from apps.sync.models import SyncCampaign

logger = logging.getLogger(__name__)

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("queued", "discovering"): "discovering",
    ("discovering", "fetching"): "fetching",
    ("fetching", "mapping"): "mapping",
    ("mapping", "normalizing"): "normalizing",
    ("normalizing", "reconciling"): "reconciling",
    ("reconciling", "enriching"): "enriching",
    ("enriching", "reviewing"): "reviewing",
    ("reviewing", "completed"): "completed",
}

for _status in (
    "discovering",
    "fetching",
    "mapping",
    "normalizing",
    "reconciling",
    "enriching",
    "reviewing",
):
    _TRANSITIONS[(_status, "failed")] = "failed"
    _TRANSITIONS[(_status, "cancelled")] = "cancelled"


@dataclass
class SyncCampaignStateMachine:
    campaign: SyncCampaign

    def advance(self, next_status: str) -> bool:
        new_status = _TRANSITIONS.get((self.campaign.status, next_status))
        if new_status is None:
            logger.warning(
                "Invalid campaign transition: %s -> %s",
                self.campaign.status,
                next_status,
            )
            return False

        now = timezone.now()
        updates = {"status": new_status, "updated_at": now}
        if self.campaign.status == SyncCampaign.Status.QUEUED:
            updates["started_at"] = now
        if new_status in {
            SyncCampaign.Status.COMPLETED,
            SyncCampaign.Status.FAILED,
            SyncCampaign.Status.CANCELLED,
        }:
            updates["finished_at"] = now

        updated = SyncCampaign.objects.filter(
            pk=self.campaign.pk, status=self.campaign.status
        ).update(**updates)
        if updated != 1:
            logger.warning(
                "Concurrent campaign transition lost for %s", self.campaign.pk
            )
            return False
        self.campaign.status = new_status
        return True
