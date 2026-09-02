"""AI harness boundary for provider synchronization campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.ai.models import AgentRun
from apps.ai.skills.field_normalization import (
    FieldNormalizationInput,
    FieldNormalizationOutput,
    field_normalization_skill,
)
from apps.ai.skills.info_completion import (
    InfoCompletionInput,
    info_completion_skill,
)
from apps.index.models import EntityDescription, EntityName
from apps.sync.exceptions import SyncAIRequiredError
from apps.sync.models import SyncCampaign

if TYPE_CHECKING:
    from apps.ai.models import SourceArtifact
    from apps.index.models import Entity, Observation


@dataclass(frozen=True)
class SyncAIContext:
    """Explicit evidence and campaign policy supplied to AI-assisted mapping."""

    campaign: SyncCampaign
    entity: Entity
    observation: Observation | None = None
    artifact: SourceArtifact | None = None

    @property
    def enabled(self) -> bool:
        return self.campaign.ai_mode != SyncCampaign.AIMode.OFF


class SyncAIService:
    @transaction.atomic
    def ensure_agent_run(self, campaign: SyncCampaign) -> AgentRun:
        """Create the durable run once; never create a second run on retry."""
        campaign = SyncCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.agent_run_id:
            return campaign.agent_run
        run = AgentRun.objects.create(
            kind=AgentRun.Kind.ADMIN_SYNC,
            title=f"{campaign.provider_slug} {campaign.campaign_type}",
            idempotency_key=str(campaign.id),
            idempotency_scope=f"sync:{campaign.id}",
            metadata={
                "campaign_id": str(campaign.id),
                "provider": campaign.provider_slug,
                "ai_mode": campaign.ai_mode,
                "scopes": ["knowledge:read"],
            },
        )
        campaign.agent_run = run
        campaign.save(update_fields=["agent_run", "updated_at"])
        return run

    def normalize_field(
        self,
        *,
        context: SyncAIContext,
        vocabulary: str,
        source_text: str,
        provider_namespace: str = "",
        language: str = "",
        field_context: dict[str, Any] | None = None,
    ) -> FieldNormalizationOutput:
        """Run a field skill only when the campaign supplies source evidence."""
        if not context.enabled:
            return FieldNormalizationOutput(
                action="preserve_raw",
                normalized_key=field_normalization_skill.normalize_key(source_text),
                preferred_term=source_text.strip(),
                language=language,
                confidence=0,
                reason="AI is disabled for this campaign.",
                source="raw",
            )
        run = self.ensure_agent_run(context.campaign)
        result = field_normalization_skill.normalize(
            FieldNormalizationInput(
                vocabulary=vocabulary,
                source_text=source_text,
                provider_namespace=provider_namespace,
                language=language,
                context=field_context or {},
            ),
            target_entity=context.entity,
            agent_run=run,
            source_observation=context.observation,
            source_artifact=context.artifact,
        )
        if (
            context.campaign.ai_mode == SyncCampaign.AIMode.REQUIRED
            and result.source == "raw"
        ):
            raise SyncAIRequiredError(
                "Required AI normalization did not produce a model or alias result."
            )
        return result

    def enrich_entity(
        self,
        *,
        context: SyncAIContext,
        apply: bool = False,
        min_confidence: float = 0.85,
        target_languages: tuple[str, ...] = ("zh", "ja", "en"),
    ) -> dict:
        """Complete missing multilingual fields for one entity (bounded pass).

        The skill persists ``AIClaim``/``ClaimEvidence`` records for every
        proposal; entity names are only auto-applied when ``apply`` is enabled
        and the calibrated confidence clears the threshold. Descriptions are
        always kept as reviewable claims.
        """
        if not context.enabled:
            return {"claims": 0, "applied": 0, "abstained": 0, "strategy": "skipped"}
        entity = context.entity
        names = {
            name.language: name.text
            for name in EntityName.objects.filter(entity=entity)
            if name.language
        }
        description_languages = set(
            EntityDescription.objects.filter(entity=entity).values_list(
                "language", flat=True
            )
        )
        missing_fields = [
            f"title:{lang}" for lang in target_languages if lang not in names
        ] + [
            f"description:{lang}"
            for lang in target_languages
            if lang not in description_languages
        ]
        if not missing_fields:
            return {"claims": 0, "applied": 0, "abstained": 0, "strategy": "skipped"}

        normalized = {}
        if context.observation is not None:
            normalized = context.observation.normalized_data or {}
        original_name = str(normalized.get("title") or "")
        preferred_name = str(normalized.get("title_cn") or "")
        if not preferred_name:
            preferred_name = next(iter(names.values()), "")
        release_date = str(normalized.get("date") or "")
        provider = context.campaign.provider_slug
        external_id = (
            context.observation.provider_record.external_id
            if context.observation is not None
            else ""
        )
        run = self.ensure_agent_run(context.campaign)
        value = InfoCompletionInput(
            entity_id=str(entity.pk),
            provider=provider,
            external_id=external_id,
            preferred_name=preferred_name,
            original_name=original_name,
            source_language="",
            release_date=release_date,
            missing_fields=missing_fields,
            existing_names=names,
        )
        return info_completion_skill.complete(
            value,
            target_entity=entity,
            agent_run=run,
            source_observation=context.observation,
            apply=apply,
            min_confidence=min_confidence,
        )


sync_ai_service = SyncAIService()
