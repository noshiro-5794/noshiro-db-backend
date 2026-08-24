import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.ai.exceptions import InvalidAIProposal

ENTITY_MATCHING_USE_CASE = "entity_matching"
ENTITY_MATCHING_DECISIONS = frozenset({"bind", "reject", "abstain"})


def ai_input_hash(payload: dict[str, Any]) -> str:
    value = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(value).hexdigest()


def validate_matching_output(output: dict[str, Any]) -> dict[str, Any]:
    decision = output.get("decision")
    reason = output.get("reason")
    raw_confidence = output.get("confidence")
    if decision not in ENTITY_MATCHING_DECISIONS:
        raise InvalidAIProposal(
            "AI proposal decision must be bind, reject, or abstain."
        )
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidAIProposal("AI proposal reason must be a non-empty string.")
    if isinstance(raw_confidence, bool):
        raise InvalidAIProposal("AI proposal confidence must be a number from 0 to 1.")
    try:
        confidence = Decimal(str(raw_confidence))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidAIProposal(
            "AI proposal confidence must be a number from 0 to 1."
        ) from exc
    if not math.isfinite(float(confidence)) or not 0 <= confidence <= 1:
        raise InvalidAIProposal("AI proposal confidence must be a number from 0 to 1.")
    return {
        "decision": decision,
        "confidence": str(confidence),
        "reason": reason.strip()[:2000],
    }


def optional_non_negative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def optional_non_negative_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None
