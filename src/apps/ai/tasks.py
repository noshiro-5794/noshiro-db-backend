from celery import shared_task

from apps.ai.services import ai_knowledge_proposal_service, ai_matching_service
from integrations.ai import AIProviderError


@shared_task(
    autoretry_for=(AIProviderError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=210,
)
def evaluate_match_candidate_task(candidate_id: str) -> str:
    proposal = ai_matching_service.evaluate(candidate_id=candidate_id)
    return str(proposal.id)


@shared_task(
    autoretry_for=(AIProviderError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=210,
)
def classify_entity_task(entity_id: str) -> str:
    proposal = ai_knowledge_proposal_service.classify_entity(entity_id=entity_id)
    return str(proposal.id)


@shared_task(
    autoretry_for=(AIProviderError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=210,
)
def extract_observation_evidence_task(observation_id: str, entity_id: str) -> str:
    proposal = ai_knowledge_proposal_service.extract_evidence(
        observation_id=observation_id,
        entity_id=entity_id,
    )
    return str(proposal.id)
