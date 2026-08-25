"""Deterministic policy for field-normalization claims."""

from decimal import Decimal

from apps.ai.models import AIClaim, AIPolicy


class FieldNormalizationPolicy:
    def __init__(self, policy: AIPolicy) -> None:
        self.policy = policy

    def decide(self, claim: AIClaim) -> tuple[str, str]:
        if claim.proposed_value.get("action") == "abstain":
            return "abstain", "The skill abstained."
        if claim.proposed_value.get("action") == "propose_new":
            return "review", "New taxonomy terms require admin review."
        if self.policy.shadow_mode or not self.policy.is_enabled:
            return "shadow", "Policy is disabled or in shadow mode."
        confidence = claim.calibrated_confidence or claim.model_confidence
        if confidence < Decimal(str(self.policy.minimum_score)):
            return "review", "Confidence is below the configured policy threshold."
        return "auto_apply", "Passed the field-normalization policy gate."


def audit_legacy_term_aliases() -> dict[str, int]:
    from apps.index.models import TermAlias

    aliases = TermAlias.objects.filter(origin=TermAlias.Origin.LEGACY_UNKNOWN)
    return {"total": aliases.count()}
